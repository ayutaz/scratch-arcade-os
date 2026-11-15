#include "lab_os.h"
#include "lab_digits.h"
static int32_t result,state,peak;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){result=0;state=-1;peak=0;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return result;}
int32_t debug_x(void){return peak;}
int32_t debug_y(void){return 0;}
int32_t debug_elapsed(void){return state;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;(void)dt;
 if(pressed&BACK)return 1;
 if(pressed&START)result=audio_record(500);
 if(pressed&RESET)result=audio_play();
 state=audio_state();peak=audio_level();if(peak<0)peak=0;
 rect(0,0,320,240,0);
 rect(20,20,280,16,state<0 ? 63488 : state ? 2016 : 31);
 lab_number(peak/100,20,70);
 rect(20,170,280,12,10565);
 int32_t width=peak*280/32768;if(width>0)rect(20,170,width,12,2016);
 return 0;
}
