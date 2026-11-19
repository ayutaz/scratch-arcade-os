/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PET_DSCNN_H
#define PET_DSCNN_H
#include <stddef.h>
#include <stdint.h>

enum { PET_DSCNN_FEATURES=2113, PET_DSCNN_CLASSES=7, PET_DSCNN_LAYERS=6 };
typedef struct {
    const int8_t *weight;
    const int32_t *bias, *shift;
    size_t weight_count, bias_count, shift_count;
} PetDscnnLayer;

/* Trusted caller-owned, accessible buffers, not an untrusted guest ABI.
 * The caller serializes use of a workspace; inference has no global state.
 * Only the original 2113-input six-layer representation is supported. */
size_t pet_dscnn_scratch_size(void);
int pet_dscnn_predict(const float *,size_t,const PetDscnnLayer *,size_t,
                     int32_t *,size_t,void *,size_t);
int pet_dscnn_classify(const int32_t *,size_t,const int32_t *,size_t);
#endif
