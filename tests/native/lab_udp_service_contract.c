#include "udp_service.h"
#include <assert.h>
#include <string.h>
static int opened,closed,failed_open,failed_close,writes,reads,write_result=64,read_result;
static uint8_t sent[64],incoming[64];
static bool io_open(void *ctx,const LabUdpRoute *route){(void)ctx;assert(route->peer_port==50000);opened++;return !failed_open;}
static bool io_close(void *ctx){(void)ctx;closed++;return !failed_close;}
static int io_send(void *ctx,const uint8_t *p,uint32_t n){(void)ctx;writes++;memcpy(sent,p,n);return write_result==64?(int)n:write_result;}
static int io_receive(void *ctx,uint8_t *p,uint32_t n){(void)ctx;reads++;assert(n==64);if(read_result>0 && read_result<=64)memcpy(p,incoming,read_result);return read_result;}
static LabUdpRoute route={.peer={127,0,0,1},.peer_port=50000};
static void init(LabDatagram *s){LabDatagramIo io={NULL,io_open,io_close,io_send,io_receive};assert(lab_datagram_init(s,&io));}
static bool clear(const LabDatagram *s){for(unsigned i=0;i<64;i++)if(s->tx[i] || s->rx[i])return false;return true;}
int main(int argc,char **argv){(void)argc;LabDatagram s={0};uint8_t p[]={0,255,42},out[64];init(&s);
 if(!strcmp(argv[1],"lease")){
  assert(!opened && !closed);assert(!lab_datagram_claim(&s,0,&route));
  LabUdpRoute bad=route;bad.peer[0]=224;assert(!lab_datagram_claim(&s,1,&bad));assert(!opened);
  assert(lab_datagram_claim(&s,7,&route));assert(!lab_datagram_claim(&s,8,&route));
  assert(lab_datagram_send(&s,8,p,3,0)==-1);assert(!lab_datagram_release(&s,8));assert(!closed);
  assert(lab_datagram_release(&s,7));assert(!s.owner && closed==1 && clear(&s));
 }else if(!strcmp(argv[1],"bounded")){
  assert(lab_datagram_claim(&s,7,&route));assert(lab_datagram_send(&s,7,NULL,1,0)==-1);
  assert(lab_datagram_send(&s,7,p,0,0)==-1);assert(lab_datagram_send(&s,7,p,65,0)==-1);
  assert(lab_datagram_send(&s,7,p,3,0)==1);memset(p,77,3);
  assert(lab_datagram_send(&s,7,p,3,0)==0);write_result=0;assert(lab_datagram_poll(&s,7,1));assert(writes==1 && s.tx_size==3);
  write_result=64;assert(lab_datagram_poll(&s,7,2));assert(!memcmp(sent,(uint8_t[]){0,255,42},3));assert(!s.tx_size && clear(&s));
  assert(lab_datagram_release(&s,7));
 }else if(!strcmp(argv[1],"receive")){
  assert(lab_datagram_claim(&s,7,&route));memset(incoming,42,64);read_result=64;
  assert(lab_datagram_poll(&s,7,0));assert(reads==1 && s.rx_size==64);
  assert(lab_datagram_poll(&s,7,1));assert(reads==1);
  memset(out,17,64);assert(lab_datagram_receive(&s,7,out,63)==-1 && out[0]==17);
  assert(lab_datagram_receive(&s,7,out,64)==64 && !memcmp(out,incoming,64));assert(clear(&s));
  assert(lab_datagram_receive(&s,7,out,64)==0);assert(lab_datagram_release(&s,7));
 }else if(!strcmp(argv[1],"deadline")){
  assert(lab_datagram_claim(&s,7,&route));write_result=0;assert(lab_datagram_send(&s,7,p,3,0xfffffff0)==1);
  assert(lab_datagram_poll(&s,7,100));assert(!lab_datagram_poll(&s,7,234));
  int before=writes;assert(!lab_datagram_poll(&s,7,235));assert(writes==before);assert(lab_datagram_release(&s,7));
 }else if(!strcmp(argv[1],"partial")){
  failed_open=failed_close=1;assert(!lab_datagram_claim(&s,7,&route));assert(s.owner==7);
  assert(!lab_datagram_claim(&s,8,&route));assert(!lab_datagram_release(&s,7));
  failed_close=0;assert(lab_datagram_release(&s,7));assert(!s.owner);
 }else if(!strcmp(argv[1],"cleanup")){
  assert(lab_datagram_claim(&s,7,&route));lab_datagram_send(&s,7,p,3,0);read_result=3;lab_datagram_poll(&s,7,1);
  failed_close=1;assert(!lab_datagram_release(&s,7));assert(s.owner==7 && clear(&s));
  assert(!lab_datagram_claim(&s,8,&route));failed_close=0;assert(lab_datagram_release(&s,7));
  assert(lab_datagram_claim(&s,8,&route));assert(lab_datagram_receive(&s,8,out,64)==0);assert(lab_datagram_release(&s,8));
 }else if(!strcmp(argv[1],"malformed")){
  assert(lab_datagram_claim(&s,7,&route));read_result=-2;assert(lab_datagram_poll(&s,7,0));
  read_result=65;assert(!lab_datagram_poll(&s,7,1));assert(lab_datagram_send(&s,7,p,3,2)==-1);
  assert(lab_datagram_release(&s,7));assert(lab_datagram_claim(&s,8,&route));
  read_result=0;write_result=2;assert(lab_datagram_send(&s,8,p,3,0)==1);assert(!lab_datagram_poll(&s,8,1));
  assert(lab_datagram_release(&s,8));
 }else return 2;return 0;
}
