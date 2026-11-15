#ifndef LAB_NETWORK_BINDING_H
#define LAB_NETWORK_BINDING_H
#include "guest_vm.h"
#include "udp_service.h"
#include "app_home.h"
typedef struct {LabDatagram *datagram;uint32_t owner,now;} LabNetworkBinding;
/* Trusted OS manager owns this lease. Fresh zeroed binding. An open failure
 * can retain a partially opened driver: always attempt close before reuse.
 * VM must close before reusing/freeing this binding's storage. A managed link
 * loss may invalidate its callbacks by closing the socket while the VM lives,
 * only if storage remains alive and a borrow guard prevents reopen/reconfigure
 * until that VM closes. close(false) retains ownership and blocks the next app.
 * OS provides route/clock; guest cannot alter either. */
bool lab_network_binding_open(LabNetworkBinding *,LabDatagram *,uint32_t owner,uint32_t caps,
                              const LabUdpRoute *,uint32_t now);
bool lab_network_binding_close(LabNetworkBinding *);
bool lab_network_binding_poll(LabNetworkBinding *,uint32_t now);
int lab_network_binding_call(LabNetworkBinding *,uint32_t op,uint8_t *,uint32_t);
LabVmNetwork lab_network_binding_services(LabNetworkBinding *);
typedef struct {
    LabDatagram *datagram;
    LabNetworkBinding binding;
    LabUdpRoute route;
    uint32_t next_owner,now;
    bool has_route,available,lease_live;
} LabNetworkManager;
/* init/configure/available are trusted OS policy, never guest imports. No I/O.
 * Configure only without a borrowed VM/partial lease. Loss of availability
 * closes the socket on poll; lease_live still blocks policy changes/reopen
 * until Home closes the VM and returns the lease. No automatic app restart. */
bool lab_network_manager_init(LabNetworkManager *,LabDatagram *);
bool lab_network_manager_configure(LabNetworkManager *,const LabUdpRoute *);
void lab_network_manager_available(LabNetworkManager *,bool);
LabHomeNetwork lab_network_manager_services(LabNetworkManager *);
#endif
