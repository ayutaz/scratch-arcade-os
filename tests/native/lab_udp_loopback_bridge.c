#include "board_udp.h"
#include <stdlib.h>
#include <string.h>
typedef struct {LabBoardUdp driver;LabDatagram service;} TestUdp;
void *test_udp_new(void){TestUdp *s=calloc(1,sizeof(*s));if(!s)return NULL;LabDatagramIo io=lab_board_udp_services(&s->driver);if(!lab_datagram_init(&s->service,&io)){free(s);return NULL;}return s;}
int test_udp_open(TestUdp *s,const uint8_t peer[4],uint16_t port){LabUdpRoute route={.peer_port=port};memcpy(route.peer,peer,4);return lab_datagram_claim(&s->service,7,&route);}
uint16_t test_udp_port(TestUdp *s){return lab_board_udp_port(&s->driver);}
int test_udp_send(TestUdp *s,const uint8_t *p,uint32_t n,uint32_t now){return lab_datagram_send(&s->service,7,p,n,now);}
int test_udp_receive(TestUdp *s,uint8_t *p,uint32_t n){return lab_datagram_receive(&s->service,7,p,n);}
int test_udp_poll(TestUdp *s,uint32_t now){return lab_datagram_poll(&s->service,7,now);}
int test_udp_free(TestUdp *s){bool ok=s->service.owner?lab_datagram_release(&s->service,7):lab_board_udp_close(&s->driver);if(ok)free(s);return ok;}
