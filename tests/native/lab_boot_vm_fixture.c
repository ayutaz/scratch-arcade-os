/* Instrument runtime ownership without replacing the actual VM implementation. */
#define lab_runtime_init test_boot_runtime_init_real
#define lab_runtime_destroy test_boot_runtime_destroy_real
#include "../../prototypes/lab-os/native/guest_vm.c"
