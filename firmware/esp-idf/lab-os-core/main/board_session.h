#ifndef LAB_BOARD_SESSION_H
#define LAB_BOARD_SESSION_H
#include "board_display.h"
#include "board_input.h"
#include "usb_transfer.h"
#include "run_loop.h"
#include "board_sound.h"
#include "board_network.h"
enum {LAB_SESSION_PROFILE_UNKNOWN=0,LAB_SESSION_PROFILE_STOCK_0111=1};
typedef struct {
    LabStore *store;
    LabHome home;
    LabRunLoop loop;
    LabBoardInput input;
    LabBoardDisplay display;
    LabUsbTransfer usb;
    LabBoardSound sound;
    LabBoardNetwork network;
    struct {uint32_t held,started,duration,session,epoch,generation,applied;bool active;} remote;
    bool physical_seen,physical_neutral;
    bool home_owned,loop_owned,input_owned,display_owned,ready;
} LabBoardSession;
/* Fresh/closed object, one OS task, exclusive hardware. Runtime and opened
 * Store are borrowed; caller keeps them alive until close succeeds. This
 * session does not mount/format storage or install/uninstall USB drivers.
 * Unknown profile/invalid Store/nonce/lease are rejected before hardware I/O.
 * USB console sharing or unavailable USB leaves the local UI usable offline.
 * TX backpressure keeps the service alive. Read failure disables USB and frees
 * upload, without stopping local UI; explicit close/open is needed to reattach.
 * STOPPED attempts close; close false retains failed ownership for retry.
 * No hard native-driver deadline. Candidate entry opens this session; physical
 * success must be validated for each reviewed image, not inferred from fixtures. */
bool lab_board_session_open(LabBoardSession *,LabStore *,int profile,uint32_t nonce,uint32_t now);
int lab_board_session_step(LabBoardSession *,uint32_t now);
bool lab_board_session_close(LabBoardSession *);
#endif
