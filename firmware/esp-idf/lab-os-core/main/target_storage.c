#include "target_storage.h"
#include "guest_vm.h"
#include "psa/crypto.h"
#include <string.h>

static bool hash(void *context,const uint8_t *data,uint32_t bytes,uint8_t digest[32]) {
    (void)context;
    if(!digest || (!data && bytes) || bytes>LAB_PACKAGE_HEADER+LAB_PACKAGE_MAX_WASM)return false;
    uint8_t temporary[32];size_t length=0;
    if(psa_hash_compute(PSA_ALG_SHA_256,data,bytes,temporary,sizeof(temporary),&length)!=PSA_SUCCESS ||
       length!=sizeof(temporary))return false;
    memcpy(digest,temporary,sizeof(temporary));return true;
}
static bool verify(void *context,uint8_t *data,uint32_t bytes,uint32_t pages,uint32_t budget,uint32_t caps) {
    (void)context;
    if(!data || !bytes || bytes>LAB_PACKAGE_MAX_WASM || pages<1 || pages>2)return false;
    LabVm vm;
    bool ok=lab_vm_open_with_audio(&vm,data,bytes,pages,budget,caps,NULL);
    if(ok)ok=lab_vm_frame(&vm,0,0)==0;
    lab_vm_close(&vm,2);return ok;
}
LabStorage lab_target_storage_services(void) {
    return (LabStorage){.hash=hash,.verify=verify};
}
