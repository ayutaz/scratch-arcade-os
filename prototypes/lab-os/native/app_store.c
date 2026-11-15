/* Immutable application packages and checksummed alternating catalog slots.
 * No GPIO, filesystem, transport or crypto implementation lives here. */
#include "app_store.h"
#include <stdlib.h>
#include <string.h>

static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p,uint32_t n) {for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
static bool zero(const uint8_t *p,uint32_t n) {for(uint32_t i=0;i<n;i++)if(p[i])return false;return true;}
static bool canonical_string(const uint8_t *p,uint32_t n) {
    uint32_t at=0;while(at<n && p[at])at++;
    return at>0 && at<n && zero(p+at,n-at);
}
static bool valid_id(const char *p) {
    if(!p || p[0]<'a' || p[0]>'z')return false;
    for(unsigned i=1;i<=32;i++) {
        if(!p[i])return true;
        if(i==32 || !((p[i]>='a' && p[i]<='z') || (p[i]>='0' && p[i]<='9') || p[i]=='-'))return false;
    }
    return false;
}
static bool valid_title(const uint8_t *p) {
    if(!canonical_string(p,81))return false;
    unsigned at=0,count=0;
    while(p[at]) {
        unsigned char c=p[at++];if(++count>20)return false;
        if(c<128) {if(c<32 || c==127)return false;continue;}
        unsigned n=c>=0xc2 && c<=0xdf ? 1 : c>=0xe0 && c<=0xef ? 2 : c>=0xf0 && c<=0xf4 ? 3 : 0;
        if(!n || at+n>80 || (c==0xe0 && p[at]<0xa0) || (c==0xed && p[at]>=0xa0) ||
           (c==0xf0 && p[at]<0x90) || (c==0xf4 && p[at]>=0x90))return false;
        for(unsigned i=0;i<n;i++)if((p[at++] & 0xc0)!=0x80)return false;
    }
    return true;
}
static bool valid_version(const uint8_t *p) {
    if(!canonical_string(p,25))return false;
    unsigned at=0;
    for(unsigned part=0;part<3;part++) {
        unsigned first=at;while(p[at]>='0' && p[at]<='9')at++;
        if(first==at || at-first>4 || (part<2 && p[at++]!='.'))return false;
    }
    return !p[at];
}
static bool digest(LabStore *s,const uint8_t *p,uint32_t n,uint8_t out[32]) {
    return s->io.hash(s->io.context,p,n,out);
}
static bool package(LabStore *s,const uint8_t *p,uint32_t n,LabAppInfo *info) {
    uint8_t hash[32];
    if(!p || n<LAB_PACKAGE_HEADER+8 || n>LAB_PACKAGE_HEADER+LAB_PACKAGE_MAX_WASM ||
       memcmp(p,"LABAPP1\0",8) || u32(p+8)!=1 || u32(p+12)!=2 ||
       u32(p+16)<1 || u32(p+16)>2 || u32(p+20)<100 || u32(p+20)>1000000 ||
       u32(p+24)>LAB_VM_CAP_ALL || u32(p+28)!=n-LAB_PACKAGE_HEADER ||
       !canonical_string(p+64,33) || !valid_id((const char *)p+64) ||
       !valid_title(p+97) || !valid_version(p+178) || !zero(p+203,53) ||
       memcmp(p+LAB_PACKAGE_HEADER,"\0asm\1\0\0\0",8) ||
       !digest(s,p+LAB_PACKAGE_HEADER,n-LAB_PACKAGE_HEADER,hash) || memcmp(hash,p+32,32))return false;
    if(info) {
        memset(info,0,sizeof(*info));
        memcpy(info->id,p+64,33);memcpy(info->title,p+97,81);memcpy(info->version,p+178,25);info->enabled=true;
    }
    return true;
}
static void blob_key(const uint8_t hash[32],char key[69]) {
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++) {key[2*i]=hex[hash[i]>>4];key[2*i+1]=hex[hash[i]&15];}
    memcpy(key+64,".lab",5);
}
static int read_object(LabStore *s,const char *key,uint32_t max,uint8_t **out,uint32_t *n) {
    *out=NULL;*n=0;
    int result=s->io.read(s->io.context,key,NULL,0,n);
    if(result!=1)return result;
    if(!*n || *n>max)return 2; /* Found but malformed. */
    uint32_t expected=*n;uint8_t *p=malloc(expected);
    if(!p)return -1;
    result=s->io.read(s->io.context,key,p,expected,n);
    if(result!=1 || *n!=expected) {free(p);return -1;}
    *out=p;return 1;
}
static uint8_t *load(LabStore *s,const LabRecord *row,bool previous,LabAppInfo *info,uint32_t *n) {
    const uint8_t *hash=previous ? row->previous : row->current;
    char key[69];blob_key(hash,key);uint8_t *p=NULL,actual[32];
    if(read_object(s,key,LAB_PACKAGE_HEADER+LAB_PACKAGE_MAX_WASM,&p,n)!=1)return NULL;
    if(!package(s,p,*n,info) || strcmp((const char *)p+64,row->id) ||
       !digest(s,p,*n,actual) || memcmp(actual,hash,32)) {free(p);return NULL;}
    return p;
}
static int index_read(LabStore *s,int slot,LabRecord *rows,uint32_t *count,uint32_t *seq) {
    const char *key=slot ? "index-1" : "index-0";
    uint8_t *p=NULL,hash[32];uint32_t n=0;
    int result=read_object(s,key,LAB_INDEX_BYTES,&p,&n);
    if(result!=1)return result;
    bool ok=n==LAB_INDEX_BYTES && !memcmp(p,"LABIDX1\0",8) && u32(p+8)>0 &&
            u32(p+12)<=LAB_MAX_APPS && zero(p+16,16) &&
            digest(s,p,LAB_INDEX_BYTES-32,hash) && !memcmp(hash,p+LAB_INDEX_BYTES-32,32);
    if(ok) {
        *count=u32(p+12);*seq=u32(p+8);
        for(uint32_t i=0;i<LAB_MAX_APPS;i++) {
            const uint8_t *r=p+32+i*104;
            if(i>=*count) {if(!zero(r,104))ok=false;continue;}
            if(!canonical_string(r,33) || !valid_id((const char *)r) || !zero(r+33,7) ||
               zero(r+40,32) || !memcmp(r+40,r+72,32)) {ok=false;break;}
            memcpy(rows[i].id,r,33);memcpy(rows[i].current,r+40,32);memcpy(rows[i].previous,r+72,32);
            if(i && strcmp(rows[i-1].id,rows[i].id)>=0) {ok=false;break;}
        }
    }
    free(p);return ok ? 1 : 2;
}
bool lab_store_init(LabStore *s,const LabStorage *io) {
    if(!s || s->maintenance || !io || !io->read || !io->put || !io->hash || !io->verify)return false;
    memset(s,0,sizeof(*s));s->io=*io;s->slot=-1;
    uint8_t owner[sizeof(LAB_STORE_OWNER)];uint32_t size=0;
    if(io->read(io->context,"owner",owner,sizeof(owner),&size)!=1 ||
       size!=sizeof(LAB_STORE_OWNER)-1 || memcmp(owner,LAB_STORE_OWNER,size))return false;
    LabRecord *rows=calloc(2*LAB_MAX_APPS,sizeof(*rows));
    if(!rows)return false;
    uint32_t count[2]={0},seq[2]={0};
    int result[2];
    result[0]=index_read(s,0,rows,&count[0],&seq[0]);
    result[1]=index_read(s,1,rows+LAB_MAX_APPS,&count[1],&seq[1]);
    bool ok=result[0]>=0 && result[1]>=0;
    if(ok && result[0]==0 && result[1]==0) {s->healthy=s->mounted=true;free(rows);return true;}
    if(result[0]!=1 && result[1]!=1)ok=false;
    if(ok && result[0]==1 && result[1]==1 && seq[0]==seq[1] &&
       (count[0]!=count[1] || memcmp(rows,rows+LAB_MAX_APPS,LAB_MAX_APPS*sizeof(*rows))))ok=false;
    if(ok) {
        s->slot=result[0]==1 && (result[1]!=1 || seq[0]>=seq[1]) ? 0 : 1;
        s->count=count[s->slot];s->sequence=seq[s->slot];
        memcpy(s->records,rows+s->slot*LAB_MAX_APPS,sizeof(s->records));
        s->recovered=result[0]==2 || result[1]==2;s->healthy=s->mounted=true;
    }
    free(rows);return ok;
}
bool lab_store_close(LabStore *s) {
    if(!s || s->lease || s->maintenance)return false;
    memset(s,0,sizeof(*s));return true;
}
static bool writable(LabStore *s) {return s && s->healthy && !s->lease && !s->maintenance && s->sequence!=UINT32_MAX;}
static bool commit(LabStore *s,const LabRecord *rows,uint32_t count) {
    uint8_t *p=calloc(1,LAB_INDEX_BYTES);if(!p)return false;
    memcpy(p,"LABIDX1\0",8);put32(p+8,s->sequence+1);put32(p+12,count);
    for(uint32_t i=0;i<count;i++) {
        uint8_t *r=p+32+104*i;
        memcpy(r,rows[i].id,33);memcpy(r+40,rows[i].current,32);memcpy(r+72,rows[i].previous,32);
    }
    bool ok=digest(s,p,LAB_INDEX_BYTES-32,p+LAB_INDEX_BYTES-32);
    int slot=s->slot==0 ? 1 : 0;const char *key=slot ? "index-1" : "index-0";
    if(ok) {
        ok=s->io.put(s->io.context,key,p,LAB_INDEX_BYTES);
        uint8_t *check=NULL;uint32_t n=0;
        if(ok)ok=read_object(s,key,LAB_INDEX_BYTES,&check,&n)==1 && n==LAB_INDEX_BYTES && !memcmp(check,p,n);
        free(check);
        if(!ok)s->healthy=false; /* Persistence outcome is uncertain. */
    }
    if(ok) {
        memset(s->records,0,sizeof(s->records));memcpy(s->records,rows,count*sizeof(*rows));
        s->count=count;s->sequence++;s->slot=slot;
    }
    free(p);return ok;
}
bool lab_store_gc_checkpoint(LabStore *s) {
    if(!s || !s->mounted || !s->healthy || !s->maintenance || s->lease || s->sequence==UINT32_MAX)return false;
    LabRecord *rows=calloc(2*LAB_MAX_APPS,sizeof(*rows));if(!rows)return false;
    uint32_t counts[2]={0},sequences[2]={0};int results[2];
    for(int i=0;i<2;i++)results[i]=index_read(s,i,rows+i*LAB_MAX_APPS,&counts[i],&sequences[i]);
    bool empty=s->slot==-1;
    bool ok=results[0]>=0 && results[1]>=0;
    if(empty)ok=ok && !s->count && !s->sequence && !results[0] && !results[1];
    else if(s->slot<0 || s->slot>1)ok=false;
    else {
        int at=s->slot,other=1-at;
        ok=ok && results[at]==1 && sequences[at]==s->sequence && counts[at]==s->count &&
           !memcmp(rows+at*LAB_MAX_APPS,s->records,sizeof(s->records));
        if(results[other]==1 && sequences[other]>=s->sequence)
            ok=ok && sequences[other]==s->sequence && counts[other]==s->count &&
               !memcmp(rows+other*LAB_MAX_APPS,s->records,sizeof(s->records));
    }
    for(uint32_t i=0;ok && i<s->count;i++) {
        uint32_t n=0;uint8_t *p=load(s,s->records+i,false,NULL,&n);
        ok=p!=NULL;free(p);
        if(ok && !zero(s->records[i].previous,32)) {
            p=load(s,s->records+i,true,NULL,&n);ok=p!=NULL;free(p);
        }
    }
    /* commit replaces s->records: never pass that same live buffer as input. */
    const LabRecord *snapshot=rows;
    if(ok && !empty)snapshot=rows+s->slot*LAB_MAX_APPS;
    if(ok)ok=commit(s,snapshot,s->count);
    if(ok && empty)ok=commit(s,snapshot,s->count);
    free(rows);
    return ok;
}
static int find(LabStore *s,const char *id) {
    for(uint32_t i=0;i<s->count;i++)if(!strcmp(s->records[i].id,id))return (int)i;
    return -1;
}
bool lab_store_install(LabStore *s,const uint8_t *p,uint32_t n) {
    LabAppInfo info;uint8_t hash[32];
    if(!writable(s) || !package(s,p,n,&info) || !digest(s,p,n,hash))return false;
    int at=find(s,info.id);
    if(at<0 && s->count==LAB_MAX_APPS)return false;
    uint8_t *copy=malloc(n-LAB_PACKAGE_HEADER);if(!copy)return false;
    memcpy(copy,p+LAB_PACKAGE_HEADER,n-LAB_PACKAGE_HEADER);
    bool ok=s->io.verify(s->io.context,copy,n-LAB_PACKAGE_HEADER,u32(p+16),u32(p+20),u32(p+24));
    free(copy);if(!ok)return false;
    char key[69];blob_key(hash,key);uint8_t *existing=NULL;uint32_t size=0;
    int result=read_object(s,key,LAB_PACKAGE_HEADER+LAB_PACKAGE_MAX_WASM,&existing,&size);
    if(result==1)ok=size==n && !memcmp(existing,p,n);
    else if(result==0) {
        ok=s->io.put(s->io.context,key,p,n);
        if(ok)ok=read_object(s,key,LAB_PACKAGE_HEADER+LAB_PACKAGE_MAX_WASM,&existing,&size)==1 && size==n && !memcmp(existing,p,n);
        if(!ok)s->healthy=false;
    } else ok=false;
    free(existing);if(!ok)return false;
    if(at>=0 && !memcmp(s->records[at].current,hash,32))return true;
    LabRecord *next=calloc(LAB_MAX_APPS,sizeof(*next));if(!next)return false;
    memcpy(next,s->records,sizeof(s->records));uint32_t count=s->count;
    if(at<0) {
        at=(int)count++;
        while(at>0 && strcmp(next[at-1].id,info.id)>0) {next[at]=next[at-1];at--;}
        memset(next+at,0,sizeof(*next));memcpy(next[at].id,info.id,33);
    } else memcpy(next[at].previous,next[at].current,32);
    memcpy(next[at].current,hash,32);
    ok=commit(s,next,count);free(next);return ok;
}
static bool change(LabStore *s,const char *id,int action) {
    if(!writable(s) || !valid_id(id))return false;
    int at=find(s,id);if(at<0)return false;
    bool has_previous=!zero(s->records[at].previous,32);
    if(action==0 && !has_previous)return false;
    if(action!=1 && has_previous) {
        uint32_t n=0;uint8_t *p=load(s,s->records+at,true,NULL,&n);
        if(!p)return false;
        free(p);
    }
    LabRecord *next=calloc(LAB_MAX_APPS,sizeof(*next));if(!next)return false;
    memcpy(next,s->records,sizeof(s->records));uint32_t count=s->count;
    if(action==1 || (action==2 && !has_previous)) {
        for(uint32_t i=(uint32_t)at+1;i<count;i++)next[i-1]=next[i];
        count--;
    } else {
        uint8_t hash[32];memcpy(hash,next[at].current,32);
        memcpy(next[at].current,next[at].previous,32);
        if(action==0)memcpy(next[at].previous,hash,32);
        else memset(next[at].previous,0,32);
    }
    bool ok=commit(s,next,count);free(next);return ok;
}
bool lab_store_rollback(LabStore *s,const char *id) {return change(s,id,0);}
bool lab_store_uninstall(LabStore *s,const char *id) {return change(s,id,1);}
bool lab_store_quarantine(LabStore *s,const char *id) {return change(s,id,2);}
static uint32_t catalog_count(void *context) {LabStore *s=context;return s->mounted ? s->count : 0;}
static bool catalog_info(void *context,uint32_t at,LabAppInfo *out) {
    LabStore *s=context;if(!s->mounted || !out || at>=s->count)return false;
    uint32_t n=0;uint8_t *p=load(s,s->records+at,false,out,&n);
    if(!p)return false;
    free(p);return true;
}
static bool catalog_open(void *context,const char *id,LabImage *out) {
    LabStore *s=context;
    if(!s->mounted || s->lease || s->maintenance || !out || out->bytes || out->lease || !valid_id(id))return false;
    int at=find(s,id);if(at<0)return false;
    uint32_t n=0;uint8_t *p=load(s,s->records+at,false,NULL,&n);
    if(!p)return false;
    s->lease=p;out->lease=p;out->bytes=p+LAB_PACKAGE_HEADER;out->size=n-LAB_PACKAGE_HEADER;
    out->pages=u32(p+16);out->budget=u32(p+20);out->capabilities=u32(p+24);return true;
}
static void catalog_release(void *context,LabImage *image) {
    LabStore *s=context;
    if(!image || !s->lease || image->lease!=s->lease)return;
    free(s->lease);s->lease=NULL;memset(image,0,sizeof(*image));
}
static bool catalog_quarantine(void *context,const char *id) {return lab_store_quarantine(context,id);}
LabCatalog lab_store_catalog(LabStore *s) {
    return (LabCatalog){s,catalog_count,catalog_info,catalog_open,catalog_release,catalog_quarantine};
}
