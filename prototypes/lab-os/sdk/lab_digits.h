#ifndef LAB_DIGITS_H
#define LAB_DIGITS_H
#include "lab_os.h"

/* Small example asset: decimal digits made from existing rectangle commands. */
static inline void lab_digit(int32_t value,int32_t x,int32_t y) {
    static const uint8_t masks[10]={63,6,91,79,102,109,125,7,127,111};
    uint8_t bits=masks[value];
    if(bits&1)rect(x+6,y,24,6,65535);
    if(bits&2)rect(x+30,y+6,6,24,65535);
    if(bits&4)rect(x+30,y+36,6,24,65535);
    if(bits&8)rect(x+6,y+60,24,6,65535);
    if(bits&16)rect(x,y+36,6,24,65535);
    if(bits&32)rect(x,y+6,6,24,65535);
    if(bits&64)rect(x+6,y+30,24,6,65535);
}
static inline void lab_number(int32_t value,int32_t x,int32_t y) {
    if(value<0)value=0;if(value>999)value=999;
    if(value>=100){lab_digit(value/100,x,y);x+=44;}
    if(value>=10){lab_digit((value/10)%10,x,y);x+=44;}
    lab_digit(value%10,x,y);
}
#endif
