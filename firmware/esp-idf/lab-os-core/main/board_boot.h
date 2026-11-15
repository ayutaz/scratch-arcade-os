#ifndef LAB_BOARD_BOOT_H
#define LAB_BOARD_BOOT_H
#include "board_session.h"
#include "flash_volume.h"

#define LAB_BOOT_POOL_BYTES 163840u

typedef struct {int profile;LabFlashLayout layout;uint32_t quota;} LabBootConfig;
typedef struct {
    _Alignas(8) uint8_t pool[LAB_BOOT_POOL_BYTES];
    LabFlashVolume volume;
    LabBoardSession session;
    LabLfsGc gc;
    bool runtime_owned,volume_owned,session_owned,usb_owned,ready;
} LabBoardBoot;
/* Fresh/closed static or heap object, never on a task stack. One exclusive OS
 * task pinned to the same core for USB install/uninstall. Runtime must not be
 * initialized elsewhere. Caller supplies a reviewed layout; no default address
 * and no format/provision. Reject foreign USB driver unless console owns it;
 * console sharing or install failure leaves the local UI offline. Failed close
 * retains child/parent ownership for retry. No driver wall-clock guarantee.
 * API fixtures and compilation are not physical-device validation. */
bool lab_board_boot_open(LabBoardBoot *,const LabBootConfig *,uint32_t now);
int lab_board_boot_step(LabBoardBoot *,uint32_t now);
bool lab_board_boot_close(LabBoardBoot *);
#endif
