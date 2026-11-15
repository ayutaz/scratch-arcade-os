#ifndef LAB_NETWORK_WIRE_H
#define LAB_NETWORK_WIRE_H
#include <stdbool.h>
#include <stdint.h>
enum {LAB_NETWORK_START=1,LAB_NETWORK_STATUS=2,LAB_NETWORK_STOP=3,LAB_NETWORK_ROUTE=4,LAB_NETWORK_CHANNEL_STATUS=5};
static inline uint32_t lab_network_u32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline bool lab_network_wire_readonly(uint32_t op) {
    return op==LAB_NETWORK_STATUS || op==LAB_NETWORK_CHANNEL_STATUS;
}
/* Canonical fixed-width request. Padding must be zero, so retries cannot hide
 * a second credential behind the declared lengths. No C strings/allocations. */
static inline bool lab_network_wire_valid(const uint8_t *p,uint32_t n) {
    if(!p || n<4)return false;
    uint32_t op=lab_network_u32(p);
    if(lab_network_wire_readonly(op) || op==LAB_NETWORK_STOP)return n==4;
    if(op==LAB_NETWORK_ROUTE) {
        if(n!=16 || !p[4] || p[4]>=224)return false;
        uint32_t local=lab_network_u32(p+8),remote=lab_network_u32(p+12);
        return (!local || (local>=1024 && local<=65535)) && remote && remote<=65535;
    }
    if(op!=LAB_NETWORK_START || n!=108)return false;
    uint32_t ssid=lab_network_u32(p+4),password=lab_network_u32(p+8);
    if(!ssid || ssid>32 || password<8 || password>63)return false;
    for(uint32_t i=0;i<32;i++) {
        uint8_t c=p[12+i];
        if(i<ssid ? (c<32 || c==127) : c!=0)return false;
    }
    for(uint32_t i=0;i<64;i++) {
        uint8_t c=p[44+i];
        if(i<password ? (c<32 || c>126) : c!=0)return false;
    }
    return true;
}
#endif
