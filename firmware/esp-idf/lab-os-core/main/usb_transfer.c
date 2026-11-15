#include "usb_transfer.h"
#include "sdkconfig.h"
#include "driver/usb_serial_jtag.h"
#include "freertos/FreeRTOS.h"
#include <string.h>

static void clear_bytes(uint8_t *p,uint32_t n) {
    volatile uint8_t *clear=p;while(n--)*clear++=0;
}
static bool send_frame(void *context,const uint8_t *p,uint32_t n) {
    LabUsbTransfer *s=context;
    return s->active && n<=207 &&
           usb_serial_jtag_write_bytes(p,n,pdMS_TO_TICKS(20))==(int)n;
}
bool lab_usb_transfer_attach(LabUsbTransfer *s,LabStore *store,LabHome *home,uint32_t nonce,uint32_t now) {
    if(!s)return false;
    memset(s,0,sizeof(*s));
#if (defined(CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG) && CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG) || \
    (defined(CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG) && CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG)
    const bool shared_console=true;
#else
    const bool shared_console=false;
#endif
    if(shared_console || !usb_serial_jtag_is_driver_installed())return false;
    s->active=lab_transfer_init(&s->transfer,store,home,send_frame,s,nonce,now);
    return s->active;
}
bool lab_usb_transfer_poll(LabUsbTransfer *s,uint32_t now) {
    if(!s)return false;
    s->received=false;
    if(!s->active)return false;
    if(!usb_serial_jtag_is_driver_installed()) {lab_usb_transfer_close(s);return false;}
    uint8_t data[128];
    int n=usb_serial_jtag_read_bytes(data,sizeof(data),0);
    if(n<0 || (uint32_t)n>sizeof(data)) {
        clear_bytes(data,sizeof(data));lab_usb_transfer_close(s);return false;
    }
    s->received=n>0;
    bool sent=lab_transfer_feed(&s->transfer,data,(uint32_t)n,now);
    clear_bytes(data,sizeof(data));
    bool polled=lab_transfer_poll(&s->transfer,now);
    return sent && polled;
}
void lab_usb_transfer_close(LabUsbTransfer *s) {
    if(!s)return;
    lab_transfer_close(&s->transfer);s->active=s->received=false;
}
