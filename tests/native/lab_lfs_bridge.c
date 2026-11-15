/* Test-only NOR block device. Every format here targets allocated host RAM. */
#include "app_lfs.h"
#include <stdlib.h>
#include <string.h>
#define BYTES (1024u*1024u)
typedef struct {
    lfs_t lfs;struct lfs_config cfg;LabLfs driver;
    uint8_t *disk;bool mounted,partial,offline;int cut,operations;
} Volume;
static int cut(Volume *v) {
    if(v->offline)return 2;
    if(v->cut>=0 && v->operations++>=v->cut) {v->offline=true;return 1;}
    return 0;
}
static int rd(const struct lfs_config *c,lfs_block_t b,lfs_off_t off,void *out,lfs_size_t n) {
    Volume *v=c->context;if(b>=256 || off+n>4096)return LFS_ERR_IO;
    memcpy(out,v->disk+b*4096+off,n);return 0;
}
static int prog(const struct lfs_config *c,lfs_block_t b,lfs_off_t off,const void *data,lfs_size_t n) {
    Volume *v=c->context;if(b>=256 || off+n>4096)return LFS_ERR_IO;
    int fail=cut(v);uint32_t count=fail ? (fail==1 && v->partial ? n/2 : 0) : n;
    uint8_t *out=v->disk+b*4096+off;const uint8_t *in=data;
    for(uint32_t i=0;i<count;i++) {
        if((out[i]&in[i])!=in[i])return LFS_ERR_CORRUPT;
        out[i]&=in[i];
    }
    return fail ? LFS_ERR_IO : 0;
}
static int erase(const struct lfs_config *c,lfs_block_t b) {
    Volume *v=c->context;if(b>=256)return LFS_ERR_IO;
    int fail=cut(v);
    memset(v->disk+b*4096,255,fail ? (fail==1 && v->partial ? 2048 : 0) : 4096);
    return fail ? LFS_ERR_IO : 0;
}
static int sync_disk(const struct lfs_config *c) {return cut(c->context) ? LFS_ERR_IO : 0;}
void *test_lfs_new(const uint8_t *image,uint32_t n,bool format) {
    if((image && (n!=BYTES || format)) || (!image && n))return NULL;
    Volume *v=calloc(1,sizeof(*v));if(!v)return NULL;
    v->disk=malloc(BYTES);if(!v->disk) {free(v);return NULL;}
    if(image)memcpy(v->disk,image,BYTES);else memset(v->disk,255,BYTES);
    v->cut=-1;
    v->cfg=(struct lfs_config){.context=v,.read=rd,.prog=prog,.erase=erase,.sync=sync_disk,
        .read_size=16,.prog_size=16,.block_size=4096,.block_count=256,
        .block_cycles=100,.cache_size=256,.lookahead_size=32};
    if(format && lfs_format(&v->lfs,&v->cfg)) {free(v->disk);free(v);return NULL;}
    v->mounted=lfs_mount(&v->lfs,&v->cfg)==0;return v;
}
void test_lfs_free(Volume *v) {if(v->mounted)lfs_unmount(&v->lfs);free(v->disk);free(v);}
int test_lfs_mounted(Volume *v) {return v->mounted;}
int test_lfs_connect(Volume *v,const LabStorage *services,uint32_t quota,bool create,LabStorage *out) {
    if(!v->mounted || !lab_lfs_init(&v->driver,&v->lfs,quota,services,create))return 0;
    *out=lab_lfs_storage(&v->driver);return 1;
}
void test_lfs_cut(Volume *v,int at,bool partial) {v->operations=0;v->cut=at;v->partial=partial;v->offline=false;}
int test_lfs_operations(Volume *v) {return v->operations;}
void test_lfs_dump(Volume *v,uint8_t *out) {memcpy(out,v->disk,BYTES);}
int test_lfs_mkdir(Volume *v,const char *path) {return lfs_mkdir(&v->lfs,path);}
int test_lfs_raw_put(Volume *v,const char *path,const uint8_t *p,uint32_t n) {
    lfs_file_t f;int err=lfs_file_open(&v->lfs,&f,path,LFS_O_WRONLY|LFS_O_CREAT|LFS_O_TRUNC);
    if(err)return 0;
    bool ok=lfs_file_write(&v->lfs,&f,p,n)==(lfs_ssize_t)n;
    return lfs_file_close(&v->lfs,&f)==0 && ok;
}
int test_lfs_raw_get(Volume *v,const char *path,uint8_t *p,uint32_t cap) {
    lfs_file_t f;if(lfs_file_open(&v->lfs,&f,path,LFS_O_RDONLY))return -1;
    lfs_ssize_t n=lfs_file_read(&v->lfs,&f,p,cap);
    if(lfs_file_close(&v->lfs,&f))return -1;
    return n;
}
