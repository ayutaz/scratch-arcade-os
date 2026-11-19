/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PET_LOGMEL_COMPACT_H
#define PET_LOGMEL_COMPACT_H
#include <stddef.h>
#include <stdint.h>
/* Trusted prepared PCM and accessible caller buffers. Output must equal the
 * aligned workspace base; its first 2113 floats survive until inference.
 * Banks cover 7*4096+3328 samples. All other overlap is rejected. */
size_t pet_logmel_compact_scratch_size(void);
int pet_logmel_compact_features(const int16_t *,size_t,float *,size_t,void *,size_t);
int pet_logmel_compact_features_banked(const int16_t *const *,size_t,float *,size_t,void *,size_t);
#endif
