/* Test-only host entry points. The store, supervisor and VM are production C. */
#include "app_store.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned char pool[196608] __attribute__((aligned(16)));
typedef struct {LabStore store; LabHome home; LabImage image; bool home_ready;} Fixture;
int test_runtime_start(void) {return lab_runtime_init(pool,sizeof(pool));}
void test_runtime_stop(void) {lab_runtime_destroy();}
void *test_store_new(const LabStorage *io) {
    Fixture *f=calloc(1,sizeof(*f));
    if(!f)return NULL;
    if(!lab_store_init(&f->store,io)) {free(f);return NULL;}
    return f;
}
void test_store_free(Fixture *f) {
    if(!f)return;
    if(f->home_ready)lab_home_close(&f->home);
    LabCatalog c=lab_store_catalog(&f->store);
    if(f->image.lease)c.release(c.context,&f->image);
    if(!lab_store_close(&f->store))abort();
    free(f);
}
int test_install(Fixture *f,const uint8_t *bytes,uint32_t n) {return lab_store_install(&f->store,bytes,n);}
int test_action(Fixture *f,const char *id,int action) {
    if(action==0)return lab_store_rollback(&f->store,id);
    if(action==1)return lab_store_uninstall(&f->store,id);
    return lab_store_quarantine(&f->store,id);
}
int test_count(Fixture *f) {LabCatalog c=lab_store_catalog(&f->store);return c.count(c.context);}
int test_info(Fixture *f,uint32_t at,char *out) {
    LabAppInfo info={0};LabCatalog c=lab_store_catalog(&f->store);
    if(!c.info(c.context,at,&info))return 0;
    snprintf(out,160,"%s|%s|%s",info.id,info.title,info.version);return 1;
}
int test_status(Fixture *f,int which) {
    return which==0 ? f->store.healthy : which==1 ? f->store.recovered : (int)f->store.sequence;
}
int test_open(Fixture *f,const char *id) {
    LabCatalog c=lab_store_catalog(&f->store);return c.open(c.context,id,&f->image);
}
void test_release(Fixture *f) {LabCatalog c=lab_store_catalog(&f->store);c.release(c.context,&f->image);}
int test_verify(void *ctx,uint8_t *bytes,uint32_t n,uint32_t pages,uint32_t budget,uint32_t caps) {
    (void)ctx;LabVm vm={0};
    bool ok=lab_vm_open_with_audio(&vm,bytes,n,pages,budget,caps,NULL);
    if(ok)ok=lab_vm_frame(&vm,0,0)==0;
    lab_vm_close(&vm,1);return ok;
}
int test_home_start(Fixture *f) {
    LabCatalog c=lab_store_catalog(&f->store);
    f->home_ready=lab_home_init(&f->home,&c);return f->home_ready;
}
int test_home_frame(Fixture *f,uint32_t held,uint32_t dt) {return lab_home_frame(&f->home,held,dt);}
int test_home_mode(Fixture *f) {return f->home.mode;}
int test_home_value(Fixture *f) {return lab_vm_debug(&f->home.vm,"debug_value");}
int test_home_refresh(Fixture *f) {return lab_home_refresh(&f->home);}
int test_home_count(Fixture *f) {return (int)f->home.count;}
LabStore *test_store_pointer(Fixture *f) {return &f->store;}
LabHome *test_home_pointer(Fixture *f) {return &f->home;}
