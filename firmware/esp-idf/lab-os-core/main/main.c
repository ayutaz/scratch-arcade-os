/* Link-only loop scenario with injected inputs and checksum sink. No device I/O. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "app_home.h"
#include "ui.h"
#include "run_loop.h"
#include "lab_apps.h"

static _Alignas(8) uint8_t pool[196608];
static LabHome home;
static LabRunLoop loop;
static LabInputSample injected;
static uint32_t scenario_ms;
typedef struct {
    unsigned leases, opened, released;
    bool disabled[2];
} RomCatalog;
static RomCatalog rom;
static struct {uint32_t frames,rows,hash;} ui;
static const LabAppInfo apps[2] = {
    {.id="counter", .title="カウンター", .version="1.0.0", .enabled=true},
    {.id="game", .title="ゲーム", .version="1.0.0", .enabled=true}
};
static uint32_t app_count(void *context) { (void)context; return 2; }
static bool app_info(void *context,uint32_t index,LabAppInfo *out) {
    RomCatalog *catalog=context;
    if(index>=2)return false;
    *out=apps[index];out->enabled=!catalog->disabled[index];return true;
}
static int app_index(const char *id) {
    for(int i=0;i<2;i++)if(!strcmp(apps[i].id,id))return i;
    return -1;
}
static bool app_open(void *context,const char *id,LabImage *image) {
    RomCatalog *catalog=context;int index=app_index(id);
    if(index<0 || catalog->disabled[index] || catalog->leases)return false;
    const uint8_t *source=index==0 ? lab_counter : lab_game;
    uint32_t size=index==0 ? sizeof(lab_counter) : sizeof(lab_game);
    image->bytes=malloc(size);
    if(!image->bytes)return false;
    memcpy(image->bytes,source,size);
    image->size=size;image->pages=2;image->budget=50000;image->capabilities=LAB_VM_CAP_DRAW;
    ++catalog->opened;++catalog->leases;return true;
}
static void app_release(void *context,LabImage *image) {
    RomCatalog *catalog=context;
    free(image->bytes);++catalog->released;--catalog->leases;
}
static bool app_quarantine(void *context,const char *id) {
    RomCatalog *catalog=context;int index=app_index(id);
    if(index<0)return false;
    catalog->disabled[index]=true;return true;
}
static bool read_injected(void *context,uint32_t now,LabInputSample *out) {
    (void)context;(void)now;*out=injected;return true;
}
static bool frame(uint32_t held,uint32_t dt) {
    injected=(LabInputSample){.held=held};
    if(held&128)injected.keys|=LAB_KEY_FN;
    if(held&16)injected.keys|=LAB_KEY_A;
    if(held&64)injected.keys|=LAB_KEY_B;
    if(held&32)injected.keys|=LAB_KEY_X;
    if(held&1)injected.x=-100;
    if(held&2)injected.x=100;
    if(held&4)injected.y=-100;
    if(held&8)injected.y=100;
    scenario_ms+=dt;return lab_loop_step(&loop,scenario_ms)==LAB_LOOP_OK;
}
static bool consume_row(void *context,uint32_t y,const uint16_t *pixels) {
    (void)context;
    if(y!=ui.rows%240)return false;
    for(unsigned x=0;x<320;x++) {
        ui.hash=(ui.hash ^ (pixels[x] & 255u))*16777619u;
        ui.hash=(ui.hash ^ (pixels[x]>>8))*16777619u;
    }
    ++ui.rows;return true;
}
static bool paint(void *context,const LabHome *state) {
    (void)context;
    if(!lab_ui_render(state,consume_row,NULL))return false;
    ++ui.frames;return true;
}
static bool cycle(void) {
    if(!frame(16,0) || home.mode!=LAB_RUNNING || !frame(0,0) || !frame(1,40) ||
       lab_vm_debug(&home.vm,"debug_value")!=1)return false;
    if(!frame(192,0) || !frame(0,0) || home.mode!=LAB_HOME)return false;
    if(!frame(4,0) || !frame(0,0) || !frame(16,0) || !frame(0,0) || !frame(16,0) ||
       !frame(1,300) || home.mode!=LAB_RUNNING ||
       lab_vm_debug(&home.vm,"debug_x")!=24 || lab_vm_debug(&home.vm,"debug_value")!=1)return false;
    return frame(192,0) && frame(0,0) && home.mode==LAB_HOME &&
           frame(8,0) && frame(0,0) && home.selected==0;
}
void app_main(void) {
    if(!lab_runtime_init(pool,sizeof(pool))) {puts("LAB_HOME_CORE runtime init failed");return;}
    memset(&rom,0,sizeof(rom));
    memset(&ui,0,sizeof(ui));ui.hash=2166136261u;
    LabCatalog catalog={&rom,app_count,app_info,app_open,app_release,app_quarantine};
    LabLoopIo io={.input=read_injected,.paint=paint};scenario_ms=0;
    unsigned passed=0;
    if(lab_home_init(&home,&catalog) && lab_loop_init(&loop,&home,&io,0) && frame(0,0)) {
        for(unsigned n=0;n<10;n++) {
            if(!cycle())break;
            ++passed;vTaskDelay(pdMS_TO_TICKS(10));
        }
    }
    lab_loop_close(&loop);lab_home_close(&home);lab_runtime_destroy();
    printf("LAB_LOOP_CORE cycles=%u leases=%u opens=%u releases=%u ui_frames=%u ui_rows=%u ui_hash=%08x scenario_ms=%u pool=%zu free_internal=%zu min_internal=%zu\n",
           passed,rom.leases,rom.opened,rom.released,(unsigned)ui.frames,(unsigned)ui.rows,(unsigned)ui.hash,(unsigned)scenario_ms,sizeof(pool),
           heap_caps_get_free_size(MALLOC_CAP_INTERNAL),heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
    /* Host API-fixture test and S3 linking do not prove physical execution. */
}
