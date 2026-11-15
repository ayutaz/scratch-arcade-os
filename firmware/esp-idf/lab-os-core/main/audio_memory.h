#ifndef LAB_AUDIO_MEMORY_H
#define LAB_AUDIO_MEMORY_H
#include <stdint.h>
#include <stdbool.h>
#include "audio_service.h"
/* Lazy internal PCM banks, <=8KiB each; preserves 32000-frame total capacity.
 * Failure scrubs/frees partial allocations. A live descriptor cannot be reused. */
bool lab_audio_pcm_banks_alloc(LabAudioPcm *,uint32_t frames);
bool lab_audio_pcm_banks_free(LabAudioPcm *);
/* PCM16, 1..32000 frames, INTERNAL|8BIT only. No fallback to PSRAM. */
int16_t *lab_audio_pcm_alloc(uint32_t frames);
/* Exact originally allocated extent, trusted OS caller. Volatile scrub before
 * free. Invalid arguments return false without guessing or touching memory. */
bool lab_audio_pcm_free(int16_t *,uint32_t frames);
#endif
