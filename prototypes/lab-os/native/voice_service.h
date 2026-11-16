/* SPDX-License-Identifier: Apache-2.0 */
#ifndef LAB_VOICE_SERVICE_H
#define LAB_VOICE_SERVICE_H
#include "audio_service.h"
/* Single OS actor; static caller-owned scratch, never guest memory. No I/O,
 * allocation or model download until an explicit audio request. */
typedef struct {
    _Alignas(8) uint8_t workspace[5680];
    float features[260];
    int32_t logits[7];
} LabVoice;
/* CLASSIFY consumes exactly one completed 2-second microphone recording;
 * result -1 unavailable, 0..4 command, 5 unknown, 6 silence. Raw PCM and
 * feature scratch are scrubbed before return. REPLY 0..4 uses speaker only,
 * returns -1 invalid/unavailable, 0 busy/failure, 1 accepted. */
int lab_voice_call(void *,LabAudio *,uint32_t owner,uint32_t op,uint32_t value,uint32_t now);
#endif
