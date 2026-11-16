#include "board_sound.h"
#include "audio_memory.h"
#include <stddef.h>
bool lab_board_sound_init(LabBoardSound *s,int profile) {
    if(!s || profile!=LAB_AUDIO_PROFILE_STOCK_0111 || s->pcm.frames || s->driver.channel || s->manager.binding.audio ||
       (s->configured && s->profile!=profile))return false;
    s->profile=profile;s->configured=true;return true;
}
bool lab_board_sound_set_voice(LabBoardSound *s,void *context,int (*call)(void *,LabAudio *,uint32_t,uint32_t,uint32_t,uint32_t)) {
    if(!s || !s->configured || !context || !call || s->pcm.frames || s->driver.channel || s->manager.binding.audio)return false;
    s->voice_context=context;s->voice_call=call;return true;
}
bool lab_board_sound_close(LabBoardSound *s) {
    if(!s)return false;
    if(!lab_audio_binding_close(&s->manager.binding))return false;
    if(!lab_board_audio_close(&s->driver))return false;
    if(s->pcm.frames) {
        if(!lab_audio_pcm_banks_free(&s->pcm))return false;
        s->frames=0;
    }
    s->audio=(LabAudio){0};s->manager=(LabAudioManager){0};return true;
}
static bool acquire(void *context,uint32_t caps,LabVmAudio *out) {
    LabBoardSound *s=context;
    if(!s || !s->configured || !out || s->pcm.frames || s->driver.channel ||
       s->manager.binding.audio || caps>LAB_VM_CAP_ALL || !(caps&6))return false;
    uint32_t frames=(caps&LAB_VM_CAP_MICROPHONE) ? 32000 : 16000;
    if(!lab_audio_pcm_banks_alloc(&s->pcm,frames))return false;
    s->frames=frames;
    LabAudioIo io=lab_board_audio_services(&s->driver);
    if(!lab_audio_init_banked(&s->audio,&io,&s->pcm) || !lab_audio_manager_init(&s->manager,&s->audio))return false;
    s->audio.voice_context=s->voice_context;s->audio.voice_call=s->voice_call;
    s->manager.now=s->now;s->manager.next_owner=s->epoch;
    LabHomeAudio hooks=lab_audio_manager_services(&s->manager);
    bool ok=hooks.open(hooks.context,caps,out);s->epoch=s->manager.next_owner;
    return ok; /* Home owns even a partial failure and invokes close. */
}
static void poll(void *context,uint32_t now) {
    LabBoardSound *s=context;s->now=now;
    if(s->manager.audio) {
        LabHomeAudio hooks=lab_audio_manager_services(&s->manager);hooks.poll(hooks.context,now);
    }
}
static bool release(void *context) {return lab_board_sound_close(context);}
LabHomeAudio lab_board_sound_services(LabBoardSound *s) {
    return s && s->configured ? (LabHomeAudio){s,acquire,poll,release} : (LabHomeAudio){0};
}
