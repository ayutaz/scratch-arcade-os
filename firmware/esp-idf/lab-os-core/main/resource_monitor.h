#ifndef LAB_RESOURCE_MONITOR_H
#define LAB_RESOURCE_MONITOR_H
#include <stdbool.h>
#include <stdint.h>
#define LAB_RESOURCE_SAMPLES 32u
enum {LAB_RESOURCE_BEFORE_BOOT=1,LAB_RESOURCE_RUNNING,LAB_RESOURCE_OPEN_FAILED,
      LAB_RESOURCE_STOPPED,LAB_RESOURCE_CLOSING,LAB_RESOURCE_CLOSED};
enum {LAB_RESOURCE_RUNTIME=1,LAB_RESOURCE_READY=2,LAB_RESOURCE_APP=4,
      LAB_RESOURCE_UPLOAD=8,LAB_RESOURCE_GC=16};
typedef struct {uint32_t free_bytes,largest_free_bytes,minimum_free_bytes;} LabHeapSample;
typedef struct {
    uint32_t now,stage,flags;
    /* INTERNAL|8BIT, DMA|8BIT, SPIRAM|8BIT; capabilities overlap, do not sum. */
    LabHeapSample heap[3];
    uint32_t stack_free_bytes,vm_total,vm_used,vm_peak;
    bool vm_valid;
} LabResourceSample;
typedef struct {
    LabResourceSample rows[LAB_RESOURCE_SAMPLES];
    uint32_t next,count,last_time,last_stage,last_flags,sequence;
} LabResourceMonitor;
/* Fresh zeroed static object; single OS task, no ISR/concurrent reader.
 * One sample per second or observed stage/flag change. No allocation, logging,
 * storage, reset or USB I/O. Copy oldest-first, out-of-range leaves out intact.
 * Stack high-water is IDF bytes for the calling task, not all-task peak.
 * VM statistics are read only while caller owns an initialized pool runtime.
 * Captures are sequential, not atomic; transient allocations between polls can
 * be missed. Heap minima are sums of per-region low watermarks, not simultaneous
 * global minima. Zero external heap does not establish PSRAM capacity. */
bool lab_resource_poll(LabResourceMonitor *,uint32_t now,uint32_t stage,uint32_t flags);
uint32_t lab_resource_count(const LabResourceMonitor *);
bool lab_resource_get(const LabResourceMonitor *,uint32_t oldest_index,LabResourceSample *out);
/* Read-only wire provider: kind 0 header(schema,count,newest), kind 1 serial row.
 * Serial uint32 wraps normally; count distinguishes empty from newest==0.
 * Returns 1 success, 0 overwritten/absent row, -1 invalid arguments.
 * At most 80 bytes, no ring freeze/copy allocation, same OS actor only. */
int lab_resource_readout(void *,uint32_t kind,uint32_t sequence,uint8_t out[80],uint32_t *length);
#endif
