#ifndef LAB_BOARD_SOUND_H
#define LAB_BOARD_SOUND_H
#include "board_audio.h"
#include "audio_binding.h"
typedef struct {
    LabBoardAudio driver;
    LabAudio audio;
    LabAudioManager manager;
    LabAudioPcm pcm;
    uint32_t frames,now,epoch;
    int profile;
    bool configured;
    void *voice_context;
    int (*voice_call)(void *,LabAudio *,uint32_t,uint32_t,uint32_t,uint32_t);
} LabBoardSound;
/* Fresh zeroed single-actor object. Init/factory perform no allocation/GPIO I/O.
 * Home callbacks lazily allocate 32KB output-only / 64KB input, in <=8KiB internal banks.
 * Close VM first. False close retains PCM/driver ownership; retry before reuse.
 * Successful app close preserves configuration; closed init is idempotent.
 * Pin/slot/timing and voice fidelity still require physical validation. */
bool lab_board_sound_init(LabBoardSound *,int profile);
LabHomeAudio lab_board_sound_services(LabBoardSound *);
/* Optional trusted callback, configured only while closed; no guest paths. */
bool lab_board_sound_set_voice(LabBoardSound *,void *,int (*)(void *,LabAudio *,uint32_t,uint32_t,uint32_t,uint32_t));
bool lab_board_sound_close(LabBoardSound *);
#endif
