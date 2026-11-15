#ifndef LAB_AUDIO_SERVICE_H
#define LAB_AUDIO_SERVICE_H
#include <stdbool.h>
#include <stdint.h>
enum {LAB_AUDIO_CAN_PLAY=1,LAB_AUDIO_CAN_RECORD=2};
enum {LAB_AUDIO_IDLE=0,LAB_AUDIO_PLAYING,LAB_AUDIO_RECORDING,LAB_AUDIO_DRAINING,LAB_AUDIO_CLOSING};
enum {LAB_AUDIO_BANK_FRAMES=4096,LAB_AUDIO_BANKS=8};
typedef struct {int16_t *banks[LAB_AUDIO_BANKS];uint32_t frames;} LabAudioPcm;
typedef struct {
    uint32_t frames;
    int32_t minimum,maximum,mean;
    uint32_t rms,ac_rms,centered_peak,saturated_frames;
} LabAudioRecordingMetrics;
typedef struct {
    void *context;
    int (*open)(void *,int mode); /* 1 output, 2 input; exactly 1 means success. */
    int (*read)(void *,int16_t *,uint32_t frames);
    int (*write)(void *,const int16_t *,uint32_t frames);
    int (*drained)(void *); /* 1 completed, 0 pending, -1 error. */
    int (*close)(void *);   /* 1 released, 0 retains ownership. */
} LabAudioIo;
typedef struct {
    LabAudioIo io;
    int16_t *buffer;
    int16_t *banks[LAB_AUDIO_BANKS];
    uint32_t capacity,owner,permissions,recorded,total,position,phase,started,limit_ms,kind,replay_gain;
    int32_t replay_mean;
    uint32_t replay_scale_q15;
    int result,outcome;
    int16_t output[256];
    bool ready,driver_owned,replaying;
} LabAudio;
/* Fresh zeroed object, single OS actor, exclusive buffer, 1..32000 PCM16 frames.
 * No heap, file/network writes or implicit recording. init does no device I/O.
 * Trusted app manager grants owner/capabilities; these are not guest-settable.
 * release cancels/scrubs; false keeps owner until release is retried. Poll may
 * retry retained cleanup once per call. Revoke permissions immediately on exit.
 * At most one <=256-frame read/write per poll, timeout/drain handled by adapter.
 * record <=2s, tone <=1s with fixed <=2048 peak and 5ms fades.
 * Replay removes the recording mean, applies desired gain 0..8 with linear
 * attenuation to the <=3277 ceiling, and fades a separate chunk. Original PCM
 * is preserved. New lease defaults to gain 1. Tone is unchanged.
 * I/O write must copy synchronously before returning. DMA completion is
 * not a human listening test. poll returns -1 failure, 0 pending, 1 completed.
 * Host contracts are not target timing, audio fidelity or VM API validation. */
bool lab_audio_init(LabAudio *,const LabAudioIo *,int16_t *buffer,uint32_t frames);
/* Trusted immutable bank layout, <=8192 bytes per allocation, same total limit.
 * Descriptor is copied; backing memory stays owned by the caller until release. */
bool lab_audio_init_banked(LabAudio *,const LabAudioIo *,const LabAudioPcm *);
/* Last <=256 captured frames only; no PCM escapes through this metric. */
int lab_audio_peak(const LabAudio *);
bool lab_audio_claim(LabAudio *,uint32_t owner,uint32_t permissions);
bool lab_audio_release(LabAudio *,uint32_t owner);
bool lab_audio_tone(LabAudio *,uint32_t owner,uint32_t hz,uint32_t ms,uint32_t now);
bool lab_audio_record(LabAudio *,uint32_t owner,uint32_t ms,uint32_t now);
bool lab_audio_play_recording(LabAudio *,uint32_t owner,uint32_t now);
/* Speaker permission, same owner and idle/released driver only. No I/O. */
bool lab_audio_set_gain(LabAudio *,uint32_t owner,uint32_t gain);
/* Idle, completed recording and current microphone lease only. One bounded
 * scan <=32000 frames, no allocation/I/O/PCM export. Failure zeroes out. */
bool lab_audio_recording_metrics(const LabAudio *,uint32_t owner,LabAudioRecordingMetrics *out);
/* Optional host diagnosis: first/second half amplitudes at 1320/1760Hz.
 * Same idle/lease gate, fixed four bins only, no PCM export. */
bool lab_audio_recording_bands(const LabAudio *,uint32_t owner,uint32_t out[4]);
int lab_audio_poll(LabAudio *,uint32_t now);
#endif
