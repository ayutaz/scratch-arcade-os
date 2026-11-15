#ifndef LAB_TARGET_STORAGE_H
#define LAB_TARGET_STORAGE_H
#include "app_store.h"
/* Borrowed PSA service (IDF initializes it before app_main) and exclusive WAMR
 * runtime. No files, global crypto init/free, or hardware ownership here. */
LabStorage lab_target_storage_services(void);
#endif
