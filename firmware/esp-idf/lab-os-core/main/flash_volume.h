#ifndef LAB_FLASH_VOLUME_H
#define LAB_FLASH_VOLUME_H
#include "app_lfs.h"
#include "esp_partition.h"
/* No default real-device address. Caller supplies an approved image layout. */
typedef struct {uint32_t address,bytes;} LabFlashLayout;
typedef struct {
    const esp_partition_t *partition;
    struct lfs_config cfg;
    lfs_t fs;
    LabLfs files;
    LabStore store;
    uint8_t read_cache[256],prog_cache[256],lookahead[32];
    bool mounted,writable,faulted,ready;
} LabFlashVolume;
/* Fresh/closed object; exclusive internal Flash volume, one OS task, no reentry.
 * Match explicit layout against the entire registered table: unique lab_apps,
 * DATA/LITTLEFS, 4KiB erase, plaintext/RW, internal chip, bounds, no overlap.
 * Mount with writes disabled; require dedicated root and existing Store owner.
 * Never formats/provisions/adopts. Hash/verify services and runtime are borrowed.
 * Physical I/O failure latches offline (including adapter/Store), until close/
 * reopen. Close refuses a live image lease; close the session/Home first and
 * keep this object alive until close succeeds. No Flash API is called by main
 * today: this module is compile/API-fixture tested only. */
bool lab_flash_volume_open(LabFlashVolume *,const LabFlashLayout *,const LabStorage *,uint32_t quota);
bool lab_flash_volume_close(LabFlashVolume *);
#endif
