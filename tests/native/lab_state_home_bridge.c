#include "app_home.h"
#include "state_binding.h"
#include <stdlib.h>
#include <string.h>
typedef struct {
 LabHome home;LabStateManager manager;LabHomeState hooks;
 uint8_t *source;uint32_t length,caps,sizes[2][2],reads,writes,closes,releases,live_closes,quarantines;
 uint8_t records[2][2][52];bool fail_read,fail_write,fail_close;char bound[33];
} Rig;
static _Alignas(8) uint8_t pool[196608];
int test_runtime_start(void){return lab_runtime_init(pool,sizeof(pool));}void test_runtime_stop(void){lab_runtime_destroy();}
static int index_of(const char *id){return !strcmp(id,"alpha")?0:!strcmp(id,"beta")?1:-1;}
static int read_state(void *c,const char *id,uint32_t b,uint8_t *p,uint32_t cap,uint32_t *n){
 Rig *r=c;r->reads++;int i=index_of(id);if(r->fail_read||i<0||b>1||cap<52)return -1;
 *n=r->sizes[i][b];memcpy(p,r->records[i][b],*n);return *n?1:0;
}
static bool put_state(void *c,const char *id,uint32_t b,const uint8_t *p,uint32_t n){
 Rig *r=c;r->writes++;int i=index_of(id);if(r->fail_write||i<0||b>1||n!=52)return false;
 memcpy(r->records[i][b],p,n);r->sizes[i][b]=n;return true;
}
static uint32_t count(void *c){(void)c;return 2;}
static bool info(void *c,uint32_t i,LabAppInfo *out){(void)c;if(i>1)return false;*out=(LabAppInfo){.version="1.0.0",.enabled=true};strcpy(out->id,i?"beta":"alpha");strcpy(out->title,out->id);return true;}
static bool image_open(void *c,const char *id,LabImage *out){Rig *r=c;if(index_of(id)<0)return false;uint8_t *p=malloc(r->length);if(!p)return false;memcpy(p,r->source,r->length);*out=(LabImage){p,r->length,2,50000,r->caps,p};return true;}
static void image_release(void *c,LabImage *out){Rig *r=c;r->releases++;free(out->lease);*out=(LabImage){0};}
static bool quarantine(void *c,const char *id){(void)id;((Rig *)c)->quarantines++;return true;}
static bool bind(void *c,const char *id,uint32_t caps,LabVmState *out){Rig *r=c;strcpy(r->bound,id);return r->hooks.open(r->hooks.context,id,caps,out);}
static void poll(void *c,uint32_t now){Rig *r=c;r->hooks.poll(r->hooks.context,now);}
static bool close_state(void *c){Rig *r=c;r->closes++;if(r->home.vm.instance)r->live_closes++;return !r->fail_close&&r->hooks.close(r->hooks.context);}
void *test_new(const uint8_t *p,uint32_t n,uint32_t caps){Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;r->source=malloc(n);if(!r->source){free(r);return NULL;}memcpy(r->source,p,n);r->length=n;r->caps=caps;
 LabStateIo io={r,read_state,put_state};LabCatalog catalog={r,count,info,image_open,image_release,quarantine};
 if(!lab_state_manager_init(&r->manager,&io)||!lab_home_init(&r->home,&catalog))abort();r->hooks=lab_state_manager_services(&r->manager);
 LabHomeState hooks={r,bind,poll,close_state};if(!lab_home_set_state(&r->home,&hooks))abort();return r;}
void test_free(Rig *r){r->fail_close=false;if(!lab_home_close(&r->home))abort();free(r->source);free(r);}
int test_step(Rig *r,uint32_t held,uint32_t dt){return lab_home_frame(&r->home,held,dt);}
int test_value(Rig *r){return lab_vm_debug(&r->home.vm,"debug_value");}int test_status(Rig *r){return lab_vm_debug(&r->home.vm,"debug_x");}
unsigned test_metric(Rig *r,unsigned n){switch(n){case 0:return r->home.mode;case 1:return r->reads;case 2:return r->writes;case 3:return r->closes;case 4:return r->releases;case 5:return r->live_closes;case 6:return r->quarantines;case 7:return r->home.notice;case 8:return r->manager.state.leased;case 9:return r->home.state_owned;default:return r->home.count;}}
void test_fault(Rig *r,int read,int write,int close){r->fail_read=read;r->fail_write=write;r->fail_close=close;}
int test_configure(Rig *r,int partial){LabHomeState hooks={r,bind,poll,close_state};if(partial)hooks.close=NULL;return lab_home_set_state(&r->home,&hooks);}
int test_bound(Rig *r,const char *id){return !strcmp(r->bound,id);}int test_close(Rig *r){return lab_home_close(&r->home);}
int test_scrubbed(Rig *r){if(r->manager.state.app_id[0])return 0;for(unsigned i=0;i<8;i++)if(r->manager.state.values[i])return 0;return 1;}
