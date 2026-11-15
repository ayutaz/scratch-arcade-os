#include "state_binding.h"
#include <stddef.h>
bool lab_state_manager_init(LabStateManager *m,const LabStateIo *io){
 return m && lab_state_init(&m->state,io);
}
static int command(void *c,uint32_t op,uint32_t slot,int32_t *value){
 LabStateManager *m=c;if(!value)return -1;
 if(op==LAB_VM_STATE_READ)return lab_state_read(&m->state,slot,value);
 if(op==LAB_VM_STATE_WRITE)return lab_state_write(&m->state,slot,*value);
 return -1;
}
static bool open_state(void *c,const char *id,uint32_t caps,LabVmState *out){
 LabStateManager *m=c;
 if(!out || caps>LAB_VM_CAP_ALL || !(caps&LAB_VM_CAP_STORAGE) || !lab_state_open(&m->state,id,m->now))return false;
 *out=(LabVmState){m,command};return true;
}
static void poll_state(void *c,uint32_t now){LabStateManager *m=c;m->now=now;lab_state_time(&m->state,now);}
static bool close_state(void *c){return lab_state_close(&((LabStateManager *)c)->state);}
LabHomeState lab_state_manager_services(LabStateManager *m){
 return m && m->state.ready ? (LabHomeState){m,open_state,poll_state,close_state}:(LabHomeState){0};
}
