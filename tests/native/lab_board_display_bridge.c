#include "board_display.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_lcd_io_spi.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"
#include "esp_heap_caps.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <string.h>
enum {LEVEL,GPIO,BUS,ALLOC,IO,PANEL,RESET,PARAM,INVERT,SWAP,MIRROR,GAP,PANEL_DEL,IO_DEL,BUS_FREE,PIN_RESET,FREE,DELAY,GENERIC_INIT};
#ifndef LAB_TEST_DISPLAY_CAPACITY
#define LAB_TEST_DISPLAY_CAPACITY 4096
#endif
static int calls[20],fault=-1,nth=1,bad,bl,bus_live,io_live,panel_live,alloc_live,sequence,first_on,first_param,first_on_nparam;
static int commands[LAB_TEST_DISPLAY_CAPACITY],lengths[LAB_TEST_DISPLAY_CAPACITY],nparam,waits[100],nwait;
static unsigned char bytes[LAB_TEST_DISPLAY_CAPACITY][640];
static uint64_t mask;
static spi_bus_config_t bus_cfg;
static esp_lcd_panel_io_spi_config_t io_cfg;
static esp_lcd_panel_dev_config_t panel_cfg;
static int hit(int id) {++sequence;++calls[id];return fault==id && calls[id]==nth;}
esp_err_t gpio_set_level(gpio_num_t pin,uint32_t level) {
 if(pin!=21 || level>1)bad=1;
 if(hit(LEVEL))return ESP_FAIL;
 bl=level;if(level && !first_on) {first_on=sequence;first_on_nparam=nparam;}return ESP_OK;
}
esp_err_t gpio_config(const gpio_config_t *cfg) {
 mask=cfg->pin_bit_mask;
 if(cfg->mode!=GPIO_MODE_OUTPUT || cfg->pull_up_en || cfg->pull_down_en || cfg->intr_type || bl)bad=1;
 return hit(GPIO) ? ESP_FAIL : ESP_OK;
}
esp_err_t gpio_reset_pin(gpio_num_t pin) {if(pin!=21 || bl)bad=1;return hit(PIN_RESET) ? ESP_FAIL : ESP_OK;}
esp_err_t spi_bus_initialize(spi_host_device_t host,const spi_bus_config_t *cfg,spi_dma_chan_t dma) {
 if(host!=1 || dma!=3 || bus_live || bl)bad=1;bus_cfg=*cfg;
 if(hit(BUS) || bus_live)return ESP_FAIL;bus_live=1;return ESP_OK;
}
void *spi_bus_dma_memory_alloc(spi_host_device_t host,size_t size,uint32_t caps) {
 if(host!=1 || size!=640 || caps!=MALLOC_CAP_INTERNAL || !bus_live || alloc_live)bad=1;
 if(hit(ALLOC))return NULL;alloc_live=1;return malloc(size);
}
void heap_caps_free(void *p) {hit(FREE);if(!alloc_live || io_live)bad=1;alloc_live=0;free(p);}
esp_err_t esp_lcd_new_panel_io_spi(esp_lcd_spi_bus_handle_t bus,const esp_lcd_panel_io_spi_config_t *cfg,esp_lcd_panel_io_handle_t *out) {
 if(bus!=1 || !bus_live || io_live || !alloc_live)bad=1;io_cfg=*cfg;
 if(hit(IO))return ESP_FAIL;io_live=1;*out=(void *)1;return ESP_OK;
}
esp_err_t esp_lcd_new_panel_st7789(esp_lcd_panel_io_handle_t io,const esp_lcd_panel_dev_config_t *cfg,esp_lcd_panel_handle_t *out) {
 if(io!=(void *)1 || !io_live || panel_live)bad=1;panel_cfg=*cfg;
 if(hit(PANEL))return ESP_FAIL;panel_live=1;*out=(void *)2;return ESP_OK;
}
static int panel_check(int id,void *p) {if(p!=(void *)2 || !panel_live)bad=1;return hit(id);}
esp_err_t esp_lcd_panel_reset(esp_lcd_panel_handle_t p) {return panel_check(RESET,p) ? ESP_FAIL : ESP_OK;}
esp_err_t esp_lcd_panel_init(esp_lcd_panel_handle_t p) {panel_check(GENERIC_INIT,p);bad=1;return ESP_FAIL;}
esp_err_t esp_lcd_panel_invert_color(esp_lcd_panel_handle_t p,bool value) {if(!value)bad=1;return panel_check(INVERT,p) ? ESP_FAIL : ESP_OK;}
esp_err_t esp_lcd_panel_swap_xy(esp_lcd_panel_handle_t p,bool value) {if(!value)bad=1;return panel_check(SWAP,p) ? ESP_FAIL : ESP_OK;}
esp_err_t esp_lcd_panel_mirror(esp_lcd_panel_handle_t p,bool x,bool y) {if(x || !y)bad=1;return panel_check(MIRROR,p) ? ESP_FAIL : ESP_OK;}
esp_err_t esp_lcd_panel_set_gap(esp_lcd_panel_handle_t p,int x,int y) {if(x || y)bad=1;return panel_check(GAP,p) ? ESP_FAIL : ESP_OK;}
esp_err_t esp_lcd_panel_io_tx_param(esp_lcd_panel_io_handle_t io,int command,const void *data,size_t size) {
 if(io!=(void *)1 || !io_live || size>640 || (size && !data) || nparam>=LAB_TEST_DISPLAY_CAPACITY)bad=1;
 if(!first_param)first_param=sequence+1;
 if(nparam<LAB_TEST_DISPLAY_CAPACITY) {commands[nparam]=command;lengths[nparam]=size;if(size<=640 && size)memcpy(bytes[nparam],data,size);nparam++;}
 return hit(PARAM) ? ESP_FAIL : ESP_OK;
}
esp_err_t esp_lcd_panel_del(esp_lcd_panel_handle_t p) {
 if(panel_check(PANEL_DEL,p))return ESP_FAIL;panel_live=0;return ESP_OK;
}
esp_err_t esp_lcd_panel_io_del(esp_lcd_panel_io_handle_t io) {
 if(io!=(void *)1 || !io_live || panel_live || bl)bad=1;
 if(hit(IO_DEL))return ESP_FAIL;io_live=0;return ESP_OK;
}
esp_err_t spi_bus_free(spi_host_device_t host) {
 if(host!=1 || !bus_live || io_live || alloc_live)bad=1;
 if(hit(BUS_FREE))return ESP_FAIL;bus_live=0;return ESP_OK;
}
void vTaskDelay(TickType_t ticks) {hit(DELAY);if(nwait>=100 || !ticks)bad=1;else waits[nwait++]=ticks;}
void test_display_reset(void) {
 memset(calls,0,sizeof(calls));memset(bytes,0,sizeof(bytes));memset(&bus_cfg,0,sizeof(bus_cfg));memset(&io_cfg,0,sizeof(io_cfg));memset(&panel_cfg,0,sizeof(panel_cfg));
 fault=-1;nth=1;bad=bl=bus_live=io_live=panel_live=alloc_live=sequence=first_on=first_param=first_on_nparam=nparam=nwait=0;mask=0;
}
void test_display_fault(int id,int occurrence) {fault=id;nth=occurrence;}
void *test_display_new(void) {return calloc(1,sizeof(LabBoardDisplay));}
void test_display_free(LabBoardDisplay *p) {fault=-1;lab_board_display_close(p);free(p);}
int test_display_open(LabBoardDisplay *p,int profile) {return lab_board_display_open(p,profile);}
int test_display_close(LabBoardDisplay *p) {return lab_board_display_close(p);}
int test_display_row(LabBoardDisplay *p,unsigned y,const uint16_t *pixels) {return lab_board_display_row(p,y,pixels);}
int test_display_paint(LabBoardDisplay *p,int invalid) {
 LabHome h={0};h.mode=invalid ? (LabHomeMode)99 : LAB_RUNNING;h.vm.draw_count=1;
 int32_t rect[5]={0,0,320,240,0x1234};memcpy(h.vm.draws[0],rect,sizeof(rect));return lab_board_display_paint(p,&h);
}
int test_display_metric(int id) {
 int values[]={bad,bl,bus_live,io_live,panel_live,alloc_live,first_on,first_param,nparam,nwait,first_on_nparam};return values[id];
}
int test_display_calls(int id) {return calls[id];}
int test_display_command(int i) {return commands[i];}
int test_display_length(int i) {return lengths[i];}
int test_display_byte(int i,int j) {return bytes[i][j];}
int test_display_wait(int i) {return waits[i];}
int test_display_config(int i) {
 int values[]={bus_cfg.mosi_io_num,bus_cfg.miso_io_num,bus_cfg.sclk_io_num,bus_cfg.quadwp_io_num,bus_cfg.quadhd_io_num,
 bus_cfg.data4_io_num,bus_cfg.data5_io_num,bus_cfg.data6_io_num,bus_cfg.data7_io_num,bus_cfg.max_transfer_sz,
 io_cfg.cs_gpio_num,io_cfg.dc_gpio_num,io_cfg.spi_mode,(int)io_cfg.pclk_hz,(int)io_cfg.trans_queue_depth,
 io_cfg.lcd_cmd_bits,io_cfg.lcd_param_bits,panel_cfg.reset_gpio_num,(int)panel_cfg.bits_per_pixel,panel_cfg.rgb_ele_order,
 panel_cfg.data_endian,panel_cfg.flags.reset_active_high,(int)(mask>>21),io_cfg.on_color_trans_done!=NULL,
 io_cfg.flags.dc_high_on_cmd,io_cfg.flags.dc_low_on_data,io_cfg.flags.dc_low_on_param,io_cfg.flags.lsb_first,io_cfg.flags.cs_high_active};
 return values[i];
}

static unsigned service_count,service_last_param,service_bad;
static void paint_service(void *context){
 if(context!=&service_count || nparam-(int)service_last_param!=24)service_bad++;
 service_last_param=(unsigned)nparam;service_count++;
}
int test_display_serviced_paint(LabBoardDisplay *p,int invalid){
 service_count=service_bad=0;service_last_param=(unsigned)nparam;
 LabHome h={0};h.mode=invalid ? (LabHomeMode)99 : LAB_RUNNING;h.vm.draw_count=1;
 int32_t rect[5]={0,0,320,240,0x1234};memcpy(h.vm.draws[0],rect,sizeof(rect));
 return lab_board_display_paint_serviced(p,&h,paint_service,&service_count);
}
unsigned test_display_service_metric(unsigned i){return i ? service_bad : service_count;}
