#ifndef LAB_UDP_SERVICE_H
#define LAB_UDP_SERVICE_H
#include <stdbool.h>
#include <stdint.h>
#define LAB_DATAGRAM_BYTES 64u
typedef struct {uint8_t peer[4];uint16_t local_port,peer_port;} LabUdpRoute;
static inline bool lab_udp_route_valid(const LabUdpRoute *p) {
    return p && p->peer[0] && p->peer[0]<224 && p->peer_port &&
        (!p->local_port || p->local_port>=1024);
}
/* Trusted nonblocking I/O. open/close are serialized OS lifecycle operations.
 * close(false) retains context/ownership; repeat calls must be safe even if
 * they can never recover. send: n bytes accepted, 0 backpressure, -1 fatal.
 * receive: 1..capacity bytes, 0 none/empty, -2 discarded oversized datagram,
 * -1 fatal. Never write beyond capacity. This is a native trust boundary. */
typedef struct {
    void *context;
    bool (*open)(void *,const LabUdpRoute *);
    bool (*close)(void *);
    int (*send)(void *,const uint8_t *,uint32_t);
    int (*receive)(void *,uint8_t *,uint32_t);
} LabDatagramIo;
enum {LAB_DATAGRAM_IDLE,LAB_DATAGRAM_ACTIVE,LAB_DATAGRAM_FAILED,LAB_DATAGRAM_CLOSING};
typedef struct {
    LabDatagramIo io;
    uint32_t owner,phase,queued_at,tx_size,rx_size;
    uint8_t tx[LAB_DATAGRAM_BYTES],rx[LAB_DATAGRAM_BYTES];
    bool ready;
} LabDatagram;
/* One OS-provided route and one app owner, no heap. No socket/GPIO at init.
 * Per poll <=1 send and <=1 receive. One pending TX and RX, each 1..64 bytes.
 * Copy before returning; short RX destination retains the pending packet.
 * TX backpressure expires at 250ms, wrap-safe. Fatal I/O stops further I/O.
 * Release wipes both queues even if close fails, retaining owner until safe.
 * Stop the guest before release. Socket/driver/task memory is additional and
 * is not bounded by these two buffers. No crypto/authentication guarantee. */
bool lab_datagram_init(LabDatagram *,const LabDatagramIo *);
bool lab_datagram_claim(LabDatagram *,uint32_t owner,const LabUdpRoute *);
int lab_datagram_send(LabDatagram *,uint32_t owner,const uint8_t *,uint32_t,uint32_t now);
int lab_datagram_receive(LabDatagram *,uint32_t owner,uint8_t *,uint32_t capacity);
bool lab_datagram_poll(LabDatagram *,uint32_t owner,uint32_t now);
bool lab_datagram_release(LabDatagram *,uint32_t owner);
#endif
