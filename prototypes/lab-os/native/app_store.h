#ifndef LAB_APP_STORE_H
#define LAB_APP_STORE_H
#include "app_home.h"

#define LAB_PACKAGE_HEADER 256u
#define LAB_PACKAGE_MAX_WASM 65536u
#define LAB_INDEX_BYTES 1728u
#define LAB_STORE_OWNER "lab-os-c-store-v1\n"

/* Trusted OS callbacks; never exposed to guests. One serialized writer, no
 * live external changes. read: 1 found, 0 absent, -1 I/O failure. A NULL output
 * queries full length; otherwise it must read the complete object or fail.
 * put must durably finish before returning true; partial/uncertain writes may
 * return false. It need not be atomic: the alternate index remains untouched.
 * Driver owns a dedicated namespace, denies symlinks/path traversal, enforces
 * quota and never removes referenced immutable blobs. hash is SHA-256.
 * verify receives a disposable mutable WASM copy and must close the VM before
 * returning. It checks ABI, imports, bounded init and a zero-input frame.
 * The last verify argument is the complete capability mask (draw=1, output=2,
 * input=4, network=8), never a boolean. Verification must not bind physical services.
 * Hashes detect corruption; they do not authenticate the publisher. */
typedef struct {
    void *context;
    int (*read)(void *,const char *,uint8_t *,uint32_t,uint32_t *);
    bool (*put)(void *,const char *,const uint8_t *,uint32_t);
    bool (*hash)(void *,const uint8_t *,uint32_t,uint8_t digest[32]);
    bool (*verify)(void *,uint8_t *,uint32_t,uint32_t,uint32_t,uint32_t);
} LabStorage;
typedef struct {char id[33];uint8_t current[32],previous[32];} LabRecord;
typedef struct {
    LabStorage io;
    LabRecord records[LAB_MAX_APPS];
    uint32_t count,sequence;
    int slot;
    bool healthy,recovered,mounted,maintenance;
    uint8_t *lease;
} LabStore;

/* Zero-initialize before first init. Owner marker must already exist; init
 * never formats/adopts a foreign store. Close collector and Home/VM before
 * closing Store. Mutations/open/close/reinit reject maintenance ownership;
 * mutations reject a live image lease.
 * On uncertain writes healthy becomes false; the mounted in-memory snapshot
 * stays readable. Close/reopen before further mutations. Home can locally
 * disable the failed app and continue using other validated immutable blobs.
 * Quarantine rolls back once, or removes the failed app's index reference.
 * Uninstall removes references only; the explicit LittleFS collector reclaims
 * obsolete packages after checkpointing the retained current/previous set. */
bool lab_store_init(LabStore *,const LabStorage *);
bool lab_store_close(LabStore *);
LabCatalog lab_store_catalog(LabStore *);
bool lab_store_install(LabStore *,const uint8_t *,uint32_t);
bool lab_store_rollback(LabStore *,const char *);
bool lab_store_uninstall(LabStore *,const char *);
bool lab_store_quarantine(LabStore *,const char *);
/* Reserved for the serialized filesystem collector while maintenance is held.
 * Revalidate the disk snapshot and every current/previous package, then mirror
 * the catalog into the alternate slot before any referenced fallback is freed.
 * An initially empty/no-index store needs two commits. Never removes a blob. */
bool lab_store_gc_checkpoint(LabStore *);
#endif
