#ifndef LAB_STATE_MOUNT_H
#define LAB_STATE_MOUNT_H
#include "state_binding.h"
#include "state_lfs.h"
/* Fresh object outlives Home and its borrowed callbacks. Already-mounted FS;
 * only a fresh HOME without children may attach. Missing/foreign/broken state
 * leaves storage apps unavailable; other apps remain usable. No format/adopt.
 * Close Home before unmounting the FS. */
typedef struct {LabStateLfs files;LabStateManager manager;bool attached;} LabStateMount;
bool lab_state_mount_attach(LabStateMount *,LabHome *,lfs_t *,bool create);
#endif
