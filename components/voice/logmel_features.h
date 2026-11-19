/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PET_LOGMEL_FEATURES_H
#define PET_LOGMEL_FEATURES_H
#include <stddef.h>
#include <stdint.h>
/* Trusted accessible caller buffers; banks cover 7*4096+3328 PCM16 samples.
 * Features consume already-prepared PCM; HP160/level is a separate operation. */
size_t pet_logmel_feature_scratch_size(void);
int pet_logmel_features(const int16_t *,size_t,float *,size_t,void *,size_t);
int pet_logmel_features_banked(const int16_t *const *,size_t,float *,size_t,void *,size_t);
/* Diagnostic fractional pooling: finite bounded double values, 1..198 x 1..32. */
int pet_logmel_pool(const double *,size_t,size_t,double *,size_t);
#endif
