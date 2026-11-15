#ifndef LAB_AUDIO_BINDING_H
#define LAB_AUDIO_BINDING_H
#include "guest_vm.h"
#include "audio_service.h"
#include "app_home.h"
typedef struct {LabAudio *audio;uint32_t owner,permissions,now;} LabAudioBinding;
/* Trusted OS manager owns this lease. Fresh zeroed binding. Open before VM,
 * update/poll on the OS clock, close VM before binding. A false close retains
 * the binding/driver; retry before reusing it or the PCM buffer. No VM owns or
 * frees this object. Do not rebind it while an old VM still borrows callbacks. */
bool lab_audio_binding_open(LabAudioBinding *,LabAudio *,uint32_t owner,uint32_t vm_caps,uint32_t now);
bool lab_audio_binding_close(LabAudioBinding *);
int lab_audio_binding_poll(LabAudioBinding *,uint32_t now);
int lab_audio_binding_call(LabAudioBinding *,uint32_t op,uint32_t a,uint32_t b);
LabVmAudio lab_audio_binding_services(LabAudioBinding *);
typedef struct {LabAudio *audio;LabAudioBinding binding;uint32_t next_owner,now;} LabAudioManager;
bool lab_audio_manager_init(LabAudioManager *,LabAudio *);
LabHomeAudio lab_audio_manager_services(LabAudioManager *);
#endif
