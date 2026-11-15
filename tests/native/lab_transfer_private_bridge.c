#include "app_transfer.h"
#include <string.h>
/* Both test transports expose LabTransfer at offset zero. Observe only the
 * service-owned bytes, never an SDK/serial/kernel allocation. */
uint32_t test_transfer_memory_size(void) {return sizeof(LabTransfer);}
int test_transfer_rx_zero(LabTransfer *s) {
    for(unsigned i=0;i<sizeof(s->rx);i++)if(s->rx[i])return 0;
    return s->rx_size==0;
}
static bool (*original_hash)(void *,const uint8_t *,uint32_t,uint8_t[32]);
static bool fail_hash(void *ctx,const uint8_t *p,uint32_t n,uint8_t out[32]) {
    (void)ctx;(void)p;(void)n;(void)out;return false;
}
void test_transfer_hash_failure(LabTransfer *s,int fail) {
    if(fail) {original_hash=s->store->io.hash;s->store->io.hash=fail_hash;}
    else s->store->io.hash=original_hash;
}
