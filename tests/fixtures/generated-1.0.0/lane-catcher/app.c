#include "lab_os.h"
#include "lab_digits.h"
#define SHIP_COLOR 2016
static uint32_t lane,target,y,elapsed,pending,score,miss,phase;
static void reset(uint32_t next){lane=target=1;y=24;elapsed=pending=score=miss=0;phase=next;}
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){reset(0);}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return (int32_t)score;}
int32_t debug_x(void){return (int32_t)lane;}
int32_t debug_y(void){return (int32_t)phase;}
int32_t debug_elapsed(void){return (int32_t)elapsed;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;
 if(pressed&BACK)return 1;
 if(pressed&RESET)reset(0);
 else if(phase!=1){if(pressed&START)reset(1);}
 else {
  uint32_t direction=pressed&(LEFT|RIGHT);
  if(direction==LEFT && lane>0)lane--;
  else if(direction==RIGHT && lane<2)lane++;
  pending+=dt;
  while(pending>=100 && phase==1){
   pending-=100;elapsed+=100;y+=16;
   if(y>=184){if(lane==target)score++;else miss++;target=(target+1)%3;y=24;}
   if(miss>=3 || elapsed>=15000)phase=2;
  }
 }
 rect(0,0,320,240,0);
 for(int32_t i=0;i<3;i++)rect(16+i*96,18,88,184,4226);
 rect(44+(int32_t)target*96,(int32_t)y,32,12,65504);
 rect(36+(int32_t)lane*96,202,48,12,SHIP_COLOR);
 int32_t width=(int32_t)((15000-elapsed)*288/15000);
 if(width)rect(16,224,width,6,phase==2?63488:2047);
 for(uint32_t i=0;i<miss;i++)rect(254+(int32_t)i*18,4,12,8,63488);
 if(phase!=1){rect(62,48,196,124,0);lab_number((int32_t)score,92,72);rect(72,150,176,8,phase==0?31:2016);}
 return 0;
}
