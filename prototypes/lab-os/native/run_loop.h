#ifndef LAB_RUN_LOOP_H
#define LAB_RUN_LOOP_H
#include "app_home.h"
#include "input.h"
enum {LAB_SERVICE_INHIBIT_HOME=1,LAB_SERVICE_CHANGED=2};
enum {LAB_LOOP_OK=0,LAB_LOOP_INPUT_ERROR=1,LAB_LOOP_STOPPED=2};
typedef struct {
    void *context;
    /* Poll even on silence. Flags describe management activity, not TX status:
     * INHIBIT while a session owns HOME; CHANGED for a transaction completed
     * inside this callback too. Do not request guest input from this callback. */
    uint32_t (*services)(void *,uint32_t now);
    bool (*input)(void *,uint32_t now,LabInputSample *);
    /* Synchronous complete paint; caller owns driver/sink buffers. */
    bool (*paint)(void *,const LabHome *);
} LabLoopIo;
typedef struct {
    LabHome *home;LabLoopIo io;
    uint32_t previous,paint_at,painted_selected,painted_catalog;
    LabHomeMode painted_mode;LabHomeNotice painted_notice;
    bool ready,gated,painted;
} LabRunLoop;
/* Fresh/closed object and initialized Home; single OS task. Borrowed I/O must
 * be finite and must not re-enter. Caller yields/waits between steps.
 * STOPPED stops guest execution; close(false) retains pending audio/image
 * ownership. Caller must retry close before freeing this loop or its parents.
 * USB/display/input/FS still belong to the caller.
 * INPUT_ERROR keeps polling services and waits for neutral after recovery.
 * Static HOME/RELEASE repaint only after visible state/catalog changes;
 * RUNNING keeps a 33ms start-to-start cadence. No driver-time guarantee.
 * Gating uses all physical keys and normalized axes, including unmapped Y. */
bool lab_loop_init(LabRunLoop *,LabHome *,const LabLoopIo *,uint32_t now);
int lab_loop_step(LabRunLoop *,uint32_t now);
bool lab_loop_close(LabRunLoop *);
#endif
