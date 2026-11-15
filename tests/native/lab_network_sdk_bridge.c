#include "guest_vm.h"
#include "network_binding.h"
#include <stdlib.h>
#include <string.h>
typedef struct {LabVm vm;LabDatagram udp;LabNetworkBinding binding;uint8_t sent[64],incoming[64];uint32_t sent_size,incoming_size,calls;int fail_close,forced,result;} Probe;
static _Alignas(8) uint8_t pool[196608];
static LabUdpRoute route={.peer={127,0,0,1},.peer_port=50000};
int test_runtime_start(void){return lab_runtime_init(pool,sizeof(pool));}
void test_runtime_stop(void){lab_runtime_destroy();}
static bool open_udp(void *p,const LabUdpRoute *r){(void)p;return r->peer_port==50000;}
static bool close_udp(void *p){return !((Probe *)p)->fail_close;}
static int send_udp(void *p,const uint8_t *data,uint32_t n){Probe *s=p;memcpy(s->sent,data,n);s->sent_size=n;return (int)n;}
static int receive_udp(void *p,uint8_t *data,uint32_t n){Probe *s=p;if(n<s->incoming_size)return -2;memcpy(data,s->incoming,s->incoming_size);uint32_t count=s->incoming_size;s->incoming_size=0;return (int)count;}
void *test_new(void){Probe *p=calloc(1,sizeof(*p));if(!p)return NULL;LabDatagramIo io={p,open_udp,close_udp,send_udp,receive_udp};
 if(!lab_datagram_init(&p->udp,&io)||!lab_network_binding_open(&p->binding,&p->udp,101,8,&route,0)){free(p);return NULL;}return p;}
void test_free(Probe *p){lab_vm_close(&p->vm,1);p->fail_close=0;lab_network_binding_close(&p->binding);if(p->udp.owner)lab_datagram_release(&p->udp,p->udp.owner);free(p);}
int test_command(Probe *p,uint32_t op,uint8_t *data,uint32_t n){p->calls++;if(p->forced){if(data && n)memset(data,0x33,n);return p->result;}return lab_network_binding_call(&p->binding,op,data,n);}
static int command(void *p,uint32_t op,uint8_t *data,uint32_t n){return test_command(p,op,data,n);}
int test_open(Probe *p,uint8_t *bytes,uint32_t n,uint32_t caps,int backend){LabVmNetwork net={p,command};return lab_vm_open_with_services(&p->vm,bytes,n,2,50000,caps,NULL,backend?&net:NULL);}
int test_frame(Probe *p){return lab_vm_frame(&p->vm,0,16);}
int test_debug(Probe *p,const char *name){return lab_vm_debug(&p->vm,name);}
void test_vm_close(Probe *p){lab_vm_close(&p->vm,1);}
int test_restart(Probe *p){p->calls=p->sent_size=p->incoming_size=0;p->forced=0;return lab_network_binding_close(&p->binding)&&lab_network_binding_open(&p->binding,&p->udp,101,8,&route,0);}
int test_poll(Probe *p,uint32_t now){return lab_network_binding_poll(&p->binding,now);}
uint32_t test_calls(Probe *p){return p->calls;}
uint32_t test_sent(Probe *p,uint8_t *out){memcpy(out,p->sent,p->sent_size);return p->sent_size;}
void test_inject(Probe *p,const uint8_t *bytes,uint32_t n){if(n<=64){memcpy(p->incoming,bytes,n);p->incoming_size=n;}}
void test_force(Probe *p,int result){p->forced=1;p->result=result;}
void test_fail_close(Probe *p,int fail){p->fail_close=fail;}
int test_release(Probe *p){return lab_network_binding_close(&p->binding);}
int test_other(Probe *p){return lab_datagram_claim(&p->udp,202,&route);}
int test_clean(Probe *p){for(unsigned i=0;i<64;i++)if(p->udp.tx[i]||p->udp.rx[i])return 0;return 1;}
int test_duplicate_binding(Probe *p){LabNetworkBinding other={0};bool opened=lab_network_binding_open(&other,&p->udp,101,8,&route,0);return !opened && !other.datagram;}
