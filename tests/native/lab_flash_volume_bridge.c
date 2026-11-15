/* All ESP Flash calls in this fixture target a 1MiB malloc buffer on the Mac. */
#include "flash_volume.h"
#include <stdlib.h>
#include <string.h>
#define BYTES (1024u*1024u)
static esp_flash_t internal_chip={1},external_chip={2};
esp_flash_t *esp_flash_default_chip=&internal_chip;
static esp_partition_t parts[3];
static uint8_t *disk;
static int mode,bad,fault=-1,occurrence=1,partial,calls[6],iter_live;
struct esp_partition_iterator_opaque_ {unsigned at;};
void test_flash_table(int value) {
 mode=value;memset(parts,0,sizeof(parts));
 parts[0]=(esp_partition_t){.flash_chip=&internal_chip,.type=0,.address=0x10000,.size=0x200000,.erase_size=4096,.label="factory"};
 parts[1]=(esp_partition_t){.flash_chip=&internal_chip,.type=1,.subtype=0x83,.address=0x400000,.size=BYTES,.erase_size=4096,.label="lab_apps"};
 parts[2]=(esp_partition_t){.flash_chip=&internal_chip,.type=1,.subtype=2,.address=0x600000,.size=0x10000,.erase_size=4096,.label="other"};
 if(value==1)strcpy(parts[1].label,"vfs");
 if(value==2)parts[1].type=0;
 if(value==3)parts[1].subtype=0x82;
 if(value==4)parts[1].encrypted=true;
 if(value==5)parts[1].readonly=true;
 if(value==6)parts[1].erase_size=8192;
 if(value==7)parts[1].flash_chip=&external_chip;
 if(value==8)parts[1].address+=4096;
 if(value==9)parts[1].size-=4096;
 if(value==10)strcpy(parts[2].label,"lab_apps");
 if(value==11)parts[2].address=0x401000;
 if(value==15)parts[1].address=0xfffff000;
 if(value==16)memset(parts[1].label,'x',sizeof(parts[1].label));
 if(value==18)parts[0].size=0x500000;
 if(value==20)parts[2].address=0xfffff000;
}
int test_flash_seed(const uint8_t *p,uint32_t n) {
 if(n!=BYTES || iter_live)return 0;
 free(disk);disk=malloc(BYTES);if(!disk)return 0;memcpy(disk,p,n);
 fault=-1;occurrence=1;partial=bad=0;memset(calls,0,sizeof(calls));test_flash_table(0);return 1;
}
void test_flash_fault(int api,int nth,int half) {fault=api;occurrence=nth;partial=half;}
static bool fail(int api) {++calls[api];return fault==api && calls[api]==occurrence;}
esp_err_t esp_flash_get_size(esp_flash_t *chip,uint32_t *size) {
 if(chip!=&internal_chip)bad=1;
 if(fail(3) || mode==13)return ESP_FAIL;
 *size=mode==12 ? 0 : 8u*1024u*1024u;return ESP_OK;
}
esp_err_t esp_partition_find_err(esp_partition_type_t type,esp_partition_subtype_t subtype,const char *label,esp_partition_iterator_t *out) {
 calls[4]++;*out=NULL;
 if(type!=0xff || subtype!=0xff || label || iter_live)bad=1;
 if(mode==14)return ESP_FAIL;
 *out=calloc(1,sizeof(**out));if(!*out)return ESP_FAIL;iter_live++;return ESP_OK;
}
const esp_partition_t *esp_partition_get(esp_partition_iterator_t it) {return mode==19 ? NULL : &parts[it->at];}
void esp_partition_iterator_release(esp_partition_iterator_t it) {if(it) {calls[5]++;iter_live--;free(it);}}
esp_partition_iterator_t esp_partition_next(esp_partition_iterator_t it) {
 if(++it->at==3) {esp_partition_iterator_release(it);return NULL;}return it;
}
static bool bounds(const esp_partition_t *p,size_t off,size_t n) {
 if(p!=&parts[1] || off>BYTES || n>BYTES-off || !disk) {bad=1;return false;}return true;
}
esp_err_t esp_partition_read(const esp_partition_t *p,size_t off,void *out,size_t n) {
 if(!bounds(p,off,n))return ESP_FAIL;
 if(fail(0))return ESP_FAIL;
 memcpy(out,disk+off,n);return ESP_OK;
}
esp_err_t esp_partition_write(const esp_partition_t *p,size_t off,const void *input,size_t n) {
 if(!bounds(p,off,n) || off%16 || n%16) {bad=1;return ESP_FAIL;}
 bool failed=fail(1);if(failed && !partial)return ESP_FAIL;
 const uint8_t *in=input;size_t count=failed ? n/2 : n;
 for(size_t i=0;i<count;i++) {if((disk[off+i]&in[i])!=in[i])return ESP_FAIL;disk[off+i]&=in[i];}
 return failed ? ESP_FAIL : ESP_OK;
}
esp_err_t esp_partition_erase_range(const esp_partition_t *p,size_t off,size_t n) {
 if(!bounds(p,off,n) || off%4096 || n!=4096) {bad=1;return ESP_FAIL;}
 bool failed=fail(2);if(failed && !partial)return ESP_FAIL;
 memset(disk+off,255,failed ? n/2 : n);return failed ? ESP_FAIL : ESP_OK;
}
typedef struct {LabFlashVolume volume;LabHome home;bool home_owned;} Rig;
void *test_flash_new(void) {return calloc(1,sizeof(Rig));}
int test_flash_open(Rig *r,const LabStorage *services,uint32_t address,uint32_t bytes,uint32_t quota) {
 LabFlashLayout layout={address,bytes};return lab_flash_volume_open(&r->volume,&layout,services,quota);
}
int test_flash_close(Rig *r) {return lab_flash_volume_close(&r->volume);}
void test_flash_end_home(Rig *r) {if(r->home_owned) {lab_home_close(&r->home);r->home_owned=false;}}
void test_flash_free(Rig *r) {fault=-1;test_flash_end_home(r);lab_flash_volume_close(&r->volume);free(r);}
int test_flash_install(Rig *r,const uint8_t *p,uint32_t n) {return lab_store_install(&r->volume.store,p,n);}
int test_flash_home(Rig *r) {
 LabCatalog c=lab_store_catalog(&r->volume.store);r->home_owned=lab_home_init(&r->home,&c);return r->home_owned;
}
int test_flash_frame(Rig *r,uint32_t held) {return lab_home_frame(&r->home,held,10);}
int test_flash_value(Rig *r) {return lab_vm_debug(&r->home.vm,"debug_value");}
int test_flash_metric(Rig *r,int i) {
 int values[]={r->volume.ready,r->volume.mounted,r->volume.writable,r->volume.faulted,
 r->volume.store.healthy,r->volume.store.mounted,r->volume.store.lease!=NULL,bad,iter_live,(int)r->volume.store.count};
 return values[i];
}
int test_flash_calls(int i) {return calls[i];}
int test_flash_block(Rig *r,int op,uint32_t block,uint32_t off,uint32_t n) {
 const struct lfs_config *c=&r->volume.cfg;uint8_t buffer[4096];memset(buffer,255,sizeof(buffer));
 if(op==0)return c->read(c,block,off,buffer,n);
 if(op==1)return c->prog(c,block,off,buffer,n);
 if(op==2)return c->erase(c,block);
 return c->sync(c);
}
void test_flash_dump(void *out) {memcpy(out,disk,BYTES);}
