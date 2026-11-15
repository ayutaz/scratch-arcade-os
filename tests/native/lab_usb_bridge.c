/* Test-only IDF I/O shim. No real USB functions are linked on the host. */
#include "usb_transfer.h"
#include <stdlib.h>
#include <string.h>
LabStore *test_store_pointer(void *);
LabHome *test_home_pointer(void *);
static bool installed=true;
static uint8_t incoming[1024];static uint32_t queued;
static LabTransferSend output;static void *output_context;
static int read_override,bad_contract,reads,writes;
bool usb_serial_jtag_is_driver_installed(void) {return installed;}
int usb_serial_jtag_read_bytes(void *p,uint32_t n,uint32_t ticks) {
    reads++;if(n!=128 || ticks)bad_contract=1;
    if(read_override) {int result=read_override;read_override=0;return result;}
    if(n>queued)n=queued;
    memcpy(p,incoming,n);memmove(incoming,incoming+n,queued-n);queued-=n;return (int)n;
}
int usb_serial_jtag_write_bytes(const void *p,size_t n,uint32_t ticks) {
    writes++;if(n>207 || ticks!=20)bad_contract=1;
    return output(output_context,p,(uint32_t)n) ? (int)n : 0;
}
void *test_transfer_new(void *fixture,LabTransferSend send,void *context,uint32_t nonce) {
    LabUsbTransfer *s=calloc(1,sizeof(*s));if(!s)return NULL;
    output=send;output_context=context;queued=0;read_override=0;bad_contract=reads=writes=0;
    if(!lab_usb_transfer_attach(s,test_store_pointer(fixture),test_home_pointer(fixture),nonce,0)) {free(s);return NULL;}
    return s;
}
void test_transfer_free(LabUsbTransfer *s) {lab_usb_transfer_close(s);free(s);}
int test_transfer_feed(LabUsbTransfer *s,const uint8_t *p,uint32_t n,uint32_t now) {
    if(n>sizeof(incoming)-queued)return 0;
    memcpy(incoming+queued,p,n);queued+=n;bool ok=true;
    do {if(!lab_usb_transfer_poll(s,now)) {ok=false;break;}}while(queued);
    return ok;
}
int test_transfer_poll(LabUsbTransfer *s,uint32_t now) {return lab_usb_transfer_poll(s,now);}
int test_transfer_busy(LabUsbTransfer *s) {return lab_transfer_busy(&s->transfer);}
void test_usb_set_installed(int value) {installed=value!=0;}
void test_usb_read_override(int value) {read_override=value;}
int test_usb_contract(void) {return bad_contract ? -1 : reads && writes;}
