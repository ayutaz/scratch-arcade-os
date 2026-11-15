#include "board_display.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_lcd_io_spi.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_commands.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
/* One physical display, one OS task. Failed cleanup retains this owner too. */
static LabBoardDisplay *owner;
/* Values, delay policy and rotation: boards/scratch-arcade/profile.json.
 * First byte is command; subsequent bytes are parameters. Not inferred LITE pins. */
static const struct {uint8_t size,delay_ms,data[15];} custom_init[]={
    {1,120,{0x11}},
    {2,0,{0x3a,0x05}},
    {6,0,{0xb2,0x0c,0x0c,0x00,0x33,0x33}},
    {2,0,{0xb7,0x35}},
    {2,0,{0xbb,0x32}},
    {2,0,{0xc2,0x01}},
    {2,0,{0xc3,0x15}},
    {2,0,{0xc4,0x20}},
    {2,0,{0xc6,0x0f}},
    {3,0,{0xd0,0xa4,0xa1}},
    {15,0,{0xe0,0xd0,0x08,0x0e,0x09,0x09,0x05,0x31,0x33,0x48,0x17,0x14,0x15,0x31,0x34}},
    {15,0,{0xe1,0xd0,0x08,0x0e,0x09,0x09,0x15,0x31,0x33,0x48,0x17,0x14,0x15,0x31,0x34}},
    {1,100,{0x29}}
};
static void wait_ms(unsigned ms) {
    /* Round up and include the unknown phase of the next scheduler tick. */
    TickType_t ticks=(TickType_t)(((uint64_t)ms*configTICK_RATE_HZ+999)/1000);
    vTaskDelay(ticks+1);
}
bool lab_board_display_close(LabBoardDisplay *s) {
    if(!s)return false;
    s->ready=false;
    /* Fail closed: preserve handles until each child can be released safely. */
    if(s->backlight_owned && gpio_set_level(21,0)!=ESP_OK)return false;
    if(s->panel) {
        if(esp_lcd_panel_del(s->panel)!=ESP_OK)return false;
        s->panel=NULL;
    }
    if(s->io) {
        if(esp_lcd_panel_io_del(s->io)!=ESP_OK)return false;
        s->io=NULL;
    }
    if(s->row) {heap_caps_free(s->row);s->row=NULL;}
    if(s->bus_owned) {
        if(spi_bus_free(SPI2_HOST)!=ESP_OK)return false;
        s->bus_owned=false;
    }
    if(s->backlight_owned) {
        if(gpio_reset_pin(21)!=ESP_OK)return false;
        s->backlight_owned=false;
    }
    if(owner==s)owner=NULL;
    return true;
}
static bool write_row(LabBoardDisplay *s,uint32_t y) {
    const uint8_t columns[4]={0,0,1,0x3f};
    const uint8_t rows[4]={0,(uint8_t)y,0,(uint8_t)y};
    return esp_lcd_panel_io_tx_param(s->io,LCD_CMD_CASET,columns,sizeof(columns))==ESP_OK &&
           esp_lcd_panel_io_tx_param(s->io,LCD_CMD_RASET,rows,sizeof(rows))==ESP_OK &&
           esp_lcd_panel_io_tx_param(s->io,LCD_CMD_RAMWR,s->row,640)==ESP_OK;
}
bool lab_board_display_open(LabBoardDisplay *s,int profile) {
    if(!s || owner || profile!=LAB_DISPLAY_PROFILE_STOCK_0111 || s->ready || s->io || s->panel ||
       s->row || s->bus_owned || s->backlight_owned)return false;
    owner=s;
    s->backlight_owned=true;
    gpio_config_t light={.pin_bit_mask=1ull<<21,.mode=GPIO_MODE_OUTPUT,
        .pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    /* Set the output latch low before enabling the pin as an output. */
    if(gpio_set_level(21,0)!=ESP_OK || gpio_config(&light)!=ESP_OK)goto failure;
    spi_bus_config_t bus={.mosi_io_num=11,.miso_io_num=-1,.sclk_io_num=12,
        .quadwp_io_num=-1,.quadhd_io_num=-1,.data4_io_num=-1,.data5_io_num=-1,
        .data6_io_num=-1,.data7_io_num=-1,.max_transfer_sz=640};
    if(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_CH_AUTO)!=ESP_OK)goto failure;
    s->bus_owned=true;
    s->row=spi_bus_dma_memory_alloc(SPI2_HOST,640,MALLOC_CAP_INTERNAL);
    if(!s->row)goto failure;
    esp_lcd_panel_io_spi_config_t io={.cs_gpio_num=10,.dc_gpio_num=45,.spi_mode=0,
        .pclk_hz=80000000,.trans_queue_depth=1,.lcd_cmd_bits=8,.lcd_param_bits=8};
    if(esp_lcd_new_panel_io_spi(SPI2_HOST,&io,&s->io)!=ESP_OK || !s->io)goto failure;
    esp_lcd_panel_dev_config_t panel={.reset_gpio_num=46,.rgb_ele_order=LCD_RGB_ELEMENT_ORDER_RGB,
        .data_endian=LCD_RGB_DATA_ENDIAN_BIG,.bits_per_pixel=16};
    if(esp_lcd_new_panel_st7789(s->io,&panel,&s->panel)!=ESP_OK || !s->panel ||
       esp_lcd_panel_reset(s->panel)!=ESP_OK)goto failure;
    /* Stock's custom branch bypasses esp_lcd_panel_init; avoid extra register writes. */
    for(unsigned i=0;i<sizeof(custom_init)/sizeof(custom_init[0]);i++) {
        if(esp_lcd_panel_io_tx_param(s->io,custom_init[i].data[0],custom_init[i].data+1,
                                   custom_init[i].size-1)!=ESP_OK)goto failure;
        wait_ms(10);
        if(custom_init[i].delay_ms)wait_ms(custom_init[i].delay_ms);
    }
    if(esp_lcd_panel_invert_color(s->panel,true)!=ESP_OK ||
       esp_lcd_panel_swap_xy(s->panel,true)!=ESP_OK ||
       esp_lcd_panel_mirror(s->panel,false,true)!=ESP_OK ||
       esp_lcd_panel_set_gap(s->panel,0,0)!=ESP_OK)goto failure;
    memset(s->row,0,640);
    for(unsigned y=0;y<240;y++)if(!write_row(s,y))goto failure;
    wait_ms(100);
    if(gpio_set_level(21,1)!=ESP_OK)goto failure;
    s->ready=true;return true;
failure:
    lab_board_display_close(s);return false;
}
static bool failed(LabBoardDisplay *s) {
    s->ready=false;
    if(s->backlight_owned)gpio_set_level(21,0);
    return false;
}
bool lab_board_display_row(LabBoardDisplay *s,uint32_t y,const uint16_t pixels[320]) {
    if(!s || !s->ready || !pixels || y>=240)return false;
    for(unsigned x=0;x<320;x++) {
        s->row[2*x]=(uint8_t)(pixels[x]>>8);s->row[2*x+1]=(uint8_t)pixels[x];
    }
    return write_row(s,y) ? true : failed(s);
}
typedef struct {
    LabBoardDisplay *display;
    void (*service)(void *);
    void *context;
    unsigned rows;
} Scanout;
static bool sink(void *context,uint32_t y,const uint16_t pixels[320]) {
    Scanout *s=context;
    if(!lab_board_display_row(s->display,y,pixels))return false;
    if(++s->rows==8) {
        s->rows=0;
        if(s->service)s->service(s->context);
    }
    return true;
}
bool lab_board_display_paint_serviced(LabBoardDisplay *s,const LabHome *home,void (*service)(void *),void *context) {
    if(!s || !s->ready || !home)return false;
    Scanout scanout={.display=s,.service=service,.context=context};
    return lab_ui_render(home,sink,&scanout) ? true : failed(s);
}
bool lab_board_display_paint(LabBoardDisplay *s,const LabHome *home) {
    return lab_board_display_paint_serviced(s,home,NULL,NULL);
}
