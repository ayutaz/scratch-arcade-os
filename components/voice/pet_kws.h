/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARCADE_PET_KWS_H
#define ARCADE_PET_KWS_H
#include <stddef.h>
#include <stdint.h>

enum { PET_AUDIO_SAMPLES=32000, PET_FEATURE_COUNT=260, PET_CLASS_COUNT=7 };
/* Trusted caller-owned, correctly aligned memory only. No guest pointers or I/O. */
size_t pet_feature_scratch_size(void);
int pet_features(const int16_t *pcm,size_t samples,float *output,size_t count,
                 void *workspace,size_t workspace_bytes);
/* Eight trusted PCM banks: first seven have 4096 samples, last >=3328.
 * Same feature output/scratch; no second 64KB PCM allocation or I/O. */
int pet_features_banked(const int16_t *const *banks,size_t samples,float *output,size_t count,
                        void *workspace,size_t workspace_bytes);
/* Q10 integer inference, fixed exported weights. Returns class 0..6 or -1.
 * Classes: play, come, wait, sleep, thanks, unknown, silence. No heap/global state. */
int pet_predict(const float *features,size_t count,int32_t *logits,size_t logits_count);
#endif
