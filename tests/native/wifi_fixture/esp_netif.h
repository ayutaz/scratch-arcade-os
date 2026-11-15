#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_WIFI_NOT_INIT 0x3001
typedef struct {int dummy;} esp_netif_t;
typedef struct {int station;} esp_netif_config_t;
#define ESP_NETIF_DEFAULT_WIFI_STA() {.station=1}
typedef struct {uint32_t addr;} esp_ip4_addr_t;
typedef struct {esp_ip4_addr_t ip;} esp_netif_ip_info_t;
typedef struct {esp_netif_t *esp_netif;esp_netif_ip_info_t ip_info;} ip_event_got_ip_t;
esp_err_t esp_netif_init(void);
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *);
esp_netif_t *esp_netif_new(const esp_netif_config_t *);
void esp_netif_destroy(esp_netif_t *);
