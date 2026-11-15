#include "board_boot.h"
#include "target_storage.h"
#include "driver/usb_serial_jtag.h"
#include "psa/crypto.h"
#include <stdlib.h>
#include <string.h>
bool test_boot_runtime_init_real(void *,uint32_t);
void test_boot_runtime_destroy_real(void);
void test_session_usb_installed(int);
void test_fault(int);
void test_display_fault(int,int);
typedef bool (*HashCallback)(const uint8_t *,uint32_t,uint8_t *);
static HashCallback digest;
static int stage,bad,calls[6],runtime_live;
static uint32_t random_word=123;
static LabBoardBoot *current;
bool lab_runtime_init(void *pool,uint32_t bytes) {
 calls[0]++;if(runtime_live || bytes!=163840 || (uintptr_t)pool%8)bad=1;
 if(stage==1)return false;
 runtime_live=test_boot_runtime_init_real(pool,bytes);return runtime_live;
}
void lab_runtime_destroy(void) {
 calls[1]++;if(!runtime_live)bad=1;test_boot_runtime_destroy_real();runtime_live=0;
}
psa_status_t psa_hash_compute(psa_algorithm_t alg,const uint8_t *p,size_t n,uint8_t *out,size_t cap,size_t *length) {
 calls[4]++;if(alg!=PSA_ALG_SHA_256 || cap!=32 || n>65800)bad=1;
 if(stage==4) {memset(out,51,32);*length=32;return -1;}
 if(stage==5) {*length=31;return 0;}
 *length=32;return digest && digest(p,(uint32_t)n,out) ? PSA_SUCCESS : -1;
}
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *cfg) {
 calls[2]++;
 if(!runtime_live || !current || !current->volume.ready || cfg->tx_buffer_size!=1024 || cfg->rx_buffer_size!=1024 ||
    usb_serial_jtag_is_driver_installed())bad=1;
 if(stage==2)return ESP_FAIL;
 test_session_usb_installed(1);return ESP_OK;
}
esp_err_t usb_serial_jtag_driver_uninstall(void) {
 calls[3]++;
 if(!runtime_live || !current || current->session.ready || current->volume.store.lease || !usb_serial_jtag_is_driver_installed())bad=1;
 if(stage==3)return ESP_FAIL;
 test_session_usb_installed(0);return ESP_OK;
}
uint32_t esp_random(void) {calls[5]++;return random_word;}
void test_boot_hash_callback(HashCallback cb) {digest=cb;}
void test_boot_reset(void) {stage=bad=0;random_word=123;memset(calls,0,sizeof(calls));}
void test_boot_stage(int value) {stage=value;}
void test_boot_random(uint32_t value) {random_word=value;}
void *test_boot_new(void) {return calloc(1,sizeof(LabBoardBoot));}
int test_boot_open(LabBoardBoot *s,int profile,uint32_t address,uint32_t bytes,uint32_t quota,uint32_t now) {
 LabBoardBoot *previous=current;current=s;
 LabBootConfig cfg={.profile=profile,.layout={address,bytes},.quota=quota};
 bool ok=lab_board_boot_open(s,&cfg,now);
 if(!s->runtime_owned && !s->ready)current=previous;
 return ok;
}
int test_boot_close(LabBoardBoot *s) {current=s;return lab_board_boot_close(s);}
void test_boot_free(LabBoardBoot *s) {
 current=s;stage=0;test_fault(0);test_display_fault(-1,1);lab_board_boot_close(s);free(s);current=NULL;
}
int test_boot_step(LabBoardBoot *s,uint32_t now) {current=s;return lab_board_boot_step(s,now);}
int test_boot_metric(LabBoardBoot *s,int i) {
 int values[]={s->ready,s->runtime_owned,s->volume.ready,s->volume.mounted,s->session.ready,s->usb_owned,
 s->session.usb.active,s->session.home.mode,s->volume.store.lease!=NULL,(int)s->session.home.count,
 runtime_live,bad,(int)s->session.usb.transfer.nonce,s->volume.faulted,s->gc.active,s->volume.store.maintenance,
 (int)s->volume.store.sequence,(int)s->gc.stats.removed_files,s->gc.phase};return values[i];
}
int test_boot_calls(int i) {return calls[i];}
uint32_t test_boot_pool(LabBoardBoot *s,int i) {
 mem_alloc_info_t info={0};if(!s->runtime_owned || !wasm_runtime_get_mem_alloc_info(&info))return 0;
 uintptr_t p=s->session.home.vm.instance ? (uintptr_t)wasm_runtime_addr_app_to_native(s->session.home.vm.instance,0) : 0;
 uint32_t values[]={info.total_size,info.total_size-info.total_free_size,info.highmark_size,
 p>=(uintptr_t)s->pool && p<(uintptr_t)s->pool+sizeof(s->pool)};return values[i];
}
int test_boot_value(LabBoardBoot *s) {return lab_vm_debug(&s->session.home.vm,"debug_value");}
int test_boot_hash(const uint8_t *p,uint32_t n,uint8_t *out) {
 LabStorage io=lab_target_storage_services();return io.hash(io.context,p,n,out);
}
int test_boot_verify(const uint8_t *p,uint32_t n,uint32_t pages,uint32_t fuel,uint32_t caps) {
 uint8_t *copy=malloc(n);if(!copy)return 0;memcpy(copy,p,n);
 LabStorage io=lab_target_storage_services();bool ok=io.verify(io.context,copy,n,pages,fuel,caps);free(copy);return ok;
}
