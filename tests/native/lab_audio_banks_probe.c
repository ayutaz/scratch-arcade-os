#include "audio_memory.h"
#include "audio_service.h"
#include "esp_heap_caps.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

static void *live[8];static size_t sizes[8];
static unsigned calls,frees,fail_at,position,sent,quantum=251;
static int cleanup=1,tone_mode;
void *heap_caps_malloc(size_t n,uint32_t caps) {
    assert(n<=8192 && caps==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    calls++;if(calls==fail_at)return NULL;
    for(unsigned i=0;i<8;i++)if(!live[i]) {
        live[i]=malloc(n);assert(live[i]);sizes[i]=n;memset(live[i],0x55,n);return live[i];
    }
    abort();
}
void heap_caps_free(void *p) {
    for(unsigned i=0;i<8;i++)if(live[i]==p) {
        for(size_t j=0;j<sizes[i];j++)assert(((unsigned char *)p)[j]==0);
        free(p);live[i]=NULL;frees++;return;
    }
    abort();
}
static int open_io(void *c,int mode){(void)c;assert(mode==1 || mode==2);return 1;}
static int read_io(void *c,int16_t *p,uint32_t n) {
    (void)c;assert(n && n<=256);if(n>quantum)n=quantum;
    for(unsigned i=0;i<n;i++)p[i]=((position+i)&1) ? 32767 : -32768;
    position+=n;return (int)n;
}
static int write_io(void *c,const int16_t *p,uint32_t n) {
    (void)c;assert(n && n<=256);if(n>quantum)n=quantum;
    for(unsigned i=0;i<n;i++) {
        unsigned at=sent+i,total=tone_mode ? 16000 : 32000;
        unsigned fade=at<total-1-at ? at : total-1-at;if(fade>80)fade=80;
        int raw=(at&1) ? 3276 : -3277; /* Q15 linear ceiling, not flat clipping. */
        if(tone_mode) {
            unsigned phase=(at*997)%16000;
            int triangle=(int)(phase<=8000 ? phase : 16000-phase)*4-16000;
            raw=triangle*2048/16000;
        }
        assert(p[i]==raw*(int)fade/80);
    }
    sent+=n;return (int)n;
}
static int drained(void *c){(void)c;return 1;}
static int close_io(void *c){(void)c;return cleanup;}
int main(int argc,char **argv) {
    (void)argc;LabAudioPcm pcm={0};
    if(argv[1][0]=='f') {
        for(unsigned f=1;f<=8;f++) {
            calls=frees=0;fail_at=f;
            assert(!lab_audio_pcm_banks_alloc(&pcm,32000));
            assert(!pcm.frames && calls==f && frees==f-1);
            for(unsigned i=0;i<8;i++)assert(!pcm.banks[i] && !live[i]);
        }
        return 0;
    }
    assert(!lab_audio_pcm_banks_alloc(&pcm,0));assert(!lab_audio_pcm_banks_alloc(&pcm,32001));
    assert(lab_audio_pcm_banks_alloc(&pcm,32000));assert(calls==8 && pcm.frames==32000);
    assert(!lab_audio_pcm_banks_alloc(&pcm,16000));assert(calls==8);
    LabAudio s={0};LabAudioIo io={NULL,open_io,read_io,write_io,drained,close_io};
    LabAudioPcm invalid=pcm;invalid.banks[1]=invalid.banks[0];
    assert(!lab_audio_init_banked(&s,&io,&invalid));assert(!s.ready);
    assert(!lab_audio_pcm_banks_free(&invalid));assert(frees==0);
    invalid=pcm;invalid.banks[7]=NULL;assert(!lab_audio_init_banked(&s,&io,&invalid));
    assert(lab_audio_init_banked(&s,&io,&pcm));assert(lab_audio_claim(&s,1,3));
    if(argv[1][0]=='t') {
        tone_mode=1;assert(lab_audio_tone(&s,1,997,1000,0));
        unsigned now=1;while(s.phase!=LAB_AUDIO_IDLE){assert(now<1000);lab_audio_poll(&s,now++);}
        assert(sent==16000 && s.result==1 && lab_audio_peak(&s)==0);
        assert(lab_audio_release(&s,1));assert(lab_audio_pcm_banks_free(&pcm));return 0;
    }
    assert(lab_audio_record(&s,1,2000,0));
    unsigned now=1;while(s.phase!=LAB_AUDIO_IDLE) {assert(now<1000);lab_audio_poll(&s,now++);assert(lab_audio_peak(&s)==32768);}
    assert(s.recorded==32000 && position==32000 && lab_audio_peak(&s)==32768);
    LabAudioRecordingMetrics metrics;
    assert(lab_audio_recording_metrics(&s,1,&metrics));
    assert(metrics.frames==32000 && metrics.minimum==-32768 && metrics.maximum==32767 && metrics.mean==0);
    assert(metrics.rms==32767 && metrics.ac_rms==32767 && metrics.centered_peak==32768 && metrics.saturated_frames==32000);
    assert(lab_audio_play_recording(&s,1,now));
    while(s.phase!=LAB_AUDIO_IDLE) {assert(now<2000);lab_audio_poll(&s,now++);}
    assert(sent==32000 && s.result==1);
    for(unsigned i=0;i<32000;i++)assert(pcm.banks[i/4096][i%4096]==((i&1) ? 32767 : -32768));
    assert(lab_audio_record(&s,1,2000,now));lab_audio_poll(&s,now+1);cleanup=0;
    assert(!lab_audio_release(&s,1));assert(s.owner==1 && !s.recorded);
    assert(!lab_audio_claim(&s,2,3));cleanup=1;assert(lab_audio_release(&s,1));
    for(unsigned i=0;i<32000;i++)assert(pcm.banks[i/4096][i%4096]==0);
    assert(lab_audio_pcm_banks_free(&pcm));assert(frees==8 && !pcm.frames);
    for(unsigned i=0;i<8;i++)assert(!pcm.banks[i] && !live[i]);
    return 0;
}
