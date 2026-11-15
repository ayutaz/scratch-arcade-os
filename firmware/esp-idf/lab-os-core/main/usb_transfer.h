#ifndef LAB_USB_TRANSFER_H
#define LAB_USB_TRANSFER_H
#include "app_transfer.h"
typedef struct {LabTransfer transfer;bool active,received;} LabUsbTransfer;
/* Borrow an already installed, exclusively owned USB Serial/JTAG driver.
 * Never installs/uninstalls/reconfigures it. Refuse USB console sharing.
 * Fresh/closed object only; close this service before Home/Store/USB driver.
 * poll reads one nonblocking 128-byte batch. A false return with active=true
 * means TX backpressure: keep polling, so the client can retry its same request.
 * A false return with active=false requires an explicit attach after repair.
 * Caller serializes OS services and defers app launch while transfer is busy. */
/* received reports a nonempty batch in the latest poll; it is cleared on each
 * poll/close. UI gating must also cover complete transactions in one read. */
bool lab_usb_transfer_attach(LabUsbTransfer *,LabStore *,LabHome *,uint32_t nonce,uint32_t now);
bool lab_usb_transfer_poll(LabUsbTransfer *,uint32_t now);
void lab_usb_transfer_close(LabUsbTransfer *);
#endif
