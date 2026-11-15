#include "board_udp.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <string.h>
static int calls[10],fault,alive,connected,transient,partial,receive_bytes=-100;
static int hit(int stage){calls[stage]++;return fault==stage;}
static int test_socket(int family,int type,int protocol){assert(family==AF_INET && type==SOCK_DGRAM && protocol==IPPROTO_UDP);if(hit(1)){errno=ENOMEM;return -1;}alive=1;return 17;}
static int test_fcntl(int fd,int command,...){assert(fd==17 && alive);int stage=command==F_GETFL?2:3;if(command==F_SETFL){va_list args;va_start(args,command);assert(va_arg(args,int)&O_NONBLOCK);va_end(args);}if(hit(stage)){errno=EIO;return -1;}return command==F_GETFL?0:0;}
static int test_bind(int fd,const struct sockaddr *addr,socklen_t n){assert(fd==17 && alive && n==sizeof(struct sockaddr_in));const struct sockaddr_in *ip=(const void *)addr;assert(ip->sin_family==AF_INET && !ip->sin_port);if(hit(4)){errno=EIO;return -1;}return 0;}
static int test_connect(int fd,const struct sockaddr *addr,socklen_t n){assert(fd==17 && alive && n==sizeof(struct sockaddr_in));const struct sockaddr_in *ip=(const void *)addr;assert(ip->sin_port==htons(50000));assert(!memcmp(&ip->sin_addr.s_addr,(uint8_t[]){127,0,0,1},4));if(hit(5)){errno=EIO;return -1;}connected=1;return 0;}
static int test_getsockname(int fd,struct sockaddr *addr,socklen_t *n){assert(fd==17 && alive && *n>=sizeof(struct sockaddr_in));if(hit(6)){errno=EIO;return -1;}struct sockaddr_in ip={.sin_family=AF_INET,.sin_port=htons(50001)};memcpy(addr,&ip,sizeof(ip));*n=sizeof(ip);return 0;}
static ssize_t test_send(int fd,const void *p,size_t n,int flags){assert(fd==17 && alive && connected && p && n && n<=64 && !flags);hit(7);if(fault==7){errno=EIO;return -1;}if(transient){errno=EAGAIN;return -1;}return partial?2:(ssize_t)n;}
static ssize_t test_recv(int fd,void *p,size_t n,int flags){assert(fd==17 && alive && connected && n>1 && n<=65 && !flags);hit(8);if(fault==8){errno=EIO;return -1;}if(receive_bytes==-100){errno=EWOULDBLOCK;return -1;}size_t bytes=receive_bytes;if(bytes>n)bytes=n;memset(p,42,bytes);return (ssize_t)bytes;}
static int test_close(int fd){assert(fd==17 && alive);alive=connected=0;if(hit(9)){errno=EINTR;return -1;}return 0;}
#define socket test_socket
#define fcntl test_fcntl
#define bind test_bind
#define connect test_connect
#define getsockname test_getsockname
#define send test_send
#define recv test_recv
#define close test_close
#include "board_udp.c"
#undef socket
#undef fcntl
#undef bind
#undef connect
#undef getsockname
#undef send
#undef recv
#undef close
static LabUdpRoute route={.peer={127,0,0,1},.peer_port=50000};
int main(int argc,char **argv){(void)argc;LabBoardUdp s={0};uint8_t p[64]={1,2,3},out[64];
 if(!strcmp(argv[1],"invalid")){
  LabUdpRoute bad=route;bad.peer[0]=224;assert(!lab_board_udp_open(&s,&bad));bad=route;bad.local_port=80;
  assert(!lab_board_udp_open(&s,&bad));assert(lab_board_udp_send(&s,p,3)==-1);assert(lab_board_udp_close(&s));
  for(unsigned i=0;i<10;i++)assert(!calls[i]);
 }else if(!strcmp(argv[1],"open")){
  LabDatagramIo io=lab_board_udp_services(&s);assert(io.open(io.context,&route));assert(lab_board_udp_port(&s)==50001);
  assert(!io.open(io.context,&route));assert(calls[1]==1);assert(io.send(io.context,p,3)==3);
  assert(io.close(io.context));assert(lab_board_udp_port(&s)==0 && !alive);
 }else if(!strcmp(argv[1],"partial")){
  for(int stage=1;stage<=6;stage++){fault=stage;assert(!lab_board_udp_open(&s,&route));assert(!alive && !s.owned);fault=0;assert(lab_board_udp_close(&s));}
 }else if(!strcmp(argv[1],"receive")){
  assert(lab_board_udp_open(&s,&route));memset(out,77,64);assert(!lab_board_udp_receive(&s,out,64));
  for(unsigned i=0;i<64;i++)assert(!out[i]);receive_bytes=65;assert(lab_board_udp_receive(&s,out,64)==-2);
  for(unsigned i=0;i<64;i++)assert(!out[i]);receive_bytes=3;assert(lab_board_udp_receive(&s,out,64)==3 && out[0]==42 && !out[3]);
  assert(lab_board_udp_close(&s));
 }else if(!strcmp(argv[1],"backpressure")){
  assert(lab_board_udp_open(&s,&route));transient=1;assert(!lab_board_udp_send(&s,p,3));transient=0;
  assert(lab_board_udp_send(&s,p,3)==3);partial=1;assert(lab_board_udp_send(&s,p,3)==-1);
  int before=calls[7];assert(lab_board_udp_send(&s,p,3)==-1 && calls[7]==before);assert(lab_board_udp_close(&s));
 }else if(!strcmp(argv[1],"fatal")){
  assert(lab_board_udp_open(&s,&route));fault=8;assert(lab_board_udp_receive(&s,out,64)==-1);
  int before=calls[8];fault=0;assert(lab_board_udp_receive(&s,out,64)==-1 && calls[8]==before);assert(lab_board_udp_close(&s));
 }else if(!strcmp(argv[1],"close")){
  assert(lab_board_udp_open(&s,&route));fault=9;assert(!lab_board_udp_close(&s));assert(s.owned && !alive);
  int before=calls[9];fault=0;assert(!lab_board_udp_close(&s) && calls[9]==before);
  assert(!lab_board_udp_open(&s,&route) && calls[1]==1);
 }else return 2;return 0;
}
