#include "app_store.h"
#include "audio_binding.h"
#include "run_loop.h"
#include "ui.h"
#include <stdlib.h>
#include <string.h>
static _Alignas(8) uint8_t pool[196608];
typedef struct {
 LabStore store;LabHome home;LabRunLoop loop;LabAudio audio;LabAudioManager manager;
 int16_t pcm[32000];uint32_t now,held,opens,closes,paints;bool fail_close,fail_paint,fail_open;
} Rig;
int test_runtime_start(void){return lab_runtime_init(pool,sizeof(pool));}
void test_runtime_stop(void){lab_runtime_destroy();}
int test_verify(void *c,uint8_t *p,uint32_t n,uint32_t pages,uint32_t fuel,uint32_t caps){
 (void)c;LabVm vm={0};bool ok=lab_vm_open_with_audio(&vm,p,n,pages,fuel,caps,NULL);
 if(ok)ok=lab_vm_frame(&vm,0,0)==0;lab_vm_close(&vm,2);return ok;
}
static int audio_open(void *c,int mode){Rig *r=c;(void)mode;r->opens++;return !r->fail_open;}
static int audio_read(void *c,int16_t *p,uint32_t n){(void)c;for(uint32_t i=0;i<n;i++)p[i]=3000;return (int)n;}
static int audio_write(void *c,const int16_t *p,uint32_t n){(void)c;(void)p;return (int)n;}
static int audio_drained(void *c){(void)c;return 1;}
static int audio_close(void *c){Rig *r=c;r->closes++;return !r->fail_close;}
static bool input(void *c,uint32_t now,LabInputSample *p){(void)now;Rig *r=c;*p=(LabInputSample){.held=r->held};return true;}
static bool paint(void *c,const LabHome *home){Rig *r=c;r->paints++;uint16_t row[320];
 return !r->fail_paint && lab_ui_row(home,0,row) && lab_ui_row(home,82,row);
}
void *test_new(const LabStorage *io){Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;
 LabAudioIo sound={r,audio_open,audio_read,audio_write,audio_drained,audio_close};
 if(!lab_store_init(&r->store,io)||!lab_audio_init(&r->audio,&sound,r->pcm,32000)||!lab_audio_manager_init(&r->manager,&r->audio)){free(r);return NULL;}
 return r;
}
void test_free(Rig *r){if(!r)return;r->fail_close=false;
 if(!lab_loop_close(&r->loop)||!lab_home_close(&r->home)||!lab_store_close(&r->store))abort();free(r);
}
int test_install(Rig *r,const uint8_t *p,uint32_t n){return lab_store_install(&r->store,p,n);}
int test_start(Rig *r){LabCatalog catalog=lab_store_catalog(&r->store);
 if(!lab_home_init(&r->home,&catalog))return 0;
 LabHomeAudio hooks=lab_audio_manager_services(&r->manager);
 if(!lab_home_set_audio(&r->home,&hooks))return 0;
 LabLoopIo io={.context=r,.input=input,.paint=paint};return lab_loop_init(&r->loop,&r->home,&io,r->now);
}
int test_step(Rig *r,unsigned held,unsigned dt){r->held=held;r->now+=dt;return lab_loop_step(&r->loop,r->now);}
int test_mode(Rig *r){return r->home.mode;}int test_value(Rig *r){return lab_vm_debug(&r->home.vm,"debug_value");}
unsigned test_metric(Rig *r,unsigned which){switch(which){case 0:return r->opens;case 1:return r->closes;
 case 2:return r->store.lease!=NULL;case 3:return r->home.vm.instance!=NULL;case 4:return r->audio.owner;
 case 5:return r->audio.permissions;case 6:return r->home.count;case 7:return r->loop.ready;case 8:return r->paints;
 case 9:return r->home.notice;default:return r->home.audio_owned;}}
void test_fault(Rig *r,int close,int paint,int open){r->fail_close=close;r->fail_paint=paint;r->fail_open=open;}
int test_loop_close(Rig *r){return lab_loop_close(&r->loop);}
int test_clean(Rig *r){for(unsigned i=0;i<32000;i++)if(r->pcm[i])return 0;return 1;}
int test_configure(Rig *r,int partial){LabHomeAudio io=lab_audio_manager_services(&r->manager);if(partial)io.close=NULL;return lab_home_set_audio(&r->home,&io);}

int test_audio_block(Rig *r,int block){return block ? lab_audio_claim(&r->audio,999,1) : lab_audio_release(&r->audio,999);}

int test_notice_audio(void){return LAB_NOTICE_AUDIO;}
