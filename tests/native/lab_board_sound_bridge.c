#include "board_sound.h"
#include <stdlib.h>
void test_audio_reset(void);void test_audio_fault(int);void test_audio_memory_reset(void);void test_audio_memory_fault(int,int);
typedef struct {LabBoardSound sound;LabHomeAudio hooks;LabVmAudio vm;} Rig;
void *test_sound_new(void){Rig *r=calloc(1,sizeof(*r));test_audio_reset();test_audio_memory_reset();return r;}
int test_sound_init(Rig *r,int profile){int ok=lab_board_sound_init(&r->sound,profile);r->hooks=lab_board_sound_services(&r->sound);return ok;}
int test_sound_open(Rig *r,unsigned caps){r->vm=(LabVmAudio){0};return r->hooks.open && r->hooks.open(r->hooks.context,caps,&r->vm);}
int test_sound_command(Rig *r,unsigned op,unsigned a,unsigned b){return r->vm.call ? r->vm.call(r->vm.context,op,a,b) : -1;}
void test_sound_poll(Rig *r,unsigned now){if(r->hooks.poll)r->hooks.poll(r->hooks.context,now);}
int test_sound_close(Rig *r){return lab_board_sound_close(&r->sound);}
unsigned test_sound_metric(Rig *r,unsigned i){return i==0 ? r->sound.frames : i==1 ? r->sound.audio.owner : i==2 ? r->sound.driver.channel!=NULL : r->sound.audio.recorded;}
void test_sound_free(Rig *r){test_audio_fault(0);test_audio_memory_fault(0,0);lab_board_sound_close(&r->sound);free(r);}
