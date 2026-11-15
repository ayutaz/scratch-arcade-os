/* Host-only RAM-backed seed image. No device, path, port or partition API. */
#ifdef ESP_PLATFORM
#error "host-only image builder"
#endif
#include "app_lfs.h"
#include <stdlib.h>
#include <string.h>
#define MAX_IMAGE (8u*1024u*1024u)
typedef struct {
    lfs_t fs;struct lfs_config cfg;LabLfs files;LabStore store;
    uint8_t *data,read_cache[256],prog_cache[256],lookahead[32];
    uint32_t bytes;bool mounted,writable;
} Seed;
static bool range(Seed *s,lfs_block_t b,lfs_off_t off,lfs_size_t n) {
    return b<s->bytes/4096 && off<4096 && n && !(off%16) && !(n%16) && n<=4096-off;
}
static int read_block(const struct lfs_config *c,lfs_block_t b,lfs_off_t off,void *out,lfs_size_t n) {
    Seed *s=c->context;if(!out || !range(s,b,off,n))return LFS_ERR_INVAL;
    memcpy(out,s->data+(size_t)b*4096+off,n);return 0;
}
static int prog_block(const struct lfs_config *c,lfs_block_t b,lfs_off_t off,const void *data,lfs_size_t n) {
    Seed *s=c->context;if(!s->writable || !data || !range(s,b,off,n))return LFS_ERR_IO;
    uint8_t *out=s->data+(size_t)b*4096+off;const uint8_t *in=data;
    for(lfs_size_t i=0;i<n;i++)if((out[i]&in[i])!=in[i])return LFS_ERR_CORRUPT;
    for(lfs_size_t i=0;i<n;i++)out[i]&=in[i];return 0;
}
static int erase_block(const struct lfs_config *c,lfs_block_t b) {
    Seed *s=c->context;if(!s->writable || b>=s->bytes/4096)return LFS_ERR_IO;
    memset(s->data+(size_t)b*4096,255,4096);return 0;
}
static int sync_blocks(const struct lfs_config *c) {(void)c;return 0;}
void lab_seed_free(Seed *s) {
    if(!s)return;
    lab_store_close(&s->store);if(s->mounted)lfs_unmount(&s->fs);
    free(s->data);free(s);
}
static bool root_owned(Seed *s) {
    lfs_dir_t dir;if(lfs_dir_open(&s->fs,&dir,"/"))return false;
    struct lfs_info info;bool found=false,ok=true;int result;
    while((result=lfs_dir_read(&s->fs,&dir,&info))>0) {
        if(!strcmp(info.name,".") || !strcmp(info.name,".."))continue;
        if(found || info.type!=LFS_TYPE_DIR || strcmp(info.name,"lab-apps")) {ok=false;break;}
        found=true;
    }
    if(result<0)ok=false;
    int closed=lfs_dir_close(&s->fs,&dir);return ok && found && !closed;
}
void *lab_seed_new(uint32_t bytes,const uint8_t *input,const LabStorage *services) {
    if(bytes<65536 || bytes>MAX_IMAGE || bytes%4096 || !services || !services->hash || !services->verify)return NULL;
    Seed *s=calloc(1,sizeof(*s));if(!s)return NULL;
    s->data=malloc(bytes);if(!s->data) {free(s);return NULL;}
    s->bytes=bytes;s->writable=input==NULL;
    if(input)memcpy(s->data,input,bytes);else memset(s->data,255,bytes);
    s->cfg=(struct lfs_config){.context=s,.read=read_block,.prog=prog_block,.erase=erase_block,.sync=sync_blocks,
        .read_size=16,.prog_size=16,.block_size=4096,.block_count=bytes/4096,
        .block_cycles=100,.cache_size=256,.lookahead_size=32,
        .read_buffer=s->read_cache,.prog_buffer=s->prog_cache,.lookahead_buffer=s->lookahead};
    if(!input && lfs_format(&s->fs,&s->cfg))goto invalid;
    if(lfs_mount(&s->fs,&s->cfg))goto invalid;
    s->mounted=true;
    if(input && !root_owned(s))goto invalid;
    if(!lab_lfs_init(&s->files,&s->fs,bytes,services,!input))goto invalid;
    LabStorage io=lab_lfs_storage(&s->files);
    if(!lab_store_init(&s->store,&io))goto invalid;
    return s;
invalid:
    lab_seed_free(s);return NULL;
}
int lab_seed_install(Seed *s,const uint8_t *p,uint32_t n) {
    return s && s->writable && n<=16384 && lab_store_install(&s->store,p,n);
}
int lab_seed_count(Seed *s) {return s && s->store.mounted ? (int)s->store.count : -1;}
int lab_seed_package(Seed *s,uint32_t at,uint8_t *out,uint32_t cap) {
    if(!s || !s->store.mounted || at>=s->store.count)return -1;
    LabCatalog catalog=lab_store_catalog(&s->store);LabAppInfo info;
    if(!catalog.info(catalog.context,at,&info))return -1;
    const char *hex="0123456789abcdef";char key[69];
    for(unsigned i=0;i<32;i++) {uint8_t b=s->store.records[at].current[i];key[2*i]=hex[b>>4];key[2*i+1]=hex[b&15];}
    memcpy(key+64,".lab",5);uint32_t bytes=0;
    if(s->store.io.read(s->store.io.context,key,out,cap,&bytes)!=1 || bytes>16384)return -1;
    return (int)bytes;
}
int lab_seed_dump(Seed *s,uint8_t *out,uint32_t bytes) {
    if(!s || !s->mounted || !out || bytes!=s->bytes)return 0;
    memcpy(out,s->data,bytes);return 1;
}
