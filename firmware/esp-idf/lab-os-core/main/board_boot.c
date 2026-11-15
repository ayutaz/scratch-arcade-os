#include "board_boot.h"
#include "target_storage.h"
#include "driver/usb_serial_jtag.h"
#include "esp_random.h"
#include <stddef.h>

#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG || CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG
#define LAB_BOOT_USB_CONSOLE 1
#else
#define LAB_BOOT_USB_CONSOLE 0
#endif
static LabBoardBoot *owner;
static int collect(void *context,uint32_t stats[4]) {
    LabBoardBoot *s=context;
    if(!s->gc.active && !lab_lfs_gc_begin(&s->gc,&s->volume.files,&s->volume.store))return -1;
    int result=lab_lfs_gc_step(&s->gc);
    stats[0]=s->gc.stats.removed_files;stats[1]=s->gc.stats.removed_bytes;
    stats[2]=s->gc.stats.logical_before;stats[3]=s->gc.stats.logical_after;
    return result;
}
static void cancel(void *context) {LabBoardBoot *s=context;lab_lfs_gc_close(&s->gc);}

bool lab_board_boot_close(LabBoardBoot *s) {
    if(!s)return false;
    s->ready=false;
    if(s->session_owned) {
        if(!lab_board_session_close(&s->session))return false;
        s->session_owned=false;
    }
    if(!lab_lfs_gc_close(&s->gc))return false;
    if(s->usb_owned) {
        if(usb_serial_jtag_is_driver_installed() && usb_serial_jtag_driver_uninstall()!=ESP_OK)return false;
        s->usb_owned=false;
    }
    if(s->volume_owned) {
        if(!lab_flash_volume_close(&s->volume))return false;
        s->volume_owned=false;
    }
    if(s->runtime_owned) {lab_runtime_destroy();s->runtime_owned=false;}
    if(owner==s)owner=NULL;
    return true;
}
bool lab_board_boot_open(LabBoardBoot *s,const LabBootConfig *cfg,uint32_t now) {
    if(!s || !cfg || owner || s->ready || s->runtime_owned || s->volume_owned || s->session_owned || s->usb_owned ||
       cfg->profile!=LAB_SESSION_PROFILE_STOCK_0111 || cfg->layout.address<0x10000 ||
       cfg->layout.address%4096 || cfg->layout.bytes<65536 || cfg->layout.bytes%4096 ||
       (uint64_t)cfg->layout.address+cfg->layout.bytes>UINT32_MAX ||
       cfg->quota<sizeof(LAB_STORE_OWNER)-1 || cfg->quota>cfg->layout.bytes ||
       (!LAB_BOOT_USB_CONSOLE && usb_serial_jtag_is_driver_installed()))return false;
    owner=s;
    if(!lab_runtime_init(s->pool,sizeof(s->pool)))goto failure;
    s->runtime_owned=true;
    LabStorage services=lab_target_storage_services();
    s->volume_owned=true;
    if(!lab_flash_volume_open(&s->volume,&cfg->layout,&services,cfg->quota))goto failure;
    if(!LAB_BOOT_USB_CONSOLE) {
        usb_serial_jtag_driver_config_t usb={.tx_buffer_size=1024,.rx_buffer_size=1024};
        if(usb_serial_jtag_driver_install(&usb)==ESP_OK)s->usb_owned=true;
        else if(usb_serial_jtag_is_driver_installed())goto failure;
    }
    uint32_t nonce=esp_random();if(!nonce)nonce=1;
    s->session_owned=true;
    if(!lab_board_session_open(&s->session,&s->volume.store,cfg->profile,nonce,now))goto failure;
    if(s->session.usb.active && !lab_transfer_set_collector(&s->session.usb.transfer,collect,cancel,s))goto failure;
    s->ready=true;return true;
failure:
    lab_board_boot_close(s);return false;
}
int lab_board_boot_step(LabBoardBoot *s,uint32_t now) {
    if(!s || !s->ready)return LAB_LOOP_STOPPED;
    int result=lab_board_session_step(&s->session,now);
    if(result==LAB_LOOP_STOPPED)lab_board_boot_close(s);
    return result;
}
