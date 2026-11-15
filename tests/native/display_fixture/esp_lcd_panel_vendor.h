#pragma once
#include "esp_lcd_types.h"
typedef struct {
 int rgb_ele_order,data_endian;uint32_t bits_per_pixel;gpio_num_t reset_gpio_num;void *vendor_config;
 struct {uint32_t reset_active_high:1;} flags;
} esp_lcd_panel_dev_config_t;
esp_err_t esp_lcd_new_panel_st7789(esp_lcd_panel_io_handle_t,const esp_lcd_panel_dev_config_t *,esp_lcd_panel_handle_t *);
