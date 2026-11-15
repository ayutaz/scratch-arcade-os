#ifndef LAB_BOARD_INPUT_H
#define LAB_BOARD_INPUT_H
#include "input.h"
#include "esp_adc/adc_oneshot.h"
enum {LAB_INPUT_PROFILE_UNKNOWN=0,LAB_INPUT_PROFILE_STOCK_0111=1};
typedef struct {
    adc_oneshot_unit_handle_t unit;
    adc_channel_t x_channel,y_channel;
    uint64_t gpio_owned;
    LabInputFilter filter;
    bool ready;
} LabBoardInput;
/* Zero-initialized/closed object, exclusive ownership, OS task context only.
 * The candidate profile is from the saved Arcade0.11.1 image, not a PCB ID.
 * No caller-supplied/guessed GPIOs. Mapping uses the IDF IO-to-channel API.
 * This code is compile/fixture tested only; main does not call it on hardware.
 * read failure clears output/filter; caller must gate until neutral again.
 * close false retains failed resource ownership so cleanup can be retried. */
bool lab_board_input_open(LabBoardInput *,int profile);
bool lab_board_input_read(LabBoardInput *,uint32_t now,LabInputSample *);
bool lab_board_input_close(LabBoardInput *);
#endif
