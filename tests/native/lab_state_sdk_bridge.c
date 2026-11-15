#include "guest_vm.h"
#include <stdlib.h>
#include <string.h>
typedef struct {LabVm vm;int32_t values[8];unsigned mask,calls;int override,write_result;} Probe;
static _Alignas(8) unsigned char pool[196608];
int test_start(void){return lab_runtime_init(pool,sizeof(pool));}void test_stop(void){lab_runtime_destroy();}
void *test_new(void){Probe *p=calloc(1,sizeof(Probe));if(p)p->write_result=1;return p;}void test_free(Probe *p){lab_vm_close(&p->vm,1);free(p);}
static int state(void *ctx,uint32_t op,uint32_t slot,int32_t *value){
 Probe *p=ctx;p->calls++;if(p->override)return p->override;if(slot>7)return -1;
 if(op==LAB_VM_STATE_READ){if(!(p->mask&(1u<<slot)))return 0;*value=p->values[slot];return 1;}
 if(op==LAB_VM_STATE_WRITE){if(p->write_result!=1)return p->write_result;p->values[slot]=*value;p->mask|=1u<<slot;return 1;}return -1;
}
int test_open(Probe *p,uint8_t *bytes,unsigned n,unsigned caps,int backend){
 p->calls=p->mask=0;memset(p->values,0,sizeof(p->values));LabVmState io={p,state};
 return lab_vm_open_with_all_services(&p->vm,bytes,n,2,50000,caps,NULL,NULL,backend?&io:NULL);
}
int test_frame(Probe *p){return lab_vm_frame(&p->vm,0,16);}int test_value(Probe *p){return lab_vm_debug(&p->vm,"debug_value");}
void test_close(Probe *p){lab_vm_close(&p->vm,1);}unsigned test_calls(Probe *p){return p->calls;}
void test_override(Probe *p,int value){p->override=value;}

void test_seed(Probe *p,int32_t value){p->mask|=1;p->values[0]=value;}
void test_result(Probe *p,int value){p->write_result=value;}
int test_reopen(Probe *p,uint8_t *bytes,unsigned n,unsigned caps,int backend){
 LabVmState io={p,state};return lab_vm_open_with_all_services(&p->vm,bytes,n,2,50000,caps,NULL,NULL,backend?&io:NULL);
}
int test_frame_input(Probe *p,unsigned held,unsigned dt){return lab_vm_frame(&p->vm,held,dt);}
int test_debug_name(Probe *p,const char *name){return lab_vm_debug(&p->vm,name);}
unsigned test_draw_count(Probe *p){return p->vm.draw_count;}
int test_draw(Probe *p,unsigned i,unsigned j){return i<p->vm.draw_count&&j<5?p->vm.draws[i][j]:-1;}
