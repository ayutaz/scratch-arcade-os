#include "lab_os.h"
#include "lab_digits.h"
static int32_t frequency,result,state;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){frequency=1000;result=0;state=-1;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return result;}
int32_t debug_x(void){return frequency;}
int32_t debug_y(void){return 0;}
int32_t debug_elapsed(void){return state;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;(void)dt;
 if(pressed&BACK)return 1;
 if((pressed&RIGHT)&&frequency<2000)frequency+=200;
 if((pressed&LEFT)&&frequency>200)frequency-=200;
 if(pressed&START)result=audio_tone(frequency,200);
 if(pressed&RESET)result=audio_stop();
 state=audio_state();
 rect(0,0,320,240,0);
 rect(20,20,280,16,state<0 ? 63488 : state ? 2016 : 31);
 lab_number(frequency/10,20,70);
 rect(20,170,280,12,10565);rect(20,170,frequency*280/2000,12,2016);
 return 0;
}
