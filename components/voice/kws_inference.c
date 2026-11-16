/* SPDX-License-Identifier: Apache-2.0 */
#include "pet_kws.h"
#include <limits.h>
#include <math.h>
#include "pet_model.h"

static int32_t quantize(float value)
{
    if (value>16)value=16;
    if (value< -16)value=-16;
    float scaled=value*1024.0f;
    int32_t integer=(int32_t)scaled;
    float fraction=scaled-(float)integer;
    if (fraction>.5f||(fraction==.5f&&integer%2))integer++;
    else if (fraction< -.5f||(fraction== -.5f&&integer%2))integer--;
    return integer;
}

static int64_t shift_floor(int64_t value,unsigned shift)
{
    int64_t divisor=(int64_t)1<<shift;
    return value>=0?value/divisor:-((-value+divisor-1)/divisor);
}

int pet_predict(const float *features,size_t count,int32_t *logits,size_t logits_count)
{
    if (!features||!logits||count!=PET_FEATURE_COUNT||logits_count!=PET_CLASS_COUNT)return -1;
    int32_t input[PET_FEATURE_COUNT],hidden[PET_HIDDEN];
    for (unsigned i=0;i<PET_FEATURE_COUNT;i++) {
        if (!isfinite(features[i]))return -1;
        input[i]=quantize(features[i]);
    }
    for (unsigned row=0;row<PET_HIDDEN;row++) {
        int64_t total=pet_bias0[row];
        for (unsigned col=0;col<PET_FEATURE_COUNT;col++)total+=(int64_t)pet_weight0[row][col]*input[col];
        int64_t value=shift_floor(total,PET_SHIFT0);
        hidden[row]=value<0?0:value>6144?6144:(int32_t)value;
    }
    int best=0;
    for (unsigned row=0;row<PET_CLASS_COUNT;row++) {
        int64_t total=pet_bias1[row];
        for (unsigned col=0;col<PET_HIDDEN;col++)total+=(int64_t)pet_weight1[row][col]*hidden[col];
        int64_t value=shift_floor(total,PET_SHIFT1);
        if (value<INT32_MIN||value>INT32_MAX)return -1;
        logits[row]=(int32_t)value;
        if (row&&logits[row]>logits[best])best=(int)row;
    }
    int32_t second=INT32_MIN;
    for (unsigned row=0;row<PET_CLASS_COUNT;row++)if ((int)row!=best&&logits[row]>second)second=logits[row];
    return best<5&&(int64_t)logits[best]-second<PET_THRESHOLD?5:best;
}
