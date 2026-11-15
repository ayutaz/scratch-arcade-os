#include "state_lfs.h"
#include <stdio.h>
#include <string.h>
#define ROOT "/lab-state"
static bool identity(const char *id){
 if(!id || id[0]<'a' || id[0]>'z')return false;
 for(unsigned i=1;i<=32;i++){
  unsigned char c=(unsigned char)id[i];if(!c)return true;
  if(i==32 || !((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'))return false;
 }
 return false;
}
static bool path(const char *id,uint32_t bank,char out[80]){
 if(!identity(id)||bank>1)return false;
 int n=snprintf(out,80,ROOT "/%s.%u",id,(unsigned)bank);return n>0&&n<80;
}
static int raw_read(LabStateLfs *s,const char *name,uint8_t *out,uint32_t cap,uint32_t *n){
 struct lfs_info info;int err=lfs_stat(s->fs,name,&info);*n=0;
 if(err==LFS_ERR_NOENT)return 0;
 if(err||info.type!=LFS_TYPE_REG||info.size>cap)return -1;
 lfs_file_t f;if(lfs_file_open(s->fs,&f,name,LFS_O_RDONLY))return -1;
 bool ok=lfs_file_read(s->fs,&f,out,info.size)==(lfs_ssize_t)info.size;
 int close=lfs_file_close(s->fs,&f);if(!ok||close)return -1;
 *n=info.size;return 1;
}
static bool owned(LabStateLfs *s){
 uint8_t bytes[sizeof(LAB_STATE_LFS_OWNER)];uint32_t n=0;
 return raw_read(s,ROOT "/owner",bytes,sizeof(bytes),&n)==1&&n==sizeof(LAB_STATE_LFS_OWNER)-1&&!memcmp(bytes,LAB_STATE_LFS_OWNER,n);
}
/* Validate every entry before writes. Bounded to 65 files / 32 identities.
 * Truncated records are allowed here so the service can recover the other
 * valid bank. Oversize/unknown entries fail closed; nothing is removed. */
static bool scan(LabStateLfs *s,const char *wanted,uint32_t *count,bool *present){
 lfs_dir_t dir;if(lfs_dir_open(s->fs,&dir,ROOT))return false;
 char ids[32][33]={{0}};uint32_t entries=0;*count=0;*present=false;bool ok=true;
 struct lfs_info info;int result;
 while((result=lfs_dir_read(s->fs,&dir,&info))>0){
  if(!strcmp(info.name,".")||!strcmp(info.name,".."))continue;
  if(++entries>65||info.type!=LFS_TYPE_REG){ok=false;break;}
  if(!strcmp(info.name,"owner")){if(info.size!=sizeof(LAB_STATE_LFS_OWNER)-1){ok=false;break;}continue;}
  size_t n=strlen(info.name);
  if(n<3||n>34||info.name[n-2]!='.'||(info.name[n-1]!='0'&&info.name[n-1]!='1')||info.size>52){ok=false;break;}
  char id[33]={0};memcpy(id,info.name,n-2);if(!identity(id)){ok=false;break;}
  if(wanted&&!strcmp(wanted,id))*present=true;
  bool seen=false;for(uint32_t i=0;i<*count;i++)if(!strcmp(ids[i],id))seen=true;
  if(!seen){if(*count>=32){ok=false;break;}strcpy(ids[(*count)++],id);}
 }
 if(result<0)ok=false;
 return !lfs_dir_close(s->fs,&dir)&&ok;
}
static bool empty(LabStateLfs *s){
 lfs_dir_t dir;if(lfs_dir_open(s->fs,&dir,ROOT))return false;
 bool ok=true;int result;struct lfs_info info;
 while((result=lfs_dir_read(s->fs,&dir,&info))>0)
  if(strcmp(info.name,".")&&strcmp(info.name,"..")){ok=false;break;}
 if(result<0)ok=false;
 return !lfs_dir_close(s->fs,&dir)&&ok;
}
bool lab_state_lfs_init(LabStateLfs *s,lfs_t *fs,bool create){
 if(!s||s->ready||!fs)return false;
 *s=(LabStateLfs){.fs=fs};struct lfs_info info;int err=lfs_stat(fs,ROOT,&info);
 if(err==LFS_ERR_NOENT){if(!create||lfs_mkdir(fs,ROOT))return false;}
 else if(err||info.type!=LFS_TYPE_DIR)return false;
 if(!owned(s)){
  if(!create||!empty(s))return false;
  lfs_file_t f;if(lfs_file_open(fs,&f,ROOT "/owner",LFS_O_WRONLY|LFS_O_CREAT|LFS_O_EXCL))return false;
  bool ok=lfs_file_write(fs,&f,LAB_STATE_LFS_OWNER,sizeof(LAB_STATE_LFS_OWNER)-1)==sizeof(LAB_STATE_LFS_OWNER)-1;
  if(ok)ok=lfs_file_sync(fs,&f)==0;
  int close=lfs_file_close(fs,&f);if(!ok||close||!owned(s))return false;
 }
 uint32_t count;bool present;s->ready=scan(s,NULL,&count,&present);return s->ready;
}
static int read_state(void *c,const char *id,uint32_t bank,uint8_t *p,uint32_t cap,uint32_t *n){
 LabStateLfs *s=c;char name[80];uint32_t count;bool present;
 if(!s||!s->ready||!p||!n||!path(id,bank,name)||!owned(s)||!scan(s,id,&count,&present))return -1;
 return raw_read(s,name,p,cap,n);
}
static bool put_state(void *c,const char *id,uint32_t bank,const uint8_t *p,uint32_t n){
 LabStateLfs *s=c;char name[80];uint32_t count;bool present;
 if(!s||!s->ready||!p||n!=52||!path(id,bank,name)||!owned(s)||!scan(s,id,&count,&present)||(!present&&count>=32))return false;
 lfs_file_t f;if(lfs_file_open(s->fs,&f,name,LFS_O_WRONLY|LFS_O_CREAT|LFS_O_TRUNC))return false;
 bool ok=lfs_file_write(s->fs,&f,p,n)==(lfs_ssize_t)n;if(ok)ok=lfs_file_sync(s->fs,&f)==0;
 int close=lfs_file_close(s->fs,&f);return ok&&!close;
}
LabStateIo lab_state_lfs_io(LabStateLfs *s){return (LabStateIo){s,read_state,put_state};}
