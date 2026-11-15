#include "state_mount.h"
#include "app_store.h"
#include <stdlib.h>
#include <string.h>
extern int test_lfs_connect(void *,const LabStorage *,uint32_t,bool,LabStorage *);
typedef struct {LabStore store;LabHome home;LabStateMount state;} Rig;
void *test_state_apps_new(void *volume,const LabStorage *trusted){
 Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;LabStorage io={0};
 if(!test_lfs_connect(volume,trusted,0xe0000,true,&io)||!lab_store_init(&r->store,&io)){free(r);return NULL;}
 LabCatalog catalog=lab_store_catalog(&r->store);
 if(!lab_home_init(&r->home,&catalog)||!lab_state_mount_attach(&r->state,&r->home,(lfs_t *)volume,true)){lab_store_close(&r->store);free(r);return NULL;}
 return r;
}
void test_state_apps_free(Rig *r){if(!lab_home_close(&r->home)||!lab_store_close(&r->store))abort();free(r);}
int test_state_apps_install(Rig *r,const uint8_t *bytes,uint32_t n){return lab_store_install(&r->store,bytes,n)&&lab_home_refresh(&r->home);}
int test_state_apps_select(Rig *r,const char *id){if(r->home.mode!=LAB_HOME)return 0;for(uint32_t i=0;i<r->home.count;i++)if(!strcmp(r->home.apps[i].id,id)){r->home.selected=i;return 1;}return 0;}
int test_state_apps_frame(Rig *r,uint32_t held,uint32_t dt){return lab_home_frame(&r->home,held,dt);}
int test_state_apps_debug(Rig *r,const char *name){return lab_vm_debug(&r->home.vm,name);}
unsigned test_state_apps_draw_count(Rig *r){return r->home.vm.draw_count;}
int test_state_apps_draw(Rig *r,unsigned i,unsigned j){return i<r->home.vm.draw_count&&j<5?r->home.vm.draws[i][j]:-1;}
