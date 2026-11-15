/* Reuse the tested ADC/key API shim; no actual device function is linked. */
#define gpio_config session_input_gpio_config
#define gpio_reset_pin session_input_gpio_reset_pin
#include "lab_board_input_bridge.c"
