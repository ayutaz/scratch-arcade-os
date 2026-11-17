/* SPDX-License-Identifier: Apache-2.0 */
#include "voice_service.h"
#include "guest_vm.h"
#include "pet_kws.h"
#include "replies.h"
_Static_assert(sizeof(LabVoice)<=8192,"bounded voice scratch");
static void wipe(void *pointer,size_t count) {volatile uint8_t *p=pointer;while(count--)*p++=0;}
/* The PDM input may have a constant offset. Center the private, consumed
 * recording before the frozen frontend; no new buffer or PCM export. */
static int16_t *sample(LabAudio *audio,uint32_t at) {
    return audio->buffer ? audio->buffer+at:audio->banks[at/LAB_AUDIO_BANK_FRAMES]+at%LAB_AUDIO_BANK_FRAMES;
}
static void center_recording(LabAudio *audio) {
    int64_t sum=0;
    for(uint32_t i=0;i<PET_AUDIO_SAMPLES;i++)sum+=*sample(audio,i);
    int32_t mean=(int32_t)(sum/PET_AUDIO_SAMPLES);
    for(uint32_t i=0;i<PET_AUDIO_SAMPLES;i++) {
        int16_t *at=sample(audio,i);int32_t value=(int32_t)*at-mean;
        *at=(int16_t)(value>32767 ? 32767:value<-32768 ? -32768:value);
    }
}
int lab_voice_call(void *context,LabAudio *audio,uint32_t owner,uint32_t op,uint32_t value,uint32_t now) {
    LabVoice *voice=context;
    if(!voice || !audio || !audio->ready || !owner || audio->owner!=owner)return -1;
    if(op==LAB_VM_AUDIO_CLASSIFY) {
        if(!(audio->permissions&LAB_AUDIO_CAN_RECORD) || audio->phase!=LAB_AUDIO_IDLE || audio->driver_owned ||
           audio->result!=1 || audio->kind!=LAB_AUDIO_RECORDING || audio->recorded!=PET_AUDIO_SAMPLES)return -1;
        int result=-1;
        if(pet_feature_scratch_size()<=sizeof(voice->workspace)) {
            center_recording(audio);
            result=audio->buffer ? pet_features(audio->buffer,32000,voice->features,260,voice->workspace,sizeof(voice->workspace)) :
                pet_features_banked((const int16_t *const *)audio->banks,32000,voice->features,260,voice->workspace,sizeof(voice->workspace));
        }
        if(!lab_audio_forget_recording(audio,owner))result=-1;
        if(result==1)result=pet_predict(voice->features,260,voice->logits,7);
        wipe(voice,sizeof(*voice));return result;
    }
    if(op==LAB_VM_AUDIO_REPLY) {
        if(!(audio->permissions&LAB_AUDIO_CAN_PLAY) || value>=5)return -1;
        if(audio->driver_owned || audio->phase!=LAB_AUDIO_IDLE)return 0;
        const PetReplyClip *clip=&pet_replies[value];
        if(clip->frames*2>audio->capacity)return -1;
        return lab_audio_play_pcm8(audio,owner,clip->samples,clip->frames,now);
    }
    return -1;
}
