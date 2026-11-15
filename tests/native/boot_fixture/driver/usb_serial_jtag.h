#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
typedef struct {uint32_t tx_buffer_size,rx_buffer_size;} usb_serial_jtag_driver_config_t;
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *);
esp_err_t usb_serial_jtag_driver_uninstall(void);
bool usb_serial_jtag_is_driver_installed(void);
int usb_serial_jtag_read_bytes(void *,uint32_t,uint32_t);
int usb_serial_jtag_write_bytes(const void *,size_t,uint32_t);
