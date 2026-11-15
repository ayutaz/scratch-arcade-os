#include "app_store.h"
#include "network_binding.h"
#include "audio_binding.h"
#include "board_udp.h"
#include "run_loop.h"
#include "ui.h"
#include <stdlib.h>
#include <string.h>
static _Alignas(8) uint8_t pool[196608];
typedef struct {
 LabStore store;LabHome home;LabRunLoop loop;
 LabDatagram udp;LabNetworkManager net;LabBoardUdp socket;
 LabAudio audio;LabAudioManager sound;int16_t pcm[16000];
 uint8_t incoming[64],sent[64];uint32_t incoming_size,sent_size,now,held,opens,closes,sends,live_closes,audio_closes;
 bool fail_open,fail_close,fail_audio_close,real;
} Rig;
int test_runtime_start(void){return lab_runtime_init(pool,sizeof(pool));}
void test_runtime_stop(void){lab_runtime_destroy();}
int test_verify(void *ctx,uint8_t *p,uint32_t n,uint32_t pages,uint32_t fuel,uint32_t caps){
 (void)ctx;LabVm vm={0};bool ok=lab_vm_open_with_audio(&vm,p,n,pages,fuel,caps,NULL);if(ok)ok=lab_vm_frame(&vm,0,0)==0;lab_vm_close(&vm,2);return ok;
}
static bool net_open(void *ctx,const LabUdpRoute *route){Rig *r=ctx;r->opens++;if(r->fail_open)return false;return !r->real || lab_board_udp_open(&r->socket,route);}
static bool net_close(void *ctx){Rig *r=ctx;r->closes++;if(r->home.vm.instance)r->live_closes++;if(r->fail_close)return false;r->incoming_size=0;return !r->real || lab_board_udp_close(&r->socket);}
static int net_send(void *ctx,const uint8_t *p,uint32_t n){Rig *r=ctx;r->sends++;memcpy(r->sent,p,n);r->sent_size=n;return r->real?lab_board_udp_send(&r->socket,p,n):(int)n;}
static int net_receive(void *ctx,uint8_t *p,uint32_t cap){Rig *r=ctx;if(r->real)return lab_board_udp_receive(&r->socket,p,cap);if(cap<r->incoming_size)return -2;uint32_t n=r->incoming_size;memcpy(p,r->incoming,n);r->incoming_size=0;return (int)n;}
static int audio_open(void *c,int mode){(void)c;(void)mode;return 1;}
static int audio_read(void *c,int16_t *p,uint32_t n){(void)c;memset(p,0,n*sizeof(*p));return (int)n;}
static int audio_write(void *c,const int16_t *p,uint32_t n){(void)c;(void)p;return (int)n;}
static int audio_drained(void *c){(void)c;return 1;}
static int audio_close(void *c){Rig *r=c;r->audio_closes++;return !r->fail_audio_close;}
static bool input(void *c,uint32_t now,LabInputSample *p){(void)now;*p=(LabInputSample){.held=((Rig *)c)->held};return true;}
static bool paint(void *c,const LabHome *home){(void)c;uint16_t row[320];return lab_ui_row(home,0,row)&&lab_ui_row(home,182,row);}
void *test_new(const LabStorage *io){Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;
 LabDatagramIo udp={r,net_open,net_close,net_send,net_receive};LabAudioIo audio={r,audio_open,audio_read,audio_write,audio_drained,audio_close};
 if(!lab_store_init(&r->store,io)||!lab_datagram_init(&r->udp,&udp)||!lab_network_manager_init(&r->net,&r->udp)||
    !lab_audio_init(&r->audio,&audio,r->pcm,16000)||!lab_audio_manager_init(&r->sound,&r->audio)){free(r);return NULL;}
 LabUdpRoute route={.peer={127,0,0,1},.peer_port=50000};
 if(!lab_network_manager_configure(&r->net,&route)){free(r);return NULL;}lab_network_manager_available(&r->net,true);return r;
}
void test_free(Rig *r){r->fail_open=r->fail_close=r->fail_audio_close=false;if(!lab_loop_close(&r->loop)||!lab_home_close(&r->home)||!lab_store_close(&r->store))abort();free(r);}
int test_install(Rig *r,const uint8_t *p,uint32_t n){return lab_store_install(&r->store,p,n);}
int test_start(Rig *r){LabCatalog catalog=lab_store_catalog(&r->store);if(!lab_home_init(&r->home,&catalog))return 0;
 LabHomeNetwork net=lab_network_manager_services(&r->net);LabHomeAudio audio=lab_audio_manager_services(&r->sound);
 if(!lab_home_set_network(&r->home,&net)||!lab_home_set_audio(&r->home,&audio))return 0;
 LabLoopIo io={.context=r,.input=input,.paint=paint};return lab_loop_init(&r->loop,&r->home,&io,r->now);
}
int test_step(Rig *r,uint32_t held,uint32_t dt){r->held=held;r->now+=dt;return lab_loop_step(&r->loop,r->now);}
int test_mode(Rig *r){return r->home.mode;}
int test_debug(Rig *r,const char *name){return lab_vm_debug(&r->home.vm,name);}
int test_loop_close(Rig *r){return lab_loop_close(&r->loop);}
unsigned test_metric(Rig *r,unsigned which){switch(which){case 0:return r->opens;case 1:return r->closes;
 case 2:return r->store.lease!=NULL;case 3:return r->home.vm.instance!=NULL;case 4:return r->udp.owner;
 case 5:return r->sends;case 6:return r->home.count;case 7:return r->loop.ready;case 8:return r->live_closes;
 case 9:return r->home.notice;case 10:return r->home.network_owned;case 11:return r->audio_closes;case 13:return r->udp.rx_size;default:return r->audio.owner;}}
void test_fault(Rig *r,int close,int open,int audio){r->fail_close=close;r->fail_open=open;r->fail_audio_close=audio;}
void test_available(Rig *r,int ready){lab_network_manager_available(&r->net,ready);}
int test_clean(Rig *r){for(unsigned i=0;i<64;i++)if(r->udp.tx[i]||r->udp.rx[i])return 0;return 1;}
void test_inject(Rig *r,const uint8_t *p,uint32_t n){if(n<=64){memcpy(r->incoming,p,n);r->incoming_size=n;}}
int test_configure(Rig *r,int partial){LabHomeNetwork net=lab_network_manager_services(&r->net);if(partial)net.close=NULL;return lab_home_set_network(&r->home,&net);}
int test_route(Rig *r,unsigned port,int real){LabUdpRoute route={.peer={127,0,0,1},.peer_port=(uint16_t)port};if(!lab_network_manager_configure(&r->net,&route))return 0;r->real=real;return 1;}
unsigned test_port(Rig *r){return lab_board_udp_port(&r->socket);}
unsigned test_notice_network(void){return LAB_NOTICE_NETWORK;}
