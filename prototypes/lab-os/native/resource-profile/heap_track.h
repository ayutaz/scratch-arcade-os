#ifndef LAB_HEAP_TRACK_H
#define LAB_HEAP_TRACK_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
/* Host-only, single actor. Payload bytes exclude allocator metadata and the
 * fixed bookkeeping table. Failed realloc preserves ownership/data. */
bool lab_heap_reset(size_t limit,uint64_t fail_at);
void lab_heap_window(size_t limit,uint64_t fail_at);
void *lab_heap_malloc(size_t);
void *lab_heap_calloc(size_t,size_t);
void *lab_heap_realloc(void *,size_t);
void lab_heap_free(void *);
uint64_t lab_heap_metric(unsigned);
#ifdef LAB_HEAP_TRACK
#define malloc lab_heap_malloc
#define calloc lab_heap_calloc
#define realloc lab_heap_realloc
#define free lab_heap_free
#endif
#endif
