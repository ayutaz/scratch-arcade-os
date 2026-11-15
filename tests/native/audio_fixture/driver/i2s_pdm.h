#pragma once
#include "i2s_common.h"
typedef struct {unsigned sample_rate_hz;} i2s_pdm_rx_clk_config_t;
typedef struct {int data_bit_width,slot_mode;} i2s_pdm_rx_slot_config_t;
typedef struct {int clk,din;struct {unsigned clk_inv;} invert_flags;} i2s_pdm_rx_gpio_config_t;
typedef struct {i2s_pdm_rx_clk_config_t clk_cfg;i2s_pdm_rx_slot_config_t slot_cfg;i2s_pdm_rx_gpio_config_t gpio_cfg;} i2s_pdm_rx_config_t;
#define I2S_PDM_RX_CLK_DEFAULT_CONFIG(r) {.sample_rate_hz=(r)}
#define I2S_PDM_RX_SLOT_PCM_FMT_DEFAULT_CONFIG(b,m) {.data_bit_width=(b),.slot_mode=(m)}
esp_err_t i2s_channel_init_pdm_rx_mode(i2s_chan_handle_t,const i2s_pdm_rx_config_t *);
