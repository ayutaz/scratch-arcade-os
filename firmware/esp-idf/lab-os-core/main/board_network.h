#ifndef LAB_BOARD_NETWORK_H
#define LAB_BOARD_NETWORK_H
#include "board_wifi.h"
#include "board_udp.h"
#include "network_binding.h"
typedef struct {
    LabWifi driver;
    LabBoardUdp socket;
    LabDatagram udp;
    LabNetworkManager manager;
    bool configured,failed,cleanup;
} LabBoardNetwork;
/* Serialized OS service, no SDK/RF/heap work at init. START consumes a borrowed
 * canonical request, copies credentials temporarily and wipes that copy before
 * returning. No files, logs, SDK config persistence, credential readback or
 * implicit restart. STOP/timeout/failure release own driver. Failed cleanup
 * retains context and is retried by poll/close; ambiguous detach needs reset.
 * Radio survives USB disconnect; ends at STOP, failure/deadline or OS close.
 * Control matches LabTransferNetwork; 1=8-byte status, 0=rejected. */
bool lab_board_network_init(LabBoardNetwork *);
int lab_board_network_control(void *,const uint8_t *,uint32_t,uint32_t,uint8_t out[8]);
void lab_board_network_poll(LabBoardNetwork *,uint32_t now);
bool lab_board_network_close(LabBoardNetwork *);
/* App lease is unavailable until both Wi-Fi READY and an explicit OS route.
 * No RF/socket at init. VM/Home must return the lease before parent close.
 * Link loss closes UDP before Wi-Fi deinit; failed UDP close holds both. */
LabHomeNetwork lab_board_network_apps(LabBoardNetwork *);
#endif
