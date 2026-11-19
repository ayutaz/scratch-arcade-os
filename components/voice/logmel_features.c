/* SPDX-License-Identifier: Apache-2.0 */
#include "logmel_features.h"
#include <math.h>
#include <string.h>
#include "logmel_tables.h"

typedef struct {
    union { double real[512]; double ordered[198]; };
    double imag[512],energy[198],bands[64][32],pooled_energy[64];
} Scratch;
size_t pet_logmel_feature_scratch_size(void) { return sizeof(Scratch); }
static int aligned(const void *p,size_t n) { return p && (uintptr_t)p%n==0; }
static int overlap(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x>UINTPTR_MAX-na || y>UINTPTR_MAX-nb || (x<y+nb && y<x+na);
}
static unsigned smaller(unsigned a,unsigned b) { return a<b?a:b; }
static unsigned larger(unsigned a,unsigned b) { return a>b?a:b; }
static void add_frame(double *output,const double *values,unsigned frame,unsigned frames,unsigned columns)
{
    unsigned left=frame*64,right=(frame+1)*64;
    for (unsigned bin=left/frames;bin<=smaller(63,(right-1)/frames);bin++) {
        unsigned amount=smaller(right,(bin+1)*frames)-larger(left,bin*frames);
        double weight=(double)amount/frames;
        for (unsigned band=0;band<columns;band++) output[bin*columns+band]+=values[band]*weight;
    }
}
int pet_logmel_pool(const double *values,size_t rows,size_t columns,double *output,size_t count)
{
    if (!aligned(values,_Alignof(double)) || !aligned(output,_Alignof(double)) ||
        rows<1 || rows>198 || columns<1 || columns>32 || count!=64*columns ||
        overlap(values,rows*columns*sizeof(double),output,count*sizeof(double))) return -1;
    for (size_t i=0;i<rows*columns;i++) if (!isfinite(values[i]) || fabs(values[i])>1e6) return -1;
    memset(output,0,count*sizeof(double));
    for (unsigned i=0;i<rows;i++) add_frame(output,values+i*columns,i,(unsigned)rows,(unsigned)columns);
    return 1;
}
static void fft(double *real,double *imag)
{
    for (unsigned i=1,j=0;i<512;i++) {
        unsigned bit=256;
        for (;j&bit;bit>>=1) j^=bit;
        j^=bit;
        if (i<j) {
            double v=real[i];real[i]=real[j];real[j]=v;
            v=imag[i];imag[i]=imag[j];imag[j]=v;
        }
    }
    for (unsigned length=2;length<=512;length*=2) {
        unsigned half=length/2,step=512/length;
        for (unsigned first=0;first<512;first+=length) for (unsigned k=0;k<half;k++) {
            unsigned a=first+k,b=a+half,t=k*step;
            double wr=pet_logmel_cos[t],wi=-pet_logmel_sin[t];
            double tr=wr*real[b]-wi*imag[b],ti=wr*imag[b]+wi*real[b];
            double ar=real[a],ai=imag[a];real[a]=ar+tr;imag[a]=ai+ti;
            real[b]=ar-tr;imag[b]=ai-ti;
        }
    }
}
static int16_t sample_at(const int16_t *pcm,const int16_t *const *banks,unsigned i)
{
    return pcm?pcm[i]:banks[i/4096][i%4096];
}
static int core(const int16_t *pcm,const int16_t *const *banks,size_t samples,float *output,size_t count,void *workspace,size_t bytes)
{
    if (samples!=32000 || count!=2113 || !aligned(output,_Alignof(float)) ||
        !aligned(workspace,_Alignof(Scratch)) || bytes<sizeof(Scratch) ||
        overlap(output,2113*sizeof(float),workspace,sizeof(Scratch))) return -1;
    if (pcm) {
        if (!aligned(pcm,_Alignof(int16_t)) || overlap(pcm,64000,workspace,sizeof(Scratch)) ||
            overlap(pcm,64000,output,2113*sizeof(float))) return -1;
    } else {
        if (!aligned(banks,_Alignof(int16_t *)) || overlap(banks,8*sizeof(*banks),workspace,sizeof(Scratch)) ||
            overlap(banks,8*sizeof(*banks),output,2113*sizeof(float))) return -1;
        for (unsigned i=0;i<8;i++) {
            size_t n=(i==7?3328:4096)*sizeof(int16_t);
            if (!aligned(banks[i],_Alignof(int16_t)) || overlap(banks[i],n,workspace,sizeof(Scratch)) ||
                overlap(banks[i],n,output,2113*sizeof(float))) return -1;
        }
    }
    int32_t peak=0;
    for (unsigned i=0;i<32000;i++) {
        int32_t v=sample_at(pcm,banks,i);if (v<0) v=-v;if (v>peak) peak=v;
    }
    memset(output,0,2113*sizeof(float));if (peak<32) return 1;
    Scratch *s=workspace;double maximum=0;
    for (unsigned frame=0;frame<198;frame++) {
        uint64_t sum=0;
        for (unsigned i=0;i<400;i++) {int32_t v=sample_at(pcm,banks,frame*160+i);sum+=(uint64_t)(v*v);}
        double e=(double)sum/(400.0*(double)peak*(double)peak);s->energy[frame]=e;if (e>maximum) maximum=e;
        s->ordered[frame]=e;
    }
    for (unsigned i=1;i<198;i++) {
        double value=s->ordered[i];unsigned j=i;
        while (j && s->ordered[j-1]>value) {s->ordered[j]=s->ordered[j-1];j--;}
        s->ordered[j]=value;
    }
    double limit=fmax(.0004,fmax(maximum*.06,fmin(s->ordered[39]*3,maximum*.8)));
    unsigned first=198,last=0;
    for (unsigned i=0;i<198;i++) if (s->energy[i]>=limit) {if (first==198) first=i;last=i+1;}
    if (first==198) {first=0;last=198;}
    if (last-first<20) {if (first>178) first=178;last=first+20;}
    output[2112]=(float)(4.0*(last-first)/198);
    first=first>10?first-10:0;last=smaller(198,last+10);
    memset(s->bands,0,sizeof(s->bands));memset(s->pooled_energy,0,sizeof(s->pooled_energy));
    double maximum_log=log(fmax(maximum,1e-8));
    for (unsigned frame=first;frame<last;frame++) {
        for (unsigned i=0;i<512;i++) {
            s->real[i]=i<400?((double)sample_at(pcm,banks,frame*160+i)/peak)*pet_logmel_window[i]:0;
            s->imag[i]=0;
        }
        fft(s->real,s->imag);double mel[32]={0};
        for (unsigned i=0;i<257;i++) {
            double power=s->real[i]*s->real[i]+s->imag[i]*s->imag[i];
            for (unsigned side=0;side<2;side++) {
                int band=pet_logmel_index[i][side];if (band>=0) mel[band]+=power*pet_logmel_weight[i][side];
            }
        }
        for (unsigned band=0;band<32;band++) mel[band]=log(fmax(mel[band],1e-8));
        add_frame(&s->bands[0][0],mel,frame-first,last-first,32);
        double energy=log(fmax(s->energy[frame],1e-8))-maximum_log;
        add_frame(s->pooled_energy,&energy,frame-first,last-first,1);
    }
    for (unsigned band=0;band<32;band++) {
        double mean=0;for (unsigned bin=0;bin<64;bin++) mean+=s->bands[bin][band];mean/=64;
        for (unsigned bin=0;bin<64;bin++) output[bin*32+band]=(float)fmin(16,fmax(-16,(s->bands[bin][band]-mean)/4));
    }
    for (unsigned bin=0;bin<64;bin++) output[2048+bin]=(float)fmin(16,fmax(-16,s->pooled_energy[bin]/2));
    return 1;
}
int pet_logmel_features(const int16_t *pcm,size_t samples,float *out,size_t count,void *work,size_t bytes)
{
    if (!pcm) return -1;
    return core(pcm,NULL,samples,out,count,work,bytes);
}
int pet_logmel_features_banked(const int16_t *const *banks,size_t samples,float *out,size_t count,void *work,size_t bytes)
{
    return core(NULL,banks,samples,out,count,work,bytes);
}
