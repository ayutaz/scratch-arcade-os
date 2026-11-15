#ifndef LAB_BOARD_DISPLAY_H
#define LAB_BOARD_DISPLAY_H
#include "ui.h"
#include "esp_lcd_types.h"
enum {LAB_DISPLAY_PROFILE_UNKNOWN=0,LAB_DISPLAY_PROFILE_STOCK_0111=1};
typedef struct {
    esp_lcd_panel_io_handle_t io;
    esp_lcd_panel_handle_t panel;
    uint8_t *row;
    bool bus_owned,backlight_owned,ready;
} LabBoardDisplay;
/* Zero-initialized/closed object; exclusive SPI2/pins, one OS task, no reentry.
 * Candidate profile is saved stock software, not a PCB ID or hardware test.
 * Fixed known pins only; unknown profiles do no I/O. Binary backlight, no PWM.
 * RGB565 is copied to a 640B internal DMA buffer and sent synchronously using
 * the pinned IDF SPI parameter path. No queued color transfer/callback exists.
 * IDF's bus/polling waits have no hard timeout: native-driver hangs are outside
 * guest isolation. A failed close retains ownership and requires retry.
 * The candidate opens this driver. Physical scanout still needs observation. */
bool lab_board_display_open(LabBoardDisplay *,int profile);
bool lab_board_display_row(LabBoardDisplay *,uint32_t y,const uint16_t pixels[320]);
bool lab_board_display_paint(LabBoardDisplay *,const LabHome *);
/* Single-actor trusted service only, after every eight completed rows. No VM,
 * app lifecycle, catalog mutation or recursive painting from this callback.
 * Frame contents stay fixed; callback/context are borrowed only for this call.
 * Row failure stops both painting and callbacks immediately. No hook on init. */
bool lab_board_display_paint_serviced(LabBoardDisplay *,const LabHome *,void (*service)(void *),void *);
bool lab_board_display_close(LabBoardDisplay *);
#endif
