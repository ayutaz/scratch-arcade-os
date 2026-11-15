#include "resource_monitor.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wasm_export.h"
#include <stddef.h>

bool lab_resource_poll(LabResourceMonitor *s,uint32_t now,uint32_t stage,uint32_t flags) {
    if(!s || stage<LAB_RESOURCE_BEFORE_BOOT || stage>LAB_RESOURCE_CLOSED || (flags&~31u))return false;
    if(s->count && s->last_stage==stage && s->last_flags==flags && (uint32_t)(now-s->last_time)<1000)return false;
    LabResourceSample row={.now=now,.stage=stage,.flags=flags};
    const uint32_t caps[]={MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT,MALLOC_CAP_DMA|MALLOC_CAP_8BIT,
                           MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT};
    for(unsigned i=0;i<3;i++) {
        multi_heap_info_t info={0};heap_caps_get_info(&info,caps[i]);
        row.heap[i]=(LabHeapSample){info.total_free_bytes,info.largest_free_block,info.minimum_free_bytes};
    }
    row.stack_free_bytes=uxTaskGetStackHighWaterMark(NULL);
    if(flags&LAB_RESOURCE_RUNTIME) {
        mem_alloc_info_t info={0};
        if(wasm_runtime_get_mem_alloc_info(&info) && info.total_free_size<=info.total_size &&
           info.highmark_size<=info.total_size && info.highmark_size>=info.total_size-info.total_free_size) {
            row.vm_valid=true;row.vm_total=info.total_size;
            row.vm_used=info.total_size-info.total_free_size;row.vm_peak=info.highmark_size;
        }
    }
    s->sequence++;s->rows[s->next]=row;s->next=(s->next+1)%LAB_RESOURCE_SAMPLES;
    if(s->count<LAB_RESOURCE_SAMPLES)s->count++;
    s->last_time=now;s->last_stage=stage;s->last_flags=flags;return true;
}
uint32_t lab_resource_count(const LabResourceMonitor *s) {return s ? s->count : 0;}
bool lab_resource_get(const LabResourceMonitor *s,uint32_t at,LabResourceSample *out) {
    if(!s || !out || at>=s->count)return false;
    *out=s->rows[(s->next+LAB_RESOURCE_SAMPLES-s->count+at)%LAB_RESOURCE_SAMPLES];return true;
}

static void put32(uint8_t *p,uint32_t value) {for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(value>>(8*i));}
int lab_resource_readout(void *context,uint32_t kind,uint32_t sequence,uint8_t out[80],uint32_t *length) {
    if(length)*length=0;
    LabResourceMonitor *s=context;
    if(!s || !out || !length || kind>1 || (!kind && sequence))return -1;
    if(!kind) {put32(out,1);put32(out+4,s->count);put32(out+8,s->sequence);*length=12;return 1;}
    uint32_t age=s->sequence-sequence;
    if(age>=s->count)return 0;
    const LabResourceSample *row=&s->rows[(s->next+LAB_RESOURCE_SAMPLES-1-age)%LAB_RESOURCE_SAMPLES];
    uint32_t words[18]={sequence,row->now,row->stage,row->flags};
    for(unsigned i=0;i<3;i++) {
        words[4+3*i]=row->heap[i].free_bytes;
        words[5+3*i]=row->heap[i].largest_free_bytes;
        words[6+3*i]=row->heap[i].minimum_free_bytes;
    }
    words[13]=row->stack_free_bytes;words[14]=row->vm_total;words[15]=row->vm_used;
    words[16]=row->vm_peak;words[17]=row->vm_valid ? 1u : 0u;
    for(unsigned i=0;i<18;i++)put32(out+4*i,words[i]);
    *length=72;return 1;
}
