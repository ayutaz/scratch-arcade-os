#ifndef LAB_UI_H
#define LAB_UI_H
#include "app_home.h"

/* Writes exactly one RGB565 scanline. No allocation, device I/O, or guest calls.
 * Invalid state/commands leave the caller's output unchanged. */
bool lab_ui_row(const LabHome *home, uint32_t y, uint16_t pixels[320]);
/* The sink must consume/copy each borrowed row before returning. */
typedef bool (*LabUiSink)(void *context, uint32_t y, const uint16_t pixels[320]);
bool lab_ui_render(const LabHome *home, LabUiSink sink, void *context);
#endif
