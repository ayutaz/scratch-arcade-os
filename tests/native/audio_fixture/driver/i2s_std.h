#pragma once
#include "i2s_common.h"
typedef struct {unsigned sample_rate_hz;} i2s_std_clk_config_t;
typedef struct {int data_bit_width,slot_mode;} i2s_std_slot_config_t;
typedef struct {int mclk,bclk,ws,dout,din;struct {unsigned mclk_inv,bclk_inv,ws_inv;} invert_flags;} i2s_std_gpio_config_t;
typedef struct {i2s_std_clk_config_t clk_cfg;i2s_std_slot_config_t slot_cfg;i2s_std_gpio_config_t gpio_cfg;} i2s_std_config_t;
#define I2S_STD_CLK_DEFAULT_CONFIG(r) {.sample_rate_hz=(r)}
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(b,m) {.data_bit_width=(b),.slot_mode=(m)}
esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t,const i2s_std_config_t *);
