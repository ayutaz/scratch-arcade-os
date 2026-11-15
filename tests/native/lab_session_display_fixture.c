/* Reuse the tested LCD API shim, with GPIO dispatched by the session rig. */
#define LAB_TEST_DISPLAY_CAPACITY 16384
#define gpio_config session_display_gpio_config
#define gpio_set_level session_display_gpio_set_level
#define gpio_reset_pin session_display_gpio_reset_pin
#define esp_lcd_panel_io_tx_param session_display_tx_param
#include "lab_board_display_bridge.c"
#undef esp_lcd_panel_io_tx_param
void test_audio_advance_us(unsigned);
esp_err_t esp_lcd_panel_io_tx_param(esp_lcd_panel_io_handle_t io,int command,const void *data,size_t n) {
 esp_err_t r=session_display_tx_param(io,command,data,n);
 if(r==ESP_OK && command==0x2c && n==640)test_audio_advance_us(333);
 return r;
}
