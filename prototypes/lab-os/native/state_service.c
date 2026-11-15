#include "state_service.h"
#include <string.h>
#include <stddef.h>
static uint32_t get32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
static uint32_t crc(const uint8_t *p){
 uint32_t value=UINT32_MAX;
 for(unsigned i=0;i<48;i++){value^=p[i];for(unsigned j=0;j<8;j++)value=(value>>1)^(0xedb88320u & (0u-(value&1u)));}
 return ~value;
}
static bool identity(const char *id){
 if(!id || id[0]<'a' || id[0]>'z')return false;
 for(unsigned i=1;i<=32;i++){
  unsigned char c=(unsigned char)id[i];if(!c)return true;
  if(i==32 || !((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'))return false;
 }
 return false;
}
static bool record(const uint8_t *p,uint32_t n){
 return n==52 && !memcmp(p,"LABST01\n",8) && get32(p+8)!=0 && get32(p+12)<=255 && get32(p+48)==crc(p);
}
bool lab_state_init(LabState *s,const LabStateIo *io){
 if(!s || s->ready || !io || !io->read || !io->put)return false;
 *s=(LabState){.io=*io,.bank=-1,.ready=true};return true;
}
bool lab_state_close(LabState *s){
 if(!s || !s->ready)return false;
 volatile int32_t *values=s->values;for(unsigned i=0;i<8;i++)values[i]=0;
 volatile char *id=s->app_id;for(unsigned i=0;i<33;i++)id[i]=0;
 s->leased=s->healthy=s->committed=false;s->mask=s->sequence=s->last_commit=0;s->bank=-1;return true;
}
bool lab_state_open(LabState *s,const char *id,uint32_t now){
 if(!s || !s->ready || s->leased || !identity(id))return false;
 uint8_t bytes[2][52]={{0}};uint32_t sizes[2]={0};int found[2];bool valid[2];
 for(unsigned b=0;b<2;b++){
  found[b]=s->io.read(s->io.context,id,b,bytes[b],52,&sizes[b]);
  if(found[b]<0 || found[b]>1)return false;
  valid[b]=found[b]==1 && record(bytes[b],sizes[b]);
 }
 int bank=-1;
 if(valid[0] && valid[1]){
  uint32_t a=get32(bytes[0]+8),b=get32(bytes[1]+8),distance=a-b;
  if((a==b && memcmp(bytes[0],bytes[1],52)) || distance==0x80000000u)return false;
  bank=a==b || distance<0x80000000u ? 0:1;
 }else if(valid[0])bank=0;
 else if(valid[1])bank=1;
 else if(found[0] || found[1])return false;
 lab_state_close(s);memcpy(s->app_id,id,strlen(id)+1);s->now=now;s->bank=bank;
 if(bank>=0){
  s->sequence=get32(bytes[bank]+8);s->mask=get32(bytes[bank]+12);
  for(unsigned i=0;i<8;i++)s->values[i]=(int32_t)get32(bytes[bank]+16+i*4);
 }
 s->leased=s->healthy=true;return true;
}
void lab_state_time(LabState *s,uint32_t now){if(s && s->ready)s->now=now;}
int lab_state_read(LabState *s,uint32_t slot,int32_t *value){
 if(value)*value=0;
 if(!s || !s->ready || !s->leased || !value || slot>=8)return -1;
 if(!(s->mask&(1u<<slot)))return 0;
 *value=s->values[slot];return 1;
}
int lab_state_write(LabState *s,uint32_t slot,int32_t value){
 if(!s || !s->ready || !s->leased || !s->healthy || slot>=8)return -1;
 if((s->mask&(1u<<slot)) && s->values[slot]==value)return 1;
 if(s->committed && (uint32_t)(s->now-s->last_commit)<1000)return 0;
 uint8_t bytes[52]={0};memcpy(bytes,"LABST01\n",8);
 uint32_t seq=s->sequence+1;if(!seq)seq=1;
 put32(bytes+8,seq);put32(bytes+12,s->mask|(1u<<slot));
 for(unsigned i=0;i<8;i++)put32(bytes+16+i*4,(uint32_t)(i==slot?value:s->values[i]));
 put32(bytes+48,crc(bytes));unsigned bank=s->bank==0?1:0;
 if(!s->io.put(s->io.context,s->app_id,bank,bytes,52)){s->healthy=false;return -1;}
 s->values[slot]=value;s->mask|=1u<<slot;s->bank=(int)bank;s->sequence=seq;
 s->last_commit=s->now;s->committed=true;return 1;
}
