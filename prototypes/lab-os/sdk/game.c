#include "lab_os.h"
#include "lab_digits.h"
static int32_t x,y,points,playing;
static uint32_t elapsed,rx,ry;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){x=y=points=playing=0;elapsed=rx=ry=0;}
void shutdown(uint32_t reason){(void)reason;playing=0;}
int32_t debug_value(void){return points;}
int32_t debug_x(void){return x;}
int32_t debug_y(void){return y;}
int32_t debug_elapsed(void){return (int32_t)elapsed;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)released;
 if(pressed&BACK)return 1;
 if(pressed&RESET)init();
 if(pressed&START)playing=1;
 if(playing){
  elapsed+=dt;
  uint32_t sx=(dt*80u+rx)/1000u,sy=(dt*80u+ry)/1000u;
  rx=(dt*80u+rx)%1000u;ry=(dt*80u+ry)%1000u;
  if((held&RIGHT)&&!(held&LEFT)){x+=(int32_t)sx;if(x>72)x=72;}
  if((held&LEFT)&&!(held&RIGHT)){x-=(int32_t)sx;if(x<0)x=0;}
  if((held&DOWN)&&!(held&UP)){y+=(int32_t)sy;if(y>232)y=232;}
  if((held&UP)&&!(held&DOWN)){y-=(int32_t)sy;if(y<0)y=0;}
  if(x==24&&y==0)points=1;
 }
 rect(0,0,320,240,0);rect(80,0,8,240,2016);
 if(!points)rect(24,0,8,8,63488);
 rect(x,y,8,8,65535);lab_number(points,110,20);return 0;
}
