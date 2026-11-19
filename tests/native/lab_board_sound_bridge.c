#include "board_sound.h"
#include <stdlib.h>
void test_audio_reset(void);void test_audio_fault(int);void test_audio_memory_reset(void);void test_audio_memory_fault(int,int);
typedef struct {LabBoardSound sound;LabHomeAudio hooks;LabVmAudio vm;unsigned voice_allocs,voice_frees,voice_fault,voice_bad;void *voice_instance;} Rig;
void *test_sound_new(void){Rig *r=calloc(1,sizeof(*r));test_audio_reset();test_audio_memory_reset();return r;}
int test_sound_init(Rig *r,int profile){int ok=lab_board_sound_init(&r->sound,profile);r->hooks=lab_board_sound_services(&r->sound);return ok;}
int test_sound_open(Rig *r,unsigned caps){r->vm=(LabVmAudio){0};return r->hooks.open && r->hooks.open(r->hooks.context,caps,&r->vm);}
int test_sound_command(Rig *r,unsigned op,unsigned a,unsigned b){return r->vm.call ? r->vm.call(r->vm.context,op,a,b) : -1;}
void test_sound_poll(Rig *r,unsigned now){if(r->hooks.poll)r->hooks.poll(r->hooks.context,now);}
int test_sound_close(Rig *r){return lab_board_sound_close(&r->sound);}
unsigned test_sound_metric(Rig *r,unsigned i){return i==0 ? r->sound.frames : i==1 ? r->sound.audio.owner : i==2 ? r->sound.driver.channel!=NULL : r->sound.audio.recorded;}
void test_sound_free(Rig *r){test_audio_fault(0);test_audio_memory_fault(0,0);r->voice_fault=0;lab_board_sound_close(&r->sound);free(r);}

static int fake_voice(void *context,LabAudio *audio,uint32_t owner,uint32_t op,uint32_t value,uint32_t now) {
 (void)op;(void)value;(void)now;return context==audio->voice_context && audio->owner==owner ? 6:-1;
}
int test_sound_voice(Rig *r){return lab_board_sound_set_voice(&r->sound,r,fake_voice);}

static void *voice_create(void *context){Rig *r=context;r->voice_allocs++;if(r->voice_fault==1)return NULL;r->voice_instance=calloc(1,32);return r->voice_instance;}
static bool voice_destroy(void *context,void *instance){Rig *r=context;if(r->sound.driver.channel || r->sound.audio.owner || instance!=r->voice_instance){r->voice_bad++;return false;}if(r->voice_fault==2)return false;free(instance);r->voice_instance=NULL;r->voice_frees++;return true;}
int test_sound_factory(Rig *r,unsigned kind){LabBoardVoice factory={r,voice_create,voice_destroy,fake_voice};if(kind==1)factory.acquire=NULL;if(kind==2)factory.release=NULL;if(kind==3)factory.call=NULL;return lab_board_sound_set_voice_factory(&r->sound,kind==4 ? NULL:&factory);}
unsigned test_sound_factory_metric(Rig *r,unsigned i){return i==0 ? r->voice_allocs:i==1 ? r->voice_frees:i==2 ? r->voice_instance!=NULL:r->voice_bad;}
void test_sound_factory_fault(Rig *r,unsigned kind){r->voice_fault=kind;}
