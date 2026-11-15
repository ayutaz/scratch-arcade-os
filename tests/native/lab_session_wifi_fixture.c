/* Same SDK fault model as the standalone driver contract, no real radio. */
#define main wifi_fixture_contract_main
#include "lab_wifi_contract.c"
#undef main
void test_wifi_reset(void) {
    assert(!active_driver && !netif_live && !attached && !wifi_cb && !ip_cb);
    fault=foreign_wifi=foreign_sta=loop_exists=netif_core=0;
    memset(calls,0,sizeof(calls));
}
void test_wifi_fault(int stage) {fault=stage;}
int test_wifi_calls(unsigned stage) {return stage<24 ? calls[stage] : -1;}
void test_wifi_notify(int kind) {if(kind==1)start_event();else if(kind==2)ip_event(true);else disconnect_event();}
