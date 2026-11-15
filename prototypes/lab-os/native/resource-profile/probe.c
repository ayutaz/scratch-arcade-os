/* Reuse the owned RAM filesystem implementation. Compile this TU without the
 * heap macros: harness/image/output buffers are not embedded-system heap. */
#ifdef ESP_PLATFORM
#error "host-only resource probe"
#endif
#include "../fs_image.c"
#include "heap_track.h"
#include "app_transfer.h"
#include <stdio.h>
typedef struct {
    Seed *seed;LabHome home;LabTransfer transfer;LabLfsGc gc;
    uint8_t output[16384];uint32_t written;
    bool runtime,home_owned;
} Probe;
static _Alignas(8) uint8_t pool[196608];
static Probe *owner;
static bool verify(void *context,uint8_t *data,uint32_t n,uint32_t pages,uint32_t fuel,uint32_t caps) {
    (void)context;if(!data || !n || pages<1 || pages>2)return false;
    LabVm vm;bool ok=lab_vm_open_with_audio(&vm,data,n,pages,fuel,caps,NULL);
    if(ok)ok=lab_vm_frame(&vm,0,0)==0;
    lab_vm_close(&vm,2);return ok;
}
static bool send(void *context,const uint8_t *p,uint32_t n) {
    Probe *s=context;if(n>sizeof(s->output)-s->written)return false;
    memcpy(s->output+s->written,p,n);s->written+=n;return true;
}
static int collect(void *context,uint32_t stats[4]) {
    Probe *s=context;
    if(!s->gc.active && !lab_lfs_gc_begin(&s->gc,&s->seed->files,&s->seed->store))return -1;
    int result=lab_lfs_gc_step(&s->gc);
    stats[0]=s->gc.stats.removed_files;stats[1]=s->gc.stats.removed_bytes;
    stats[2]=s->gc.stats.logical_before;stats[3]=s->gc.stats.logical_after;return result;
}
static void cancel(void *context) {Probe *s=context;lab_lfs_gc_close(&s->gc);}
void lab_resource_free(Probe *s) {
    if(!s)return;
    lab_transfer_close(&s->transfer);lab_lfs_gc_close(&s->gc);
    if(s->home_owned)lab_home_close(&s->home);
    lab_seed_free(s->seed);
    if(s->runtime)lab_runtime_destroy();
    if(owner==s)owner=NULL;free(s);
}
void *lab_resource_new(const uint8_t *image,uint32_t n,
                      bool (*hash)(void *,const uint8_t *,uint32_t,uint8_t *),uint32_t cap) {
    if(owner || !image || !hash || n<65536 || n>MAX_IMAGE || n%4096 || cap>262144 || !lab_heap_reset(cap,0))return NULL;
    Probe *s=calloc(1,sizeof(*s));if(!s)return NULL;owner=s;
    if(!lab_runtime_init(pool,sizeof(pool)))goto failure;s->runtime=true;
    wasm_runtime_set_log_level(WASM_LOG_LEVEL_ERROR);
    LabStorage io={.hash=hash,.verify=verify};
    s->seed=lab_seed_new(n,image,&io);if(!s->seed)goto failure;
    /* The input has passed root/owner/catalog checks; all writes still target
     * this private malloc-backed image. No physical block API exists here. */
    s->seed->writable=true;
    LabCatalog catalog=lab_store_catalog(&s->seed->store);s->home_owned=true;
    if(!lab_home_init(&s->home,&catalog) ||
       !lab_transfer_init(&s->transfer,&s->seed->store,&s->home,send,s,123,0) ||
       !lab_transfer_set_collector(&s->transfer,collect,cancel,s))goto failure;
    return s;
failure:
    lab_resource_free(s);return NULL;
}
int lab_resource_feed(Probe *s,const uint8_t *p,uint32_t n,uint32_t now) {return lab_transfer_feed(&s->transfer,p,n,now);}
int lab_resource_poll(Probe *s,uint32_t now) {return lab_transfer_poll(&s->transfer,now);}
uint32_t lab_resource_read(Probe *s,uint8_t *p,uint32_t cap) {
    uint32_t n=s->written<cap ? s->written : cap;
    memcpy(p,s->output,n);memmove(s->output,s->output+n,s->written-n);s->written-=n;return n;
}
int lab_resource_dump(Probe *s,uint8_t *p,uint32_t n) {return lab_seed_dump(s->seed,p,n);}
int lab_resource_info(Probe *s,uint32_t at,char out[160]) {
    LabAppInfo info;LabCatalog c=lab_store_catalog(&s->seed->store);
    if(!c.info(c.context,at,&info))return 0;
    snprintf(out,160,"%s|%s",info.id,info.version);return 1;
}
int lab_resource_package(Probe *s,uint32_t at,uint8_t *out,uint32_t cap) {return lab_seed_package(s->seed,at,out,cap);}
uint32_t lab_resource_count(Probe *s) {return s->seed->store.count;}
int lab_resource_counter(Probe *s) {
    if(s->transfer.session || s->home.mode!=LAB_HOME)return -1;
    if(!lab_home_frame(&s->home,16,0) || !lab_home_frame(&s->home,0,0) ||
       !lab_home_frame(&s->home,1,16))return -1;
    int value=lab_vm_debug(&s->home.vm,"debug_value");
    lab_home_frame(&s->home,192,0);lab_home_frame(&s->home,0,0);return value;
}
