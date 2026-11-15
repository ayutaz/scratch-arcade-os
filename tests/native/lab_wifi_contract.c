#include "board_wifi.h"
#include "esp_wifi_default.h"
#include <assert.h>
#include <string.h>
#include <stdlib.h>
static esp_netif_t interface,foreign;
const char *WIFI_EVENT="wifi",*IP_EVENT="ip";
static int fault,calls[24],foreign_wifi,foreign_sta,loop_exists,active_driver,netif_live,attached,netif_core;
static wifi_config_t *config_pointer;
static esp_event_handler_t wifi_cb,ip_cb;static void *wifi_ctx,*ip_ctx;static int32_t ip_id;
static int hit(int stage){calls[stage]++;return fault==stage;}
esp_err_t esp_wifi_get_mode(wifi_mode_t *m){hit(0);*m=WIFI_MODE_STA;return foreign_wifi ? ESP_OK : ESP_ERR_WIFI_NOT_INIT;}
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key){assert(netif_core);hit(1);return foreign_sta && !strcmp(key,"WIFI_STA_DEF") ? &foreign : NULL;}
esp_err_t esp_netif_init(void){if(hit(2))return ESP_FAIL;netif_core=1;return ESP_OK;}
esp_err_t esp_event_loop_create_default(void){if(hit(3))return ESP_FAIL;if(loop_exists)return ESP_ERR_INVALID_STATE;loop_exists=1;return ESP_OK;}
esp_err_t esp_wifi_init(const wifi_init_config_t *c){assert(!foreign_wifi && !c->nvs_enable);if(hit(4))return ESP_FAIL;active_driver=1;return ESP_OK;}
esp_err_t esp_wifi_set_storage(int storage){assert(active_driver && storage==WIFI_STORAGE_RAM);return hit(5)?ESP_FAIL:ESP_OK;}
esp_err_t esp_wifi_set_mode(wifi_mode_t mode){assert(calls[5] && mode==WIFI_MODE_STA);return hit(6)?ESP_FAIL:ESP_OK;}
esp_netif_t *esp_netif_new(const esp_netif_config_t *c){assert(c->station && active_driver);if(hit(7))return NULL;netif_live=1;return &interface;}
esp_err_t esp_netif_attach_wifi_station(esp_netif_t *p){assert(p==&interface && netif_live);attached=1;return hit(8)?ESP_FAIL:ESP_OK;}
esp_err_t esp_wifi_set_default_wifi_sta_handlers(void){assert(attached);return hit(9)?ESP_FAIL:ESP_OK;}
esp_err_t esp_event_handler_instance_register(esp_event_base_t b,int32_t id,esp_event_handler_t f,void *ctx,esp_event_handler_instance_t *out){
 int stage=b==WIFI_EVENT ? 10:11;if(hit(stage))return ESP_FAIL;
 if(b==WIFI_EVENT){assert(id==ESP_EVENT_ANY_ID);wifi_cb=f;wifi_ctx=ctx;*out=(void *)1;}
 else{assert(b==IP_EVENT && (id==ESP_EVENT_ANY_ID || id==IP_EVENT_STA_GOT_IP));ip_id=id;ip_cb=f;ip_ctx=ctx;*out=(void *)2;}return ESP_OK;
}
esp_err_t esp_wifi_set_config(int iface,wifi_config_t *c){assert(iface==WIFI_IF_STA && calls[5] && calls[6]);
 assert(!memcmp(c->sta.ssid,"lab-test",8) && !memcmp(c->sta.password,"test-only-key",13));
 assert(c->sta.threshold.authmode==WIFI_AUTH_WPA2_PSK);config_pointer=c;return hit(12)?ESP_FAIL:ESP_OK;
}
esp_err_t esp_wifi_start(void){for(unsigned i=0;i<sizeof(*config_pointer);i++)assert(!((uint8_t *)config_pointer)[i]);return hit(13)?ESP_FAIL:ESP_OK;}
esp_err_t esp_wifi_connect(void){assert(active_driver);return hit(14)?ESP_FAIL:ESP_OK;}
esp_err_t esp_wifi_stop(void){assert(active_driver);return hit(15)?ESP_FAIL:ESP_OK;}
esp_err_t esp_event_handler_instance_unregister(esp_event_base_t b,int32_t id,esp_event_handler_instance_t h){
 int stage=b==WIFI_EVENT ? 16:17;if(hit(stage))return ESP_FAIL;
 if(b==WIFI_EVENT){assert(id==ESP_EVENT_ANY_ID && h==(void *)1);wifi_cb=NULL;}
 else{assert(id==ip_id && h==(void *)2);ip_cb=NULL;}return ESP_OK;
}
esp_err_t esp_wifi_deinit(void){assert(!foreign_wifi && active_driver && !wifi_cb && !ip_cb);if(hit(18))return ESP_FAIL;active_driver=0;return ESP_OK;}
esp_err_t esp_wifi_clear_default_wifi_driver_and_handlers(void *p){assert(p==&interface && attached);if(hit(19))return ESP_FAIL;attached=0;return ESP_OK;}
void esp_netif_destroy(esp_netif_t *p){assert(p==&interface && netif_live && !attached);hit(20);netif_live=0;}
static LabWifiCredentials credentials(void){LabWifiCredentials c={.ssid_bytes=8,.password_bytes=13};memcpy(c.ssid,"lab-test",8);memcpy(c.password,"test-only-key",13);return c;}
static void start_event(void){assert(wifi_cb);wifi_cb(wifi_ctx,WIFI_EVENT,WIFI_EVENT_STA_START,NULL);}
static void disconnect_event(void){assert(wifi_cb);wifi_cb(wifi_ctx,WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,NULL);}
static void ip_event(bool correct){assert(ip_cb);ip_event_got_ip_t e={.esp_netif=correct ? &interface:&foreign,.ip_info.ip.addr=0x0a0200c0};ip_cb(ip_ctx,IP_EVENT,IP_EVENT_STA_GOT_IP,&e);}
static void open_wifi(LabWifi *w,uint32_t now){LabWifiCredentials c=credentials();assert(lab_wifi_open(w,&c,now));}
int main(int argc,char **argv){(void)argc;LabWifi w={0};LabWifiCredentials c=credentials();
 if(!strcmp(argv[1],"invalid")){
  c.ssid_bytes=0;assert(!lab_wifi_open(&w,&c,0));c=credentials();c.password_bytes=7;assert(!lab_wifi_open(&w,&c,0));
  c=credentials();c.ssid[0]=0;assert(!lab_wifi_open(&w,&c,0));for(unsigned i=0;i<24;i++)assert(!calls[i]);
 }else if(!strcmp(argv[1],"foreign")){
  foreign_wifi=1;assert(!lab_wifi_open(&w,&c,0));assert(!calls[4] && !calls[18]);foreign_wifi=0;
  foreign_sta=1;assert(!lab_wifi_open(&w,&c,0));assert(!calls[4] && !calls[18]);
 }else if(!strcmp(argv[1],"ram")){
  open_wifi(&w,0);assert(!calls[14]);start_event();assert(lab_wifi_poll(&w,0));assert(calls[14]==1);
  ip_event(false);assert(lab_wifi_status(&w)!=LAB_WIFI_READY);ip_event(true);assert(lab_wifi_poll(&w,16));
  assert(lab_wifi_status(&w)==LAB_WIFI_READY && lab_wifi_ipv4(&w)==0x0a0200c0);
  assert(lab_wifi_close(&w));assert(!active_driver && !netif_live && loop_exists);
 }else if(!strcmp(argv[1],"timeout")){
  open_wifi(&w,0xfffffff0);start_event();assert(lab_wifi_poll(&w,0));
  assert(!lab_wifi_poll(&w,30001));assert(lab_wifi_status(&w)==LAB_WIFI_FAILED);ip_event(true);
  assert(lab_wifi_status(&w)==LAB_WIFI_FAILED);assert(lab_wifi_close(&w));
 }else if(!strcmp(argv[1],"reconnect")){
  open_wifi(&w,0);start_event();lab_wifi_poll(&w,0);ip_event(true);lab_wifi_poll(&w,16);
  disconnect_event();assert(!lab_wifi_ipv4(&w));lab_wifi_poll(&w,17);assert(calls[14]==2);
  disconnect_event();lab_wifi_poll(&w,100);assert(calls[14]==2);lab_wifi_poll(&w,1017);assert(calls[14]==3);
  disconnect_event();lab_wifi_poll(&w,2017);assert(calls[14]==4);disconnect_event();
  assert(!lab_wifi_poll(&w,3017));assert(calls[14]==4);assert(lab_wifi_close(&w));
 }else if(!strcmp(argv[1],"partial")){
  for(int stage=2;stage<=13;stage++){fault=stage;assert(!lab_wifi_open(&w,&c,0));
   assert(!active_driver && !netif_live && !attached && !wifi_cb && !ip_cb);fault=0;assert(lab_wifi_close(&w));}
 }else if(!strcmp(argv[1],"stop-fail")){
  open_wifi(&w,0);fault=15;assert(!lab_wifi_close(&w));ip_event(true);assert(lab_wifi_status(&w)==LAB_WIFI_CLOSING);
  LabWifi other={0};assert(!lab_wifi_open(&other,&c,0));assert(!lab_wifi_open(&w,&c,0));
  fault=0;assert(lab_wifi_close(&w));assert(!active_driver && !netif_live);
 }else if(!strcmp(argv[1],"handlers")){
  open_wifi(&w,0);fault=17;assert(!lab_wifi_close(&w));assert(!wifi_cb && ip_cb && active_driver);
  int before=calls[16];fault=0;assert(lab_wifi_close(&w));assert(calls[16]==before && !active_driver);
 }else if(!strcmp(argv[1],"detach-fail")){
  open_wifi(&w,0);fault=19;assert(!lab_wifi_close(&w));int before=calls[19];fault=0;
  assert(!lab_wifi_close(&w));assert(calls[19]==before && netif_live && !calls[20]);
 }else if(!strcmp(argv[1],"cold-netif")){
  assert(!netif_core);open_wifi(&w,0);assert(netif_core);assert(lab_wifi_close(&w));assert(netif_core);
 }else if(!strcmp(argv[1],"borrow-loop")){
  loop_exists=1;open_wifi(&w,0);assert(lab_wifi_close(&w));assert(loop_exists);
  open_wifi(&w,10);assert(lab_wifi_close(&w));assert(loop_exists);
 }else if(!strcmp(argv[1],"lost-ip")){
  open_wifi(&w,0);start_event();lab_wifi_poll(&w,0);ip_event(true);lab_wifi_poll(&w,16);
  assert(lab_wifi_status(&w)==LAB_WIFI_READY);
  ip_event_got_ip_t e={.esp_netif=&foreign};
  ip_cb(ip_ctx,IP_EVENT,IP_EVENT_STA_LOST_IP,&e);assert(lab_wifi_status(&w)==LAB_WIFI_READY);
  e.esp_netif=&interface;if(ip_id==ESP_EVENT_ANY_ID)ip_cb(ip_ctx,IP_EVENT,IP_EVENT_STA_LOST_IP,&e);
  assert(!lab_wifi_ipv4(&w));assert(lab_wifi_status(&w)==LAB_WIFI_FAILED);
  ip_event(true);assert(lab_wifi_status(&w)==LAB_WIFI_FAILED);assert(lab_wifi_close(&w));
 }else if(!strcmp(argv[1],"stopped")){
  open_wifi(&w,0);start_event();lab_wifi_poll(&w,0);ip_event(true);lab_wifi_poll(&w,16);
  wifi_cb(wifi_ctx,WIFI_EVENT,WIFI_EVENT_STA_STOP,NULL);
  assert(!lab_wifi_poll(&w,17));assert(!lab_wifi_ipv4(&w));assert(lab_wifi_close(&w));
 }else if(!strcmp(argv[1],"deinit-fail")){
  open_wifi(&w,0);fault=18;assert(!lab_wifi_close(&w));
  assert(active_driver && netif_live && attached && !wifi_cb && !ip_cb && !calls[19]);
  int stops=calls[15];fault=0;assert(lab_wifi_close(&w));assert(calls[15]==stops && !netif_live);
 }else if(!strcmp(argv[1],"connect-fail")){
  open_wifi(&w,0);start_event();fault=14;
  assert(lab_wifi_poll(&w,0));assert(lab_wifi_poll(&w,999));assert(calls[14]==1);
  assert(lab_wifi_poll(&w,1000));assert(lab_wifi_poll(&w,2000));
  assert(!lab_wifi_poll(&w,3000));assert(calls[14]==3);fault=0;assert(lab_wifi_close(&w));
 }else return 2;
 return 0;}
