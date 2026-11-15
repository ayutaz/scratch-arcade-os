#ifdef ESP_PLATFORM
#error "host-only heap instrumentation"
#endif
#include "heap_track.h"
#include <string.h>
typedef struct {void *p;size_t bytes;} Slot;
static Slot slots[4096];
static uint64_t live,peak,attempts,failures,blocks,bad,fail_at;
static size_t limit;
void lab_heap_window(size_t cap,uint64_t at) {
    limit=cap;fail_at=at;attempts=failures=0;peak=live;
}
bool lab_heap_reset(size_t cap,uint64_t at) {
    if(blocks)return false;
    memset(slots,0,sizeof(slots));live=bad=0;lab_heap_window(cap,at);return true;
}
uint64_t lab_heap_metric(unsigned i) {
    uint64_t values[]={live,peak,attempts,failures,blocks,bad};return i<6 ? values[i] : 0;
}
static int find(void *p) {
    for(unsigned i=0;i<4096;i++)if(slots[i].p==p)return (int)i;
    return -1;
}
static bool allowed(size_t n,size_t old) {
    attempts++;
    if((fail_at && attempts==fail_at) || live-old>limit || n>limit-(live-old)) {failures++;return false;}
    return true;
}
void *lab_heap_malloc(size_t n) {
    if(!n)n=1;
    if(!allowed(n,0))return NULL;
    int at=find(NULL);if(at<0) {failures++;return NULL;}
    void *p=malloc(n);if(!p) {failures++;return NULL;}
    slots[at]=(Slot){p,n};blocks++;live+=n;if(live>peak)peak=live;return p;
}
void *lab_heap_calloc(size_t count,size_t n) {
    if(n && count>SIZE_MAX/n) {attempts++;failures++;return NULL;}
    size_t bytes=count*n;void *p=lab_heap_malloc(bytes);
    if(p)memset(p,0,bytes);return p;
}
void lab_heap_free(void *p) {
    if(!p)return;
    int at=find(p);if(at<0) {bad++;return;}
    live-=slots[at].bytes;blocks--;slots[at]=(Slot){0};free(p);
}
void *lab_heap_realloc(void *p,size_t n) {
    if(!p)return lab_heap_malloc(n);
    if(!n) {lab_heap_free(p);return NULL;}
    int at=find(p);if(at<0) {bad++;return NULL;}
    size_t old=slots[at].bytes;if(!allowed(n,old))return NULL;
    void *q=realloc(p,n);if(!q) {failures++;return NULL;}
    slots[at]=(Slot){q,n};live=live-old+n;if(live>peak)peak=live;return q;
}
