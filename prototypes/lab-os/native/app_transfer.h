#ifndef LAB_APP_TRANSFER_H
#define LAB_APP_TRANSFER_H
#include "app_store.h"

#define LAB_TRANSFER_PACKAGE 16384u
#define LAB_TRANSFER_PAYLOAD 516u
#define LAB_TRANSFER_FRAME (28u+LAB_TRANSFER_PAYLOAD)
typedef bool (*LabTransferSend)(void *,const uint8_t *,uint32_t);
/* Collector: -1 failed, 0 more, 1 done; fills four cumulative uint32 stats.
 * cancel releases its Store/FS maintenance ownership, without formatting. */
typedef int (*LabTransferCollect)(void *,uint32_t stats[4]);
typedef void (*LabTransferCancel)(void *);
/* Read-only, bounded wire provider: 1 success, 0 stale row, -1 failure.
 * Writes at most 80 bytes. No re-entry; context outlives Transfer. */
typedef int (*LabTransferTelemetry)(void *,uint32_t kind,uint32_t sequence,uint8_t out[80],uint32_t *length);
/* Trusted USB-only Wi-Fi control, never an app/WASM import. 1 success (8-byte
 * state/IPv4), 0 rejected, -1 error. START is a canonical 108-byte RAM-only
 * configuration, STATUS/STOP are 4 bytes. No reentry/retained payload pointer.
 * Controller owns radio lifetime independently of the USB session. */
typedef int (*LabTransferNetwork)(void *,const uint8_t *,uint32_t,uint32_t now,uint8_t out[8]);
/* Trusted USB test control: read-only STATUS, or bounded 20..250ms logical key
 * pulse. 1 success (80-byte snapshot), 0 rejected, -1 error. No GPIO writes,
 * WASM import, retained payload pointer or reentry. */
typedef int (*LabTransferControl)(void *,const uint8_t *,uint32_t,uint32_t now,uint8_t out[80]);
typedef struct {
    LabStore *store;LabHome *home;LabTransferSend send;void *context;
    LabTransferCollect collect;LabTransferCancel cancel;void *maintenance_context;
    LabTransferTelemetry telemetry;void *telemetry_context;
    LabTransferNetwork network;void *network_context;
    LabTransferControl control;void *control_context;
    uint32_t epoch;
    uint32_t nonce,session,last_session,last_request,activity,started,rx_started,beacon_at;
    uint32_t rx_size,previous_size,response_size,total,received;
    uint8_t rx[LAB_TRANSFER_FRAME],previous[LAB_TRANSFER_FRAME],response[207],digest[32];
    uint8_t *upload;
    bool ready,beacon_due,collecting,previous_private;
} LabTransfer;

/* init requires a fresh/closed object and Home initialized with this Store's
 * catalog. Close Transfer before Home/Store. Transport-free, single actor.
 * send consumes/copies the complete borrowed
 * frame before returning. No callbacks may re-enter this service. Caller polls
 * even on silence, uses monotonic uint32 milliseconds, and serializes Home/FS.
 * While busy, the UI should defer app launch. Each command also rechecks HOME.
 * 16KiB upload cap; idle 5s, absolute upload/collection 30s, partial frame 2s.
 * Optional COLLECT advances one maintenance step; other commands are blocked
 * until done/cancel. Retries replay ACKs without repeating collection work.
 * Optional TELEMETRY reads serial-numbered RAM samples even during an app,
 * upload or collection; it neither advances nor cancels those operations.
 * Optional NETWORK uses a trusted OS controller, not app imports. START/STOP
 * require HOME without upload/collection; STATUS remains read-only anywhere.
 * NETWORK requests retain only a SHA-256 retry fingerprint, never raw config.
 * CONTROL STATUS reads anywhere; PULSE rejects upload/collection, and a trusted
 * board provider cancels it on session/epoch change, timeout or physical input.
 * Owned RX is wiped on consumed frames, partial timeout and close. This does
 * not guarantee erasure of caller/SDK/kernel copies or native memory isolation.
 * CRC/SHA/nonce are corruption/stale-frame guards, not authentication. No raw Flash,
 * reset, REPL, GPIO, arbitrary file or shell command exists in this protocol. */
bool lab_transfer_init(LabTransfer *,LabStore *,LabHome *,LabTransferSend,void *,uint32_t nonce,uint32_t now);
bool lab_transfer_set_collector(LabTransfer *,LabTransferCollect,LabTransferCancel,void *);
bool lab_transfer_set_telemetry(LabTransfer *,LabTransferTelemetry,void *);
bool lab_transfer_set_network(LabTransfer *,LabTransferNetwork,void *);
bool lab_transfer_set_control(LabTransfer *,LabTransferControl,void *);
bool lab_transfer_feed(LabTransfer *,const uint8_t *,uint32_t bytes,uint32_t now);
bool lab_transfer_poll(LabTransfer *,uint32_t now);
bool lab_transfer_busy(const LabTransfer *);
void lab_transfer_close(LabTransfer *);
#endif
