#include "resource_monitor.h"
#include "esp_heap_caps.h"
#include "freertos/task.h"
#include <string.h>
static LabResourceMonitor monitor;
static uint32_t now;
void heap_caps_get_info(multi_heap_info_t *p,uint32_t caps) {
    (void)caps;*p=(multi_heap_info_t){.total_free_bytes=50000,.largest_free_block=20000,.minimum_free_bytes=10000};
}
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t task) {(void)task;return 1234;}
void *test_telemetry_init(void) {memset(&monitor,0,sizeof(monitor));now=0;return &monitor;}
void test_telemetry_advance(unsigned n) {
    for(unsigned i=0;i<n;i++) {now+=1000;lab_resource_poll(&monitor,now,LAB_RESOURCE_RUNNING,0);}
}
void test_telemetry_sequence(uint32_t sequence) {monitor.sequence=sequence;}
