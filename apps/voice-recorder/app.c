#include "lab_os.h"
#include "lab_digits.h"
#include "lab_labels.h"
static int32_t result,peak,state;
static uint32_t position,waiting,kind,recorded;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){result=peak=state=0;position=waiting=kind=recorded=0;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return result;}
int32_t debug_x(void){return peak;}
int32_t debug_y(void){return (int32_t)recorded;}
int32_t debug_elapsed(void){return (int32_t)position;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;
 if(pressed&BACK)return 1;
 state=audio_state();int32_t frames=audio_position();position=frames>0?(uint32_t)frames:0;
 if(position>32000)position=32000;
 if(state==0 && kind==2 && position==32000)recorded=1;
 if(pressed&DOWN){result=audio_stop();waiting=kind=recorded=position=0;state=audio_state();}
 else if(state<=0){
  waiting=0;
  if(pressed&START){
   result=audio_record(2000);
   if(result==1){kind=2;recorded=position=0;}state=audio_state();
  }else if((pressed&RESET) && recorded){
   result=audio_set_gain(4);if(result==1)result=audio_play();
   if(result==1){kind=1;position=0;}state=audio_state();
  }
 }else{
  waiting+=dt;
  if(waiting>=4000){audio_stop();result=-2;state=-1;waiting=kind=recorded=position=0;}
 }
 peak=audio_level();if(peak<0)peak=0;
 rect(0,0,320,240,0);
 lab_number((int32_t)((32000-position+15999)/16000),136,35);
 rect(20,120,280,12,10565);int32_t level=peak*280/32768;
 if(level)rect(20,120,level,12,2016);
 rect(20,154,280,12,10565);uint32_t width=position*280/32000;
 if(width)rect(20,154,(int32_t)width,12,2047);
 lab_label(state>0?LAB_LABEL_STOP:recorded?LAB_LABEL_PLAY:LAB_LABEL_RECORD,20,184,65535);
 lab_label(LAB_LABEL_END,220,184,65535);
 rect(20,216,280,8,result<0||state<0?63488:state?65504:2016);
 return 0;
}
