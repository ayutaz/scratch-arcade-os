#include "board_audio.h"
#include "driver/i2s_std.h"
#include "driver/i2s_pdm.h"
#include <stddef.h>
#include <string.h>
#include "esp_attr.h"
_Static_assert(ATOMIC_INT_LOCK_FREE==2,"DMA callback needs lock-free 32-bit atomics");

static LabBoardAudio *owner;
static bool IRAM_ATTR sent(i2s_chan_handle_t channel,i2s_event_data_t *event,void *context) {
    LabBoardAudio *s=context;
    (void)event;
    if(s && channel==s->channel)atomic_fetch_add_explicit(&s->sent,1,memory_order_relaxed);
    return false;
}
bool lab_board_audio_close(LabBoardAudio *s) {
    if(!s)return false;
    s->ready=false;
    if(s->enabled) {
        if(i2s_channel_disable(s->channel)!=ESP_OK)return false;
        s->enabled=false;
    }
    if(s->channel) {
        if(i2s_del_channel(s->channel)!=ESP_OK)return false;
        s->channel=NULL;
    }
    s->mode=0;s->pending=false;s->drain_after=0;s->priming_remaining=0;
    if(owner==s)owner=NULL;
    return true;
}
bool lab_board_audio_open(LabBoardAudio *s,int profile,int mode) {
    if(!s || owner || s->channel || s->enabled || s->ready || s->mode ||
       profile!=LAB_AUDIO_PROFILE_STOCK_0111 ||
       (mode!=LAB_AUDIO_OUTPUT && mode!=LAB_AUDIO_INPUT))return false;
    owner=s;s->mode=mode;s->priming_remaining=0;atomic_init(&s->sent,0);
    i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);
    channel.dma_desc_num=4;channel.dma_frame_num=128;
    channel.auto_clear_after_cb=mode==LAB_AUDIO_OUTPUT;
    channel.auto_clear_before_cb=false;
    if(i2s_new_channel(&channel,mode==LAB_AUDIO_OUTPUT ? &s->channel : NULL,
                      mode==LAB_AUDIO_INPUT ? &s->channel : NULL)!=ESP_OK)goto failure;
    if(mode==LAB_AUDIO_OUTPUT) {
        const i2s_std_config_t cfg={
            .clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(16000),
            .slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_MONO),
            .gpio_cfg={.mclk=I2S_GPIO_UNUSED,.bclk=41,.ws=42,.dout=1,.din=I2S_GPIO_UNUSED}};
        if(i2s_channel_init_std_mode(s->channel,&cfg)!=ESP_OK)goto failure;
    } else {
        const i2s_pdm_rx_config_t cfg={
            .clk_cfg=I2S_PDM_RX_CLK_DEFAULT_CONFIG(16000),
            .slot_cfg=I2S_PDM_RX_SLOT_PCM_FMT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_MONO),
            .gpio_cfg={.clk=47,.din=48}};
        if(i2s_channel_init_pdm_rx_mode(s->channel,&cfg)!=ESP_OK)goto failure;
    }
    if(mode==LAB_AUDIO_OUTPUT) {
        const i2s_event_callbacks_t callbacks={.on_sent=sent};
        if(i2s_channel_register_event_callback(s->channel,&callbacks,s)!=ESP_OK)goto failure;
    }
    if(i2s_channel_enable(s->channel)!=ESP_OK)goto failure;
    s->enabled=true;s->ready=true;return true;
failure:
    lab_board_audio_close(s);return false;
}
static bool valid(LabBoardAudio *s,int mode,const void *buffer,uint32_t frames) {
    return s && owner==s && s->ready && s->enabled && s->channel && s->mode==mode &&
           buffer && frames && frames<=LAB_AUDIO_MAX_FRAMES;
}
static int result(LabBoardAudio *s,esp_err_t err,size_t bytes,uint32_t frames) {
    if((err!=ESP_OK && err!=ESP_ERR_TIMEOUT) || bytes>frames*2u || bytes%2u) {
        s->ready=false;return -1;
    }
    return (int)(bytes/2u);
}
int lab_board_audio_write(LabBoardAudio *s,const int16_t *pcm,uint32_t frames) {
    if(!valid(s,LAB_AUDIO_OUTPUT,pcm,frames))return -1;
    size_t bytes=0;
    esp_err_t err=i2s_channel_write(s->channel,pcm,frames*2u,&bytes,0);
    int count=result(s,err,bytes,frames);
    if(count>0) {
        s->drain_after=atomic_load_explicit(&s->sent,memory_order_relaxed)+5u;
        s->pending=true;
    }
    return count;
}
int lab_board_audio_read(LabBoardAudio *s,int16_t *pcm,uint32_t frames) {
    if(!valid(s,LAB_AUDIO_INPUT,pcm,frames))return -1;
    memset(pcm,0,frames*2u);
    size_t bytes=0;
    esp_err_t err=i2s_channel_read(s->channel,pcm,frames*2u,&bytes,0);
    int count=result(s,err,bytes,frames);
    if(count<0)memset(pcm,0,frames*2u);
    else {
        uint32_t discard=(uint32_t)count<s->priming_remaining ? (uint32_t)count:s->priming_remaining;
        s->priming_remaining-=discard;s->discarded_input_frames+=discard;count-=(int)discard;
        if(discard && count)memmove(pcm,pcm+discard,(uint32_t)count*2u);
        memset(pcm+count,0,(frames-(uint32_t)count)*2u);
    }
    return count;
}

int lab_board_audio_drained(LabBoardAudio *s) {
    if(!s || owner!=s || !s->ready || !s->enabled || s->mode!=LAB_AUDIO_OUTPUT)return -1;
    if(s->pending && (uint32_t)(atomic_load_explicit(&s->sent,memory_order_relaxed)-s->drain_after)<0x80000000u)
        s->pending=false;
    return s->pending ? 0 : 1;
}

static int service_open(void *s,int mode) {
    int opened=lab_board_audio_open(s,LAB_AUDIO_PROFILE_STOCK_0111,mode);
    if(opened==1 && mode==LAB_AUDIO_INPUT){
        LabBoardAudio *d=s;d->priming_remaining=1600;d->discarded_input_frames=0;
    }
    return opened;
}
static int service_read(void *s,int16_t *pcm,uint32_t frames) {return lab_board_audio_read(s,pcm,frames);}
static int service_write(void *s,const int16_t *pcm,uint32_t frames) {return lab_board_audio_write(s,pcm,frames);}
static int service_drained(void *s) {return lab_board_audio_drained(s);}
static int service_close(void *s) {return lab_board_audio_close(s);}
LabAudioIo lab_board_audio_services(LabBoardAudio *s) {
    if(!s)return (LabAudioIo){0};
    return (LabAudioIo){s,service_open,service_read,service_write,service_drained,service_close};
}
