#ifndef LAB_STATE_BINDING_H
#define LAB_STATE_BINDING_H
#include "app_home.h"
#include "state_service.h"
/* One foreground lease. Trusted Home supplies identity and monotonic time.
 * No guest filenames/ids; close the VM before returning this borrowed lease. */
typedef struct {LabState state;uint32_t now;} LabStateManager;
bool lab_state_manager_init(LabStateManager *,const LabStateIo *);
LabHomeState lab_state_manager_services(LabStateManager *);
#endif
