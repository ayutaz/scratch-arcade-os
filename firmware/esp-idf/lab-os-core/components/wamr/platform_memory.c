/* Interpreter-only platform adapter. No executable/native mappings. */
#include "platform_api_vmcore.h"
#include "platform_api_extension.h"
#include "wasm_export.h"
#include <limits.h>
#include <string.h>

void *os_mmap(void *hint, size_t size, int prot, int flags, os_file_handle file) {
    (void)hint;
    if (!size || size > UINT_MAX - 16 ||
        (prot != MMAP_PROT_NONE && prot != (MMAP_PROT_READ | MMAP_PROT_WRITE)) ||
        flags != 0 || file != os_get_invalid_handle()) return NULL;
    /* Interpreter/software bounds only: NONE reserves zeroed ordinary RW
     * memory. It does not establish inaccessible pages. Keep linear memory in
     * the initialized runtime pool, rather than a second 128KiB system heap. */
    void *memory = wasm_runtime_malloc((unsigned)size);
    if (memory) memset(memory, 0, size);
    return memory;
}

void os_munmap(void *memory, size_t size) {
    (void)size;
    wasm_runtime_free(memory);
}

void *os_mremap(void *old, size_t old_size, size_t new_size) {
    void *memory = os_mmap(NULL, new_size, MMAP_PROT_READ | MMAP_PROT_WRITE,
                           0, os_get_invalid_handle());
    if (!memory) return NULL;
    memcpy(memory, old, old_size < new_size ? old_size : new_size);
    os_munmap(old, old_size);
    return memory;
}

int os_mprotect(void *memory, size_t size, int prot) {
    (void)memory; (void)size;
    /* RW is ordinary allocation, not hardware-enforced protection. */
    return prot == (MMAP_PROT_READ | MMAP_PROT_WRITE) ? 0 : -1;
}

void os_dcache_flush(void) {}
void os_icache_flush(void *start, size_t size) { (void)start; (void)size; }
