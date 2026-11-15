#include "board_udp.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <unistd.h>

static void wipe(void *ptr,uint32_t n) {volatile uint8_t *p=ptr;while(n--)*p++=0;}
bool lab_board_udp_close(LabBoardUdp *s) {
    if(!s)return false;
    s->ready=false;s->port=0;
    if(s->ambiguous)return false;
    if(!s->owned)return true;
    if(close(s->descriptor)!=0) {s->ambiguous=true;return false;}
    s->owned=false;s->descriptor=-1;return true;
}
uint16_t lab_board_udp_port(const LabBoardUdp *s) {return s && s->ready ? s->port : 0;}
bool lab_board_udp_open(LabBoardUdp *s,const LabUdpRoute *route) {
    if(!s || s->owned || s->ambiguous || !lab_udp_route_valid(route))return false;
    int fd=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
    if(fd<0)return false;
    s->descriptor=fd;s->owned=true;s->ready=false;
    int flags=fcntl(fd,F_GETFL,0);
    if(flags<0 || fcntl(fd,F_SETFL,flags|O_NONBLOCK)!=0)goto fail;
    struct sockaddr_in local={.sin_family=AF_INET,.sin_port=htons(route->local_port)};
    struct sockaddr_in peer={.sin_family=AF_INET,.sin_port=htons(route->peer_port)};
#if defined(__APPLE__) || defined(ESP_PLATFORM)
    local.sin_len=sizeof(local);peer.sin_len=sizeof(peer);
#endif
    memcpy(&peer.sin_addr.s_addr,route->peer,4);
    if(bind(fd,(const struct sockaddr *)&local,sizeof(local))!=0 ||
       connect(fd,(const struct sockaddr *)&peer,sizeof(peer))!=0)goto fail;
    socklen_t n=sizeof(local);
    if(getsockname(fd,(struct sockaddr *)&local,&n)!=0 || n!=sizeof(local) ||
       local.sin_family!=AF_INET || !local.sin_port)goto fail;
    s->port=ntohs(local.sin_port);s->ready=true;return true;
fail:
    lab_board_udp_close(s);return false;
}
static bool temporary(void) {return errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR;}
int lab_board_udp_send(LabBoardUdp *s,const uint8_t *p,uint32_t n) {
    if(!s || !s->owned || !s->ready || !p || !n || n>LAB_DATAGRAM_BYTES)return -1;
    ssize_t sent=send(s->descriptor,p,n,0);
    if(sent<0 && temporary())return 0;
    if(sent!=(ssize_t)n) {s->ready=false;return -1;}
    return (int)sent;
}
int lab_board_udp_receive(LabBoardUdp *s,uint8_t *out,uint32_t capacity) {
    if(!out || !capacity || capacity>LAB_DATAGRAM_BYTES)return -1;
    wipe(out,capacity);
    if(!s || !s->owned || !s->ready)return -1;
    uint8_t incoming[LAB_DATAGRAM_BYTES+1]={0};
    ssize_t n=recv(s->descriptor,incoming,capacity+1,0);
    bool transient=n<0 && temporary();
    if(n>0 && n<=(ssize_t)capacity)memcpy(out,incoming,(size_t)n);
    wipe(incoming,sizeof(incoming));
    if(transient || n==0)return 0;
    if(n>(ssize_t)capacity)return -2;
    if(n<0) {s->ready=false;return -1;}
    return (int)n;
}
static bool open_io(void *s,const LabUdpRoute *route) {return lab_board_udp_open(s,route);}
static bool close_io(void *s) {return lab_board_udp_close(s);}
static int send_io(void *s,const uint8_t *p,uint32_t n) {return lab_board_udp_send(s,p,n);}
static int receive_io(void *s,uint8_t *p,uint32_t n) {return lab_board_udp_receive(s,p,n);}
LabDatagramIo lab_board_udp_services(LabBoardUdp *s) {
    return s ? (LabDatagramIo){s,open_io,close_io,send_io,receive_io} : (LabDatagramIo){0};
}
