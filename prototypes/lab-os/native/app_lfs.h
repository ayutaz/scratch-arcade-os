#ifndef LAB_APP_LFS_H
#define LAB_APP_LFS_H
#include "app_store.h"
#include "lfs.h"

typedef struct {
    lfs_t *fs;
    LabStorage services;
    uint32_t quota;
    bool ready,collecting,gc_write;
} LabLfs;
/* Zero-initialize before first init. Caller supplies an already mounted,
 * dedicated filesystem and serializes all
 * access. This adapter never mounts, formats or grows a device. create=true
 * provisions /lab-apps/owner only in a missing/empty directory; never adopts
 * existing data. quota counts logical file bytes, not allocated flash blocks.
 * services supplies only hash/verify and their original context. There are no
 * symlinks in littlefs; all keys are restricted to a flat owned namespace.
 * Reinitialization during collection is rejected. */
bool lab_lfs_init(LabLfs *,lfs_t *,uint32_t quota,const LabStorage *services,bool create);
LabStorage lab_lfs_storage(LabLfs *);

typedef struct {uint32_t removed_files,removed_bytes,logical_before,logical_after;} LabGcStats;
typedef struct {
    LabLfs *files;LabStore *store;lfs_dir_t dir;LabGcStats stats;
    uint32_t entries,candidates;int phase;bool opened,active;
} LabLfsGc;
/* Fresh/closed collector, exclusive serialized access to this dedicated FS.
 * Locks Store mutations/open/close; existing leases reject begin. Preflight
 * the entire namespace (max 1024 files), checkpoint both fallback catalogs,
 * then remove only blobs absent from current/previous. Scan/sweep/count phases
 * inspect <=8 directory entries and remove <=1 blob per step. The checkpoint
 * phase validates up to 32 packages and its index puts rescan the namespace;
 * it may add two index files beyond the preflight limit. This bounds work,
 * not native wall-clock duration.
 * step: -1 failure, 0 more, 1 done. Successful done is repeatable. close cancels
 * and unlocks; close collector before Store/FS. Failure blocks writes until
 * adapter/Store reopen. Never mounts, formats or edits package contents. */
bool lab_lfs_gc_begin(LabLfsGc *,LabLfs *,LabStore *);
int lab_lfs_gc_step(LabLfsGc *);
bool lab_lfs_gc_close(LabLfsGc *);
#endif
