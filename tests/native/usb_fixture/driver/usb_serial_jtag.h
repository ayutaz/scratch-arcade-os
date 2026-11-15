#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
bool usb_serial_jtag_is_driver_installed(void);
int usb_serial_jtag_read_bytes(void *,uint32_t,uint32_t);
int usb_serial_jtag_write_bytes(const void *,size_t,uint32_t);
