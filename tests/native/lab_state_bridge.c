#include "state_service.h"
#include <stdlib.h>
#include <string.h>
static uint8_t disk[2][2][52];static int present[2][2],reads,writes,write_fault,read_fault,last_read;
static int index_of(const char *id){return !strcmp(id,"alpha")?0:!strcmp(id,"beta")?1:-1;}
static int read_state(void *ctx,const char *id,unsigned bank,uint8_t *out,unsigned cap,unsigned *size){
 (void)ctx;reads++;int a=index_of(id);if(a<0 || bank>1 || cap!=52 || read_fault)return -1;
 if(!present[a][bank])return 0;memcpy(out,disk[a][bank],52);*size=52;return 1;
}
static bool put_state(void *ctx,const char *id,unsigned bank,const uint8_t *data,unsigned size){
 (void)ctx;writes++;int a=index_of(id);if(a<0 || bank>1 || size!=52)return false;
 if(write_fault==1)return false;
 memcpy(disk[a][bank],data,write_fault==2?17:52);present[a][bank]=1;return !write_fault;
}
void test_disk_reset(void){memset(disk,0,sizeof(disk));memset(present,0,sizeof(present));reads=writes=write_fault=read_fault=last_read=0;}
void *test_new(void){LabState *s=calloc(1,sizeof(*s));LabStateIo io={NULL,read_state,put_state};if(!lab_state_init(s,&io)){free(s);return NULL;}return s;}
void test_free(LabState *s){lab_state_close(s);free(s);}
int test_open(LabState *s,const char *id,unsigned now){return lab_state_open(s,id,now);}
int test_close(LabState *s){return lab_state_close(s);}
int test_read(LabState *s,unsigned slot,int fallback){int32_t value=0;last_read=lab_state_read(s,slot,&value);return last_read==1?value:fallback;}
int test_write(LabState *s,unsigned slot,int value,unsigned now){lab_state_time(s,now);return lab_state_write(s,slot,value);}
int test_last_read(void){return last_read;}
int test_io_count(void){return reads+writes;}int test_writes(void){return writes;}
void test_write_fault(int value){write_fault=value;}void test_read_fault(int value){read_fault=value;}
void test_corrupt(unsigned a,unsigned b,unsigned at){if(a<2 && b<2 && at<52)disk[a][b][at]^=128;}
int test_scrubbed(LabState *s){for(unsigned i=0;i<8;i++)if(s->values[i])return 0;for(unsigned i=0;i<33;i++)if(s->app_id[i])return 0;return 1;}
unsigned test_record_byte(unsigned a,unsigned b,unsigned at){return a<2 && b<2 && at<52?disk[a][b][at]:0;}
