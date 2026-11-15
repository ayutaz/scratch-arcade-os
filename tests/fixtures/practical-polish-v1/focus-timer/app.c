#include "lab_os.h"
#include "lab_digits.h"
#include "lab_labels.h"
static uint32_t seconds,remaining,phase,elapsed,alarm_wait,alarm_pending;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){seconds=60;remaining=60000;phase=elapsed=alarm_wait=alarm_pending=0;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return (int32_t)remaining;}
int32_t debug_x(void){return (int32_t)seconds;}
int32_t debug_y(void){return (int32_t)phase;}
int32_t debug_elapsed(void){return (int32_t)elapsed;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;
 if(pressed&BACK)return 1;
 uint32_t completed=0;
 if(phase==1){
  uint32_t used=dt<remaining?dt:remaining;remaining-=used;elapsed+=used;
  if(remaining==0){phase=3;alarm_pending=1;alarm_wait=0;completed=1;}
 }
 if(pressed&RESET){remaining=seconds*1000;elapsed=phase=alarm_wait=alarm_pending=0;}
 else if(pressed&START){
  if(phase==1)phase=2;
  else if(phase==2)phase=1;
  else{remaining=seconds*1000;elapsed=alarm_wait=alarm_pending=0;phase=1;}
 }else if(phase==0){
  uint32_t direction=pressed&(UP|DOWN);
  if(direction==UP && seconds<300)seconds+=10;
  else if(direction==DOWN && seconds>10)seconds-=10;
  remaining=seconds*1000;
 }
 if(alarm_pending){
  if(!completed)alarm_wait+=dt;
  if(alarm_wait>=1000)alarm_pending=0;
  else if(audio_tone(1320,200)!=0)alarm_pending=0;
 }
 rect(0,0,320,240,0);
 int32_t color=phase==3?2016:phase==2?65504:phase==1?2047:31;
 for(int32_t i=0;i<4;i++)rect(20+i*72,16,64,8,(uint32_t)i==phase?color:10565);
 uint32_t value=(remaining+999)/1000;
 lab_number((int32_t)value,value>=100?92:value>=10?114:136,64);
 rect(20,164,280,16,10565);
 int32_t width=(int32_t)(remaining*280/(seconds*1000));
 if(width)rect(20,164,width,16,color);
 rect(20,204,280,8,color);
 lab_label(phase==1?LAB_LABEL_PAUSE:phase==2?LAB_LABEL_RESUME:LAB_LABEL_START,20,184,65535);
 lab_label(LAB_LABEL_END,220,184,65535);
 return 0;
}
