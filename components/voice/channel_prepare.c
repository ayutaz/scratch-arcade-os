/* SPDX-License-Identifier: Apache-2.0
 * Fixed HP160 -> mean removal -> peak4096 for the frozen channel model.
 * Consumes trusted caller-owned PCM only; no allocation or I/O.
 */
#include "channel_features.h"
#include <math.h>
static int16_t *at(int16_t *pcm,int16_t *const *banks,size_t i) {
    return pcm ? pcm+i:banks[i/4096]+i%4096;
}
static int prepare(int16_t *pcm,int16_t *const *banks,size_t count) {
    if((!pcm&&!banks)||count!=32000)return -1;
    float alpha=expf(-2.0f*3.14159265358979323846f*160.0f/16000.0f);
    float previous=(float)*at(pcm,banks,0),value=0;int64_t sum=0;
    for(size_t i=0;i<count;i++) {
        float input=(float)*at(pcm,banks,i);value=alpha*(value+input-previous);previous=input;
        *at(pcm,banks,i)=(int16_t)roundf(fminf(32767,fmaxf(-32768,value)));
        sum+=*at(pcm,banks,i);
    }
    int32_t mean=(int32_t)(sum/(int64_t)count),peak=0;
    for(size_t i=0;i<count;i++) {
        int32_t centered=(int32_t)*at(pcm,banks,i)-mean;
        int16_t sample=(int16_t)(centered>32767 ? 32767:centered<-32768 ? -32768:centered);
        *at(pcm,banks,i)=sample;int32_t magnitude=sample<0 ? -(int32_t)sample:sample;
        if(magnitude>peak)peak=magnitude;
    }
    if(peak)for(size_t i=0;i<count;i++)*at(pcm,banks,i)=(int16_t)((int64_t)*at(pcm,banks,i)*4096/peak);
    return 1;
}
int pet_channel_prepare(int16_t *pcm,size_t count) {return prepare(pcm,NULL,count);}
int pet_channel_prepare_banked(int16_t *const *banks,size_t count) {
    if(!banks)return -1;
    for(unsigned i=0;i<8;i++)if(!banks[i])return -1;
    return prepare(NULL,banks,count);
}
