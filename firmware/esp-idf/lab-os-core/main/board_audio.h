#ifndef LAB_BOARD_AUDIO_H
#define LAB_BOARD_AUDIO_H
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include "driver/i2s_common.h"
#include "audio_service.h"
enum {LAB_AUDIO_PROFILE_UNKNOWN=0,LAB_AUDIO_PROFILE_STOCK_0111=1};
enum {LAB_AUDIO_OUTPUT=1,LAB_AUDIO_INPUT=2,LAB_AUDIO_MAX_FRAMES=256};
typedef struct {
    i2s_chan_handle_t channel;
    int mode;
    bool enabled,ready,pending;
    atomic_uint sent;
    uint32_t drain_after;
    uint32_t priming_remaining,discarded_input_frames;
} LabBoardAudio;
/* Fresh zeroed object, exclusive OS task. Fixed stock-derived pins, no caller
 * GPIOs. Sequential TX/RX only, 16kHz signed PCM16 mono. No automatic startup.
 * New-IDF slot/clock/DMA defaults are proposals, not stock timing measurements.
 * close(false) retains failed ownership for retry; do not free the object.
 * I/O uses timeout=0 and at most 256 frames; returns frames, 0 backpressure,
 * -1 invalid/error. A valid partial TIMEOUT is not a fatal error. Fatal I/O
 * stops further I/O until close. RX clears unused/error output, never exports
 * audio. TX acceptance means queued bytes, not audible playback completion.
 * drained() waits for five full DMA completions after the last accepted write
 * (four descriptors plus a margin), without blocking. It does not prove audible
 * output; poll with a bounded service deadline. close cancels immediately. */
bool lab_board_audio_open(LabBoardAudio *,int profile,int mode);
bool lab_board_audio_close(LabBoardAudio *);
int lab_board_audio_drained(LabBoardAudio *);
/* Trusted manager adapter; no automatic claim/open or guest ABI exposure.
 * Each explicit RX start primes 1600 frames (100ms at 16kHz) incrementally.
 * Priming samples are scrubbed, not returned or counted as the recording. */
LabAudioIo lab_board_audio_services(LabBoardAudio *);
int lab_board_audio_write(LabBoardAudio *,const int16_t *,uint32_t frames);
int lab_board_audio_read(LabBoardAudio *,int16_t *,uint32_t frames);
#endif
