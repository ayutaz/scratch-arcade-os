#include "audio_service.h"
#include <stddef.h>
#include <math.h>
#include <string.h>

static int16_t *span(const LabAudio *s,uint32_t at,uint32_t *frames) {
    uint32_t remaining=s->capacity-at;
    if(s->buffer) {*frames=remaining;return s->buffer+at;}
    uint32_t offset=at%LAB_AUDIO_BANK_FRAMES,n=LAB_AUDIO_BANK_FRAMES-offset;
    *frames=n<remaining ? n : remaining;return s->banks[at/LAB_AUDIO_BANK_FRAMES]+offset;
}
static void scrub(LabAudio *s) {
    for(uint32_t at=0;at<s->capacity;) {
        uint32_t n;volatile int16_t *p=span(s,at,&n);
        for(uint32_t i=0;i<n;i++)p[i]=0;
        at+=n;
    }
    s->recorded=0;s->replay_mean=0;s->replay_scale_q15=0;memset(s->output,0,sizeof(s->output));
}
static bool io_valid(const LabAudioIo *io) {
    return io && io->open && io->read && io->write && io->drained && io->close;
}
bool lab_audio_init(LabAudio *s,const LabAudioIo *io,int16_t *buffer,uint32_t frames) {
    if(!s || s->ready || !io_valid(io) || !buffer || !frames || frames>32000)return false;
    *s=(LabAudio){.io=*io,.buffer=buffer,.capacity=frames,.ready=true};scrub(s);return true;
}
bool lab_audio_init_banked(LabAudio *s,const LabAudioIo *io,const LabAudioPcm *pcm) {
    if(!s || s->ready || !io_valid(io) || !pcm || !pcm->frames || pcm->frames>32000)return false;
    unsigned count=(pcm->frames+LAB_AUDIO_BANK_FRAMES-1)/LAB_AUDIO_BANK_FRAMES;
    for(unsigned i=0;i<LAB_AUDIO_BANKS;i++) {
        if((i<count)!=!!pcm->banks[i])return false;
        for(unsigned j=0;j<i && i<count;j++)if(pcm->banks[i]==pcm->banks[j])return false;
    }
    *s=(LabAudio){.io=*io,.capacity=pcm->frames,.ready=true};
    memcpy(s->banks,pcm->banks,sizeof(s->banks));scrub(s);return true;
}
int lab_audio_peak(const LabAudio *s) {
    if(!s || !s->ready || s->position>s->capacity)return -1;
    if(s->kind!=LAB_AUDIO_RECORDING)return 0;
    uint32_t at=s->position>256 ? s->position-256 : 0;int32_t peak=0;
    while(at<s->position) {
        uint32_t n;const int16_t *p=span(s,at,&n);
        if(n>s->position-at)n=s->position-at;
        for(uint32_t i=0;i<n;i++){int32_t v=p[i];if(v<0)v=-v;if(v>peak)peak=v;}
        at+=n;
    }
    return (int)peak;
}
bool lab_audio_claim(LabAudio *s,uint32_t owner,uint32_t permissions) {
    if(!s || !s->ready || s->owner || s->driver_owned || s->phase!=LAB_AUDIO_IDLE ||
       !owner || !permissions || permissions>3)return false;
    scrub(s);s->owner=owner;s->permissions=permissions;s->result=0;
    /* A fresh lease must not expose the previous app's operation metadata. */
    s->position=s->total=s->kind=0;s->replaying=false;s->replay_gain=1;return true;
}
static int finish(LabAudio *s,int outcome) {
    s->phase=LAB_AUDIO_CLOSING;s->outcome=outcome;
    if(s->io.close(s->io.context)!=1)return 0;
    s->driver_owned=false;s->phase=LAB_AUDIO_IDLE;s->result=outcome;
    if(outcome<0)scrub(s);
    else if(s->kind==LAB_AUDIO_RECORDING)s->recorded=s->total;
    return outcome;
}
bool lab_audio_release(LabAudio *s,uint32_t owner) {
    if(!s || !s->ready || !owner || s->owner!=owner)return false;
    s->permissions=0;scrub(s);
    if(s->driver_owned && finish(s,-1)==0)return false;
    s->owner=0;s->result=0;return true;
}
static bool allowed(LabAudio *s,uint32_t owner,uint32_t permission) {
    return s && s->ready && owner && s->owner==owner && (s->permissions&permission) &&
        !s->driver_owned && s->phase==LAB_AUDIO_IDLE;
}
static bool begin(LabAudio *s,uint32_t frames,uint32_t kind,uint32_t ms,uint32_t now) {
    s->total=frames;s->position=0;s->started=now;s->limit_ms=ms+1000;s->kind=kind;s->result=0;
    /* A failed open may retain a partly acquired channel. Always close it. */
    s->driver_owned=true;
    if(s->io.open(s->io.context,kind==LAB_AUDIO_RECORDING ? 2 : 1)!=1) {
        finish(s,-1);return false;
    }
    s->phase=kind;return true;
}
bool lab_audio_set_gain(LabAudio *s,uint32_t owner,uint32_t gain) {
    if(!allowed(s,owner,LAB_AUDIO_CAN_PLAY) || gain>8)return false;
    s->replay_gain=gain;return true;
}
static uint32_t root64(uint64_t n) {
    uint64_t result=0,bit=UINT64_C(1)<<62;
    while(bit>n)bit>>=2;
    while(bit) {
        if(n>=result+bit){n-=result+bit;result=(result>>1)+bit;}
        else result>>=1;
        bit>>=2;
    }
    return (uint32_t)result;
}
bool lab_audio_recording_metrics(const LabAudio *s,uint32_t owner,LabAudioRecordingMetrics *out) {
    if(!out)return false;
    *out=(LabAudioRecordingMetrics){0};
    if(!s || !s->ready || !owner || s->owner!=owner || !(s->permissions&LAB_AUDIO_CAN_RECORD) ||
       s->phase!=LAB_AUDIO_IDLE || s->driver_owned || !s->recorded ||
       s->recorded>s->capacity || s->capacity>32000)return false;
    int64_t sum=0;uint64_t squares=0;
    int32_t low=32767,high=-32768;uint32_t saturated=0;
    for(uint32_t at=0;at<s->recorded;) {
        uint32_t n;const int16_t *p=span(s,at,&n);
        if(n>s->recorded-at)n=s->recorded-at;
        for(uint32_t i=0;i<n;i++) {
            int32_t v=p[i];sum+=v;squares+=(uint64_t)((int64_t)v*v);
            if(v<low)low=v;
            if(v>high)high=v;
            if(v==-32768 || v==32767)saturated++;
        }
        at+=n;
    }
    uint64_t count=s->recorded;int32_t mean=(int32_t)(sum/(int64_t)count);
    uint32_t peak=(uint32_t)(high-mean)>(uint32_t)(mean-low) ? (uint32_t)(high-mean):(uint32_t)(mean-low);
    *out=(LabAudioRecordingMetrics){s->recorded,low,high,mean,root64(squares/count),
        root64((squares*count-(uint64_t)(sum*sum))/(count*count)),peak,saturated};
    return true;
}
static uint32_t tone_amplitude(const LabAudio *s,uint32_t start,uint32_t end,int32_t mean,float coefficient) {
    float first=0,second=0;
    for(uint32_t at=start;at<end;) {
        uint32_t n;const int16_t *p=span(s,at,&n);
        if(n>end-at)n=end-at;
        for(uint32_t i=0;i<n;i++) {
            float next=(float)(p[i]-mean)+coefficient*first-second;
            second=first;first=next;
        }
        at+=n;
    }
    float power=first*first+second*second-coefficient*first*second;
    float amplitude=power>0 && end>start ? 2*sqrtf(power)/(float)(end-start):0;
    return amplitude>=65535 ? 65535:(uint32_t)(amplitude+0.5f);
}
bool lab_audio_recording_bands(const LabAudio *s,uint32_t owner,uint32_t out[4]) {
    if(!out)return false;
    memset(out,0,4*sizeof(*out));LabAudioRecordingMetrics metrics;
    if(!lab_audio_recording_metrics(s,owner,&metrics))return false;
    uint32_t half=metrics.frames/2;
    /* 2*cos(2*pi*f/16000), fixed diagnostic frequencies; not a speech detector. */
    const float coefficients[2]={1.737263f,1.5410265f};
    for(unsigned h=0;h<2;h++)for(unsigned f=0;f<2;f++)
        out[h*2+f]=tone_amplitude(s,h ? half:0,h ? metrics.frames:half,metrics.mean,coefficients[f]);
    return true;
}
bool lab_audio_tone(LabAudio *s,uint32_t owner,uint32_t hz,uint32_t ms,uint32_t now) {
    if(!allowed(s,owner,LAB_AUDIO_CAN_PLAY) || hz<200 || hz>4000 || ms<20 || ms>1000 || ms*16>s->capacity)return false;
    uint32_t frames=ms*16;s->recorded=0;s->replaying=false;
    for(uint32_t i=0;i<frames;i++) {
        uint32_t phase=(i*hz)%16000;
        int32_t triangle=(int32_t)(phase<=8000 ? phase : 16000-phase)*4-16000;
        uint32_t fade=i<frames-1-i ? i : frames-1-i;if(fade>80)fade=80;
        uint32_t n;*span(s,i,&n)=(int16_t)(triangle*2048/16000*(int32_t)fade/80);
    }
    return begin(s,frames,LAB_AUDIO_PLAYING,ms,now);
}
bool lab_audio_record(LabAudio *s,uint32_t owner,uint32_t ms,uint32_t now) {
    if(!allowed(s,owner,LAB_AUDIO_CAN_RECORD) || !ms || ms>2000 || ms*16>s->capacity)return false;
    scrub(s);s->replaying=false;return begin(s,ms*16,LAB_AUDIO_RECORDING,ms,now);
}
bool lab_audio_play_recording(LabAudio *s,uint32_t owner,uint32_t now) {
    if(!allowed(s,owner,LAB_AUDIO_CAN_PLAY) || !s->recorded || s->recorded>s->capacity)return false;
    LabAudioRecordingMetrics metrics;
    if(!lab_audio_recording_metrics(s,owner,&metrics))return false;
    uint32_t desired=s->replay_gain*32768u;
    uint32_t ceiling=metrics.centered_peak ? 3277u*32768u/metrics.centered_peak : 0;
    s->replay_mean=metrics.mean;s->replay_scale_q15=desired<ceiling ? desired:ceiling;
    s->replaying=true;return begin(s,s->recorded,LAB_AUDIO_PLAYING,(s->recorded+15)/16,now);
}
bool lab_audio_forget_recording(LabAudio *s,uint32_t owner) {
    if(!allowed(s,owner,LAB_AUDIO_CAN_RECORD))return false;
    scrub(s);return true;
}
bool lab_audio_play_pcm8(LabAudio *s,uint32_t owner,const int8_t *clip,uint32_t samples,uint32_t now) {
    if(!allowed(s,owner,LAB_AUDIO_CAN_PLAY) || !clip || samples<80 || samples>16000 || samples*2>s->capacity)return false;
    scrub(s);uint32_t frames=samples*2;
    for(uint32_t i=0;i<frames;i++) {
        int32_t value=(int32_t)clip[i/2]*28;
        if(value>3277)value=3277;
        if(value< -3277)value=-3277;
        uint32_t fade=i<frames-1-i ? i:frames-1-i;if(fade>80)fade=80;
        uint32_t n;*span(s,i,&n)=(int16_t)(value*(int32_t)fade/80);
    }
    s->replaying=false;return begin(s,frames,LAB_AUDIO_PLAYING,(frames+15)/16,now);
}
int lab_audio_poll(LabAudio *s,uint32_t now) {
    if(!s || !s->ready)return -1;
    if(s->phase==LAB_AUDIO_IDLE)return s->result;
    if(s->phase==LAB_AUDIO_CLOSING)return finish(s,s->outcome);
    if((uint32_t)(now-s->started)>s->limit_ms)return finish(s,-1);
    if(s->phase==LAB_AUDIO_DRAINING) {
        int done=s->io.drained(s->io.context);
        if(done==0)return 0;
        return finish(s,done==1 ? 1 : -1);
    }
    uint32_t remaining=s->total-s->position,frames=remaining>256 ? 256 : remaining;
    uint32_t available;int16_t *data=span(s,s->position,&available);
    if(frames>available)frames=available;
    const int16_t *out=data;
    if(s->phase==LAB_AUDIO_PLAYING && s->replaying) {
        for(uint32_t i=0;i<frames;i++) {
            uint32_t at=s->position+i,fade=at<s->total-1-at ? at : s->total-1-at;
            if(fade>80)fade=80;
            int32_t v=(int32_t)(((int64_t)data[i]-s->replay_mean)*s->replay_scale_q15/32768);
            if(v>3277)v=3277;
            if(v< -3277)v=-3277;
            s->output[i]=(int16_t)(v*(int32_t)fade/80);
        }
        out=s->output;
    }
    int count=s->phase==LAB_AUDIO_RECORDING ? s->io.read(s->io.context,data,frames) :
        s->io.write(s->io.context,out,frames);
    if(count<0 || (uint32_t)count>frames)return finish(s,-1);
    s->position+=(uint32_t)count;
    if(s->position==s->total) {
        if(s->phase==LAB_AUDIO_RECORDING)return finish(s,1);
        s->phase=LAB_AUDIO_DRAINING;
    }
    return 0;
}
