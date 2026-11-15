#include "audio_binding.h"
#include <stddef.h>
bool lab_audio_binding_open(LabAudioBinding *s,LabAudio *audio,uint32_t owner,uint32_t caps,uint32_t now) {
    if(!s || s->audio || !audio || !owner || caps>LAB_VM_CAP_ALL || !(caps&6))return false;
    uint32_t permissions=((caps&2) ? LAB_AUDIO_CAN_PLAY : 0)|((caps&4) ? LAB_AUDIO_CAN_RECORD : 0);
    if(!lab_audio_claim(audio,owner,permissions))return false;
    *s=(LabAudioBinding){audio,owner,permissions,now};return true;
}
bool lab_audio_binding_close(LabAudioBinding *s) {
    if(!s)return false;
    if(!s->audio)return true;
    if(!lab_audio_release(s->audio,s->owner))return false;
    *s=(LabAudioBinding){0};return true;
}
int lab_audio_binding_poll(LabAudioBinding *s,uint32_t now) {
    if(!s || !s->audio || s->audio->owner!=s->owner)return -1;
    s->now=now;return lab_audio_poll(s->audio,now);
}
int lab_audio_binding_call(LabAudioBinding *s,uint32_t op,uint32_t a,uint32_t b) {
    if(!s || !s->audio || s->audio->owner!=s->owner)return -1;
    LabAudio *audio=s->audio;
    if(op==LAB_VM_AUDIO_SET_GAIN) {
        if(!(s->permissions&LAB_AUDIO_CAN_PLAY) || a>8)return -1;
        return lab_audio_set_gain(audio,s->owner,a);
    }
    if(op==LAB_VM_AUDIO_TONE || op==LAB_VM_AUDIO_PLAY) {
        if(!(s->permissions&LAB_AUDIO_CAN_PLAY))return -1;
        return op==LAB_VM_AUDIO_TONE ? lab_audio_tone(audio,s->owner,a,b,s->now) :
            lab_audio_play_recording(audio,s->owner,s->now);
    }
    if(op==LAB_VM_AUDIO_RECORD) {
        if(!(s->permissions&LAB_AUDIO_CAN_RECORD))return -1;
        return lab_audio_record(audio,s->owner,a,s->now);
    }
    if(op==LAB_VM_AUDIO_STATE)return audio->phase==LAB_AUDIO_IDLE && audio->result<0 ? -1 : (int)audio->phase;
    if(op==LAB_VM_AUDIO_POSITION)return (int)audio->position;
    if(op==LAB_VM_AUDIO_LEVEL) {
        if(!(s->permissions&LAB_AUDIO_CAN_RECORD))return -1;
        return lab_audio_peak(audio);
    }
    if(op==LAB_VM_AUDIO_STOP) {
        if(!lab_audio_release(audio,s->owner))return 0;
        return lab_audio_claim(audio,s->owner,s->permissions) ? 1 : -1;
    }
    return -1;
}
static int command(void *s,uint32_t op,uint32_t a,uint32_t b) {return lab_audio_binding_call(s,op,a,b);}
LabVmAudio lab_audio_binding_services(LabAudioBinding *s) {
    return s && s->audio ? (LabVmAudio){s,command} : (LabVmAudio){0};
}

bool lab_audio_manager_init(LabAudioManager *s,LabAudio *audio) {
    if(!s || s->audio || !audio || !audio->ready)return false;
    *s=(LabAudioManager){.audio=audio};return true;
}
static bool home_open(void *context,uint32_t capabilities,LabVmAudio *out) {
    LabAudioManager *s=context;
    if(!out || s->binding.audio)return false;
    if(++s->next_owner==0)s->next_owner=1;
    if(!lab_audio_binding_open(&s->binding,s->audio,s->next_owner,capabilities,s->now))return false;
    *out=lab_audio_binding_services(&s->binding);return true;
}
static void home_poll(void *context,uint32_t now) {
    LabAudioManager *s=context;s->now=now;
    if(s->binding.audio)lab_audio_binding_poll(&s->binding,now);
}
static bool home_close(void *context) {return lab_audio_binding_close(&((LabAudioManager *)context)->binding);}
LabHomeAudio lab_audio_manager_services(LabAudioManager *s) {
    return s && s->audio ? (LabHomeAudio){s,home_open,home_poll,home_close} : (LabHomeAudio){0};
}
