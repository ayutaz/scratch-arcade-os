#include "audio_memory.h"
#include "esp_heap_caps.h"
#include <stddef.h>
static uint32_t bank_frames(uint32_t frames,unsigned i) {
    uint32_t n=frames-i*LAB_AUDIO_BANK_FRAMES;
    return n>LAB_AUDIO_BANK_FRAMES ? LAB_AUDIO_BANK_FRAMES : n;
}
bool lab_audio_pcm_banks_alloc(LabAudioPcm *pcm,uint32_t frames) {
    if(!pcm || pcm->frames || !frames || frames>32000)return false;
    for(unsigned i=0;i<LAB_AUDIO_BANKS;i++)if(pcm->banks[i])return false;
    unsigned count=(frames+LAB_AUDIO_BANK_FRAMES-1)/LAB_AUDIO_BANK_FRAMES;
    for(unsigned i=0;i<count;i++) {
        pcm->banks[i]=lab_audio_pcm_alloc(bank_frames(frames,i));
        if(!pcm->banks[i]) {
            for(unsigned j=0;j<i;j++){lab_audio_pcm_free(pcm->banks[j],bank_frames(frames,j));pcm->banks[j]=NULL;}
            return false;
        }
    }
    pcm->frames=frames;return true;
}
bool lab_audio_pcm_banks_free(LabAudioPcm *pcm) {
    if(!pcm || !pcm->frames || pcm->frames>32000)return false;
    unsigned count=(pcm->frames+LAB_AUDIO_BANK_FRAMES-1)/LAB_AUDIO_BANK_FRAMES;
    for(unsigned i=0;i<LAB_AUDIO_BANKS;i++) {
        if((i<count)!=!!pcm->banks[i])return false;
        for(unsigned j=0;j<i && i<count;j++)if(pcm->banks[i]==pcm->banks[j])return false;
    }
    for(unsigned i=0;i<count;i++){lab_audio_pcm_free(pcm->banks[i],bank_frames(pcm->frames,i));pcm->banks[i]=NULL;}
    pcm->frames=0;return true;
}
int16_t *lab_audio_pcm_alloc(uint32_t frames) {
    if(!frames || frames>32000)return NULL;
    return heap_caps_malloc(frames*sizeof(int16_t),MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
}
bool lab_audio_pcm_free(int16_t *pcm,uint32_t frames) {
    if(!pcm || !frames || frames>32000)return false;
    volatile int16_t *wipe=pcm;
    for(uint32_t i=0;i<frames;i++)wipe[i]=0;
    heap_caps_free(pcm);return true;
}
