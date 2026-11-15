#include "board_input.h"
#include "driver/gpio.h"
#include <string.h>
/* Confirmed stock software settings: boards/scratch-arcade/profile.json. */
static const int key_pins[5]={0,39,5,9,4}; /* FN,A,B,X,Y */
bool lab_board_input_close(LabBoardInput *s) {
    if(!s)return false;
    s->ready=false;memset(&s->filter,0,sizeof(s->filter));
    for(unsigned i=0;i<5;i++) {
        uint64_t bit=1ull<<key_pins[i];
        if((s->gpio_owned&bit) && gpio_reset_pin((gpio_num_t)key_pins[i])==ESP_OK)s->gpio_owned&=~bit;
    }
    if(s->unit && adc_oneshot_del_unit(s->unit)==ESP_OK)s->unit=NULL;
    return !s->unit && !s->gpio_owned;
}
bool lab_board_input_open(LabBoardInput *s,int profile) {
    if(!s || profile!=LAB_INPUT_PROFILE_STOCK_0111 || s->ready || s->unit || s->gpio_owned)return false;
    adc_unit_t x_unit,y_unit;adc_channel_t x,y;
    if(adc_oneshot_io_to_channel(6,&x_unit,&x)!=ESP_OK ||
       adc_oneshot_io_to_channel(8,&y_unit,&y)!=ESP_OK || x_unit!=y_unit || x==y)return false;
    adc_oneshot_unit_init_cfg_t cfg={.unit_id=x_unit,.ulp_mode=ADC_ULP_MODE_DISABLE};
    adc_oneshot_chan_cfg_t channel={.atten=ADC_ATTEN_DB_12,.bitwidth=ADC_BITWIDTH_12};
    if(adc_oneshot_new_unit(&cfg,&s->unit)!=ESP_OK || !s->unit ||
       adc_oneshot_config_channel(s->unit,x,&channel)!=ESP_OK ||
       adc_oneshot_config_channel(s->unit,y,&channel)!=ESP_OK) {
        lab_board_input_close(s);return false;
    }
    for(unsigned i=0;i<5;i++)s->gpio_owned|=1ull<<key_pins[i];
    gpio_config_t pins={.pin_bit_mask=s->gpio_owned,.mode=GPIO_MODE_INPUT,
        .pull_up_en=GPIO_PULLUP_ENABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    if(gpio_config(&pins)!=ESP_OK) {lab_board_input_close(s);return false;}
    s->x_channel=x;s->y_channel=y;s->ready=true;return true;
}
bool lab_board_input_read(LabBoardInput *s,uint32_t now,LabInputSample *out) {
    if(!out)return false;
    memset(out,0,sizeof(*out));
    if(!s || !s->ready)return false;
    uint32_t keys=0;int x,y;
    for(unsigned i=0;i<5;i++) {
        int value=gpio_get_level((gpio_num_t)key_pins[i]);
        if(value!=0 && value!=1)goto failure;
        if(!value)keys|=1u<<i;
    }
    if(adc_oneshot_read(s->unit,s->x_channel,&x)!=ESP_OK ||
       adc_oneshot_read(s->unit,s->y_channel,&y)!=ESP_OK ||
       !lab_input_sample(&s->filter,keys,x,y,now,out))goto failure;
    return true;
failure:
    memset(&s->filter,0,sizeof(s->filter));return false;
}
