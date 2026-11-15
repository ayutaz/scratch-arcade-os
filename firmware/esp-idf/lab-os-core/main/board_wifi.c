#include "sdkconfig.h"
#include "board_wifi.h"
#include "esp_wifi_default.h"
#include <string.h>

#if !CONFIG_IDF_TARGET_ESP32S3
#error "Wi-Fi profile requires ESP32-S3"
#endif
#if CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE || CONFIG_ESP_WIFI_NVS_ENABLED || CONFIG_ESP_PHY_INIT_DATA_IN_PARTITION
#error "Wi-Fi profile requires volatile calibration/configuration and embedded PHY init data"
#endif
_Static_assert(ATOMIC_INT_LOCK_FREE == 2 && ATOMIC_BOOL_LOCK_FREE == 2,
               "event notifications require lock-free atomics");
static LabWifi *owner;

static bool valid(const LabWifiCredentials *c) {
    if (!c || !c->ssid_bytes || c->ssid_bytes > sizeof(c->ssid) ||
        c->password_bytes < 8 || c->password_bytes > 63) return false;
    for (unsigned i=0; i<c->ssid_bytes; ++i)
        if (c->ssid[i] < 32 || c->ssid[i] == 127) return false;
    for (unsigned i=0; i<c->password_bytes; ++i)
        if (c->password[i] < 32 || c->password[i] > 126) return false;
    return true;
}
static void wipe(void *ptr, size_t size) {
    volatile unsigned char *p=ptr;
    while (size--) *p++=0;
}
unsigned lab_wifi_status(const LabWifi *w) {
    return w ? atomic_load(&w->state) : LAB_WIFI_COLD;
}
uint32_t lab_wifi_ipv4(const LabWifi *w) {
    return w && lab_wifi_status(w)==LAB_WIFI_READY ? atomic_load(&w->ipv4) : 0;
}
static void stopped(LabWifi *w) {
    unsigned state=atomic_load(&w->state);
    while ((state==LAB_WIFI_CONNECTING || state==LAB_WIFI_READY) &&
           !atomic_compare_exchange_weak(&w->state,&state,LAB_WIFI_FAILED)) { }
    atomic_store(&w->ipv4,0);
    atomic_store(&w->pending,false);
}
static void event(void *ctx, esp_event_base_t base, int32_t id, void *data) {
    LabWifi *w=ctx;
    if (atomic_load(&w->closing)) return;
    unsigned state=atomic_load(&w->state);
    if (state!=LAB_WIFI_CONNECTING && state!=LAB_WIFI_READY) return;
    if (base==WIFI_EVENT && id==WIFI_EVENT_STA_STOP) {
        stopped(w);
    } else if (base==IP_EVENT && id==IP_EVENT_STA_LOST_IP && data) {
        const ip_event_got_ip_t *ip=data;
        if (ip->esp_netif==w->netif) stopped(w);
    } else if (base==WIFI_EVENT && (id==WIFI_EVENT_STA_START || id==WIFI_EVENT_STA_DISCONNECTED)) {
        if (id==WIFI_EVENT_STA_DISCONNECTED) {
            atomic_store(&w->ipv4,0);
            unsigned expected=LAB_WIFI_READY;
            atomic_compare_exchange_strong(&w->state,&expected,LAB_WIFI_CONNECTING);
        }
        if (lab_wifi_status(w)==LAB_WIFI_CONNECTING) atomic_store(&w->pending,true);
    } else if (base==IP_EVENT && id==IP_EVENT_STA_GOT_IP && data) {
        const ip_event_got_ip_t *ip=data;
        if (ip->esp_netif!=w->netif || !ip->ip_info.ip.addr) return;
        atomic_store(&w->ipv4,ip->ip_info.ip.addr);
        unsigned expected=LAB_WIFI_CONNECTING;
        if (atomic_compare_exchange_strong(&w->state,&expected,LAB_WIFI_READY))
            atomic_store(&w->pending,false);
        else if (expected!=LAB_WIFI_READY) atomic_store(&w->ipv4,0);
    }
}
bool lab_wifi_close(LabWifi *w) {
    if (!w) return false;
    if (owner!=w) return !w->initialized && !w->netif;
    atomic_store(&w->closing,true);
    atomic_store(&w->state,LAB_WIFI_CLOSING);
    atomic_store(&w->ipv4,0);
    atomic_store(&w->pending,false);
    if (w->detach_failed) return false;
    if (w->start_attempted) {
        esp_err_t err=esp_wifi_stop();
        if (err!=ESP_OK) return false;
        w->start_attempted=false;
    }
    if (w->wifi_handler) {
        if (esp_event_handler_instance_unregister(WIFI_EVENT,ESP_EVENT_ANY_ID,w->wifi_handler)!=ESP_OK)
            return false;
        w->wifi_handler=NULL;
    }
    if (w->ip_handler) {
        if (esp_event_handler_instance_unregister(IP_EVENT,ESP_EVENT_ANY_ID,w->ip_handler)!=ESP_OK)
            return false;
        w->ip_handler=NULL;
    }
    if (w->initialized) {
        if (esp_wifi_deinit()!=ESP_OK) return false;
        w->initialized=false;
    }
    if (w->attached) {
        /* IDF may free the driver even when this returns an error. Never retry. */
        if (esp_wifi_clear_default_wifi_driver_and_handlers(w->netif)!=ESP_OK) {
            w->detach_failed=true;
            return false;
        }
        w->attached=false;
    }
    if (w->netif) { esp_netif_destroy(w->netif); w->netif=NULL; }
    atomic_store(&w->state,LAB_WIFI_COLD);
    owner=NULL;
    return true;
}
bool lab_wifi_open(LabWifi *w, const LabWifiCredentials *c, uint32_t now) {
    if (!w || !valid(c) || owner || w->initialized || w->netif) return false;
    wifi_mode_t mode;
    if (esp_wifi_get_mode(&mode)!=ESP_ERR_WIFI_NOT_INIT) return false;
    /* IDF routes netif queries through TCP/IP IPC; querying before init may
     * wait on uninitialized semaphores. This idempotent core is OS-lifetime. */
    if (esp_netif_init()!=ESP_OK) return false;
    if (esp_netif_get_handle_from_ifkey("WIFI_STA_DEF") ||
        esp_netif_get_handle_from_ifkey("WIFI_AP_DEF")) return false;
    memset(w,0,sizeof(*w));
    atomic_init(&w->state,LAB_WIFI_CONNECTING);
    atomic_init(&w->ipv4,0);
    atomic_init(&w->pending,false);
    atomic_init(&w->closing,false);
    w->started=now; w->next_retry=now; owner=w;
    esp_err_t err=esp_event_loop_create_default();
    if (err!=ESP_OK && err!=ESP_ERR_INVALID_STATE) goto fail;
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable=0;
    if (esp_wifi_init(&init)!=ESP_OK) goto fail;
    w->initialized=true;
    if (esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK || esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK)
        goto fail;
    esp_netif_config_t netif_config=ESP_NETIF_DEFAULT_WIFI_STA();
    w->netif=esp_netif_new(&netif_config);
    if (!w->netif) goto fail;
    w->attached=true;
    if (esp_netif_attach_wifi_station(w->netif)!=ESP_OK ||
        esp_wifi_set_default_wifi_sta_handlers()!=ESP_OK) goto fail;
    if (esp_event_handler_instance_register(WIFI_EVENT,ESP_EVENT_ANY_ID,event,w,&w->wifi_handler)!=ESP_OK ||
        esp_event_handler_instance_register(IP_EVENT,ESP_EVENT_ANY_ID,event,w,&w->ip_handler)!=ESP_OK)
        goto fail;
    wifi_config_t config={0};
    memcpy(config.sta.ssid,c->ssid,c->ssid_bytes);
    memcpy(config.sta.password,c->password,c->password_bytes);
    config.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;
    err=esp_wifi_set_config(WIFI_IF_STA,&config);
    wipe(&config,sizeof(config));
    if (err!=ESP_OK) goto fail;
    w->start_attempted=true;
    if (esp_wifi_start()!=ESP_OK) goto fail;
    return true;
fail:
    lab_wifi_close(w);
    return false;
}
static bool fail_connect(LabWifi *w) {
    unsigned expected=LAB_WIFI_CONNECTING;
    if (atomic_compare_exchange_strong(&w->state,&expected,LAB_WIFI_FAILED)) {
        atomic_store(&w->pending,false);
        atomic_store(&w->ipv4,0);
        return false;
    }
    return expected==LAB_WIFI_READY;
}
bool lab_wifi_poll(LabWifi *w, uint32_t now) {
    if (!w || owner!=w) return false;
    unsigned state=lab_wifi_status(w);
    if (state==LAB_WIFI_READY) {
        w->attempts=0; w->started=now; w->next_retry=now;
        return true;
    }
    if (state!=LAB_WIFI_CONNECTING) return false;
    if ((uint32_t)(now-w->started)>=30000) return fail_connect(w);
    if (!atomic_load(&w->pending) || (int32_t)(now-w->next_retry)<0) return true;
    if (w->attempts>=3) return fail_connect(w);
    atomic_store(&w->pending,false);
    ++w->attempts;
    w->next_retry=now+1000;
    if (esp_wifi_connect()!=ESP_OK && lab_wifi_status(w)==LAB_WIFI_CONNECTING)
        atomic_store(&w->pending,true);
    return lab_wifi_status(w)!=LAB_WIFI_FAILED;
}
