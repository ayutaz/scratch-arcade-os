/* Host-only workload. No device, filesystem write, port or GPIO API. */
#ifdef ESP_PLATFORM
#error "host-only memory profile"
#endif
#include "platform_api_vmcore.h"
#include "guest_vm.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef OS_ENABLE_HW_BOUND_CHECK
#error "profile must exercise software bounds checks"
#endif
static _Alignas(8) uint8_t pool[196608];
static LabVm vm;
static bool number(const char *p,unsigned min,unsigned max,unsigned *out) {
    if(!p || *p<'0' || *p>'9')return false;
    char *end;errno=0;unsigned long n=strtoul(p,&end,10);
    if(errno || *end || n<min || n>max)return false;
    *out=(unsigned)n;return true;
}
static bool info(mem_alloc_info_t *out) {memset(out,0,sizeof(*out));return wasm_runtime_get_mem_alloc_info(out);}
static int allocator_check(void) {
    if(!lab_runtime_init(pool,sizeof(pool)))return 2;
    mem_alloc_info_t baseline,before,after,done;
    if(!info(&baseline))return 3;
    void *a=wasm_runtime_malloc(32),*b=wasm_runtime_malloc(32);
    if(!a || !b)return 3;
    wasm_runtime_free(b);if(!info(&before))return 3;
    void *grown=wasm_runtime_realloc(a,96);
    if(grown!=a || !info(&after))return 3;
    uint32_t consumed=before.total_free_size-after.total_free_size;
    wasm_runtime_free(grown);if(!info(&done))return 3;
    uint32_t initial=baseline.total_size-baseline.total_free_size,final=done.total_size-done.total_free_size;
    printf("{\"consumed_by_growth\":%u,\"baseline_used\":%u,\"after_used\":%u}\n",consumed,initial,final);
    lab_runtime_destroy();return consumed==64 && initial==final ? 0 : 6;
}
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--allocator-check"))return allocator_check();
    unsigned cycles,capacity,caps=LAB_VM_CAP_DRAW;int arg_at=1;
    if(argc>1 && !strncmp(argv[1],"--caps=",7)) {
        if(!number(argv[1]+7,0,LAB_VM_CAP_ALL,&caps))return 64;
        arg_at++;
    }
    if(argc<arg_at+3 || argc>arg_at+18 || !number(argv[arg_at],1,200,&cycles) || !number(argv[arg_at+1],65536,sizeof(pool),&capacity))return 64;
    if(!lab_runtime_init(pool,capacity))return 2;
    mem_alloc_info_t first,after;
    if(!info(&first)) {lab_runtime_destroy();return 3;}
    unsigned opened=0,closed=0,rejected=0,traps=0,exits=0,leaks=0,contained=0,input_peak=0;
    uint32_t baseline=first.total_size-first.total_free_size;
    for(unsigned i=0;i<cycles;i++)for(int app=arg_at+2;app<argc;app++) {
        FILE *f=fopen(argv[app],"rb");if(!f) {lab_runtime_destroy();return 4;}
        if(fseek(f,0,SEEK_END)) {fclose(f);lab_runtime_destroy();return 4;}
        long n=ftell(f);rewind(f);
        if(n<8 || n>65536) {fclose(f);lab_runtime_destroy();return 64;}
        uint8_t *data=malloc((size_t)n);
        if(!data) {fclose(f);lab_runtime_destroy();return 5;}
        size_t read=fread(data,1,(size_t)n,f);fclose(f);
        if(read!=(size_t)n) {free(data);lab_runtime_destroy();return 4;}
        if((unsigned)n>input_peak)input_peak=(unsigned)n;
        if(lab_vm_open_with_services(&vm,data,(uint32_t)n,2,50000,caps,NULL,NULL)) {
            opened++;
            uintptr_t p=(uintptr_t)wasm_runtime_addr_app_to_native(vm.instance,0);
            uintptr_t start=(uintptr_t)pool,end=start+capacity;
            if(p>=start && p<end)contained++;
            for(unsigned frame=0;frame<3;frame++) {
                int status=lab_vm_frame(&vm,frame==1 ? 1 : 0,16);
                if(status) {if(status<0)traps++;else exits++;break;}
            }
            lab_vm_close(&vm,2);closed++;
        } else {rejected++;lab_vm_close(&vm,2);}
        free(data);
        if(!info(&after)) {lab_runtime_destroy();return 3;}
        if(after.total_size-after.total_free_size!=baseline)leaks++;
    }
    if(!info(&after)) {lab_runtime_destroy();return 3;}
    printf("{\"format\":\"lab-os-memory-profile-v1\",\"device_tested\":false,\"software_bounds\":true,"
           "\"capabilities\":%u,\"pool_capacity\":%u,\"pool_total\":%u,\"baseline_used\":%u,\"after_used\":%u,\"peak_used\":%u,"
           "\"opened\":%u,\"closed\":%u,\"rejected\":%u,\"traps\":%u,\"normal_exits\":%u,\"leak_cycles\":%u,"
           "\"linear_in_pool\":%u,\"input_buffer_peak\":%u}\n",caps,capacity,after.total_size,baseline,
           after.total_size-after.total_free_size,after.highmark_size,opened,closed,rejected,traps,exits,leaks,contained,input_peak);
    lab_runtime_destroy();return 0;
}
