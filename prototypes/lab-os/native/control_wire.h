#ifndef LAB_CONTROL_WIRE_H
#define LAB_CONTROL_WIRE_H
#include <stdbool.h>
#include <stdint.h>
enum {LAB_CONTROL_STATUS=1,LAB_CONTROL_PULSE=2,LAB_CONTROL_AUDIO=3,LAB_CONTROL_AUDIO_METRICS=4,LAB_CONTROL_VOICE=5};
static inline uint32_t lab_control_u32(const uint8_t *p){
 return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline bool lab_control_wire_valid(const uint8_t *p,uint32_t n){
 if(!p || n<4)return false;
 uint32_t op=lab_control_u32(p);
 if(op==LAB_CONTROL_STATUS || op==LAB_CONTROL_AUDIO || op==LAB_CONTROL_AUDIO_METRICS || op==LAB_CONTROL_VOICE)return n==4;
 return op==LAB_CONTROL_PULSE && n==12 && lab_control_u32(p+4)<=255 &&
        lab_control_u32(p+8)>=20 && lab_control_u32(p+8)<=250;
}
#endif
