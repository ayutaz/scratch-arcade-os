/* Volume fixture's first member is lfs_t; all formatting stays in its RAM NOR. */
#include "state_lfs.h"
#include "state_binding.h"
#include <stdlib.h>
typedef struct {LabStateLfs files;LabStateManager manager;LabStateIo io;bool ready;} Rig;
void *test_state_new(void *volume,int create){Rig *r=calloc(1,sizeof(*r));if(!r)return NULL;
 r->ready=lab_state_lfs_init(&r->files,(lfs_t *)volume,create!=0);
 if(r->ready){r->io=lab_state_lfs_io(&r->files);if(!lab_state_manager_init(&r->manager,&r->io))abort();}return r;}
void test_state_free(Rig *r){if(r->manager.state.ready)lab_state_close(&r->manager.state);free(r);}
int test_state_ready(Rig *r){return r->ready;}
int test_state_open(Rig *r,const char *id){return lab_state_open(&r->manager.state,id,0);}
int test_state_close(Rig *r){return lab_state_close(&r->manager.state);}
int test_state_read(Rig *r,unsigned slot,int fallback){int32_t v=0;return lab_state_read(&r->manager.state,slot,&v)==1?v:fallback;}
int test_state_write(Rig *r,unsigned slot,int value,unsigned now){lab_state_time(&r->manager.state,now);return lab_state_write(&r->manager.state,slot,value);}
int test_state_io_read(Rig *r,const char *id,unsigned bank){uint8_t bytes[52];uint32_t n=0;return r->ready?r->io.read(r->io.context,id,bank,bytes,52,&n):-1;}
int test_state_io_put(Rig *r,const char *id,unsigned bank){uint8_t bytes[52]={0};return r->ready&&r->io.put(r->io.context,id,bank,bytes,52);}
