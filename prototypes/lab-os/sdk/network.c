#include "lab_os.h"
#include "lab_digits.h"

/* Diagnostic packets are 12 bytes: LBN1 + positive int31 sequence (LE) +
 * opaque 4-byte tag. A queues LBA1 with the same sequence/tag. Neither the tag
 * nor UDP provides authentication; the OS supplies the trusted peer route. */
static uint8_t incoming[64],reply[12];
static int32_t received,sent,sequence,state;
static uint32_t pending,have_last;
static void wipe(uint8_t *p,uint32_t n){volatile uint8_t *v=p;while(n--)*v++=0;}
static void discard(void){wipe(reply,sizeof(reply));pending=have_last=0;}
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){received=sent=sequence=0;state=-1;wipe(incoming,sizeof(incoming));discard();}
void shutdown(uint32_t reason){(void)reason;wipe(incoming,sizeof(incoming));discard();}
int32_t debug_value(void){return received;}
int32_t debug_x(void){return sent;}
int32_t debug_y(void){return sequence;}
int32_t debug_elapsed(void){return state;}
static void receive(void){
 int32_t n=network_receive(incoming,sizeof(incoming));
 if(n<0){state=-1;discard();}
 else if(n==12 && incoming[0]=='L' && incoming[1]=='B' && incoming[2]=='N' && incoming[3]=='1'){
  uint32_t id=(uint32_t)incoming[4]|(uint32_t)incoming[5]<<8|(uint32_t)incoming[6]<<16|(uint32_t)incoming[7]<<24;
  if(id && id<=2147483647u){
   uint32_t same=have_last;
   for(uint32_t i=4;i<12;i++)if(reply[i]!=incoming[i])same=0;
   if(!same && received<999)received++;
   sequence=(int32_t)id;reply[0]='L';reply[1]='B';reply[2]='A';reply[3]='1';
   for(uint32_t i=4;i<12;i++)reply[i]=incoming[i];
   have_last=pending=1;
  }
 }
 wipe(incoming,sizeof(incoming));
}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;(void)dt;
 if(pressed&BACK)return 1;
 state=network_state();
 if(state==1){
  receive();
  if(state==1 && pending && (pressed&START)){
   int32_t result=network_send(reply,sizeof(reply));
   if(result==1){pending=0;if(sent<999)sent++;}
   else if(result<0){state=-1;discard();}
  }
 }else discard();
 rect(0,0,320,240,0);
 rect(20,16,280,12,state==1 ? 2016 : 63488);
 /* Left upper = received, right upper = queued replies, lower = sequence %1000.
  * Yellow lower-right = waiting for A; blue = no pending reply. */
 lab_number(received,20,54);lab_number(sent,180,54);
 lab_number(sequence%1000,20,150);
 rect(200,170,80,16,pending ? 65504 : 31);
 return 0;
}
