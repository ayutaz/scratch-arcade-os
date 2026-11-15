#ifndef LAB_BOARD_WIFI_H
#define LAB_BOARD_WIFI_H
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"

enum {LAB_WIFI_COLD, LAB_WIFI_CONNECTING, LAB_WIFI_READY, LAB_WIFI_FAILED,
      LAB_WIFI_CLOSING};
typedef struct {
    uint8_t ssid[32], password[64];
    uint32_t ssid_bytes, password_bytes;
} LabWifiCredentials;
typedef struct {
    esp_netif_t *netif;
    esp_event_handler_instance_t wifi_handler, ip_handler;
    atomic_uint state, ipv4;
    atomic_bool pending, closing;
    uint32_t started, next_retry, attempts;
    bool initialized, attached, start_attempted, detach_failed;
} LabWifi;

/* Exclusive OS actor; fresh zeroed object, no concurrent API calls. SDK events
 * only update atomics. Object must outlive close(false). One owner; reject an
 * existing driver/default STA/AP. No scans, AP, GPIO settings or NVS writes.
 * SSID 1..32 bytes (no control/NUL); WPA2 passphrase 8..63 printable ASCII.
 * Caller retains and must wipe its credential copy. Driver stores configuration
 * in RAM; the temporary SDK config is wiped before start. No credential logs.
 * poll returns true while connecting/ready, false on timeout/error/closed;
 * caller polls frequently, with a monotonic uint32 millisecond clock.
 * Three attempts per outage, 1s backoff and a 30s deadline, wrap safe.
 * Shared event loop/netif core live for OS lifetime. close only releases own
 * driver/interface/handlers. Ambiguous SDK detach failure requires a reset:
 * repeated close remains false, never repeats a potentially unsafe detach. */
bool lab_wifi_open(LabWifi *, const LabWifiCredentials *, uint32_t now);
bool lab_wifi_poll(LabWifi *, uint32_t now);
bool lab_wifi_close(LabWifi *);
unsigned lab_wifi_status(const LabWifi *);
uint32_t lab_wifi_ipv4(const LabWifi *);
#endif
