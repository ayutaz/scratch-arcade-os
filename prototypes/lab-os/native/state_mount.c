#include "state_mount.h"
#include <stddef.h>
static bool open_state(void *ctx,const char *id,uint32_t caps,LabVmState *out){
 LabStateMount *s=ctx;if(!s->manager.state.ready)return false;
 LabHomeState services=lab_state_manager_services(&s->manager);
 return services.open(services.context,id,caps,out);
}
static void poll_state(void *ctx,uint32_t now){
 LabStateMount *s=ctx;if(!s->manager.state.ready)return;
 LabHomeState services=lab_state_manager_services(&s->manager);services.poll(services.context,now);
}
static bool close_state(void *ctx){
 LabStateMount *s=ctx;return !s->manager.state.ready||lab_state_close(&s->manager.state);
}
bool lab_state_mount_attach(LabStateMount *s,LabHome *home,lfs_t *fs,bool create){
 if(!s||s->attached||s->files.fs||s->manager.state.ready||!home||!fs||!home->catalog.count||
    home->mode!=LAB_HOME||home->image.bytes||home->image.lease||home->vm.instance||
    home->audio_owned||home->network_owned||home->state_owned||home->state.open)return false;
 if(lab_state_lfs_init(&s->files,fs,create)){
  LabStateIo io=lab_state_lfs_io(&s->files);
  if(!lab_state_manager_init(&s->manager,&io))return false;
 }
 LabHomeState services={s,open_state,poll_state,close_state};
 s->attached=lab_home_set_state(home,&services);return s->attached;
}
