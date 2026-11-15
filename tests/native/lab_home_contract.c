#include "app_home.h"
#include "ui.h"
#include "fixture_data.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static _Alignas(8) uint8_t pool[196608];
static LabHome home;
typedef struct {
    LabAppInfo info[17];
    const uint8_t *code[17], *previous[17];
    uint32_t sizes[17], previous_sizes[17], count;
    unsigned opened, released, leases, quarantines;
    bool fail_open, fail_quarantine;
} Fixture;
static Fixture fixture;

static uint32_t count(void *ctx) { return ((Fixture *)ctx)->count; }
static bool info(void *ctx, uint32_t index, LabAppInfo *out) {
    Fixture *f=ctx;
    if(index>=f->count) return false;
    *out=f->info[index]; return true;
}
static int index_of(Fixture *f, const char *id) {
    for(uint32_t i=0;i<f->count;i++) if(!strcmp(f->info[i].id,id)) return (int)i;
    return -1;
}
static bool open_image(void *ctx,const char *id,LabImage *out) {
    Fixture *f=ctx; int n=index_of(f,id); if(n<0)return false;
    out->bytes=malloc(f->sizes[n]); assert(out->bytes);
    memcpy(out->bytes,f->code[n],f->sizes[n]);
    out->size=f->sizes[n];out->pages=2;out->budget=50000;out->capabilities=LAB_VM_CAP_DRAW;
    ++f->opened;++f->leases;
    return !f->fail_open;
}
static void release_image(void *ctx,LabImage *image) {
    Fixture *f=ctx;
    assert(home.vm.instance==NULL && home.vm.module==NULL && home.vm.env==NULL);
    assert(image->bytes && f->leases==1);
    free(image->bytes);++f->released;--f->leases;
}
static bool quarantine(void *ctx,const char *id) {
    Fixture *f=ctx; int n=index_of(f,id); assert(n>=0 && f->leases==0);
    ++f->quarantines;
    if(f->fail_quarantine)return false;
    if(f->previous[n]){
        f->code[n]=f->previous[n];f->sizes[n]=f->previous_sizes[n];f->previous[n]=NULL;
        strcpy(f->info[n].version,"1.0.0");
    }else f->info[n].enabled=false;
    return true;
}
static LabCatalog catalog(void) {
    return (LabCatalog){&fixture,count,info,open_image,release_image,quarantine};
}
static void setup(void) {
    memset(&fixture,0,sizeof(fixture));fixture.count=2;
    fixture.info[0]=(LabAppInfo){.id="counter",.title="カウンター",.version="1.0.0",.enabled=true};
    fixture.info[1]=(LabAppInfo){.id="game",.title="ゲーム",.version="1.0.0",.enabled=true};
    for(int i=0;i<2;i++){fixture.code[i]=normal_blob;fixture.sizes[i]=sizeof(normal_blob);}
    LabCatalog c=catalog();assert(lab_home_init(&home,&c));
}
static void frame(uint32_t held,uint32_t dt){ assert(lab_home_frame(&home,held,dt)); }
static void back(void){ frame(192,1);frame(0,1);assert(home.mode==LAB_HOME); }

static void navigation(void) {
    setup();frame(4,0);assert(home.selected==1);frame(4,10);assert(home.selected==1);
    frame(0,0);frame(8,0);frame(0,0);
    fixture.code[0]=exiting_blob;fixture.sizes[0]=sizeof(exiting_blob);
    frame(16,0);assert(home.mode==LAB_RUNNING && !strcmp(home.active_id,"counter"));
    frame(16,10);assert(lab_vm_debug(&home.vm,"debug_value")==0);
    assert(!lab_home_refresh(&home));
    frame(0,0);frame(64,0);assert(home.mode==LAB_RELEASE);
    assert(fixture.leases==0 && fixture.quarantines==0);
    frame(0,0);assert(home.mode==LAB_HOME);lab_home_close(&home);
}
static void system_exit(void) {
    setup();frame(16,0);assert(fixture.leases==1);
    frame(192,1);assert(home.mode==LAB_RELEASE && fixture.leases==0);
    frame(16,0);assert(home.mode==LAB_RELEASE);
    frame(0,0);frame(16,0);assert(home.mode==LAB_RUNNING);
    lab_home_close(&home);lab_home_close(&home);
    assert(fixture.opened==fixture.released && fixture.leases==0);
}
static void faults(void) {
    const uint8_t *codes[]={looping_blob,oob_blob,oom_blob};
    const uint32_t sizes[]={sizeof(looping_blob),sizeof(oob_blob),sizeof(oom_blob)};
    for(int i=0;i<3;i++){
        setup();fixture.code[0]=codes[i];fixture.sizes[0]=sizes[i];
        fixture.previous[0]=normal_blob;fixture.previous_sizes[0]=sizeof(normal_blob);
        frame(16,0);frame(0,0);frame(1,1);
        assert(home.mode==LAB_RELEASE && fixture.quarantines==1 && fixture.leases==0);
        frame(0,0);frame(16,0);assert(home.mode==LAB_RUNNING);back();
        assert(home.count==2);frame(4,0);frame(0,0);frame(16,0);
        assert(!strcmp(home.active_id,"game"));back();lab_home_close(&home);
    }
    setup();fixture.code[0]=looping_blob;fixture.sizes[0]=sizeof(looping_blob);
    frame(16,0);frame(0,0);frame(1,0);frame(0,0);
    assert(home.count==1 && !strcmp(home.apps[0].id,"game"));lab_home_close(&home);
}
static void failures(void) {
    setup();fixture.fail_open=true;frame(16,0);
    assert(home.mode==LAB_RELEASE && fixture.leases==0 && fixture.opened==fixture.released);
    lab_home_close(&home);
    setup();fixture.fail_quarantine=true;fixture.code[0]=bad_blob;fixture.sizes[0]=sizeof(bad_blob);
    frame(16,0);frame(0,0);frame(0,1);assert(fixture.leases==0);
    assert(home.count==1 && !strcmp(home.apps[0].id,"game"));
    frame(0,0);frame(16,0);assert(home.mode==LAB_RUNNING);back();lab_home_close(&home);
}
static void host_input(void) {
    setup();frame(16,0);
    assert(!lab_home_frame(&home,256,0));
    assert(home.mode==LAB_RELEASE && fixture.leases==0 && fixture.quarantines==0);
    frame(0,0);frame(16,0);
    assert(!lab_home_frame(&home,0,60001));
    assert(fixture.leases==0 && fixture.quarantines==0);lab_home_close(&home);
}
static void catalog_checks(void) {
    setup();fixture.count=17;assert(!lab_home_refresh(&home));assert(home.count==2);
    fixture.count=2;strcpy(fixture.info[1].id,"counter");
    assert(!lab_home_refresh(&home));assert(home.count==2);
    strcpy(fixture.info[1].id,"game");memset(fixture.info[0].title,'x',sizeof(fixture.info[0].title));
    assert(lab_home_refresh(&home));assert(home.count==1 && !strcmp(home.apps[0].id,"game"));
    fixture.count=0;assert(lab_home_refresh(&home));frame(16,0);assert(home.mode==LAB_HOME);
    lab_home_close(&home);
}
static void repeat(void) {
    setup();
    for(int i=0;i<100;i++) {frame(16,0);frame(0,0);assert(home.mode==LAB_RUNNING);back();}
    lab_home_close(&home);assert(fixture.opened==100 && fixture.released==100 && fixture.leases==0);
}
static void disabled_limit(void) {
    setup();fixture.count=1;fixture.fail_quarantine=true;
    fixture.code[0]=bad_blob;fixture.sizes[0]=sizeof(bad_blob);
    for(unsigned n=0;n<32;n++) {
        snprintf(fixture.info[0].id,sizeof(fixture.info[0].id),"app%u",n);
        assert(lab_home_refresh(&home) && home.count==1);
        frame(16,0);frame(0,0);
        assert(home.mode==LAB_RELEASE && home.count==0 && fixture.leases==0);
        frame(0,0);
    }
    lab_home_close(&home);
}
static bool file_row(void *context,uint32_t y,const uint16_t *pixels) {
    (void)y;FILE *file=context;
    unsigned char bytes[640];
    for(unsigned x=0;x<320;x++){bytes[x*2]=(unsigned char)pixels[x];bytes[x*2+1]=(unsigned char)(pixels[x]>>8);}
    return fwrite(bytes,1,sizeof(bytes),file)==sizeof(bytes);
}
static void capture(const char *name) {
    const char *folder=getenv("LAB_HOME_GALLERY");if(!folder)return;
    char path[1024];int n=snprintf(path,sizeof(path),"%s/%s.rgb565",folder,name);
    assert(n>0 && (size_t)n<sizeof(path));
    FILE *file=fopen(path,"wb");assert(file);
    assert(lab_ui_render(&home,file_row,file));assert(!fclose(file));
}
static void actual(void) {
#if HAS_C_APPS
    setup();fixture.code[0]=counter_blob;fixture.sizes[0]=sizeof(counter_blob);
    fixture.code[1]=game_blob;fixture.sizes[1]=sizeof(game_blob);
    capture("home");
    frame(16,0);frame(0,0);frame(1,10);assert(lab_vm_debug(&home.vm,"debug_value")==1);
    capture("counter");frame(192,1);capture("release");frame(0,1);assert(home.mode==LAB_HOME);
    frame(4,0);frame(0,0);frame(16,0);frame(0,0);frame(16,0);frame(1,300);
    assert(lab_vm_debug(&home.vm,"debug_x")==24 && lab_vm_debug(&home.vm,"debug_value")==1);
    capture("game");
    back();lab_home_close(&home);assert(fixture.opened==fixture.released);
#endif
}
int main(int argc,char **argv) {
    assert(argc==2);assert(lab_runtime_init(pool,sizeof(pool)));
    if(!strcmp(argv[1],"navigation"))navigation();
    else if(!strcmp(argv[1],"system-exit"))system_exit();
    else if(!strcmp(argv[1],"faults"))faults();
    else if(!strcmp(argv[1],"failures"))failures();
    else if(!strcmp(argv[1],"host-input"))host_input();
    else if(!strcmp(argv[1],"catalog"))catalog_checks();
    else if(!strcmp(argv[1],"repeat"))repeat();
    else if(!strcmp(argv[1],"disabled-limit"))disabled_limit();
    else if(!strcmp(argv[1],"actual"))actual();
    else abort();
    lab_runtime_destroy();return 0;
}
