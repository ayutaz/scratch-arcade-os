#include "board_session.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include <stdlib.h>
#include <string.h>
LabStore *test_store_pointer(void *);
esp_err_t session_display_gpio_config(const gpio_config_t *);
esp_err_t session_display_gpio_set_level(gpio_num_t,uint32_t);
esp_err_t session_display_gpio_reset_pin(gpio_num_t);
esp_err_t session_input_gpio_config(const gpio_config_t *);
esp_err_t session_input_gpio_reset_pin(gpio_num_t);
void test_fault(int);
void test_audio_reset(void);void test_audio_fault(int);void test_audio_memory_reset(void);void test_audio_memory_fault(int,int);
void test_wifi_reset(void);void test_wifi_fault(int);
void test_display_fault(int,int);
static bool installed=true,reject_tx,audio_cleanup_failure,udp_cleanup_failure;
static uint8_t incoming[2048],outgoing[8192];
static uint32_t queued,written;
static int read_override,reads,writes,bad;
esp_err_t gpio_config(const gpio_config_t *p) {
 return p->pin_bit_mask==(1ull<<21) ? session_display_gpio_config(p) : session_input_gpio_config(p);
}
esp_err_t gpio_set_level(gpio_num_t pin,uint32_t level) {return session_display_gpio_set_level(pin,level);}
esp_err_t gpio_reset_pin(gpio_num_t pin) {
 return pin==21 ? session_display_gpio_reset_pin(pin) : session_input_gpio_reset_pin(pin);
}
bool usb_serial_jtag_is_driver_installed(void) {return installed;}
int usb_serial_jtag_read_bytes(void *p,uint32_t n,uint32_t ticks) {
 reads++;if(n!=128 || ticks)bad=1;
 if(read_override) {int result=read_override;read_override=0;return result;}
 if(n>queued)n=queued;memcpy(p,incoming,n);memmove(incoming,incoming+n,queued-n);queued-=n;return (int)n;
}
int usb_serial_jtag_write_bytes(const void *p,size_t n,uint32_t ticks) {
 writes++;if(n>207 || ticks!=pdMS_TO_TICKS(20) || n>sizeof(outgoing)-written)bad=1;
 if(reject_tx) {reject_tx=false;return 0;}
 if(n>sizeof(outgoing)-written)return 0;
 memcpy(outgoing+written,p,n);written+=n;return (int)n;
}
void test_session_usb_reset(void) {test_wifi_reset();test_audio_reset();test_audio_memory_reset();installed=true;reject_tx=false;audio_cleanup_failure=udp_cleanup_failure=false;queued=written=0;read_override=reads=writes=bad=0;}
void test_session_usb_installed(int value) {installed=value!=0;}
void test_session_usb_read_fault(int value) {read_override=value;}
void test_session_usb_reject_tx(void) {reject_tx=true;}
int test_session_enqueue(const uint8_t *p,uint32_t n) {
 if(n>sizeof(incoming)-queued)return 0;memcpy(incoming+queued,p,n);queued+=n;return 1;
}
uint32_t test_session_output(uint8_t *p,uint32_t max) {
 if(max<written)return 0;uint32_t n=written;memcpy(p,outgoing,n);written=0;return n;
}
void *test_session_new(void) {return calloc(1,sizeof(LabBoardSession));}
int test_session_open(LabBoardSession *s,void *fixture,int profile,uint32_t nonce,uint32_t now) {
 return lab_board_session_open(s,fixture ? test_store_pointer(fixture) : NULL,profile,nonce,now);
}
int test_session_step(LabBoardSession *s,uint32_t now) {return lab_board_session_step(s,now);}
int test_session_close(LabBoardSession *s) {return lab_board_session_close(s);}
void test_session_free(LabBoardSession *s) {
 audio_cleanup_failure=udp_cleanup_failure=false;test_wifi_fault(0);test_audio_fault(0);test_audio_memory_fault(0,0);test_fault(0);test_display_fault(-1,1);lab_home_close(&s->home);lab_board_session_close(s);free(s);
}
int test_session_metric(LabBoardSession *s,int i) {
 int values[]={s->ready,s->home.mode,(int)s->home.count,s->store && s->store->lease!=NULL,
 s->usb.active,s->usb.transfer.upload!=NULL,(int)s->usb.transfer.session,s->loop.gated,
 reads,writes,bad,(int)queued,s->store!=NULL};return values[i];
}
int test_session_value(LabBoardSession *s) {return lab_vm_debug(&s->home.vm,"debug_value");}

static int audio_stub(void *ctx,uint32_t op,uint32_t a,uint32_t b){(void)ctx;(void)op;(void)a;(void)b;return -1;}
static bool audio_acquire(void *ctx,uint32_t caps,LabVmAudio *out){(void)caps;*out=(LabVmAudio){ctx,audio_stub};return true;}
static void audio_poll(void *ctx,uint32_t now){(void)ctx;(void)now;}
static bool audio_release(void *ctx){(void)ctx;return !audio_cleanup_failure;}
int test_session_audio_hooks(LabBoardSession *s){LabHomeAudio io={s,audio_acquire,audio_poll,audio_release};return lab_home_set_audio(&s->home,&io);}
void test_session_audio_fault(int fail){audio_cleanup_failure=fail;}

unsigned test_session_sound_metric(LabBoardSession *s,unsigned which){return which==0 ? s->sound.frames : which==1 ? s->sound.audio.owner : which==2 ? s->sound.driver.channel!=NULL : which==3 ? s->sound.pcm.frames!=0 : which==4 ? s->home.notice : LAB_NOTICE_AUDIO;}
unsigned test_session_network_state(LabBoardSession *s){return s->network.configured ? lab_wifi_status(&s->network.driver) : 99;}
unsigned test_session_remote_metric(LabBoardSession *s,unsigned which){
 return which==0 ? s->remote.active : which==1 ? s->home.vm.held : s->remote.applied;
}
unsigned test_session_network_metric(LabBoardSession *s,unsigned which){switch(which){
 case 0:return s->network.udp.owner;case 1:return s->network.socket.owned;case 2:return lab_board_udp_port(&s->network.socket);
 case 3:return s->network.manager.binding.owner;case 4:return s->home.network.open!=NULL;
 case 5:return s->network.udp.rx_size;case 6:return s->network.manager.lease_live;case 7:return s->home.notice;
 default:return LAB_NOTICE_NETWORK;}}
static bool udp_close_fault(void *ctx){return !udp_cleanup_failure && lab_board_udp_close(ctx);}
void test_session_udp_fault(LabBoardSession *s,int fail){udp_cleanup_failure=fail;s->network.udp.io.close=udp_close_fault;}

/* Protocol fixture only: deterministic provider scalars, no recorded PCM. */
static int fixture_voice_snapshot(void *context,LabAudio *audio,uint32_t owner,uint32_t op,uint32_t field,uint32_t now){
 (void)now;
 if(context!=audio->voice_context || audio->owner!=owner || op!=LAB_AUDIO_VOICE_SNAPSHOT || field>17)return -1;
 if(!field)return 1;
 const uint32_t values[]={7,6,0,32000,1600,1600,1600,1600,0,0,0,1600,1600,1,3,1234};
 return field==17 ? (int32_t)audio->lease_generation:(int32_t)values[field-1];
}
int test_session_voice_fixture(LabBoardSession *s){return lab_board_sound_set_voice(&s->sound,s,fixture_voice_snapshot);}
