#include "state_mount.h"
#include <stdlib.h>
static uint32_t count(void *c){(void)c;return 0;}
static bool info(void *c,uint32_t i,LabAppInfo *out){(void)c;(void)i;(void)out;abort();}
static bool open_image(void *c,const char *id,LabImage *out){(void)c;(void)id;(void)out;abort();}
static void release(void *c,LabImage *image){(void)c;(void)image;abort();}
/* 1 attached; 2 storage opened; 4 written; 8 closed; 16 cannot reattach;
 * 32 Home close; 64 cache scrubbed. Only the mounted RAM fixture is used. */
unsigned test_state_mount(void *volume,int busy){
 LabHome h={0};LabStateMount s={0};LabCatalog cat={NULL,count,info,open_image,release,NULL};
 if(!lab_home_init(&h,&cat))abort();if(busy)h.mode=LAB_RUNNING;
 if(!lab_state_mount_attach(&s,&h,(lfs_t *)volume,true))return 0;
 unsigned result=1;LabVmState vm={0};
 if(h.state.open(h.state.context,"alpha",LAB_VM_CAP_STORAGE,&vm)){
  result|=2;int32_t v=41;if(vm.call(vm.context,LAB_VM_STATE_WRITE,0,&v)==1)result|=4;
  if(h.state.close(h.state.context))result|=8;
 }
 if(!lab_state_mount_attach(&s,&h,(lfs_t *)volume,true))result|=16;
 if(lab_home_close(&h))result|=32;
 if(!s.manager.state.leased&&!s.manager.state.app_id[0])result|=64;
 return result;
}
