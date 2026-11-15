#pragma once
#include "esp_lcd_types.h"
#include "driver/spi_master.h"
typedef int esp_lcd_spi_bus_handle_t;
typedef struct {
 gpio_num_t cs_gpio_num,dc_gpio_num;int spi_mode;unsigned pclk_hz;size_t trans_queue_depth;
 void *on_color_trans_done,*user_ctx;int lcd_cmd_bits,lcd_param_bits;
 uint8_t cs_ena_pretrans,cs_ena_posttrans;
 struct {unsigned dc_high_on_cmd:1,dc_low_on_data:1,dc_low_on_param:1,octal_mode:1,quad_mode:1,sio_mode:1,psram_dma_direct:1,lsb_first:1,cs_high_active:1;} flags;
} esp_lcd_panel_io_spi_config_t;
esp_err_t esp_lcd_new_panel_io_spi(esp_lcd_spi_bus_handle_t,const esp_lcd_panel_io_spi_config_t *,esp_lcd_panel_io_handle_t *);
