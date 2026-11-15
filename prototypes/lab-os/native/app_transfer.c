#include "app_transfer.h"
#include "network_wire.h"
#include "control_wire.h"
#include <stdlib.h>
#include <string.h>
enum {HELLO=1,OPEN,BEGIN,DATA,COMMIT,ABORT,LIST,REMOVE,ROLLBACK,CLOSE,PING,COLLECT,TELEMETRY,NETWORK,CONTROL};
enum {OK,BAD,BUSY,SEQUENCE,INTEGRITY,STORAGE,NO_SESSION,UNUSED_TIMEOUT,REJECTED,STALE};
static const uint8_t magic[8]="LABXFR1";
static void wipe(void *ptr,uint32_t n) {volatile uint8_t *p=ptr;while(n--)*p++=0;}
static void clear_rx(LabTransfer *s) {wipe(s->rx,sizeof(s->rx));s->rx_size=0;}
static void shift_rx(LabTransfer *s) {
    --s->rx_size;memmove(s->rx,s->rx+1,s->rx_size);s->rx[s->rx_size]=0;
}
static uint32_t get32(const uint8_t *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put32(uint8_t *p,uint32_t v) {for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
static uint32_t crc_part(uint32_t crc,const uint8_t *p,uint32_t n) {
    for(uint32_t i=0;i<n;i++) {crc^=p[i];for(unsigned b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));}
    return crc;
}
static uint32_t crc(const uint8_t *p,uint32_t n) {return ~crc_part(crc_part(UINT32_MAX,p,24),p+28,n);}
static uint32_t response(uint8_t *out,uint8_t op,uint32_t session,uint32_t request,uint8_t status,const uint8_t *payload,uint32_t n) {
    memset(out,0,28);memcpy(out,magic,8);out[8]=op;out[9]=128;out[10]=status;
    put32(out+12,session);put32(out+16,request);put32(out+20,n);
    if(n)memcpy(out+28,payload,n);
    put32(out+24,crc(out,n));return 28+n;
}
static void discard(LabTransfer *s) {
    free(s->upload);s->upload=NULL;s->received=s->total=0;
    if(s->collecting && s->cancel)s->cancel(s->maintenance_context);
    s->collecting=false;
}
static void next_epoch(LabTransfer *s){if(!++s->epoch)++s->epoch;}
static void expire(LabTransfer *s,uint32_t now) {
    if(s->rx_size && now-s->rx_started>=2000)clear_rx(s);
    if(s->session && (now-s->activity>=5000 || ((s->upload || s->collecting) && now-s->started>=30000))) {
        discard(s);s->session=0;s->last_request=0;s->previous_size=s->response_size=0;s->beacon_due=true;
    }
}
bool lab_transfer_init(LabTransfer *s,LabStore *store,LabHome *home,LabTransferSend send,void *context,uint32_t nonce,uint32_t now) {
    if(!s || !store || !store->mounted || !home || !send || !nonce)return false;
    memset(s,0,sizeof(*s));s->store=store;s->home=home;s->send=send;s->context=context;
    s->nonce=nonce;s->activity=s->beacon_at=now;s->ready=s->beacon_due=true;return true;
}
bool lab_transfer_set_collector(LabTransfer *s,LabTransferCollect collect,LabTransferCancel cancel,void *context) {
    if(!s || !s->ready || s->session || s->upload || s->collecting || s->rx_size || !collect || !cancel)return false;
    s->collect=collect;s->cancel=cancel;s->maintenance_context=context;return true;
}
bool lab_transfer_set_telemetry(LabTransfer *s,LabTransferTelemetry read,void *context) {
    if(!s || !s->ready || s->session || s->upload || s->collecting || s->rx_size || !read)return false;
    s->telemetry=read;s->telemetry_context=context;return true;
}
bool lab_transfer_set_network(LabTransfer *s,LabTransferNetwork network,void *context) {
    if(!s || !s->ready || s->session || s->upload || s->collecting || s->rx_size || !network)return false;
    s->network=network;s->network_context=context;return true;
}
bool lab_transfer_set_control(LabTransfer *s,LabTransferControl control,void *context) {
    if(!s || !s->ready || s->session || s->upload || s->collecting || s->rx_size || !control)return false;
    s->control=control;s->control_context=context;return true;
}
bool lab_transfer_poll(LabTransfer *s,uint32_t now) {
    if(!s || !s->ready)return false;
    expire(s,now);
    if((s->upload || s->collecting) && s->home->mode!=LAB_HOME)discard(s);
    if(!s->session && (s->beacon_due || now-s->beacon_at>=1000)) {
        uint8_t payload[32],out[60];memcpy(payload,"LABOS_TRANSFER_1",16);
        put32(payload+16,s->nonce);put32(payload+20,LAB_TRANSFER_PACKAGE);put32(payload+24,512);put32(payload+28,2);
        uint32_t n=response(out,HELLO,0,0,OK,payload,sizeof(payload));
        s->beacon_at=now;s->beacon_due=false;return s->send(s->context,out,n);
    }
    return true;
}
static bool app_id(const uint8_t *p,uint32_t n,char id[33]) {
    if(!n || n>32 || p[0]<'a' || p[0]>'z')return false;
    for(uint32_t i=1;i<n;i++)if(!((p[i]>='a' && p[i]<='z') || (p[i]>='0' && p[i]<='9') || p[i]=='-'))return false;
    memset(id,0,33);memcpy(id,p,n);return true;
}
static uint8_t dispatch(LabTransfer *s,uint8_t op,const uint8_t *p,uint32_t n,uint8_t out[179],uint32_t *length,uint32_t now) {
    *length=0;
    if(op==ABORT || op==CLOSE || op==PING) {
        if(n)return BAD;
        if(op!=PING) {discard(s);next_epoch(s);}
        if(op==CLOSE) {s->session=0;s->beacon_due=true;}
        return OK;
    }
    if(op==TELEMETRY) {
        if(n!=8 || get32(p)>1 || (!get32(p) && get32(p+4)))return BAD;
        if(!s->telemetry)return REJECTED;
        uint32_t bytes=0;int result=s->telemetry(s->telemetry_context,get32(p),get32(p+4),out,&bytes);
        if(!result)return STALE;
        if(result!=1 || bytes>80)return STORAGE;
        *length=bytes;return OK;
    }
    if(op==NETWORK) {
        if(!lab_network_wire_valid(p,n))return BAD;
        if(!lab_network_wire_readonly(get32(p)) && (s->home->mode!=LAB_HOME || s->upload || s->collecting))return BUSY;
        if(!s->network)return REJECTED;
        uint8_t status[8]={0};
        int result=s->network(s->network_context,p,n,now,status);
        if(result==1) {memcpy(out,status,8);*length=8;}
        wipe(status,sizeof(status));
        return result==1 ? OK : result==0 ? REJECTED : STORAGE;
    }
    if(op==CONTROL) {
        if(!lab_control_wire_valid(p,n))return BAD;
        if(get32(p)==LAB_CONTROL_PULSE && (s->upload || s->collecting))return BUSY;
        if(!s->control)return REJECTED;
        uint8_t snapshot[80]={0};int result=s->control(s->control_context,p,n,now,snapshot);
        if(result==1) {memcpy(out,snapshot,80);*length=80;}
        return result==1 ? OK : result==0 ? REJECTED : STORAGE;
    }
    if(s->home->mode!=LAB_HOME) {discard(s);return BUSY;}
    if(op==COLLECT) {
        if(n)return BAD;
        if(s->upload)return BUSY;
        if(!s->collect || !s->cancel)return REJECTED;
        if(!s->store->healthy)return STORAGE;
        if(!s->collecting)s->started=now;
        s->collecting=true;
        uint32_t stats[4]={0};int result=s->collect(s->maintenance_context,stats);
        if(result<0 || result>1) {discard(s);return STORAGE;}
        for(unsigned i=0;i<4;i++)put32(out+4*i,stats[i]);
        put32(out+16,(uint32_t)result);*length=20;
        if(result==1) {s->cancel(s->maintenance_context);s->collecting=false;}
        return OK;
    }
    if(s->collecting)return BUSY;
    if(op==LIST) {
        if(n!=4)return BAD;
        if(s->upload)return BUSY;
        if(!lab_home_refresh(s->home))return STORAGE;
        uint32_t at=get32(p);put32(out,s->home->count);*length=4;
        if(at>=s->home->count)return at==s->home->count ? OK : BAD;
        const LabAppInfo *info=s->home->apps+at;
        put32(out+4,at);memcpy(out+8,info->id,33);memcpy(out+41,info->title,81);memcpy(out+122,info->version,25);
        for(uint32_t i=0;i<s->store->count;i++)if(!strcmp(info->id,s->store->records[i].id)) {
            memcpy(out+147,s->store->records[i].current,32);*length=179;return OK;
        }
        *length=0;return STORAGE;
    }
    if(op!=BEGIN && op!=DATA && op!=COMMIT && op!=REMOVE && op!=ROLLBACK)return BAD;
    if(!s->store->healthy)return STORAGE;
    if(op==BEGIN) {
        if(n!=36 || get32(p)<264 || get32(p)>LAB_TRANSFER_PACKAGE)return BAD;
        if(s->upload)return BUSY;
        s->upload=malloc(get32(p));if(!s->upload)return STORAGE;
        s->total=get32(p);s->received=0;s->started=now;memcpy(s->digest,p+4,32);
        put32(out,0);*length=4;return OK;
    }
    if(op==DATA) {
        if(n<5 || n>516)return BAD;
        if(!s->upload || get32(p)!=s->received || n-4>s->total-s->received)return SEQUENCE;
        memcpy(s->upload+s->received,p+4,n-4);s->received+=n-4;put32(out,s->received);*length=4;return OK;
    }
    if(op==COMMIT) {
        if(n)return BAD;
        if(!s->upload || s->received!=s->total)return SEQUENCE;
        uint8_t hash[32];
        bool valid=s->store->io.hash(s->store->io.context,s->upload,s->total,hash) && !memcmp(hash,s->digest,32);
        bool installed=valid && lab_store_install(s->store,s->upload,s->total);
        discard(s);
        if(!valid)return INTEGRITY;
        if(!installed)return s->store->healthy ? REJECTED : STORAGE;
        if(!lab_home_refresh(s->home))return STORAGE;
        put32(out,s->store->sequence);*length=4;return OK;
    }
    if(s->upload)return BUSY;
    char id[33];if(!app_id(p,n,id))return BAD;
    bool changed=op==REMOVE ? lab_store_uninstall(s->store,id) : lab_store_rollback(s->store,id);
    if(!changed)return s->store->healthy ? REJECTED : STORAGE;
    if(!lab_home_refresh(s->home))return STORAGE;
    put32(out,s->store->sequence);*length=4;return OK;
}
static bool handle(LabTransfer *s,uint32_t now) {
    const uint8_t *p=s->rx;uint8_t op=p[8];uint32_t session=get32(p+12),request=get32(p+16),n=get32(p+20);
    if(p[9]==128)return true; /* Do not reply to replies or echoed beacons. */
    uint8_t out[207],payload[179];uint32_t length=0;uint8_t status=BAD;bool cache=false;
    bool private_request=op==NETWORK;
    uint8_t digest[32]={0};
    if(private_request && !s->store->io.hash(s->store->io.context,p,s->rx_size,digest)) {
        uint32_t bytes=response(out,op,session,request,STORAGE,NULL,0);
        return s->send(s->context,out,bytes);
    }
    if(session && request && s->previous_size==s->rx_size && session==s->last_session && request==s->last_request &&
       s->previous_private==private_request &&
       !memcmp(s->previous,private_request ? digest:p,private_request ? 32:s->rx_size)) {
        if(s->session==session)s->activity=now;
        return s->send(s->context,s->response,s->response_size);
    }
    if(!session || !request || p[10])status=BAD;
    else if(op==OPEN && !s->session) {
        if(request!=1 || n!=4 || get32(p+28)!=s->nonce)status=BAD;
        else {s->session=session;s->activity=now;next_epoch(s);status=OK;cache=true;}
    } else if(session!=s->session)status=s->session && op==OPEN ? BUSY : NO_SESSION;
    else if(s->last_request==UINT32_MAX || request!=s->last_request+1)status=SEQUENCE;
    else {
        cache=true;s->activity=now;
        status=dispatch(s,op,p+28,n,payload,&length,now);
    }
    uint32_t bytes=response(out,op,session,request,status,payload,length);
    if(cache) {
        wipe(s->previous,sizeof(s->previous));
        memcpy(s->previous,private_request ? digest:p,private_request ? 32:s->rx_size);
        s->previous_size=s->rx_size;s->previous_private=private_request;
        memcpy(s->response,out,bytes);s->response_size=bytes;s->last_request=request;s->last_session=session;
    }
    return s->send(s->context,out,bytes);
}
bool lab_transfer_feed(LabTransfer *s,const uint8_t *p,uint32_t n,uint32_t now) {
    if(!s || !s->ready || (!p && n) || n>1024)return false;
    expire(s,now);bool sent=true;
    for(uint32_t at=0;at<n;at++) {
        if(!s->rx_size)s->rx_started=now;
        s->rx[s->rx_size++]=p[at];
        while(s->rx_size>=8) {
            if(memcmp(s->rx,magic,8)) {shift_rx(s);continue;}
            if(s->rx_size<28)break;
            uint32_t payload=get32(s->rx+20);
            if((s->rx[9]!=0 && s->rx[9]!=128) || s->rx[11] || payload>LAB_TRANSFER_PAYLOAD) {
                shift_rx(s);continue;
            }
            if(s->rx_size<28+payload)break;
            if(crc(s->rx,payload)==get32(s->rx+24) && !handle(s,now))sent=false;
            clear_rx(s);break;
        }
    }
    return sent;
}
bool lab_transfer_busy(const LabTransfer *s) {return s && s->ready && (s->upload || s->collecting);}
void lab_transfer_close(LabTransfer *s) {if(s) {discard(s);wipe(s,sizeof(*s));}}
