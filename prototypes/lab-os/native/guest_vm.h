#ifndef LAB_GUEST_VM_H
#define LAB_GUEST_VM_H
#include <stdbool.h>
#include <stdint.h>
#include "wasm_export.h"

enum {LAB_VM_CAP_DRAW=1,LAB_VM_CAP_SPEAKER=2,LAB_VM_CAP_MICROPHONE=4,LAB_VM_CAP_NETWORK=8,LAB_VM_CAP_STORAGE=16,LAB_VM_CAP_ALL=31};
enum {LAB_VM_AUDIO_TONE=1,LAB_VM_AUDIO_RECORD,LAB_VM_AUDIO_PLAY,LAB_VM_AUDIO_STATE,LAB_VM_AUDIO_LEVEL,LAB_VM_AUDIO_STOP,LAB_VM_AUDIO_POSITION,LAB_VM_AUDIO_SET_GAIN};
/* Borrowed trusted binding, not guest memory. Caller closes VM before releasing
 * this lease; failed external cleanup must retain it and block the next app. */
typedef struct {void *context;int (*call)(void *,uint32_t op,uint32_t a,uint32_t b);} LabVmAudio;
enum {LAB_VM_NETWORK_SEND=1,LAB_VM_NETWORK_RECEIVE,LAB_VM_NETWORK_STATE};
/* Borrowed trusted lease. Bytes point to a VM-owned temporary copy (<=64B),
 * never guest memory. No retaining the pointer or VM/service reentry. STATE has NULL/zero bytes.
 * Return SEND -1..1, RECEIVE -1..capacity, STATE -1..3. */
typedef struct {void *context;int (*call)(void *,uint32_t op,uint8_t *,uint32_t);} LabVmNetwork;

enum {LAB_VM_STATE_READ=1,LAB_VM_STATE_WRITE=2};
/* Borrowed app-bound lease. No guest path/id/pointer. READ returns -1 error,
 * 0 missing, 1 found; WRITE -1 error, 0 busy, 1 durable. */
typedef struct {void *context;int (*call)(void *,uint32_t op,uint32_t slot,int32_t *value);} LabVmState;

typedef struct {
    wasm_module_t module;
    wasm_module_inst_t instance;
    wasm_exec_env_t env;
    wasm_function_inst_t tick;
    uint32_t held, budget, draw_count;
    bool allow_draw;
    uint32_t capabilities,audio_mutations,audio_queries;
    LabVmAudio audio;
    LabVmNetwork network;
    uint32_t network_mutations,network_queries;
    bool network_memory;
    LabVmState state;
    uint32_t state_queries,state_mutations;
    int32_t state_result;
    int32_t draws[128][5];
    char error[160];
} LabVm;

bool lab_runtime_init(void *pool, uint32_t bytes);
void lab_runtime_destroy(void);
bool lab_vm_open(LabVm *vm, uint8_t *bytes, uint32_t size, uint32_t pages,
                 uint32_t budget, bool allow_draw);
bool lab_vm_open_with_audio(LabVm *,uint8_t *,uint32_t size,uint32_t pages,
                            uint32_t budget,uint32_t capabilities,const LabVmAudio *);
bool lab_vm_open_with_services(LabVm *,uint8_t *,uint32_t,uint32_t,uint32_t,uint32_t,
                              const LabVmAudio *,const LabVmNetwork *);
bool lab_vm_open_with_all_services(LabVm *,uint8_t *,uint32_t,uint32_t,uint32_t,uint32_t,
                                  const LabVmAudio *,const LabVmNetwork *,const LabVmState *);
/* 戻り値: -1 trap/closed、0 running、1 normal exit。 */
int lab_vm_frame(LabVm *vm, uint32_t held, uint32_t dt);
int32_t lab_vm_debug(LabVm *vm, const char *name);
void lab_vm_close(LabVm *vm, uint32_t reason);
#endif
