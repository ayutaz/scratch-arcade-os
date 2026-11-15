#include "lab_os.h"
#include "lab_digits.h"
static int32_t mode,result,state,peak;
static uint32_t waiting,total,gain;
static void multiplier(void){
 static const uint8_t masks[9]={63,6,91,79,102,109,125,7,127};
 uint8_t bits=masks[gain];
 for(int32_t i=0;i<5;i++){rect(20+i*2,108+i*2,2,2,65535);rect(28-i*2,108+i*2,2,2,65535);}
 if(bits&1)rect(46,104,8,2,65535);
 if(bits&2)rect(54,106,2,8,65535);
 if(bits&4)rect(54,116,2,8,65535);
 if(bits&8)rect(46,124,8,2,65535);
 if(bits&16)rect(44,116,2,8,65535);
 if(bits&32)rect(44,106,2,8,65535);
 if(bits&64)rect(46,114,8,2,65535);
}
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){mode=result=peak=0;state=0;waiting=total=0;gain=4;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return result;}
int32_t debug_x(void){return peak;}
int32_t debug_y(void){return mode;}
int32_t debug_elapsed(void){return state;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;
 if(pressed&BACK)return 1;
 state=audio_state();
 if(pressed&RESET){result=audio_stop();waiting=total=0;state=audio_state();}
 else {
  if(state<=0){
   waiting=0;
   if(pressed&RIGHT)mode=(mode+1)%3;
   else if(pressed&LEFT)mode=(mode+2)%3;
   if(pressed&UP){if(gain<8)gain*=2;}
   else if(pressed&DOWN){if(gain>1)gain/=2;}
   if(pressed&START){
    if(mode==2){result=audio_set_gain((int32_t)gain);if(result==1)result=audio_play();}
    else result=mode==0?audio_tone(1000,200):audio_record(500);
    if(result==1)total=mode==0?3200:8000;
    state=audio_state();
   }
  }else {
   waiting+=dt;
   if(waiting>=3000){audio_stop();result=-2;state=-1;waiting=total=0;}
  }
 }
 peak=audio_level();if(peak<0)peak=0;
 rect(0,0,320,240,0);
 for(int32_t i=0;i<3;i++)rect(20+i*96,8,84,8,i==mode?2016:10565);
 lab_number(mode+1,20,30);lab_number(peak/100,150,30);
 /* Replay multiplier: diagonal cross and number, distinct from peak/progress. */
 multiplier();
 rect(20,130,280,12,10565);
 int32_t width=peak*280/32768;if(width)rect(20,130,width,12,2016);
 rect(20,156,280,12,10565);
 int32_t position=audio_position();
 if(total && position>0){
  uint32_t done=(uint32_t)position;if(done>total)done=total;
  int32_t progress=(int32_t)(done*280/total);if(progress)rect(20,156,progress,12,2047);
 }
 rect(20,180,280,16,result<0||state<0?63488:state?65504:31);
 return 0;
}
