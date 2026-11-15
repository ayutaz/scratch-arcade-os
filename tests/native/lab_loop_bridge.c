#include "run_loop.h"
#include "ui.h"
#include <stdlib.h>
LabHome *test_home_pointer(void *);
typedef struct {
    LabRunLoop loop;LabInputSample sample;
    uint32_t flags,reads,paints,rows,last_mode,last_draws,pixel,last_selected,last_count;
    bool input_ok,paint_ok;
} Rig;
static uint32_t service(void *context,uint32_t now) {(void)now;return ((Rig *)context)->flags;}
static bool read_input(void *context,uint32_t now,LabInputSample *sample) {
    (void)now;Rig *r=context;r->reads++;*sample=r->sample;return r->input_ok;
}
static bool row(void *context,uint32_t y,const uint16_t *pixels) {
    Rig *r=context;r->rows++;
    if(y==10)r->pixel=pixels[10];
    return r->paint_ok || y<7;
}
static bool paint(void *context,const LabHome *home) {
    Rig *r=context;r->paints++;r->last_mode=home->mode;r->last_draws=home->vm.draw_count;r->last_selected=home->selected;r->last_count=home->count;
    return lab_ui_render(home,row,r);
}
void *test_loop_new(void *fixture,uint32_t now) {
    Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;
    r->input_ok=r->paint_ok=true;
    LabLoopIo io={r,service,read_input,paint};
    if(!lab_loop_init(&r->loop,test_home_pointer(fixture),&io,now)) {free(r);return NULL;}
    return r;
}
void test_loop_free(Rig *r) {lab_loop_close(&r->loop);free(r);}
void test_loop_input(Rig *r,uint32_t held,uint32_t keys,int x,int y,int valid) {
    r->sample=(LabInputSample){held,keys,x,y};r->input_ok=valid!=0;
}
void test_loop_flags(Rig *r,uint32_t flags) {r->flags=flags;}
void test_loop_paint_ok(Rig *r,int value) {r->paint_ok=value!=0;}
void test_loop_notice(Rig *r,int notice) {r->loop.home->notice=(LabHomeNotice)notice;}
int test_loop_step(Rig *r,uint32_t now) {return lab_loop_step(&r->loop,now);}
uint32_t test_loop_metric(Rig *r,int which) {
    switch(which) {case 0:return r->reads;case 1:return r->paints;case 2:return r->rows;
        case 3:return r->last_mode;case 4:return r->last_draws;case 5:return r->pixel;case 7:return r->last_selected;case 8:return r->last_count;
        default:return r->loop.gated;}
}
