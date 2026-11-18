/* SPDX-License-Identifier: Apache-2.0 */
#include "voice_service.h"
#include "guest_vm.h"
#include "channel_features.h"
#include "replies.h"
#include "pet_model.h"
#include <string.h>
_Static_assert(sizeof(LabVoice)<=8192,"bounded voice scratch");
static void wipe(void *pointer,size_t count) {volatile uint8_t *p=pointer;while(count--)*p++=0;}
static void scrub_voice(LabVoice *v) {
    wipe(v->workspace,sizeof(v->workspace));wipe(v->features,sizeof(v->features));wipe(v->logits,sizeof(v->logits));
}
uint32_t pet_rejection_threshold(void) {return PET_THRESHOLD;}
int lab_voice_rank(const int32_t *logits,size_t count,LabVoiceScores *out) {
    if(!out)return 0;
    memset(out,0,sizeof(*out));
    if(!logits || count!=7)return 0;
    unsigned first=0;for(unsigned i=1;i<7;i++)if(logits[i]>logits[first])first=i;
    unsigned second=first ? 0:1;
    for(unsigned i=0;i<7;i++)if(i!=first && logits[i]>logits[second])second=i;
    *out=(LabVoiceScores){first,second,logits[first],logits[second],(uint32_t)((int64_t)logits[first]-logits[second])};
    return 1;
}
static int16_t sample(const LabAudio *a,uint32_t i) {
    return a->buffer ? a->buffer[i]:a->banks[i/LAB_AUDIO_BANK_FRAMES][i%LAB_AUDIO_BANK_FRAMES];
}
static int32_t chunk_mean(const LabAudio *a,uint32_t first) {
    int64_t sum=0;for(uint32_t i=first;i<first+1024;i++)sum+=sample(a,i);
    return (int32_t)(sum/1024);
}
static void observe_begin(LabVoice *v,const LabAudio *a,uint32_t owner,uint32_t now) {
    uint32_t seq=0,errors=0;
    if(v->observed_owner==owner && v->observed_generation==a->lease_generation) {
        seq=v->observed[0];errors=v->observed[2];
    }
    wipe(v->observed,sizeof(v->observed));wipe(&v->scores,sizeof(v->scores));v->scores_valid=false;v->observed_owner=owner;v->observed_generation=a->lease_generation;
    v->observed[0]=seq==UINT32_MAX ? 1:seq+1;v->observed[1]=UINT32_MAX;v->observed[2]=errors;
    v->observed[14]=3;v->observed[15]=now;
}
static int observe_finish(LabVoice *v,int result) {
    if(result<-1 || result>6)result=-1;
    v->observed[1]=(uint32_t)result;
    if(result<0 && v->observed[2]!=UINT32_MAX)v->observed[2]++;
    scrub_voice(v);return result;
}
int lab_voice_call(void *context,LabAudio *audio,uint32_t owner,uint32_t op,uint32_t value,uint32_t now) {
    LabVoice *voice=context;
    if(!voice || !audio || !audio->ready || !owner || audio->owner!=owner)return -1;
    if(op==LAB_AUDIO_VOICE_SNAPSHOT) {
        if(!(audio->permissions&LAB_AUDIO_CAN_RECORD) || value>17)return -1;
        bool current=voice->observed_owner==owner && voice->observed_generation==audio->lease_generation && voice->observed[0];
        if(!current)return value==0 ? 0:-1;
        if(!value)return 1;
        return value==17 ? (int32_t)voice->observed_generation:(int32_t)voice->observed[value-1];
    }
    if(op==LAB_AUDIO_VOICE_SCORES) {
        if(!(audio->permissions&LAB_AUDIO_CAN_RECORD) || value>11)return -1;
        bool current=voice->scores_valid && voice->observed_owner==owner &&
                     voice->observed_generation==audio->lease_generation && voice->observed[0];
        if(!current)return value==0 ? 0:-1;
        if(!value)return 1;
        uint32_t fields[]={voice->observed[0],voice->observed[1],voice->scores.top1,voice->scores.top2,
            (uint32_t)voice->scores.first,(uint32_t)voice->scores.second,voice->scores.margin,
            pet_rejection_threshold(),voice->observed[14],voice->observed[15],voice->observed_generation};
        return (int32_t)fields[value-1];
    }
    if(op==LAB_VM_AUDIO_CLASSIFY) {
        if(!(audio->permissions&LAB_AUDIO_CAN_RECORD))return -1;
        observe_begin(voice,audio,owner,now);
        if(audio->phase!=LAB_AUDIO_IDLE || audio->driver_owned || audio->result!=1 ||
           audio->kind!=LAB_AUDIO_RECORDING || audio->recorded!=PET_AUDIO_SAMPLES)return observe_finish(voice,-1);
        LabAudioRecordingMetrics m;
        if(!lab_audio_recording_metrics(audio,owner,&m) || m.frames!=PET_AUDIO_SAMPLES) {
            lab_audio_forget_recording(audio,owner);return observe_finish(voice,-1);
        }
        uint32_t fields[]={m.frames,(uint32_t)m.minimum,(uint32_t)m.maximum,(uint32_t)m.mean,m.rms,m.ac_rms,m.centered_peak,m.saturated_frames};
        for(unsigned i=0;i<8;i++)voice->observed[3+i]=fields[i];
        voice->observed[11]=(uint32_t)chunk_mean(audio,0);
        voice->observed[12]=(uint32_t)chunk_mean(audio,PET_AUDIO_SAMPLES-1024);
        int result=-1;
        if(pet_channel_feature_scratch_size()<=sizeof(voice->workspace)) {
            int prepared=audio->buffer ? pet_channel_prepare(audio->buffer,32000):pet_channel_prepare_banked(audio->banks,32000);
            if(prepared==1)result=audio->buffer ? pet_channel_features(audio->buffer,32000,voice->features,260,voice->workspace,sizeof(voice->workspace)) :
                pet_channel_features_banked((const int16_t *const *)audio->banks,32000,voice->features,260,voice->workspace,sizeof(voice->workspace));
        }
        voice->observed[13]=result==1;
        if(!lab_audio_forget_recording(audio,owner))result=-1;
        if(result==1) {
            result=pet_predict(voice->features,260,voice->logits,7);
            if(result>=0)voice->scores_valid=lab_voice_rank(voice->logits,7,&voice->scores)==1;
        }
        return observe_finish(voice,result);
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
