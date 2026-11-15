#include "network_binding.h"
#include <stddef.h>
bool lab_network_binding_open(LabNetworkBinding *s,LabDatagram *udp,uint32_t owner,uint32_t caps,
                              const LabUdpRoute *route,uint32_t now) {
    if(!s || s->datagram || !udp || udp->owner || !owner || caps>LAB_VM_CAP_ALL || !(caps&LAB_VM_CAP_NETWORK))return false;
    bool opened=lab_datagram_claim(udp,owner,route);
    if(udp->owner==owner)*s=(LabNetworkBinding){udp,owner,now};
    return opened;
}
bool lab_network_binding_close(LabNetworkBinding *s) {
    if(!s)return false;
    if(!s->datagram)return true;
    if(!lab_datagram_release(s->datagram,s->owner))return false;
    *s=(LabNetworkBinding){0};return true;
}
bool lab_network_binding_poll(LabNetworkBinding *s,uint32_t now) {
    if(!s || !s->datagram)return false;
    s->now=now;return lab_datagram_poll(s->datagram,s->owner,now);
}
int lab_network_binding_call(LabNetworkBinding *s,uint32_t op,uint8_t *p,uint32_t n) {
    if(!s || !s->datagram || s->datagram->owner!=s->owner)return -1;
    if(op==LAB_VM_NETWORK_SEND)return lab_datagram_send(s->datagram,s->owner,p,n,s->now);
    if(op==LAB_VM_NETWORK_RECEIVE)return lab_datagram_receive(s->datagram,s->owner,p,n);
    if(op==LAB_VM_NETWORK_STATE && !p && !n)return (int)s->datagram->phase;
    return -1;
}
static int command(void *s,uint32_t op,uint8_t *p,uint32_t n) {return lab_network_binding_call(s,op,p,n);}
LabVmNetwork lab_network_binding_services(LabNetworkBinding *s) {
    return s && s->datagram ? (LabVmNetwork){s,command} : (LabVmNetwork){0};
}
bool lab_network_manager_init(LabNetworkManager *s,LabDatagram *udp) {
    if(!s || s->datagram || !udp || !udp->ready || udp->owner)return false;
    *s=(LabNetworkManager){.datagram=udp};return true;
}
bool lab_network_manager_configure(LabNetworkManager *s,const LabUdpRoute *route) {
    if(!s || !s->datagram || s->lease_live || s->binding.datagram || s->datagram->owner ||
       (route && !lab_udp_route_valid(route)))return false;
    s->route=route ? *route : (LabUdpRoute){0};s->has_route=route!=NULL;return true;
}
void lab_network_manager_available(LabNetworkManager *s,bool available) {
    if(s && s->datagram)s->available=available;
}
static bool home_open(void *ctx,uint32_t caps,LabVmNetwork *out) {
    LabNetworkManager *s=ctx;
    if(!out || !s->available || !s->has_route || s->lease_live || s->binding.datagram)return false;
    s->lease_live=true;
    if(++s->next_owner==0)s->next_owner=1;
    if(!lab_network_binding_open(&s->binding,s->datagram,s->next_owner,caps,&s->route,s->now))return false;
    *out=lab_network_binding_services(&s->binding);return true;
}
static void home_poll(void *ctx,uint32_t now) {
    LabNetworkManager *s=ctx;s->now=now;
    if(!s->binding.datagram)return;
    if(!s->available || s->binding.datagram->phase==LAB_DATAGRAM_CLOSING)
        lab_network_binding_close(&s->binding);
    else lab_network_binding_poll(&s->binding,now);
}
static bool home_close(void *ctx) {
    LabNetworkManager *s=ctx;
    if(!lab_network_binding_close(&s->binding))return false;
    s->lease_live=false;return true;
}
LabHomeNetwork lab_network_manager_services(LabNetworkManager *s) {
    return s && s->datagram ? (LabHomeNetwork){s,home_open,home_poll,home_close} : (LabHomeNetwork){0};
}
