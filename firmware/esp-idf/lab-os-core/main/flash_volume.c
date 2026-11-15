#include "flash_volume.h"
#include "esp_flash.h"
#include <string.h>
static LabFlashVolume *owner;
static const esp_partition_t *select_partition(const LabFlashLayout *layout) {
    uint32_t flash_size=0;
    if(!esp_flash_default_chip || esp_flash_get_size(esp_flash_default_chip,&flash_size)!=ESP_OK ||
       (uint64_t)layout->address+layout->bytes>flash_size)return NULL;
    esp_partition_iterator_t it=NULL;
    if(esp_partition_find_err(ESP_PARTITION_TYPE_ANY,ESP_PARTITION_SUBTYPE_ANY,NULL,&it)!=ESP_OK || !it)return NULL;
    const esp_partition_t *selected=NULL;
    unsigned scanned=0;
    while(it) {
        const esp_partition_t *p=esp_partition_get(it);
        if(++scanned>128 || !p || !memchr(p->label,0,sizeof(p->label)))goto invalid;
        bool named=!strcmp(p->label,"lab_apps");
        if(named) {
            if(selected || p->flash_chip!=esp_flash_default_chip || p->type!=ESP_PARTITION_TYPE_DATA ||
               p->subtype!=ESP_PARTITION_SUBTYPE_DATA_LITTLEFS || p->encrypted || p->readonly ||
               p->erase_size!=4096 || p->address!=layout->address || p->size!=layout->bytes)goto invalid;
            selected=p;
        }
        if(p->flash_chip==esp_flash_default_chip) {
            uint64_t end=(uint64_t)p->address+p->size;
            if(!p->size || end>flash_size)goto invalid;
            if(!named && p->address<(uint64_t)layout->address+layout->bytes && layout->address<end)goto invalid;
        }
        it=esp_partition_next(it);
    }
    return selected;
invalid:
    esp_partition_iterator_release(it);return NULL;
}
static LabFlashVolume *context(const struct lfs_config *c) {
    LabFlashVolume *s=c ? c->context : NULL;
    return s && c==&s->cfg && s->partition && !s->faulted ? s : NULL;
}
static bool range(LabFlashVolume *s,lfs_block_t b,lfs_off_t off,lfs_size_t n) {
    return b<s->partition->size/4096 && off<4096 && n && !(off%16) && !(n%16) && n<=4096-off;
}
static int failed(LabFlashVolume *s) {
    s->faulted=true;s->writable=s->ready=s->files.ready=s->store.healthy=false;return LFS_ERR_IO;
}
static int read_block(const struct lfs_config *c,lfs_block_t b,lfs_off_t off,void *out,lfs_size_t n) {
    LabFlashVolume *s=context(c);if(!s)return LFS_ERR_IO;
    if(!out || !range(s,b,off,n))return LFS_ERR_INVAL;
    size_t at=(size_t)b*4096+off;
    return esp_partition_read(s->partition,at,out,n)==ESP_OK ? 0 : failed(s);
}
static int prog_block(const struct lfs_config *c,lfs_block_t b,lfs_off_t off,const void *data,lfs_size_t n) {
    LabFlashVolume *s=context(c);if(!s)return LFS_ERR_IO;
    if(!data || !range(s,b,off,n))return LFS_ERR_INVAL;
    if(!s->writable)return LFS_ERR_IO;
    size_t at=(size_t)b*4096+off;
    return esp_partition_write(s->partition,at,data,n)==ESP_OK ? 0 : failed(s);
}
static int erase_block(const struct lfs_config *c,lfs_block_t b) {
    LabFlashVolume *s=context(c);if(!s)return LFS_ERR_IO;
    if(b>=s->partition->size/4096)return LFS_ERR_INVAL;
    if(!s->writable)return LFS_ERR_IO;
    return esp_partition_erase_range(s->partition,(size_t)b*4096,4096)==ESP_OK ? 0 : failed(s);
}
static int sync_blocks(const struct lfs_config *c) {
    LabFlashVolume *s=context(c);
    /* Partition write/erase APIs complete synchronously; no separate sync API. */
    return s && s->writable ? 0 : LFS_ERR_IO;
}
static bool dedicated_root(LabFlashVolume *s) {
    lfs_dir_t dir;if(lfs_dir_open(&s->fs,&dir,"/"))return false;
    struct lfs_info info;bool found=false,state=false,ok=true;int result;
    while((result=lfs_dir_read(&s->fs,&dir,&info))>0) {
        if(!strcmp(info.name,".") || !strcmp(info.name,".."))continue;
        if(info.type!=LFS_TYPE_DIR) {ok=false;break;}
        if(!strcmp(info.name,"lab-apps") && !found)found=true;
        else if(!strcmp(info.name,"lab-state") && !state)state=true;
        else {ok=false;break;}
    }
    if(result<0)ok=false;
    int closed=lfs_dir_close(&s->fs,&dir);return ok && found && !closed;
}
bool lab_flash_volume_close(LabFlashVolume *s) {
    if(!s || s->store.lease)return false;
    s->ready=s->writable=s->files.ready=false;
    if(!lab_store_close(&s->store))return false;
    if(s->mounted && lfs_unmount(&s->fs))return false;
    memset(s,0,sizeof(*s));if(owner==s)owner=NULL;return true;
}
bool lab_flash_volume_open(LabFlashVolume *s,const LabFlashLayout *layout,const LabStorage *services,uint32_t quota) {
    if(!s || owner || s->partition || s->mounted || s->ready || s->store.mounted || s->store.lease ||
       !layout || !services || !services->hash || !services->verify ||
       layout->address<0x10000 || layout->address%4096 || layout->bytes<65536 || layout->bytes%4096 ||
       (uint64_t)layout->address+layout->bytes>UINT32_MAX || quota<sizeof(LAB_STORE_OWNER)-1 || quota>layout->bytes)return false;
    const esp_partition_t *partition=select_partition(layout);if(!partition)return false;
    owner=s;s->partition=partition;
    s->cfg=(struct lfs_config){.context=s,.read=read_block,.prog=prog_block,.erase=erase_block,.sync=sync_blocks,
        .read_size=16,.prog_size=16,.block_size=4096,.block_count=partition->size/4096,
        .block_cycles=100,.cache_size=256,.lookahead_size=32,
        .read_buffer=s->read_cache,.prog_buffer=s->prog_cache,.lookahead_buffer=s->lookahead};
    if(lfs_mount(&s->fs,&s->cfg))goto invalid;
    s->mounted=true;
    if(!dedicated_root(s) || !lab_lfs_init(&s->files,&s->fs,quota,services,false))goto invalid;
    LabStorage io=lab_lfs_storage(&s->files);
    if(!lab_store_init(&s->store,&io) || s->faulted)goto invalid;
    s->writable=s->ready=true;return true;
invalid:
    lab_flash_volume_close(s);return false;
}
