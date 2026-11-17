/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PET_CHANNEL_FEATURES_H
#define PET_CHANNEL_FEATURES_H
#include "pet_kws.h"
int pet_channel_prepare(int16_t *,size_t);
int pet_channel_prepare_banked(int16_t *const *,size_t);
size_t pet_channel_feature_scratch_size(void);
int pet_channel_features(const int16_t *,size_t,float *,size_t,void *,size_t);
int pet_channel_features_banked(const int16_t *const *,size_t,float *,size_t,void *,size_t);
#endif
