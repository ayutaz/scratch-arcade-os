/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PET_DECISION_FEATURES_H
#define PET_DECISION_FEATURES_H
#include "channel_features.h"
enum { PET_DECISION_FEATURE_COUNT=261 };
/* Trusted aligned caller-owned buffers only, as in pet_kws.h. Not a guest ABI. */
size_t pet_decision_feature_scratch_size(void);
int pet_decision_features(const int16_t *,size_t,float *,size_t,void *,size_t);
int pet_decision_features_banked(const int16_t *const *,size_t,float *,size_t,void *,size_t);
int pet_decision_predict(const float *,size_t,int32_t *,size_t);
int pet_decision_classify(const int32_t *,size_t,const int32_t *,size_t);
#endif
