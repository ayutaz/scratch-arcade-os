#include "app_transfer.h"
#include <stdlib.h>
LabStore *test_store_pointer(void *);
LabHome *test_home_pointer(void *);
void *test_transfer_new(void *fixture,LabTransferSend send,void *context,uint32_t nonce) {
    LabTransfer *s=calloc(1,sizeof(*s));if(!s)return NULL;
    if(!lab_transfer_init(s,test_store_pointer(fixture),test_home_pointer(fixture),send,context,nonce,0)) {
        free(s);return NULL;
    }
    return s;
}
void test_transfer_free(LabTransfer *s) {lab_transfer_close(s);free(s);}
int test_transfer_feed(LabTransfer *s,const uint8_t *p,uint32_t n,uint32_t now) {return lab_transfer_feed(s,p,n,now);}
int test_transfer_poll(LabTransfer *s,uint32_t now) {return lab_transfer_poll(s,now);}
int test_transfer_busy(LabTransfer *s) {return lab_transfer_busy(s);}
