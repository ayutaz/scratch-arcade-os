#include "guest_vm.h"
#include "audio_binding.h"
#include <stdlib.h>
#include <string.h>
typedef struct {LabVm vm;LabAudio audio;LabAudioBinding binding;int16_t pcm[32000];unsigned opens,closes,gain_calls;int fail_close,gain_override,voice_enabled,voice_result;unsigned voice_calls;} Probe;
static _Alignas(8) unsigned char pool[196608];
int test_runtime_start(void){return lab_runtime_init(pool,sizeof(pool));}
void test_runtime_stop(void){lab_runtime_destroy();}
static int open_audio(void *ctx,int mode){Probe *p=ctx;(void)mode;p->opens++;return 1;}
static int read_audio(void *ctx,int16_t *pcm,uint32_t n){(void)ctx;for(uint32_t i=0;i<n;i++)pcm[i]=-32768;return (int)n;}
static int write_audio(void *ctx,const int16_t *pcm,uint32_t n){(void)ctx;(void)pcm;return (int)n;}
static int drained_audio(void *ctx){(void)ctx;return 1;}
static int close_audio(void *ctx){Probe *p=ctx;p->closes++;return !p->fail_close;}
void *test_new(void){Probe *p=calloc(1,sizeof(*p));if(!p)return NULL;
 LabAudioIo io={p,open_audio,read_audio,write_audio,drained_audio,close_audio};
 if(!lab_audio_init(&p->audio,&io,p->pcm,32000)||!lab_audio_binding_open(&p->binding,&p->audio,101,6,0)){free(p);return NULL;}
 return p;
}
void test_free(void *ctx){Probe *p=ctx;if(!p)return;lab_vm_close(&p->vm,1);p->fail_close=0;lab_audio_binding_close(&p->binding);free(p);}
static int command(void *ctx,uint32_t op,uint32_t a,uint32_t b){Probe *p=ctx;
 if((op==9 || op==10) && p->voice_enabled){p->voice_calls++;return p->voice_result;}
 if(op==8){p->gain_calls++;if(p->gain_override)return p->gain_override;}
 return lab_audio_binding_call(&p->binding,op,a,b);
}
int test_open(void *ctx,uint8_t *bytes,uint32_t n,uint32_t caps,int backend){Probe *p=ctx;
 LabVmAudio audio={p,command};
 return lab_vm_open_with_audio(&p->vm,bytes,n,2,50000,caps,backend ? &audio : NULL);
}
int test_frame(void *ctx){return lab_vm_frame(&((Probe *)ctx)->vm,0,16);}
int test_value(void *ctx){return lab_vm_debug(&((Probe *)ctx)->vm,"debug_value");}
int test_command(void *ctx,unsigned op,unsigned a,unsigned b){return command(ctx,op,a,b);}
int test_poll(void *ctx,unsigned now){return lab_audio_binding_poll(&((Probe *)ctx)->binding,now);}
unsigned test_opens(void *ctx){return ((Probe *)ctx)->opens;}
void test_fail_close(void *ctx,int fail){((Probe *)ctx)->fail_close=fail;}
int test_release(void *ctx){return lab_audio_binding_close(&((Probe *)ctx)->binding);}
int test_claim_other(void *ctx){return lab_audio_claim(&((Probe *)ctx)->audio,202,3);}
int test_clean(void *ctx){Probe *p=ctx;for(unsigned i=0;i<32000;i++)if(p->pcm[i])return 0;return 1;}
void test_vm_close(void *ctx){lab_vm_close(&((Probe *)ctx)->vm,1);}
void test_position_override(void *ctx,unsigned value){((Probe *)ctx)->audio.position=value;}
int test_rebind(void *ctx){Probe *p=ctx;return lab_audio_binding_close(&p->binding) && lab_audio_binding_open(&p->binding,&p->audio,202,6,0);}
unsigned test_gain_calls(void *ctx){return ((Probe *)ctx)->gain_calls;}
unsigned test_gain_value(void *ctx){return ((Probe *)ctx)->audio.replay_gain;}
void test_gain_override(void *ctx,int value){((Probe *)ctx)->gain_override=value;}

void test_voice_result(void *ctx,int value){Probe *p=ctx;p->voice_enabled=1;p->voice_result=value;}
unsigned test_voice_calls(void *ctx){return ((Probe*)ctx)->voice_calls;}
