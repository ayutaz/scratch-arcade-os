#include "lab_os.h"
#include "lab_digits.h"
static int32_t value;
static uint32_t elapsed;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){value=0;elapsed=0;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return value;}
int32_t debug_x(void){return 0;}
int32_t debug_y(void){return 0;}
int32_t debug_elapsed(void){return (int32_t)elapsed;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;
 if(pressed&BACK)return 1;
 elapsed+=dt;
 if(pressed&RESET)value=0;
 if((pressed&RIGHT)&&value<200)value++;
 if((pressed&LEFT)&&value>0)value--;
 rect(0,0,320,240,0);rect(10,10,value+1,16,2016);
 lab_number(value,20,80);return 0;
}
