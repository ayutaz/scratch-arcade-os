/* ABI 2 bridge shared by the host probe and the non-flashing S3 build. */
#include "guest_vm.h"
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static void rect(wasm_exec_env_t env, int32_t x, int32_t y, int32_t w,
                 int32_t h, int32_t color) {
    wasm_module_inst_t inst = wasm_runtime_get_module_inst(env);
    LabVm *vm = wasm_runtime_get_custom_data(inst);
    if (!vm || !vm->allow_draw || vm->draw_count >= 128 || x < 0 || y < 0 ||
        x >= 320 || y >= 240 || w < 1 || h < 1 || w > 320 - x || h > 240 - y ||
        color < 0 || color > 65535) {
        wasm_runtime_set_exception(inst, "draw permission/quota/bounds");
        return;
    }
    int32_t command[5] = {x, y, w, h, color};
    memcpy(vm->draws[vm->draw_count++], command, sizeof(command));
}

static int32_t audio_call(wasm_exec_env_t env,uint32_t op,int32_t a,int32_t b) {
    wasm_module_inst_t instance=wasm_runtime_get_module_inst(env);
    LabVm *vm=wasm_runtime_get_custom_data(instance);
    uint32_t required=op==LAB_VM_AUDIO_TONE || op==LAB_VM_AUDIO_PLAY || op==LAB_VM_AUDIO_SET_GAIN || op==LAB_VM_AUDIO_REPLY ? LAB_VM_CAP_SPEAKER :
        op==LAB_VM_AUDIO_RECORD || op==LAB_VM_AUDIO_LEVEL || op==LAB_VM_AUDIO_CLASSIFY ? LAB_VM_CAP_MICROPHONE : 6;
    if(!vm || !(vm->capabilities&required)) {
        wasm_runtime_set_exception(instance,"audio permission");return -1;
    }
    bool query=op==LAB_VM_AUDIO_STATE || op==LAB_VM_AUDIO_LEVEL || op==LAB_VM_AUDIO_POSITION;
    if((query && ++vm->audio_queries>8) || (!query && ++vm->audio_mutations>2)) {
        wasm_runtime_set_exception(instance,"audio per-frame quota");return -1;
    }
    if((op==LAB_VM_AUDIO_TONE && (a<200 || a>4000 || b<20 || b>1000)) ||
       (op==LAB_VM_AUDIO_RECORD && (a<1 || a>2000)) ||
       (op==LAB_VM_AUDIO_SET_GAIN && (a<0 || a>8)) ||
       (op==LAB_VM_AUDIO_REPLY && (a<0 || a>4)))return -1;
    if(!vm->audio.call)return -1;
    int value=vm->audio.call(vm->audio.context,op,(uint32_t)a,(uint32_t)b);
    int maximum=op==LAB_VM_AUDIO_CLASSIFY ? 6 : op==LAB_VM_AUDIO_STATE ? 4 : op==LAB_VM_AUDIO_LEVEL ? 32768 : op==LAB_VM_AUDIO_POSITION ? 32000 : 1;
    if(value< -1 || value>maximum) {
        wasm_runtime_set_exception(instance,"audio service contract");return -1;
    }
    return value;
}
static int32_t audio_tone(wasm_exec_env_t e,int32_t hz,int32_t ms) {return audio_call(e,LAB_VM_AUDIO_TONE,hz,ms);}
static int32_t audio_record(wasm_exec_env_t e,int32_t ms) {return audio_call(e,LAB_VM_AUDIO_RECORD,ms,0);}
static int32_t audio_play(wasm_exec_env_t e) {return audio_call(e,LAB_VM_AUDIO_PLAY,0,0);}
static int32_t audio_state(wasm_exec_env_t e) {return audio_call(e,LAB_VM_AUDIO_STATE,0,0);}
static int32_t audio_level(wasm_exec_env_t e) {return audio_call(e,LAB_VM_AUDIO_LEVEL,0,0);}
static int32_t audio_stop(wasm_exec_env_t e) {return audio_call(e,LAB_VM_AUDIO_STOP,0,0);}
static int32_t audio_position(wasm_exec_env_t e) {return audio_call(e,LAB_VM_AUDIO_POSITION,0,0);}
static int32_t audio_classify(wasm_exec_env_t e) {return audio_call(e,LAB_VM_AUDIO_CLASSIFY,0,0);}
static int32_t audio_reply(wasm_exec_env_t e,int32_t id) {return audio_call(e,LAB_VM_AUDIO_REPLY,id,0);}
static int32_t audio_set_gain(wasm_exec_env_t e,int32_t gain) {return audio_call(e,LAB_VM_AUDIO_SET_GAIN,gain,0);}

static void wipe(void *ptr,uint32_t n) {volatile uint8_t *p=ptr;while(n--)*p++=0;}
static int32_t network_call(wasm_exec_env_t env,uint32_t op,int32_t address,int32_t length) {
    wasm_module_inst_t instance=wasm_runtime_get_module_inst(env);
    LabVm *vm=wasm_runtime_get_custom_data(instance);
    if(!vm || !(vm->capabilities&LAB_VM_CAP_NETWORK)) {
        wasm_runtime_set_exception(instance,"network permission");return -1;
    }
    bool query=op==LAB_VM_NETWORK_STATE;
    if((query && ++vm->network_queries>8) || (!query && ++vm->network_mutations>2)) {
        wasm_runtime_set_exception(instance,"network per-frame quota");return -1;
    }
    uint8_t *guest=NULL;
    if(!query) {
        if(length<1 || length>64)return -1;
        wasm_memory_inst_t memory=wasm_runtime_lookup_memory(instance,"memory");
        if(!vm->network_memory || !memory || memory!=wasm_runtime_get_default_memory(instance) ||
           !wasm_runtime_validate_app_addr(instance,(uint32_t)address,(uint32_t)length) ||
           !(guest=wasm_runtime_addr_app_to_native(instance,(uint32_t)address))) {
            wasm_runtime_set_exception(instance,"network memory bounds/export");return -1;
        }
    }
    if(!vm->network.call)return -1;
    uint8_t bytes[64]={0};
    if(op==LAB_VM_NETWORK_SEND)memcpy(bytes,guest,(uint32_t)length);
    int result=vm->network.call(vm->network.context,op,query ? NULL:bytes,query ? 0:(uint32_t)length);
    int maximum=query ? 3 : op==LAB_VM_NETWORK_SEND ? 1:length;
    bool valid=result>= -1 && result<=maximum;
    if(valid && op==LAB_VM_NETWORK_RECEIVE && result>0)memcpy(guest,bytes,(uint32_t)result);
    wipe(bytes,sizeof(bytes));
    if(!valid) {wasm_runtime_set_exception(instance,"network service contract");return -1;}
    return result;
}
static int32_t network_send(wasm_exec_env_t e,int32_t p,int32_t n) {return network_call(e,LAB_VM_NETWORK_SEND,p,n);}
static int32_t network_receive(wasm_exec_env_t e,int32_t p,int32_t n) {return network_call(e,LAB_VM_NETWORK_RECEIVE,p,n);}
static int32_t network_state(wasm_exec_env_t e) {return network_call(e,LAB_VM_NETWORK_STATE,0,0);}

static int32_t state_call(wasm_exec_env_t env,uint32_t op,int32_t slot,int32_t value) {
    wasm_module_inst_t instance=wasm_runtime_get_module_inst(env);
    LabVm *vm=wasm_runtime_get_custom_data(instance);
    if(!vm || !(vm->capabilities&LAB_VM_CAP_STORAGE)) {
        wasm_runtime_set_exception(instance,"storage permission");return -1;
    }
    bool query=op!=LAB_VM_STATE_WRITE;
    if((query && ++vm->state_queries>8) || (!query && ++vm->state_mutations>1)) {
        wasm_runtime_set_exception(instance,"storage per-frame quota");return -1;
    }
    if(!op)return vm->state_result;
    int32_t fallback=value;
    int result=-1;
    if(slot>=0 && slot<8 && vm->state.call)
        result=vm->state.call(vm->state.context,op,(uint32_t)slot,&value);
    if(result< -1 || result>1) {
        wasm_runtime_set_exception(instance,"storage service contract");return -1;
    }
    vm->state_result=result;
    return op==LAB_VM_STATE_READ ? (result==1 ? value:fallback) : result;
}
static int32_t state_read(wasm_exec_env_t e,int32_t slot,int32_t fallback) {return state_call(e,LAB_VM_STATE_READ,slot,fallback);}
static int32_t state_write(wasm_exec_env_t e,int32_t slot,int32_t value) {return state_call(e,LAB_VM_STATE_WRITE,slot,value);}
static int32_t state_status(wasm_exec_env_t e) {return state_call(e,0,0,0);}

bool lab_runtime_init(void *pool, uint32_t bytes) {
    RuntimeInitArgs args = {0};
    args.mem_alloc_type = Alloc_With_Pool;
    args.mem_alloc_option.pool.heap_buf = pool;
    args.mem_alloc_option.pool.heap_size = bytes;
    if (!wasm_runtime_full_init(&args)) return false;
    static NativeSymbol symbols[] = {
        {"rect",rect,"(iiiii)",NULL}, {"audio_tone",audio_tone,"(ii)i",NULL},
        {"audio_record",audio_record,"(i)i",NULL}, {"audio_play",audio_play,"()i",NULL},
        {"audio_state",audio_state,"()i",NULL}, {"audio_level",audio_level,"()i",NULL},
        {"audio_stop",audio_stop,"()i",NULL},
        {"audio_position",audio_position,"()i",NULL},
        {"audio_set_gain",audio_set_gain,"(i)i",NULL},
        {"audio_classify",audio_classify,"()i",NULL},{"audio_reply",audio_reply,"(i)i",NULL},
        {"network_send",network_send,"(ii)i",NULL},{"network_receive",network_receive,"(ii)i",NULL},
        {"network_state",network_state,"()i",NULL},
        {"state_read",state_read,"(ii)i",NULL},{"state_write",state_write,"(ii)i",NULL},
        {"state_status",state_status,"()i",NULL}};
    if (!wasm_runtime_register_natives("os", symbols, sizeof(symbols)/sizeof(*symbols))) {
        wasm_runtime_destroy();
        return false;
    }
    return true;
}

void lab_runtime_destroy(void) { wasm_runtime_destroy(); }

static bool uleb(const uint8_t **cursor, const uint8_t *end, uint32_t *out) {
    uint32_t result = 0;
    for (unsigned shift = 0; shift <= 28; shift += 7) {
        if (*cursor >= end) return false;
        uint8_t byte = *(*cursor)++;
        if (shift == 28 && (byte & 0xf0)) return false;
        result |= (uint32_t)(byte & 127) << shift;
        if (!(byte & 128)) { *out = result; return true; }
    }
    return false;
}

static bool allowed_export(const uint8_t *name, uint32_t length) {
    static const char *names[] = {"sdk_abi", "init", "tick", "shutdown", "memory",
        "debug_value", "debug_x", "debug_y", "debug_elapsed"};
    for (unsigned i = 0; i < sizeof(names) / sizeof(*names); ++i)
        if (strlen(names[i]) == length && !memcmp(name, names[i], length)) return true;
    return false;
}

/* WAMR runs start/constructor hooks during instantiation, before our metered
 * exec_env exists. Reject them before calling the loader/instantiator. */
static bool format_gate(const uint8_t *data, uint32_t size,bool *exported_memory) {
    static const uint8_t magic[8] = {0, 97, 115, 109, 1, 0, 0, 0};
    if (size < 8 || size > 262144 || memcmp(data, magic, 8)) return false;
    const uint8_t *p = data + 8, *end = data + size;
    while (p < end) {
        uint8_t id = *p++;
        uint32_t n;
        if (!uleb(&p, end, &n) || n > (uint32_t)(end - p) || id == 8) return false;
        const uint8_t *section_end = p + n;
        if (id == 7) {
            uint32_t count;
            if (!uleb(&p, section_end, &count) || count > 128) return false;
            for (uint32_t i = 0; i < count; ++i) {
                uint32_t len, index;
                if (!uleb(&p, section_end, &len) || len > (uint32_t)(section_end - p) ||
                    !allowed_export(p, len)) return false;
                const uint8_t *name=p;
                p += len;
                if (p == section_end) return false;
                uint8_t kind=*p++; /* Other kinds are validated by WAMR. */
                if (!uleb(&p, section_end, &index)) return false;
                if(kind==2 && index==0 && len==6 && !memcmp(name,"memory",6))*exported_memory=true;
            }
            if (p != section_end) return false;
        }
        p = section_end;
    }
    return p == end;
}

static wasm_function_inst_t function(LabVm *vm, const char *name,
                                    uint32_t params, uint32_t results) {
    wasm_function_inst_t fn = wasm_runtime_lookup_function(vm->instance, name);
    if (!fn || wasm_func_get_param_count(fn, vm->instance) != params ||
        wasm_func_get_result_count(fn, vm->instance) != results) return NULL;
    wasm_valkind_t types[4] = {0};
    wasm_func_get_param_types(fn, vm->instance, types);
    for (uint32_t i = 0; i < params; ++i) if (types[i] != WASM_I32) return NULL;
    wasm_func_get_result_types(fn, vm->instance, types);
    for (uint32_t i = 0; i < results; ++i) if (types[i] != WASM_I32) return NULL;
    return fn;
}

static bool call(LabVm *vm, wasm_function_inst_t fn, uint32_t argc, uint32_t *args,
                 uint32_t budget) {
    if (!fn) { snprintf(vm->error, sizeof(vm->error), "ABI signature"); return false; }
    wasm_runtime_clear_exception(vm->instance);
    wasm_runtime_set_instruction_count_limit(vm->env, (int)budget);
    bool ok = wasm_runtime_call_wasm(vm->env, fn, argc, args);
    if (!ok) {
        const char *message = wasm_runtime_get_exception(vm->instance);
        snprintf(vm->error, sizeof(vm->error), "%s", message ? message : "guest trap");
    }
    return ok;
}

bool lab_vm_open_with_all_services(LabVm *vm,uint8_t *bytes,uint32_t size,uint32_t pages,
                            uint32_t budget,uint32_t capabilities,const LabVmAudio *audio,const LabVmNetwork *network,const LabVmState *state) {
    memset(vm, 0, sizeof(*vm));
    if (capabilities>LAB_VM_CAP_ALL || (audio && !audio->call) || (network && !network->call) || (state && !state->call) || pages < 1 || pages > 16 || budget < 100 || budget > 1000000 || !format_gate(bytes, size,&vm->network_memory)) {
        snprintf(vm->error, sizeof(vm->error), "package policy"); return false;
    }
    vm->budget = budget;
    vm->capabilities=capabilities;
    vm->allow_draw=(capabilities&LAB_VM_CAP_DRAW)!=0;
    if(audio)vm->audio=*audio;
    if(network)vm->network=*network;
    if(state)vm->state=*state;
    vm->state_result=state ? 0:-1;
    vm->module = wasm_runtime_load(bytes, size, vm->error, sizeof(vm->error));
    if (!vm->module) return false;
    struct InstantiationArgs2 *args = NULL;
    if (!wasm_runtime_instantiation_args_create(&args)) goto fail;
    wasm_runtime_instantiation_args_set_default_stack_size(args, 8192);
    wasm_runtime_instantiation_args_set_host_managed_heap_size(args, 0);
    wasm_runtime_instantiation_args_set_max_memory_pages(args, pages);
    vm->instance = wasm_runtime_instantiate_ex2(vm->module, args, vm->error, sizeof(vm->error));
    wasm_runtime_instantiation_args_destroy(args);
    if (!vm->instance) goto fail;
    wasm_runtime_set_custom_data(vm->instance, vm);
    vm->env = wasm_runtime_create_exec_env(vm->instance, 8192);
    if (!vm->env) goto fail;
    uint32_t value = 0;
    if (!call(vm, function(vm, "sdk_abi", 0, 1), 0, &value, budget) || value != 2 ||
        !call(vm, function(vm, "init", 0, 0), 0, &value, budget)) goto fail;
    vm->tick = function(vm, "tick", 4, 1);
    if (!vm->tick) goto fail;
    return true;
fail:
    lab_vm_close(vm, 2);
    return false;
}

bool lab_vm_open_with_services(LabVm *vm,uint8_t *bytes,uint32_t size,uint32_t pages,
                            uint32_t budget,uint32_t capabilities,const LabVmAudio *audio,const LabVmNetwork *network) {
    return lab_vm_open_with_all_services(vm,bytes,size,pages,budget,capabilities,audio,network,NULL);
}

bool lab_vm_open_with_audio(LabVm *vm,uint8_t *bytes,uint32_t size,uint32_t pages,
                            uint32_t budget,uint32_t capabilities,const LabVmAudio *audio) {
    return lab_vm_open_with_services(vm,bytes,size,pages,budget,capabilities,audio,NULL);
}
bool lab_vm_open(LabVm *vm,uint8_t *bytes,uint32_t size,uint32_t pages,uint32_t budget,bool allow_draw) {
    return lab_vm_open_with_audio(vm,bytes,size,pages,budget,allow_draw ? LAB_VM_CAP_DRAW : 0,NULL);
}

int lab_vm_frame(LabVm *vm, uint32_t held, uint32_t dt) {
    if (!vm->instance || !vm->tick) return -1;
    vm->draw_count = 0;
    vm->audio_mutations=vm->audio_queries=0;
    vm->network_mutations=vm->network_queries=0;
    vm->state_mutations=vm->state_queries=0;
    if (held > 255 || dt > 60000) { lab_vm_close(vm, 2); return -1; }
    uint32_t args[4] = {held, held & ~vm->held, vm->held & ~held, dt};
    vm->held = held;
    if (!call(vm, vm->tick, 4, args, vm->budget) || args[0] > 1) {
        lab_vm_close(vm, 2); return -1;
    }
    if (args[0]) { lab_vm_close(vm, 0); return 1; }
    return 0;
}

int32_t lab_vm_debug(LabVm *vm, const char *name) {
    if (!vm->instance || !vm->env) return -1;
    uint32_t value = 0;
    return call(vm, function(vm, name, 0, 1), 0, &value, vm->budget) ? (int32_t)value : -1;
}

void lab_vm_close(LabVm *vm, uint32_t reason) {
    if (vm->instance && vm->env && reason != 2) {
        wasm_function_inst_t fn = function(vm, "shutdown", 1, 0);
        if (fn) (void)call(vm, fn, 1, &reason, 1000);
    }
    if (vm->env) wasm_runtime_destroy_exec_env(vm->env);
    if (vm->instance) wasm_runtime_deinstantiate(vm->instance);
    if (vm->module) wasm_runtime_unload(vm->module);
    vm->env = NULL; vm->instance = NULL; vm->module = NULL; vm->tick = NULL;
    vm->draw_count = 0;
    vm->audio_mutations=vm->audio_queries=0;
    vm->network_mutations=vm->network_queries=0;
    vm->state_mutations=vm->state_queries=0;
}
