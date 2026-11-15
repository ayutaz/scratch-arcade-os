#ifndef LAB_STATE_LFS_H
#define LAB_STATE_LFS_H
#include "state_service.h"
#include "lfs.h"
#define LAB_STATE_LFS_OWNER "lab-os-app-state-v1\n"
/* Already-mounted OS filesystem, one serialized OS actor. No mount/format,
 * package edits or foreign adoption. create provisions only missing/empty
 * /lab-state. Max 32 identities, two <=52B records each, fixed owner marker.
 * Guest never supplies names. No deletion/GC of orphan state in this version.
 * Counts logical bytes, not littlefs allocation/erase overhead. */
typedef struct {lfs_t *fs;bool ready;} LabStateLfs;
bool lab_state_lfs_init(LabStateLfs *,lfs_t *,bool create);
LabStateIo lab_state_lfs_io(LabStateLfs *);
#endif
