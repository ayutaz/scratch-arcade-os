#pragma once
#include <stddef.h>
#define MALLOC_CAP_INTERNAL (1u<<11)
void heap_caps_free(void *);
