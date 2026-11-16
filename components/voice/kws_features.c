/* SPDX-License-Identifier: Apache-2.0 */
#include "pet_kws.h"
#include <math.h>
#include "feature_tables.h"

typedef struct {
    float real[512];
    float imag[512];
    double energy[198];
} FeatureScratch;

size_t pet_feature_scratch_size(void) { return sizeof(FeatureScratch); }

static void fft(float *real,float *imag)
{
    for (unsigned i=1,j=0;i<512;i++) {
        unsigned bit=256;
        for (;j&bit;bit>>=1) j^=bit;
        j^=bit;
        if (i<j) {
            float value=real[i];real[i]=real[j];real[j]=value;
            value=imag[i];imag[i]=imag[j];imag[j]=value;
        }
    }
    for (unsigned length=2;length<=512;length*=2) {
        unsigned half=length/2,step=512/length;
        for (unsigned first=0;first<512;first+=length) {
            for (unsigned k=0;k<half;k++) {
                unsigned a=first+k,b=a+half,t=k*step;
                float wr=pet_fft_cos[t],wi=-pet_fft_sin[t];
                float tr=wr*real[b]-wi*imag[b],ti=wr*imag[b]+wi*real[b];
                float ar=real[a],ai=imag[a];
                real[a]=ar+tr;imag[a]=ai+ti;
                real[b]=ar-tr;imag[b]=ai-ti;
            }
        }
    }
}

static int16_t sample_at(const int16_t *pcm,const int16_t *const *banks,unsigned index) {
    return pcm ? pcm[index]:banks[index/4096][index%4096];
}

static int features_core(const int16_t *pcm,const int16_t *const *banks,size_t samples,float *output,size_t count,
                         void *workspace,size_t workspace_bytes)
{
    if ((!pcm&&!banks)||!output||!workspace||samples!=PET_AUDIO_SAMPLES||count!=PET_FEATURE_COUNT||
        workspace_bytes<sizeof(FeatureScratch)||(uintptr_t)workspace%_Alignof(FeatureScratch)) return -1;
    FeatureScratch *scratch=workspace;
    int32_t peak=0;
    for (unsigned i=0;i<PET_AUDIO_SAMPLES;i++) {
        int32_t value=sample_at(pcm,banks,i);if (value<0)value=-value;
        if (value>peak)peak=value;
    }
    for (unsigned i=0;i<PET_FEATURE_COUNT;i++)output[i]=0;
    if (peak<32)return 1;
    double maximum=0;
    for (unsigned frame=0;frame<198;frame++) {
        uint64_t total=0;
        for (unsigned i=0;i<400;i++) {
            int32_t value=sample_at(pcm,banks,frame*160+i);total+=(uint64_t)(value*value);
        }
        double energy=(double)total/(400.0*(double)peak*(double)peak);
        scratch->energy[frame]=energy;if (energy>maximum)maximum=energy;
    }
    double limit=maximum*.06;if (limit<.0004)limit=.0004;
    unsigned first=198,last=0;
    for (unsigned frame=0;frame<198;frame++) {
        if (scratch->energy[frame]>=limit) {
            if (first==198)first=frame;
            last=frame+1;
        }
    }
    if (first==198) { first=0;last=198; }
    if (last-first<20) { if (first>178)first=178;last=first+20; }
    unsigned base=(last-first)/20,extra=(last-first)%20;
    unsigned bin=0,next=first+base+(extra>0);
    float maximum_log=(float)log(fmax(maximum,1e-8));
    for (unsigned frame=first;frame<last;frame++) {
        while (frame>=next) { bin++;next+=base+(bin<extra); }
        for (unsigned i=0;i<512;i++) {
            scratch->real[i]=i<400?((float)sample_at(pcm,banks,frame*160+i)/(float)peak)*pet_window[i]:0;
            scratch->imag[i]=0;
        }
        fft(scratch->real,scratch->imag);
        float mel[32]={0};
        for (unsigned i=0;i<257;i++) {
            float power=scratch->real[i]*scratch->real[i]+scratch->imag[i]*scratch->imag[i];
            for (unsigned side=0;side<2;side++) {
                int index=pet_mel_index[i][side];
                if (index>=0)mel[index]+=power*pet_mel_weight[i][side];
            }
        }
        for (unsigned i=0;i<32;i++)mel[i]=logf(fmaxf(mel[i],1e-8f));
        for (unsigned coefficient=0;coefficient<12;coefficient++) {
            float value=0;
            for (unsigned band=0;band<32;band++)value+=mel[band]*pet_dct[coefficient][band];
            output[bin*12+coefficient]+=value;
        }
        float log_energy=(float)log(fmax(scratch->energy[frame],1e-8));
        output[240+bin]+=log_energy-maximum_log;
    }
    for (unsigned group=0;group<20;group++) {
        float frames=(float)(base+(group<extra));
        for (unsigned coefficient=0;coefficient<12;coefficient++) {
            unsigned index=group*12+coefficient;
            output[index]=fminf(16,fmaxf(-16,output[index]/frames/4));
        }
        output[240+group]=fminf(16,fmaxf(-16,output[240+group]/frames/2));
    }
    return 1;
}

int pet_features(const int16_t *pcm,size_t samples,float *output,size_t count,
                 void *workspace,size_t workspace_bytes) {
    return features_core(pcm,NULL,samples,output,count,workspace,workspace_bytes);
}
int pet_features_banked(const int16_t *const *banks,size_t samples,float *output,size_t count,
                        void *workspace,size_t workspace_bytes) {
    if(!banks)return -1;
    for(unsigned i=0;i<8;i++)if(!banks[i])return -1;
    return features_core(NULL,banks,samples,output,count,workspace,workspace_bytes);
}
