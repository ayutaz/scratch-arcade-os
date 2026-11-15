#pragma once
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
typedef int esp_err_t;
typedef void *i2s_chan_handle_t;
#ifndef ESP_OK
#define ESP_OK 0
#endif
#ifndef ESP_FAIL
#define ESP_FAIL -1
#endif
#ifndef ESP_ERR_TIMEOUT
#define ESP_ERR_TIMEOUT 2
#endif
enum {I2S_NUM_0=0,I2S_ROLE_MASTER=1,I2S_DATA_BIT_WIDTH_16BIT=16,I2S_SLOT_MODE_MONO=1,I2S_GPIO_UNUSED=-1};
typedef struct {int id,role;unsigned dma_desc_num,dma_frame_num;bool auto_clear_after_cb,auto_clear_before_cb;} i2s_chan_config_t;
#define I2S_CHANNEL_DEFAULT_CONFIG(i,r) {.id=(i),.role=(r),.dma_desc_num=6,.dma_frame_num=240}
esp_err_t i2s_new_channel(const i2s_chan_config_t *,i2s_chan_handle_t *,i2s_chan_handle_t *);
esp_err_t i2s_channel_enable(i2s_chan_handle_t);
esp_err_t i2s_channel_disable(i2s_chan_handle_t);
esp_err_t i2s_del_channel(i2s_chan_handle_t);
esp_err_t i2s_channel_write(i2s_chan_handle_t,const void *,size_t,size_t *,uint32_t);
esp_err_t i2s_channel_read(i2s_chan_handle_t,void *,size_t,size_t *,uint32_t);

typedef struct {size_t size;} i2s_event_data_t;
typedef struct {bool (*on_sent)(i2s_chan_handle_t,i2s_event_data_t *,void *);} i2s_event_callbacks_t;
esp_err_t i2s_channel_register_event_callback(i2s_chan_handle_t,const i2s_event_callbacks_t *,void *);
