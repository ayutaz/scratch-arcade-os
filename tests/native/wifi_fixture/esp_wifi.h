#pragma once
#include "esp_event.h"
#include <stdint.h>
typedef int wifi_mode_t;
enum {WIFI_MODE_STA=1,WIFI_STORAGE_RAM=2,WIFI_IF_STA=0,WIFI_AUTH_WPA2_PSK=3,WIFI_EVENT_STA_START=1,WIFI_EVENT_STA_DISCONNECTED=2};
#define WIFI_EVENT_STA_STOP 3
typedef struct {int nvs_enable;} wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() {.nvs_enable=1}
typedef struct {uint8_t ssid[32],password[64];struct {int authmode;} threshold;} wifi_sta_config_t;
typedef union {wifi_sta_config_t sta;} wifi_config_t;
esp_err_t esp_wifi_get_mode(wifi_mode_t *);
esp_err_t esp_wifi_init(const wifi_init_config_t *);
esp_err_t esp_wifi_set_storage(int);
esp_err_t esp_wifi_set_mode(wifi_mode_t);
esp_err_t esp_wifi_set_config(int,wifi_config_t *);
esp_err_t esp_wifi_start(void);
esp_err_t esp_wifi_connect(void);
esp_err_t esp_wifi_stop(void);
esp_err_t esp_wifi_deinit(void);
