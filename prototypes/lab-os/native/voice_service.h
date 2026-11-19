/* SPDX-License-Identifier: Apache-2.0 */
#ifndef LAB_VOICE_SERVICE_H
#define LAB_VOICE_SERVICE_H
#include "audio_service.h"
#include "voice_model_config.h"
#include <stddef.h>
/* Single OS actor; static caller-owned scratch, never guest memory. No I/O,
 * allocation or model download until an explicit audio request. */
typedef struct {uint32_t top1,top2;int32_t first,second;uint32_t margin;} LabVoiceScores;
int lab_voice_rank(const int32_t *,size_t,LabVoiceScores *);
uint32_t lab_voice_rejection_threshold(uint32_t top_class);
#if !LAB_VOICE_CONTEXT_DURATION && !LAB_VOICE_LOGMEL
uint32_t pet_rejection_threshold(void); /* Legacy global-threshold helper only. */
#endif
typedef struct {
    _Alignas(8) uint8_t workspace[LAB_VOICE_WORKSPACE_BYTES];
    float features[LAB_VOICE_FEATURE_COUNT];
    int32_t logits[7];
    uint32_t observed_owner,observed_generation,observed[16];
    LabVoiceScores scores;bool scores_valid;
} LabVoice;
/* CLASSIFY consumes exactly one completed 2-second microphone recording;
 * applies fixed HP160/centering/peak4096 and the selected frozen frontend;
 * result -1 unavailable, 0..4 command, 5 unknown, 6 silence. Raw PCM and
 * feature scratch are scrubbed before return. REPLY 0..4 uses speaker only,
 * returns -1 invalid/unavailable, 0 busy/failure, 1 accepted.
 * Trusted SNAPSHOT 0 reports availability; 1..16 return sequence/result/errors,
 * frames/min/max/mean/rms/ac/peak/saturation, first/last1024 means, features_ok,
 * model_revision and observed_at_ms; 17 is lease_generation. No PCM/features
 * leave through this interface. Owner/lease and microphone permission gate it.
 * Trusted SCORES: 0 available, 1..11 sequence/result/top1/top2/first/second/
 * margin/threshold/model_revision/observed_at_ms/lease_generation. Only a
 * successful classification is available; failed attempts clear old scores. */
int lab_voice_call(void *,LabAudio *,uint32_t owner,uint32_t op,uint32_t value,uint32_t now);
#endif
