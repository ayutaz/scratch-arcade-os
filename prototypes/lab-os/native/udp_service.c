#include "udp_service.h"
#include <string.h>
static void wipe(void *ptr,uint32_t n) {volatile uint8_t *p=ptr;while(n--)*p++=0;}
static bool owns(const LabDatagram *s,uint32_t owner) {return s && s->ready && owner && s->owner==owner;}
static bool active(const LabDatagram *s,uint32_t owner) {return owns(s,owner) && s->phase==LAB_DATAGRAM_ACTIVE;}
bool lab_datagram_init(LabDatagram *s,const LabDatagramIo *io) {
    if(!s || s->ready || s->owner || !io || !io->open || !io->close || !io->send || !io->receive)return false;
    LabDatagramIo copy=*io;
    memset(s,0,sizeof(*s));s->io=copy;s->ready=true;return true;
}
bool lab_datagram_release(LabDatagram *s,uint32_t owner) {
    if(!owns(s,owner))return false;
    wipe(s->tx,sizeof(s->tx));wipe(s->rx,sizeof(s->rx));s->tx_size=s->rx_size=0;
    s->phase=LAB_DATAGRAM_CLOSING;
    if(!s->io.close(s->io.context))return false;
    s->owner=s->queued_at=0;s->phase=LAB_DATAGRAM_IDLE;return true;
}
bool lab_datagram_claim(LabDatagram *s,uint32_t owner,const LabUdpRoute *route) {
    if(!s || !s->ready || s->owner || !owner || !lab_udp_route_valid(route))return false;
    s->owner=owner;
    if(!s->io.open(s->io.context,route)) {lab_datagram_release(s,owner);return false;}
    s->phase=LAB_DATAGRAM_ACTIVE;return true;
}
int lab_datagram_send(LabDatagram *s,uint32_t owner,const uint8_t *p,uint32_t n,uint32_t now) {
    if(!active(s,owner) || !p || !n || n>LAB_DATAGRAM_BYTES)return -1;
    if(s->tx_size)return 0;
    memcpy(s->tx,p,n);s->tx_size=n;s->queued_at=now;return 1;
}
int lab_datagram_receive(LabDatagram *s,uint32_t owner,uint8_t *p,uint32_t capacity) {
    if(!active(s,owner) || !p || !capacity || capacity>LAB_DATAGRAM_BYTES || capacity<s->rx_size)return -1;
    uint32_t n=s->rx_size;
    if(n) {memcpy(p,s->rx,n);wipe(s->rx,sizeof(s->rx));s->rx_size=0;}
    return (int)n;
}
static bool failed(LabDatagram *s) {s->phase=LAB_DATAGRAM_FAILED;return false;}
bool lab_datagram_poll(LabDatagram *s,uint32_t owner,uint32_t now) {
    if(!active(s,owner))return false;
    if(s->tx_size) {
        if((uint32_t)(now-s->queued_at)>=250)return failed(s);
        int n=s->io.send(s->io.context,s->tx,s->tx_size);
        if(n<0 || (n && (uint32_t)n!=s->tx_size))return failed(s);
        if(n) {wipe(s->tx,sizeof(s->tx));s->tx_size=0;}
    }
    if(!s->rx_size) {
        uint8_t incoming[LAB_DATAGRAM_BYTES]={0};
        int n=s->io.receive(s->io.context,incoming,sizeof(incoming));
        bool bad=n< -2 || n== -1 || n>(int)sizeof(incoming);
        if(n>0 && !bad) {memcpy(s->rx,incoming,n);s->rx_size=(uint32_t)n;}
        wipe(incoming,sizeof(incoming));
        if(bad)return failed(s);
    }
    return true;
}
