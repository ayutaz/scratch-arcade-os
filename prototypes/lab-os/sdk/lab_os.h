#ifndef LAB_OS_ABI2_H
#define LAB_OS_ABI2_H
#include <stdint.h>
#define LAB_ABI 2
#define RIGHT 1u
#define LEFT 2u
#define DOWN 4u
#define UP 8u
#define START 16u
#define RESET 32u
#define BACK 64u
__attribute__((import_module("os"),import_name("rect")))
void rect(int32_t x,int32_t y,int32_t w,int32_t h,int32_t color);
/* Optional audio imports require matching capability-aware firmware and a
 * trusted OS audio lease. Initial/pthread-only firmware rejects audio packages.
 * Requests: 1 accepted, 0 not accepted/busy, -1 invalid/unavailable.
 * Tone 200..4000Hz/20..1000ms; record 1..2000ms. No raw PCM access.
 * Per init/frame: <=2 mutations, <=8 state/level queries; excess traps. */
__attribute__((import_module("os"),import_name("audio_tone")))
int32_t audio_tone(int32_t hz,int32_t ms);
__attribute__((import_module("os"),import_name("audio_record")))
int32_t audio_record(int32_t ms);
__attribute__((import_module("os"),import_name("audio_play")))
int32_t audio_play(void);
/* -1 error/unavailable, 0 idle, 1 playing, 2 recording, 3 draining, 4 closing. */
__attribute__((import_module("os"),import_name("audio_state")))
int32_t audio_state(void);
/* Latest <=256 captured samples' absolute peak (0..32768), -1 unavailable. */
__attribute__((import_module("os"),import_name("audio_level")))
int32_t audio_level(void);
__attribute__((import_module("os"),import_name("audio_stop")))
int32_t audio_stop(void);
/* Serviced PCM frames for this lease's latest operation: 0..32000, -1
 * unavailable. Shared <=8-query budget with state/level. No PCM is exported.
 * Resets on a newly accepted operation/stop/lease release; does not prove
 * audible output, DMA continuity or recording quality. Requires new firmware:
 * f6fc and earlier reject packages importing audio_position. */
__attribute__((import_module("os"),import_name("audio_position")))
int32_t audio_position(void);
/* Replay-only desired integer gain 0..8 (0 mute, 1 unity). Speaker permission,
 * idle state required; shared <=2-mutation budget. Returns 1 accepted,
 * 0 busy, -1 invalid/unavailable. Output ceiling remains +/-3277 PCM16,
 * 5ms fade; the next quality firmware removes DC and linearly attenuates
 * overly large input instead of flat clipping. Tone/capture/original PCM are
 * unchanged. New lease and
 * audio_stop reset gain to 1. Requires firmware newer than 778e. */
__attribute__((import_module("os"),import_name("audio_set_gain")))
int32_t audio_set_gain(int32_t gain);
/* Optional fixed Japanese command service. Requires newer voice firmware;
 * older ABI2 firmware rejects these imports. Each is a mutation, sharing the
 * <=2/frame audio budget. classify requires microphone and consumes one idle,
 * completed 2000ms recording: -1 unavailable, 0 play, 1 come, 2 wait, 3 sleep,
 * 4 thanks, 5 unknown, 6 silence. PCM is erased before return, never exported.
 * Fixed native work is bounded, but S3 latency still requires device testing.
 * reply requires speaker: id0..4, -1 invalid/unavailable, 0 busy, 1 accepted.
 * Replies are pre-synthesized clips, not free-form on-device TTS. */
__attribute__((import_module("os"),import_name("audio_classify")))
int32_t audio_classify(void);
__attribute__((import_module("os"),import_name("audio_reply")))
int32_t audio_reply(int32_t id);
/* Optional network capability and OS-provided UDP lease. Caller memory must
 * be exported as "memory". Route/SSID/password are never guest arguments.
 * 1..64 bytes, <=2 send/receive operations and <=8 state queries per frame.
 * send: 1 queued, 0 backpressure, -1 invalid/unavailable. receive: 0 empty,
 * 1..capacity bytes, -1 invalid/unavailable/short destination (packet retained).
 * state: -1 unavailable, 0 idle, 1 active, 2 failed, 3 closing.
 * Old/pthread-only firmware rejects network packages. No delivery guarantee. */
__attribute__((import_module("os"),import_name("network_send")))
int32_t network_send(const uint8_t *bytes,int32_t size);
__attribute__((import_module("os"),import_name("network_receive")))
int32_t network_receive(uint8_t *bytes,int32_t capacity);
__attribute__((import_module("os"),import_name("network_state")))
int32_t network_state(void);
/* Optional storage permission; requires the new storage-enabled firmware.
 * OS binds the lease to the current app id. No filenames/pointers/other app ids.
 * Eight signed int32 slots; read returns fallback if missing/error, status
 * distinguishes -1 unavailable/error, 0 missing/busy, 1 found/durably saved.
 * write returns -1/0/1; unchanged value succeeds without I/O. Changed writes
 * may return busy within 1000ms of the previous commit in this lease.
 * Per init/frame <=8 read/status calls and <=1 write; excess traps. */
__attribute__((import_module("os"),import_name("state_read")))
int32_t state_read(int32_t slot,int32_t fallback);
__attribute__((import_module("os"),import_name("state_write")))
int32_t state_write(int32_t slot,int32_t value);
__attribute__((import_module("os"),import_name("state_status")))
int32_t state_status(void);
uint32_t sdk_abi(void);
void init(void);
/* 0=continue, 1=normal exit. dt is elapsed monotonic milliseconds (0..60000). */
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt);
void shutdown(uint32_t reason);
#endif
