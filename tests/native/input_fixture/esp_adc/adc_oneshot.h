#pragma once
#include "esp_err.h"
typedef int adc_unit_t;
typedef int adc_channel_t;
enum {ADC_UNIT_1=0,ADC_UNIT_2=1,ADC_ULP_MODE_DISABLE=0,ADC_ATTEN_DB_12=3,ADC_BITWIDTH_12=12};
typedef void *adc_oneshot_unit_handle_t;
typedef struct {adc_unit_t unit_id;int clk_src,ulp_mode;} adc_oneshot_unit_init_cfg_t;
typedef struct {int atten,bitwidth;} adc_oneshot_chan_cfg_t;
esp_err_t adc_oneshot_io_to_channel(int,adc_unit_t *,adc_channel_t *);
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *,adc_oneshot_unit_handle_t *);
esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t,adc_channel_t,const adc_oneshot_chan_cfg_t *);
esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t,adc_channel_t,int *);
esp_err_t adc_oneshot_del_unit(adc_oneshot_unit_handle_t);
