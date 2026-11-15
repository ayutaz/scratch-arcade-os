#include "board_network.h"
#define main driver_contract_main
#include "lab_wifi_contract.c"
#undef main
static uint32_t value(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void packet(uint8_t p[108]){memset(p,0,108);put(p,1);put(p+4,8);put(p+8,13);memcpy(p+12,"lab-test",8);memcpy(p+44,"test-only-key",13);}
static void command(LabBoardNetwork *s,uint32_t op,uint8_t out[8],uint32_t now){uint8_t p[108];packet(p);put(p,op);assert(lab_board_network_control(s,p,op==1?108:4,now,out)==1);}
static int set_route(LabBoardNetwork *s,uint16_t port){uint8_t p[16]={4,0,0,0,127,0,0,1},out[8];put(p+12,port);return lab_board_network_control(s,p,16,0,out);}
static void ready_wifi(LabBoardNetwork *s){uint8_t out[8];command(s,1,out,0);start_event();lab_board_network_poll(s,0);ip_event(true);lab_board_network_poll(s,16);}
static bool fail_udp_close;
static bool (*actual_udp_close)(void *);
static bool close_udp(void *ctx){return !fail_udp_close && actual_udp_close(ctx);}
int main(int argc,char **argv){(void)argc;LabBoardNetwork s={0};uint8_t out[8],p[108];packet(p);
 if(!strcmp(argv[1],"lazy")){
  assert(lab_board_network_init(&s));for(unsigned i=0;i<24;i++)assert(!calls[i]);
  assert(lab_board_network_close(&s));for(unsigned i=0;i<24;i++)assert(!calls[i]);
 }else if(!strcmp(argv[1],"roundtrip")){
  assert(lab_board_network_init(&s));command(&s,1,out,0);assert(value(out)==LAB_WIFI_CONNECTING);
  start_event();lab_board_network_poll(&s,0);ip_event(true);lab_board_network_poll(&s,16);
  command(&s,2,out,17);assert(value(out)==LAB_WIFI_READY && value(out+4)==0x0a0200c0);
  assert(lab_board_network_control(&s,p,108,17,out)==0);assert(calls[4]==1);
  command(&s,3,out,18);assert(value(out)==LAB_WIFI_COLD && !value(out+4));assert(!active_driver && !netif_live);
  assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"timeout")){
  assert(lab_board_network_init(&s));command(&s,1,out,0);start_event();lab_board_network_poll(&s,0);
  lab_board_network_poll(&s,30000);assert(!active_driver && !netif_live);
  command(&s,2,out,30001);assert(value(out)==LAB_WIFI_FAILED && !value(out+4));
  command(&s,1,out,30002);assert(value(out)==LAB_WIFI_CONNECTING);assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"cleanup")){
  assert(lab_board_network_init(&s));command(&s,1,out,0);fault=15;command(&s,3,out,1);
  assert(value(out)==LAB_WIFI_CLOSING && active_driver);assert(!lab_board_network_close(&s));
  assert(lab_board_network_control(&s,p,108,2,out)==0);fault=0;lab_board_network_poll(&s,3);
  command(&s,2,out,4);assert(value(out)==LAB_WIFI_COLD);assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"invalid")){
  assert(lab_board_network_control(&s,p,108,0,out)==0);assert(lab_board_network_init(&s));
  assert(lab_board_network_control(NULL,p,108,0,out)==0);assert(lab_board_network_control(&s,NULL,108,0,out)==0);
  assert(lab_board_network_control(&s,p,107,0,out)==0);put(p+4,0);assert(lab_board_network_control(&s,p,108,0,out)==0);
  for(unsigned i=0;i<24;i++)assert(!calls[i]);assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"failed-open")){
  assert(lab_board_network_init(&s));fault=13;command(&s,1,out,0);assert(value(out)==LAB_WIFI_FAILED);
  assert(!active_driver && !netif_live);fault=0;command(&s,1,out,1);assert(value(out)==LAB_WIFI_CONNECTING);
  assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"route")){
  assert(lab_board_network_init(&s));assert(set_route(&s,50000)==1);
  LabHomeNetwork hooks=lab_board_network_apps(&s);LabVmNetwork net={0};
  assert(!hooks.open(hooks.context,8,&net));assert(hooks.close(hooks.context));
  for(unsigned i=0;i<24;i++)assert(!calls[i]);command(&s,5,out,0);assert(!value(out) && !value(out+4));
  ready_wifi(&s);assert(hooks.open(hooks.context,8,&net));command(&s,5,out,17);
  assert(value(out)==LAB_DATAGRAM_ACTIVE && value(out+4)>0 && value(out+4)<=65535);
  assert(!lab_board_network_close(&s));assert(active_driver);assert(hooks.close(hooks.context));assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"borrowed")){
  assert(lab_board_network_init(&s));assert(set_route(&s,50000));ready_wifi(&s);
  LabHomeNetwork hooks=lab_board_network_apps(&s);LabVmNetwork net={0};assert(hooks.open(hooks.context,8,&net));
  assert(!set_route(&s,50001));put(p,3);assert(lab_board_network_control(&s,p,4,17,out)==0);
  packet(p);assert(lab_board_network_control(&s,p,108,17,out)==0);assert(!lab_board_network_close(&s));
  assert(hooks.close(hooks.context));assert(set_route(&s,50001));assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"lost-link")){
  assert(lab_board_network_init(&s));assert(set_route(&s,50000));ready_wifi(&s);
  LabHomeNetwork hooks=lab_board_network_apps(&s);LabVmNetwork net={0};assert(hooks.open(hooks.context,8,&net));
  wifi_cb(wifi_ctx,WIFI_EVENT,WIFI_EVENT_STA_STOP,NULL);lab_board_network_poll(&s,17);
  assert(!s.socket.owned && !active_driver && !netif_live);assert(s.manager.lease_live);
  assert(net.call(net.context,LAB_VM_NETWORK_STATE,NULL,0)==-1);assert(!set_route(&s,50001));
  assert(hooks.close(hooks.context));assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"udp-cleanup")){
  assert(lab_board_network_init(&s));assert(set_route(&s,50000));ready_wifi(&s);
  LabHomeNetwork hooks=lab_board_network_apps(&s);LabVmNetwork net={0};assert(hooks.open(hooks.context,8,&net));
  actual_udp_close=s.udp.io.close;s.udp.io.close=close_udp;fail_udp_close=true;
  wifi_cb(wifi_ctx,WIFI_EVENT,WIFI_EVENT_STA_STOP,NULL);lab_board_network_poll(&s,17);
  assert(s.socket.owned && active_driver && !calls[18]);assert(!lab_board_network_close(&s));
  fail_udp_close=false;lab_board_network_poll(&s,18);assert(!s.socket.owned && !active_driver && calls[18]==1);
  assert(hooks.close(hooks.context));assert(lab_board_network_close(&s));
 }else if(!strcmp(argv[1],"reinit")){
  assert(lab_board_network_init(&s));assert(set_route(&s,50000));assert(lab_board_network_close(&s));
  assert(lab_board_network_init(&s));assert(!s.manager.has_route && !s.udp.owner && !s.socket.owned);
  assert(lab_board_network_close(&s));for(unsigned i=0;i<24;i++)assert(!calls[i]);
 }else return 2;return 0;
}
