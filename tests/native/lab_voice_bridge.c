#include "voice_service.h"
#include "audio_binding.h"
#include <stdlib.h>
#include <string.h>
typedef struct {LabAudio audio;LabAudioBinding binding;LabVoice voice;int16_t banks[8][4096];unsigned read_at,written,opens;int closing,over_limit;} Rig;
static int open_io(void *p,int mode){Rig *r=p;(void)mode;r->opens++;return 1;}
static int read_io(void *p,int16_t *out,uint32_t n){Rig *r=p;memset(out,0,n*2);r->read_at+=n;return (int)n;}
static int write_io(void *p,const int16_t *data,uint32_t n){Rig *r=p;for(unsigned i=0;i<n;i++)if(data[i]>3277 || data[i]<-3277)r->over_limit=1;r->written+=n;return (int)n;}
static int drained(void *p){(void)p;return 1;}
static int close_io(void *p){return !((Rig*)p)->closing;}
void *voice_new(unsigned caps){Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;
 LabAudioPcm pcm={.frames=(caps&4) ? 32000:16000};for(unsigned i=0;i<(pcm.frames+4095)/4096;i++)pcm.banks[i]=r->banks[i];
 LabAudioIo io={r,open_io,read_io,write_io,drained,close_io};
 if(!lab_audio_init_banked(&r->audio,&io,&pcm) || !lab_audio_binding_open(&r->binding,&r->audio,1,caps,0)){free(r);return NULL;}
 r->audio.voice_context=&r->voice;r->audio.voice_call=lab_voice_call;return r;}
void voice_free(void *p){Rig *r=p;r->closing=0;lab_audio_binding_close(&r->binding);free(r);}
int voice_call(void *p,unsigned op,unsigned value){Rig *r=p;return lab_audio_binding_call(&r->binding,op,value,0);}
int voice_poll(void *p,unsigned now){return lab_audio_binding_poll(&((Rig*)p)->binding,now);}
unsigned voice_value(void *p,unsigned field){Rig *r=p;switch(field){case 0:return r->opens;case 1:return r->audio.recorded;case 2:return r->written;case 3:return r->over_limit;case 4:return r->audio.driver_owned;case 5:return r->audio.owner;default:return 0;}}
int voice_clean(void *p){Rig *r=p;for(unsigned i=0;i<8;i++)for(unsigned j=0;j<4096;j++)if(r->banks[i][j])return 0;for(unsigned i=0;i<sizeof(r->voice);i++)if(((uint8_t*)&r->voice)[i])return 0;return 1;}
int voice_close(void *p,int fail){Rig *r=p;r->closing=fail;return lab_audio_binding_close(&r->binding);}
