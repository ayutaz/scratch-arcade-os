#ifndef LAB_APP_HOME_H
#define LAB_APP_HOME_H
#include "guest_vm.h"

#define LAB_MAX_APPS 16
typedef struct {
    char id[33], title[81], version[25];
    bool enabled;
} LabAppInfo;
typedef struct {
    uint8_t *bytes;
    uint32_t size, pages, budget;
    uint32_t capabilities;
    void *lease;
} LabImage;
/* Catalog is a trusted OS service, never a guest import. open returns a mutable
 * image lease; release is called exactly once after all VM references close.
 * On a failed open, a partially returned image is also released. */
typedef struct {
    void *context;
    uint32_t (*count)(void *context);
    bool (*info)(void *context, uint32_t index, LabAppInfo *out);
    bool (*open)(void *context, const char *id, LabImage *out);
    void (*release)(void *context, LabImage *image);
    bool (*quarantine)(void *context, const char *id);
} LabCatalog;
typedef struct {
    void *context;
    bool (*open)(void *,uint32_t capabilities,LabVmAudio *);
    void (*poll)(void *,uint32_t os_time);
    bool (*close)(void *);
} LabHomeAudio;
typedef struct {
    void *context;
    bool (*open)(void *,uint32_t capabilities,LabVmNetwork *);
    void (*poll)(void *,uint32_t os_time);
    bool (*close)(void *);
} LabHomeNetwork;
typedef struct {
    void *context;
    bool (*open)(void *,const char *trusted_id,uint32_t capabilities,LabVmState *);
    void (*poll)(void *,uint32_t os_time);
    bool (*close)(void *);
} LabHomeState;
typedef enum { LAB_HOME, LAB_RUNNING, LAB_RELEASE, LAB_CLEANUP } LabHomeMode;
typedef enum { LAB_NOTICE_NONE, LAB_NOTICE_RETURN, LAB_NOTICE_FAULT,
               LAB_NOTICE_STORAGE, LAB_NOTICE_HOST_INPUT, LAB_NOTICE_AUDIO,LAB_NOTICE_NETWORK } LabHomeNotice;
typedef struct {
    LabCatalog catalog;
    LabAppInfo apps[LAB_MAX_APPS];
    uint32_t count, selected, previous_held, catalog_revision;
    char active_id[33], disabled[LAB_MAX_APPS][33];
    uint32_t disabled_count,os_time,release_reason;
    LabHomeAudio audio;
    LabHomeNetwork network;
    LabHomeState state;
    bool audio_owned,network_owned,state_owned,pending_failure,pending_quarantine;
    char failed_id[33];
    LabVm vm;
    LabImage image;
    LabHomeMode mode;
    LabHomeNotice notice;
} LabHome;

/* init expects a fresh/closed object and an already initialized runtime. */
bool lab_home_init(LabHome *home, const LabCatalog *catalog);
bool lab_home_refresh(LabHome *home);
bool lab_home_frame(LabHome *home, uint32_t held, uint32_t dt);
/* Configure only on HOME with no child. Optional trusted hooks; no device I/O.
 * On exit close VM, attempt network/audio release, then image. False close retains children and
 * LAB_CLEANUP, blocking launch/update/quarantine until a later retry succeeds. */
bool lab_home_set_audio(LabHome *,const LabHomeAudio *);
bool lab_home_set_network(LabHome *,const LabHomeNetwork *);
bool lab_home_set_state(LabHome *,const LabHomeState *);
bool lab_home_close(LabHome *home);
#endif
