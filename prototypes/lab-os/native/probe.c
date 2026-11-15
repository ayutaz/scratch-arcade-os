#include "guest_vm.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static _Alignas(8) uint8_t pool[196608];
static LabVm vm;

static bool frames(const char *p, uint32_t keys[256], uint32_t dt[256], int *count) {
    *count = 0;
    if (!*p || strlen(p) > 4096) return false;
    while (*p) {
        if (*count >= 256 || *p < '0' || *p > '9') return false;
        char *end;
        errno = 0;
        unsigned long k = strtoul(p, &end, 10);
        if (errno || k > 255 || *end != ':') return false;
        p = end + 1;
        if (*p < '0' || *p > '9') return false;
        unsigned long time = strtoul(p, &end, 10);
        if (errno || time > 60000 || (*end && *end != ',') || (*end == ',' && !end[1])) return false;
        keys[*count] = (uint32_t)k; dt[(*count)++] = (uint32_t)time;
        p = *end ? end + 1 : end;
    }
    return true;
}

int main(int argc, char **argv) {
    uint32_t keys[256], dt[256],caps=LAB_VM_CAP_DRAW; int count,first=1;
    if(argc>1 && !strncmp(argv[1],"--caps=",7)){
        char *end;errno=0;
        if(argv[1][7]<'0' || argv[1][7]>'9')return 64;
        unsigned long value=strtoul(argv[1]+7,&end,10);
        if(errno || *end || value>LAB_VM_CAP_ALL)return 64;
        caps=(uint32_t)value;first++;
    }
    if (argc < first+2 || !frames(argv[first], keys, dt, &count)) return 64;
    if (!lab_runtime_init(pool, sizeof(pool))) return 2;
    for (int app = first+1; app < argc; ++app) {
        FILE *f = fopen(argv[app], "rb"); if (!f) return 3;
        fseek(f, 0, SEEK_END); long size = ftell(f); rewind(f);
        if (size <= 0 || size > 262144) { fclose(f); return 4; }
        uint8_t *bytes = malloc((size_t)size); if (!bytes) { fclose(f); return 5; }
        size_t read = fread(bytes, 1, (size_t)size, f); fclose(f);
        if (read != (size_t)size) { free(bytes); return 6; }
        if (!lab_vm_open_with_services(&vm, bytes, (uint32_t)size, 2, 50000, caps, NULL, NULL)) {
            puts("{\"status\":\"rejected\",\"pool_bytes\":196608}");
        } else {
            for (int frame = 0; frame < count; ++frame) {
                int status = lab_vm_frame(&vm, keys[frame], dt[frame]);
                int32_t value = -1, x = -1, y = -1, elapsed = -1;
                if (status == 0) {
                    value = lab_vm_debug(&vm, "debug_value");
                    x = lab_vm_debug(&vm, "debug_x"); y = lab_vm_debug(&vm, "debug_y");
                    elapsed = lab_vm_debug(&vm, "debug_elapsed");
                }
                printf("{\"status\":\"%s\",\"app\":%d,\"frame\":%d,\"pool_bytes\":%zu,"
                       "\"value\":%d,\"x\":%d,\"y\":%d,\"elapsed\":%d,\"rects\":[",
                       status < 0 ? "trap" : (status ? "exit" : "running"), app - first - 1,
                       frame, sizeof(pool), value, x, y, elapsed);
                for (uint32_t d = 0; d < vm.draw_count; ++d) {
                    int32_t *r = vm.draws[d];
                    printf("%s[%d,%d,%d,%d,%d]", d ? "," : "", r[0], r[1], r[2], r[3], r[4]);
                }
                puts("]}");
                if (status) break;
            }
        }
        lab_vm_close(&vm, 1); free(bytes);
    }
    lab_runtime_destroy();
    return 0;
}
