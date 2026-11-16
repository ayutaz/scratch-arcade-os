/* Candidate entry; UI and guest behavior require target validation. */
#include "board_boot.h"
#include "resource_monitor.h"
#include "voice_service.h"
#include "state_mount.h"
#include "lab_candidate.h"
#include "esp_timer.h"
#include "esp_pthread.h"
#include <pthread.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* The runtime pool and children belong in static storage, never task stack. */
static LabBoardBoot boot;
/* Storage callbacks borrow this object until Home closes before FS unmount. */
static LabStateMount app_state;
static LabVoice voice;
/* Single-task RAM recorder. Debugger-visible; never printed to app USB. */
LabResourceMonitor lab_candidate_resources;
static uint32_t now(void) {return (uint32_t)(esp_timer_get_time()/1000);}
static void capture(uint32_t stage) {
    uint32_t flags=(boot.runtime_owned ? LAB_RESOURCE_RUNTIME : 0) |
        (boot.ready ? LAB_RESOURCE_READY : 0) |
        (boot.runtime_owned && boot.session.home.mode==LAB_RUNNING ? LAB_RESOURCE_APP : 0) |
        (boot.session.usb.transfer.session ? LAB_RESOURCE_UPLOAD : 0) |
        (boot.gc.active ? LAB_RESOURCE_GC : 0);
    lab_resource_poll(&lab_candidate_resources,now(),stage,flags);
}
static void *os_main(void *unused) {
    (void)unused;
    const LabBootConfig cfg={.profile=LAB_SESSION_PROFILE_STOCK_0111,
        .layout={LAB_CANDIDATE_ADDRESS,LAB_CANDIDATE_BYTES},.quota=LAB_CANDIDATE_QUOTA};
    capture(LAB_RESOURCE_BEFORE_BOOT);
    bool opened=lab_board_boot_open(&boot,&cfg,now());
    if(opened && !lab_board_sound_set_voice(&boot.session.sound,&voice,lab_voice_call))opened=false;
    if(opened && boot.session.usb.active &&
       !lab_transfer_set_telemetry(&boot.session.usb.transfer,lab_resource_readout,&lab_candidate_resources))opened=false;
    if(opened && !lab_state_mount_attach(&app_state,&boot.session.home,&boot.volume.fs,true))opened=false;
    if(opened) {
        capture(LAB_RESOURCE_RUNNING);
        for(;;) {
            int result=lab_board_boot_step(&boot,now());
            capture(result==LAB_LOOP_STOPPED ? LAB_RESOURCE_STOPPED : LAB_RESOURCE_RUNNING);
            if(result==LAB_LOOP_STOPPED)break;
            vTaskDelay(1);
        }
    } else capture(LAB_RESOURCE_OPEN_FAILED);
    /* Failed native cleanup retains parents. Retry without a busy loop; do not
     * reset, format or silently abandon a still-owned driver/runtime. */
    capture(LAB_RESOURCE_CLOSING);
    while(!lab_board_boot_close(&boot)) {capture(LAB_RESOURCE_CLOSING);vTaskDelay(1);}
    capture(LAB_RESOURCE_CLOSED);
    return NULL;
}

void app_main(void) {
    /* WAMR's ESP-IDF os_self_thread() requires a registered pthread.
     * A raw FreeRTOS app_main task aborts on the first guest function call.
     * Keep every driver/runtime operation on one core and one OS owner. */
    esp_pthread_cfg_t cfg=esp_pthread_get_default_config();
    cfg.stack_size=16384;
    cfg.prio=1;
    cfg.pin_to_core=0;
    cfg.inherit_cfg=false;
    cfg.thread_name="lab-os";
    pthread_t thread;
    if(esp_pthread_set_cfg(&cfg)!=ESP_OK || pthread_create(&thread,NULL,os_main,NULL)!=0) {
        capture(LAB_RESOURCE_OPEN_FAILED);
        return;
    }
    (void)pthread_join(thread,NULL);
}
