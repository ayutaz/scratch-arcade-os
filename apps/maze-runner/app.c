#include "lab_os.h"
#include "lab_digits.h"

/* One foreground app; no device pins, allocation, filesystem or native code. */
static int32_t x,y,score,phase;
static uint32_t elapsed,rx,ry;
static const int32_t tx[3]={56,248,32},ty[3]={104,208,208};
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){x=16;y=104;score=phase=0;elapsed=rx=ry=0;}
void shutdown(uint32_t reason){(void)reason;phase=0;}
int32_t debug_value(void){return score;}
int32_t debug_x(void){return x;}
int32_t debug_y(void){return y;}
int32_t debug_elapsed(void){return (int32_t)elapsed;}

static int32_t clamp(int32_t v,int32_t lo,int32_t hi){return v<lo?lo:v>hi?hi:v;}
static void pickup(int32_t ox,int32_t oy){
 if(score>=3)return;
 int32_t left=x<ox?x:ox,top=y<oy?y:oy;
 int32_t right=(x>ox?x:ox)+8,bottom=(y>oy?y:oy)+8;
 if(left<tx[score]+8 && right>tx[score] && top<ty[score]+8 && bottom>ty[score]){
  if(++score==3)phase=2;
 }
}
static void move(uint32_t held,uint32_t dt){
 uint32_t sx=(dt*100u+rx)/1000u,sy=(dt*100u+ry)/1000u;
 rx=(dt*100u+rx)%1000u;ry=(dt*100u+ry)%1000u;
 int32_t ox=x,oy=y,nx=x,ny=y;
 if((held&RIGHT)&&!(held&LEFT))nx+=(int32_t)sx;
 if((held&LEFT)&&!(held&RIGHT))nx-=(int32_t)sx;
 nx=clamp(nx,8,304);
 if(y<192 && y+8>88){
  if(x+8<=152 && nx+8>152)nx=144;
  if(x>=160 && nx<160)nx=160;
 }
 x=nx;pickup(ox,oy);if(phase!=1)return;
 if((held&DOWN)&&!(held&UP))ny+=(int32_t)sy;
 if((held&UP)&&!(held&DOWN))ny-=(int32_t)sy;
 ny=clamp(ny,88,224);
 if(x<160 && x+8>152 && y>=192 && ny<192)ny=192;
 oy=y;y=ny;pickup(x,oy);
}
static void paint(void){
 int32_t color=phase==0?31:phase==1?10565:phase==2?2016:63488;
 rect(0,0,320,240,0);rect(0,0,4,240,color);
 lab_number(score,16,4);lab_number((int32_t)((30000-elapsed+999)/1000),210,4);
 rect(8,80,304,4,color);rect(8,232,304,4,color);
 rect(152,88,8,104,10565);
 if(score<3)rect(tx[score],ty[score],8,8,65504);
 rect(x,y,8,8,65535);
 /* A/start icon on cover and result, remaining-time bar during play. */
 if(phase!=1){rect(274,140,26,26,color);rect(284,146,6,14,65535);}
 else {int32_t w=(int32_t)((30000-elapsed)*280/30000);if(w)rect(20,72,w,3,2016);}
}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)released;
 if(pressed&BACK)return 1;
 if(pressed&RESET)init();
 else if((pressed&START)&&phase!=1){init();phase=1;}
 else if(phase==1){
  if(dt>=30000-elapsed){elapsed=30000;phase=3;}
  else {elapsed+=dt;move(held,dt);}
 }
 paint();return 0;
}
