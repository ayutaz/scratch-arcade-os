#include "run_loop.h"
#include <string.h>
bool lab_loop_init(LabRunLoop *s,LabHome *home,const LabLoopIo *io,uint32_t now) {
    if(!s || !home || !io || !io->input || !io->paint)return false;
    memset(s,0,sizeof(*s));s->home=home;s->io=*io;s->previous=now;s->ready=s->gated=true;return true;
}
static int stop(LabRunLoop *s) {lab_home_close(s->home);s->ready=false;return LAB_LOOP_STOPPED;}
static bool valid(const LabInputSample *p) {
    return p->held<=255 && p->keys<=31 && p->x>=-100 && p->x<=100 && p->y>=-100 && p->y<=100;
}
int lab_loop_step(LabRunLoop *s,uint32_t now) {
    if(!s || !s->ready)return LAB_LOOP_STOPPED;
    uint32_t dt=now-s->previous;s->previous=now;
    if(dt>60000)return stop(s);
    uint32_t flags=s->io.services ? s->io.services(s->io.context,now) : 0;
    if(flags&~3u)return stop(s);
    LabHomeMode old_mode=s->home->mode;
    LabInputSample sample={0};int result=LAB_LOOP_OK;
    if(!s->io.input(s->io.context,now,&sample) || !valid(&sample)) {
        lab_home_close(s->home);s->home->notice=LAB_NOTICE_HOST_INPUT;s->gated=true;result=LAB_LOOP_INPUT_ERROR;
    } else {
        bool feed=true;
        bool neutral=lab_input_is_neutral(&sample);
        if(s->home->mode==LAB_HOME) {
            if(flags)s->gated=true;
            if(s->gated) {
                if(neutral && !(flags&LAB_SERVICE_INHIBIT_HOME))s->gated=false;
                else feed=false;
            }
        }
        if(feed) {
            if(!lab_home_frame(s->home,sample.held,dt))return stop(s);
            /* Paint initialized app content immediately, without reusing the
             * launch key as a pressed edge or charging pre-launch elapsed time. */
            if(old_mode==LAB_HOME && s->home->mode==LAB_RUNNING &&
               !lab_home_frame(s->home,sample.held,0))return stop(s);
        }
        if(old_mode==LAB_RELEASE && s->home->mode==LAB_HOME)
            s->gated=!neutral || (flags&LAB_SERVICE_INHIBIT_HOME);
    }
    bool changed=s->painted_mode!=s->home->mode || s->painted_notice!=s->home->notice ||
                 (s->home->mode==LAB_HOME && (s->painted_selected!=s->home->selected ||
                                             s->painted_catalog!=s->home->catalog_revision));
    if(!s->painted || changed || (s->home->mode==LAB_RUNNING && now-s->paint_at>=33)) {
        if(!s->io.paint(s->io.context,s->home))return stop(s);
        s->painted=true;s->paint_at=now;s->painted_mode=s->home->mode;s->painted_notice=s->home->notice;
        s->painted_selected=s->home->selected;s->painted_catalog=s->home->catalog_revision;
    }
    return result;
}
bool lab_loop_close(LabRunLoop *s) {
    if(!s)return false;
    s->ready=false;
    if(s->home && !lab_home_close(s->home))return false;
    memset(s,0,sizeof(*s));return true;
}
