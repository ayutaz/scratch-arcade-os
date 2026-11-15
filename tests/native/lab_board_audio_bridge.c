#include "board_audio.h"
#include "driver/i2s_std.h"
#include "driver/i2s_pdm.h"
#include <stdlib.h>
#include <string.h>
static bool auto_io;static int fault,bad,calls[9],input;static int response;static size_t transferred;
static bool paced_audio,hardware_enabled;static unsigned available_frames,dropped_frames,arrival_remainder;
static bool paced_output;static unsigned output_budget;
void test_output_budget(unsigned frames){paced_output=true;output_budget=frames;}
void test_audio_paced(int value){paced_audio=value!=0;available_frames=dropped_frames=arrival_remainder=0;}
void test_audio_advance_us(unsigned us){
 if(!paced_audio || !input || !hardware_enabled)return;
 unsigned value=arrival_remainder+us*16;available_frames+=value/1000;arrival_remainder=value%1000;
 if(available_frames>512){dropped_frames+=available_frames-512;available_frames=512;}
}
unsigned test_audio_dropped(void){return dropped_frames;}
static int pins[5];static int token;static i2s_event_callbacks_t callbacks;static void *user;
void test_reset(void){paced_output=false;output_budget=0;paced_audio=hardware_enabled=false;available_frames=dropped_frames=arrival_remainder=0;fault=bad=input=response=0;auto_io=false;transferred=0;memset(&callbacks,0,sizeof(callbacks));user=NULL;memset(calls,0,sizeof(calls));memset(pins,0,sizeof(pins));}
void test_fault(int n){fault=n;}
void test_io(int code,unsigned n){response=code;transferred=n;}
int test_calls(int i){return calls[i];}int test_bad(void){return bad;}int test_pin(int i){return pins[i];}
void *test_new(void){return calloc(1,sizeof(LabBoardAudio));}
void test_free(void *s){fault=0;lab_board_audio_close(s);free(s);}
int test_open(void *s,int profile,int mode){return lab_board_audio_open(s,profile,mode);}
int test_close(void *s){return lab_board_audio_close(s);}
int test_write(void *s,const int16_t *p,unsigned n){return lab_board_audio_write(s,p,n);}
int test_read(void *s,int16_t *p,unsigned n){return lab_board_audio_read(s,p,n);}
int test_ready(void *s){return ((LabBoardAudio *)s)->ready;}
int test_service_open(void *s,int mode){LabAudioIo io=lab_board_audio_services(s);return io.open(io.context,mode);}
unsigned test_priming_left(void *s){return ((LabBoardAudio *)s)->priming_remaining;}
esp_err_t i2s_new_channel(const i2s_chan_config_t *c,i2s_chan_handle_t *tx,i2s_chan_handle_t *rx){
 calls[0]++;if((!tx)==(!rx)||c->id!=0||c->role!=I2S_ROLE_MASTER||c->dma_desc_num!=4||c->dma_frame_num!=128||c->auto_clear_before_cb)bad=1;
 input=rx!=NULL;if(c->auto_clear_after_cb==input)bad=1;
 if(fault==1)return ESP_FAIL;if(tx)*tx=&token;if(rx)*rx=&token;return ESP_OK;
}
esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t h,const i2s_std_config_t *c){
 calls[1]++;if(h!=&token||input||c->clk_cfg.sample_rate_hz!=16000||c->slot_cfg.data_bit_width!=16||c->slot_cfg.slot_mode!=1||c->gpio_cfg.invert_flags.mclk_inv||c->gpio_cfg.invert_flags.bclk_inv||c->gpio_cfg.invert_flags.ws_inv)bad=1;
 pins[0]=c->gpio_cfg.bclk;pins[1]=c->gpio_cfg.ws;pins[2]=c->gpio_cfg.dout;pins[3]=c->gpio_cfg.mclk;pins[4]=c->gpio_cfg.din;return fault==2?ESP_FAIL:ESP_OK;
}
esp_err_t i2s_channel_init_pdm_rx_mode(i2s_chan_handle_t h,const i2s_pdm_rx_config_t *c){
 calls[2]++;if(h!=&token||!input||c->clk_cfg.sample_rate_hz!=16000||c->slot_cfg.data_bit_width!=16||c->slot_cfg.slot_mode!=1||c->gpio_cfg.invert_flags.clk_inv)bad=1;
 pins[0]=c->gpio_cfg.clk;pins[1]=c->gpio_cfg.din;return fault==3?ESP_FAIL:ESP_OK;
}
esp_err_t i2s_channel_enable(i2s_chan_handle_t h){calls[3]++;if(h!=&token)bad=1;if(fault==4)return ESP_FAIL;hardware_enabled=true;return ESP_OK;}
esp_err_t i2s_channel_disable(i2s_chan_handle_t h){calls[6]++;if(h!=&token)bad=1;if(fault==7)return ESP_FAIL;hardware_enabled=false;return ESP_OK;}
esp_err_t i2s_del_channel(i2s_chan_handle_t h){calls[7]++;if(h!=&token)bad=1;return fault==8?ESP_FAIL:ESP_OK;}
esp_err_t i2s_channel_write(i2s_chan_handle_t h,const void *p,size_t n,size_t *done,uint32_t timeout){
 calls[5]++;if(h!=&token||input||!p||n>512||timeout)bad=1;*done=auto_io ? n : transferred;
 if(paced_output){size_t frames=*done/2;if(frames>output_budget)frames=output_budget;*done=frames*2;output_budget-=(unsigned)frames;}
 return response;
}
esp_err_t i2s_channel_read(i2s_chan_handle_t h,void *p,size_t n,size_t *done,uint32_t timeout){
 calls[4]++;if(h!=&token||!input||!p||n>512||timeout)bad=1;
 int16_t values[]={10,-20,30};memcpy(p,values,n<sizeof(values)?n:sizeof(values));*done=auto_io ? n : transferred;
 if(paced_audio){size_t frames=n/2;if(frames>available_frames)frames=available_frames;*done=frames*2;available_frames-=(unsigned)frames;}
 return response;
}

esp_err_t i2s_channel_register_event_callback(i2s_chan_handle_t h,const i2s_event_callbacks_t *c,void *u){
 calls[8]++;if(h!=&token || input || !c || !c->on_sent || !u)bad=1;
 if(fault==9)return ESP_FAIL;callbacks=*c;user=u;return ESP_OK;
}
void test_sent(unsigned n){i2s_event_data_t event={.size=256};for(unsigned i=0;i<n;i++)if(callbacks.on_sent)callbacks.on_sent(&token,&event,user);}
int test_drained(void *s){return lab_board_audio_drained(s);}

void test_auto_io(int enabled){auto_io=enabled;}
