#include "board_network.h"
#include "network_wire.h"
#include <string.h>
static void wipe(void *ptr,uint32_t n) {volatile uint8_t *p=ptr;while(n--)*p++=0;}
static void put32(uint8_t *p,uint32_t v) {for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
bool lab_board_network_init(LabBoardNetwork *s) {
    if(!s || s->configured || s->cleanup || s->driver.initialized || s->driver.netif ||
       s->socket.owned || s->socket.ambiguous || s->udp.ready || s->manager.datagram)return false;
    LabDatagramIo io=lab_board_udp_services(&s->socket);
    if(!lab_datagram_init(&s->udp,&io))return false;
    if(!lab_network_manager_init(&s->manager,&s->udp)) {memset(&s->udp,0,sizeof(s->udp));return false;}
    s->configured=true;s->failed=false;return true;
}
LabHomeNetwork lab_board_network_apps(LabBoardNetwork *s) {
    return s && s->configured ? lab_network_manager_services(&s->manager) : (LabHomeNetwork){0};
}
static void status(LabBoardNetwork *s,uint8_t out[8]) {
    unsigned state=s->cleanup ? LAB_WIFI_CLOSING : s->failed ? LAB_WIFI_FAILED : lab_wifi_status(&s->driver);
    uint32_t ip=state==LAB_WIFI_READY ? lab_wifi_ipv4(&s->driver) : 0;
    /* A concurrent disconnect may clear IP after the state load. Report the
     * transition conservatively, never an invalid READY/zero-IP pair. */
    if(state==LAB_WIFI_READY && !ip)state=LAB_WIFI_CONNECTING;
    put32(out,state);put32(out+4,ip);
}
int lab_board_network_control(void *context,const uint8_t *p,uint32_t n,uint32_t now,uint8_t out[8]) {
    LabBoardNetwork *s=context;
    if(!s || !s->configured || !out || !lab_network_wire_valid(p,n))return 0;
    uint32_t op=lab_network_u32(p);
    if(op==LAB_NETWORK_CHANNEL_STATUS) {
        uint32_t phase=s->udp.owner ? s->udp.phase : LAB_DATAGRAM_IDLE;
        uint32_t port=phase==LAB_DATAGRAM_ACTIVE ? lab_board_udp_port(&s->socket) : 0;
        if(phase==LAB_DATAGRAM_ACTIVE && !port)phase=LAB_DATAGRAM_FAILED;
        put32(out,phase);put32(out+4,port);return 1;
    }
    if(!lab_network_wire_readonly(op) &&
       (s->manager.lease_live || s->manager.binding.datagram || s->udp.owner || s->socket.owned))return 0;
    if(op==LAB_NETWORK_START) {
        if(s->cleanup || lab_wifi_status(&s->driver)!=LAB_WIFI_COLD)return 0;
        lab_network_manager_available(&s->manager,false);
        LabWifiCredentials credentials={.ssid_bytes=lab_network_u32(p+4),.password_bytes=lab_network_u32(p+8)};
        memcpy(credentials.ssid,p+12,32);memcpy(credentials.password,p+44,64);
        bool opened=lab_wifi_open(&s->driver,&credentials,now);
        wipe(&credentials,sizeof(credentials));
        s->failed=!opened;s->cleanup=lab_wifi_status(&s->driver)==LAB_WIFI_CLOSING;
    } else if(op==LAB_NETWORK_STOP) {
        lab_network_manager_available(&s->manager,false);
        s->failed=false;s->cleanup=!lab_wifi_close(&s->driver);
    } else if(op==LAB_NETWORK_ROUTE) {
        LabUdpRoute route={.local_port=(uint16_t)lab_network_u32(p+8),.peer_port=(uint16_t)lab_network_u32(p+12)};
        memcpy(route.peer,p+4,4);
        if(!lab_network_manager_configure(&s->manager,&route))return 0;
    }
    status(s,out);return 1;
}
static bool close_app_socket(LabBoardNetwork *s,uint32_t now) {
    lab_network_manager_available(&s->manager,false);
    if(s->manager.binding.datagram) {
        LabHomeNetwork apps=lab_board_network_apps(s);apps.poll(apps.context,now);
    }
    return !s->udp.owner && !s->socket.owned;
}
void lab_board_network_poll(LabBoardNetwork *s,uint32_t now) {
    if(!s || !s->configured)return;
    if(s->cleanup) {
        if(close_app_socket(s,now))s->cleanup=!lab_wifi_close(&s->driver);
        return;
    }
    unsigned state=lab_wifi_status(&s->driver);
    if((state==LAB_WIFI_CONNECTING || state==LAB_WIFI_READY) && lab_wifi_poll(&s->driver,now)) {
        bool ready=lab_wifi_status(&s->driver)==LAB_WIFI_READY;
        lab_network_manager_available(&s->manager,ready);
        if(!ready)close_app_socket(s,now);
        return;
    }
    bool closed=close_app_socket(s,now);
    if(state!=LAB_WIFI_COLD) {
        s->failed=true;s->cleanup=true;
        if(closed)s->cleanup=!lab_wifi_close(&s->driver);
    }
}
bool lab_board_network_close(LabBoardNetwork *s) {
    if(!s)return false;
    if(!s->configured)return !s->cleanup && !s->driver.initialized && !s->driver.netif &&
        !s->socket.owned && !s->socket.ambiguous && !s->udp.owner && !s->manager.lease_live;
    lab_network_manager_available(&s->manager,false);
    if(s->manager.lease_live || s->manager.binding.datagram || s->udp.owner)return false;
    if(!lab_board_udp_close(&s->socket))return false;
    s->cleanup=!lab_wifi_close(&s->driver);
    if(s->cleanup)return false;
    s->configured=s->failed=false;
    memset(&s->udp,0,sizeof(s->udp));memset(&s->manager,0,sizeof(s->manager));return true;
}
