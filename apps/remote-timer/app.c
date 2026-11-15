#include "lab_os.h"
#include "lab_digits.h"
#include "lab_labels.h"
static uint32_t seconds,remaining,phase,elapsed,last_sequence,reply_pending,reply_age,failed;
static uint8_t incoming[64],last_request[16],outgoing[24];
static uint32_t get32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void reset(void){remaining=seconds*1000;phase=elapsed=0;}
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){seconds=60;reset();last_sequence=reply_pending=reply_age=failed=0;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return (int32_t)remaining;}
int32_t debug_x(void){return (int32_t)seconds;}
int32_t debug_y(void){return (int32_t)phase;}
int32_t debug_elapsed(void){return (int32_t)elapsed;}
static int request(int32_t n){
 if(n!=16 || incoming[0]!='L'||incoming[1]!='R'||incoming[2]!='T'||incoming[3]!='1')return 0;
 uint32_t seq=get32(incoming+4),op=get32(incoming+8),value=get32(incoming+12);
 if(!seq||op<1||op>4||(op==1?(value<10||value>300):value!=0))return 0;
 if(seq==last_sequence){
  for(unsigned i=0;i<16;i++)if(incoming[i]!=last_request[i])return 0;
 }else{
  uint32_t distance=seq-last_sequence;
  if(last_sequence && (!distance||distance>=0x80000000u))return 0;
  if(op==1){seconds=value;reset();phase=1;}
  else if(op==2 && phase==1)phase=2;
  else if(op==4)reset();
  last_sequence=seq;for(unsigned i=0;i<16;i++)last_request[i]=incoming[i];
 }
 outgoing[0]='L';outgoing[1]='R';outgoing[2]='A';outgoing[3]='1';
 put32(outgoing+4,seq);put32(outgoing+8,phase);put32(outgoing+12,remaining);put32(outgoing+16,seconds);put32(outgoing+20,elapsed);
 reply_pending=1;reply_age=failed=0;return 1;
}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;if(pressed&BACK)return 1;
 if(phase==1){uint32_t used=dt<remaining?dt:remaining;remaining-=used;elapsed+=used;if(!remaining)phase=3;}
 if(pressed&RESET)reset();
 else if(pressed&START){if(phase==1)phase=2;else if(phase==2)phase=1;else{reset();phase=1;}}
 if(reply_pending){reply_age+=dt;if(reply_age>=1000){reply_pending=0;failed=1;}}
 int32_t n=network_receive(incoming,64);if(n>0)request(n);else if(n<0)failed=1;
 if(reply_pending){int32_t result=network_send(outgoing,24);if(result!=0){reply_pending=0;failed=result<0;}}
 rect(0,0,320,240,0);
 int32_t color=phase==3?2016:phase==2?65504:phase==1?2047:31;
 for(int32_t i=0;i<4;i++)rect(20+i*72,16,64,8,(uint32_t)i==phase?color:10565);
 uint32_t value=(remaining+999)/1000;
 lab_number((int32_t)value,value>=100?92:value>=10?114:136,64);
 rect(20,164,280,16,10565);int32_t width=(int32_t)(remaining*280/(seconds*1000));if(width)rect(20,164,width,16,color);
 lab_label(phase==1?LAB_LABEL_PAUSE:phase==2?LAB_LABEL_RESUME:LAB_LABEL_START,20,184,65535);
 lab_label(LAB_LABEL_END,220,184,65535);rect(20,204,280,8,color);rect(304,204,6,6,failed?63488:reply_pending?65504:2016);
 return 0;
}
