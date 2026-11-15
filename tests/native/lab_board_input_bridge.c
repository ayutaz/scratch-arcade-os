#include "board_input.h"
#include "driver/gpio.h"
#include <stdlib.h>
#include <string.h>
static int stage,keys,x=2048,y=2048,bad,calls[8];
static uint64_t mask;
static const int pins[5]={0,39,5,9,4};
esp_err_t adc_oneshot_io_to_channel(int pin,adc_unit_t *unit,adc_channel_t *channel) {
    calls[0]++;if(pin!=6 && pin!=8)bad=1;
    if(stage==1 && pin==8)return ESP_FAIL;
    *unit=stage==5 && pin==8 ? ADC_UNIT_2 : ADC_UNIT_1;*channel=pin==6 ? 5 : 7;return ESP_OK;
}
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *cfg,adc_oneshot_unit_handle_t *out) {
    calls[1]++;if(cfg->unit_id!=ADC_UNIT_1 || cfg->ulp_mode!=ADC_ULP_MODE_DISABLE || cfg->clk_src)bad=1;
    if(stage==2)return ESP_FAIL;
    *out=(void *)0x1234;return ESP_OK;
}
esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t h,adc_channel_t c,const adc_oneshot_chan_cfg_t *cfg) {
    calls[2]++;if(h!=(void *)0x1234 || (c!=5 && c!=7) || cfg->atten!=3 || cfg->bitwidth!=12)bad=1;
    return stage==3 && c==7 ? ESP_FAIL : ESP_OK;
}
esp_err_t gpio_config(const gpio_config_t *cfg) {
    calls[3]++;mask=cfg->pin_bit_mask;
    if(cfg->mode!=GPIO_MODE_INPUT || cfg->pull_up_en!=GPIO_PULLUP_ENABLE ||
       cfg->pull_down_en!=GPIO_PULLDOWN_DISABLE || cfg->intr_type!=GPIO_INTR_DISABLE)bad=1;
    return stage==4 ? ESP_FAIL : ESP_OK;
}
esp_err_t gpio_reset_pin(gpio_num_t pin) {
    calls[4]++;bool found=false;for(unsigned i=0;i<5;i++)if(pin==pins[i])found=true;
    if(!found)bad=1;
    return stage==8 && pin==9 ? ESP_FAIL : ESP_OK;
}
esp_err_t adc_oneshot_del_unit(adc_oneshot_unit_handle_t h) {
    calls[5]++;if(h!=(void *)0x1234)bad=1;
    return stage==7 ? ESP_FAIL : ESP_OK;
}
esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t h,adc_channel_t c,int *out) {
    calls[6]++;if(h!=(void *)0x1234 || (c!=5 && c!=7))bad=1;
    if(stage==6 && c==7)return ESP_FAIL;
    *out=c==5 ? x : y;return ESP_OK;
}
int gpio_get_level(gpio_num_t pin) {
    calls[7]++;for(unsigned i=0;i<5;i++)if(pin==pins[i])return stage==10 ? -1 : !(keys&(1u<<i));
    bad=1;return -1;
}
void test_reset(void) {stage=keys=bad=0;x=y=2048;mask=0;memset(calls,0,sizeof(calls));}
void test_fault(int value) {stage=value;}
void test_values(int k,int a,int b) {keys=k;x=a;y=b;}
int test_calls(int index) {return calls[index];}
int test_bad(void) {return bad;}
uint64_t test_mask(void) {return mask;}
void *test_driver_new(void) {return calloc(1,sizeof(LabBoardInput));}
void test_driver_free(LabBoardInput *s) {stage=0;lab_board_input_close(s);free(s);}
int test_driver_open(LabBoardInput *s,int profile) {return lab_board_input_open(s,profile);}
int test_driver_read(LabBoardInput *s,uint32_t now,LabInputSample *out) {return lab_board_input_read(s,now,out);}
int test_driver_close(LabBoardInput *s) {return lab_board_input_close(s);}
