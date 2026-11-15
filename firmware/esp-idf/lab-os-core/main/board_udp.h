#ifndef LAB_BOARD_UDP_H
#define LAB_BOARD_UDP_H
#include "udp_service.h"
typedef struct {int descriptor;uint16_t port;bool owned,ready,ambiguous;} LabBoardUdp;
/* Fresh zeroed object, exclusive OS actor. Caller supplies an OS-approved
 * numeric IPv4 route; no DNS/scanning/AP/Wi-Fi initialization. Connected UDP
 * filters peer address+port, but does not authenticate packets. open uses an
 * ephemeral port if local_port=0, no SO_REUSEADDR or foreign descriptor reuse.
 * Nonblocking send/receive only, 1..64-byte messages. receive returns -2 for
 * an oversized datagram and zeros unused/error output. Empty datagrams are
 * ignored. Socket queues/driver memory are separate from these payload bounds.
 * Any ambiguous close error retains ownership forever and never closes that
 * numeric descriptor again (it may already have been reused). Keep context
 * and block reuse; a reset is required. No automatic reset or flash operation. */
bool lab_board_udp_open(LabBoardUdp *,const LabUdpRoute *);
bool lab_board_udp_close(LabBoardUdp *);
uint16_t lab_board_udp_port(const LabBoardUdp *);
int lab_board_udp_send(LabBoardUdp *,const uint8_t *,uint32_t);
int lab_board_udp_receive(LabBoardUdp *,uint8_t *,uint32_t);
LabDatagramIo lab_board_udp_services(LabBoardUdp *);
#endif
