/* SPDX-License-Identifier: Apache-2.0 */
#include "dscnn.h"
#include <limits.h>
#include <math.h>

enum { EVEN_BYTES=8192, ODD_BYTES=4096, SCRATCH_BYTES=EVEN_BYTES+ODD_BYTES };
static const unsigned outputs[6]={8,8,16,16,24,7};
static const unsigned weights[6]={72,72,128,144,384,21959};
static const unsigned kernels[5]={3,3,1,3,1}, strides[5]={2,1,1,2,1};

size_t pet_dscnn_scratch_size(void) { return SCRATCH_BYTES; }
static int aligned(const void *p,size_t alignment) { return p && (uintptr_t)p%alignment==0; }
static int overlap(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if (x>UINTPTR_MAX-na || y>UINTPTR_MAX-nb) return 1;
    return x<y+nb && y<x+na;
}
static int64_t floor_shift(int64_t value,unsigned shift)
{
    int64_t divisor=(int64_t)1<<shift;
    return value/divisor-(value<0 && value%divisor!=0);
}
static int16_t q5(float value)
{
    float scaled=value*32.0f;
    int32_t whole=(int32_t)scaled;
    float fraction=scaled-(float)whole;
    if (fraction>.5f || (fraction==.5f && whole%2)) whole++;
    if (fraction<-.5f || (fraction==-.5f && whole%2)) whole--;
    return (int16_t)whole;
}
static int validate_model(const PetDscnnLayer *layers,void *scratch,int32_t *out,const float *input)
{
    if (overlap(layers,6*sizeof(*layers),scratch,SCRATCH_BYTES) ||
        overlap(layers,6*sizeof(*layers),out,7*sizeof(*out))) return 0;
    for (unsigned i=0;i<6;i++) {
        const PetDscnnLayer *p=&layers[i];
        if (!p->weight || !aligned(p->bias,_Alignof(int32_t)) || !aligned(p->shift,_Alignof(int32_t)) ||
            p->weight_count!=weights[i] || p->bias_count!=outputs[i] || p->shift_count!=outputs[i]) return 0;
        const void *buffers[3]={p->weight,p->bias,p->shift};
        size_t sizes[3]={weights[i],outputs[i]*sizeof(int32_t),outputs[i]*sizeof(int32_t)};
        for (unsigned j=0;j<3;j++)
            if (overlap(buffers[j],sizes[j],scratch,SCRATCH_BYTES) ||
                overlap(buffers[j],sizes[j],out,7*sizeof(*out)) ||
                overlap(buffers[j],sizes[j],input,PET_DSCNN_FEATURES*sizeof(float))) return 0;
        for (unsigned j=0;j<outputs[i];j++) if (p->shift[j]<0 || p->shift[j]>16) return 0;
    }
    return 1;
}
static void conv(const void *input,int first,unsigned h,unsigned w,unsigned channels,
                 const PetDscnnLayer *p,unsigned index,uint8_t *output)
{
    unsigned kernel=kernels[index],stride=strides[index],depthwise=index==1 || index==3;
    unsigned depth=depthwise?1:channels,oh=(h+stride-1)/stride,ow=(w+stride-1)/stride;
    for (unsigned oc=0;oc<outputs[index];oc++)
        for (unsigned row=0;row<oh;row++) for (unsigned col=0;col<ow;col++) {
            int64_t total=p->bias[oc];
            for (unsigned ic=0;ic<depth;ic++) for (unsigned ky=0;ky<kernel;ky++) for (unsigned kx=0;kx<kernel;kx++) {
                int y=(int)(row*stride+ky)-(int)(kernel/2),x=(int)(col*stride+kx)-(int)(kernel/2);
                if (y<0 || x<0 || y>=(int)h || x>=(int)w) continue;
                size_t source=((depthwise?oc:ic)*h+(unsigned)y)*w+(unsigned)x;
                int32_t value=first?((const int16_t *)input)[source]:((const uint8_t *)input)[source];
                total+=(int64_t)value*p->weight[((oc*depth+ic)*kernel+ky)*kernel+kx];
            }
            int64_t value=floor_shift(total,(unsigned)p->shift[oc]);
            output[(oc*oh+row)*ow+col]=(uint8_t)(value<0?0:value>192?192:value);
        }
}
int pet_dscnn_predict(const float *features,size_t count,const PetDscnnLayer *layers,size_t layer_count,
                     int32_t *logits,size_t logits_count,void *workspace,size_t workspace_bytes)
{
    if (!aligned(features,_Alignof(float)) || !aligned(layers,_Alignof(PetDscnnLayer)) ||
        !aligned(logits,_Alignof(int32_t)) || !aligned(workspace,_Alignof(int16_t)) ||
        count!=PET_DSCNN_FEATURES || layer_count!=6 || logits_count!=7 || workspace_bytes<SCRATCH_BYTES ||
        overlap(features,count*sizeof(float),workspace,SCRATCH_BYTES) ||
        overlap(features,count*sizeof(float),logits,7*sizeof(int32_t)) ||
        overlap(logits,7*sizeof(int32_t),workspace,SCRATCH_BYTES)) return -1;
    if (!validate_model(layers,workspace,logits,features)) return -1;
    for (unsigned i=0;i<count;i++)
        if (!isfinite(features[i]) || features[i]<-16 || features[i]>16 ||
            (i>=2048 && i<2112 && features[i]>0) ||
            (i==2112 && (features[i]<0 || features[i]>4))) return -1;
    uint8_t *even=workspace,*odd=even+EVEN_BYTES;
    for (unsigned i=0;i<2048;i++) ((int16_t *)odd)[i]=q5(features[i]);
    const void *current=odd;
    unsigned h=64,w=32,channels=1;
    for (unsigned i=0;i<5;i++) {
        uint8_t *next=i%2?odd:even;
        conv(current,i==0,h,w,channels,&layers[i],i,next);
        h=(h+strides[i]-1)/strides[i];w=(w+strides[i]-1)/strides[i];channels=outputs[i];current=next;
    }
    for (unsigned oc=0;oc<7;oc++) {
        int64_t total=layers[5].bias[oc];
        for (unsigned i=0;i<3137;i++) {
            int32_t value=i<3072?((const uint8_t *)current)[i]:q5(features[2048+i-3072]);
            total+=(int64_t)value*layers[5].weight[oc*3137+i];
        }
        int shift=layers[5].shift[oc]-5;
        int64_t value=shift>=0?floor_shift(total,(unsigned)shift):total*((int64_t)1<<-shift);
        logits[oc]=(int32_t)(value<INT32_MIN?INT32_MIN:value>INT32_MAX?INT32_MAX:value);
    }
    return 1;
}
int pet_dscnn_classify(const int32_t *logits,size_t count,const int32_t *thresholds,size_t threshold_count)
{
    if (!aligned(logits,_Alignof(int32_t)) || !aligned(thresholds,_Alignof(int32_t)) || count!=7 || threshold_count!=5) return -1;
    for (unsigned i=0;i<5;i++) if (thresholds[i]<0 || thresholds[i]>4096) return -1;
    unsigned best=0;
    for (unsigned i=1;i<7;i++) if (logits[i]>logits[best]) best=i;
    int32_t second=INT32_MIN;
    for (unsigned i=0;i<7;i++) if (i!=best && logits[i]>second) second=logits[i];
    return best<5 && (int64_t)logits[best]-second<thresholds[best]?5:(int)best;
}
