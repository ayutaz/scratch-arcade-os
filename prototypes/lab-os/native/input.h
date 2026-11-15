#ifndef LAB_INPUT_H
#define LAB_INPUT_H
#include <stdint.h>
#include <stdbool.h>
enum {LAB_KEY_FN=1,LAB_KEY_A=2,LAB_KEY_B=4,LAB_KEY_X=8,LAB_KEY_Y=16};
enum {LAB_INPUT_DIRECTION_THRESHOLD=40};
typedef struct {uint32_t held,keys;int32_t x,y;} LabInputSample;
/* Neutral means no physical keys or logical direction, including small ADC
 * drift. Raw/debounced keys remain conservative; Y also blocks the gate. */
static inline bool lab_input_is_neutral(const LabInputSample *s) {
    return s && !s->held && !s->keys &&
        s->x>=-LAB_INPUT_DIRECTION_THRESHOLD && s->x<=LAB_INPUT_DIRECTION_THRESHOLD &&
        s->y>=-LAB_INPUT_DIRECTION_THRESHOLD && s->y<=LAB_INPUT_DIRECTION_THRESHOLD;
}
typedef struct {
    uint32_t changed[5];
    uint32_t stable,candidate;
    bool primed;
} LabInputFilter;
/* Raw 12-bit axis codes and an active-high physical key mask (FN/A/B/X/Y).
 * New OS policy: per-key 20ms debounce and integer nearest/half-away rounding.
 * Pure stock evidence: center2048, dead zone120, +/-40 virtual threshold and
 * axis signs. keys is raw|debounced for conservative all-release gating;
 * held uses debounced keys only. Y stays in keys; ABI2 has no dedicated Y bit.
 * Invalid data changes neither filter nor output. A fresh filter reports held
 * keys immediately; the OS must gate startup until all controls are released. */
bool lab_input_sample(LabInputFilter *,uint32_t keys,int x_raw,int y_raw,uint32_t now,LabInputSample *);
#endif
