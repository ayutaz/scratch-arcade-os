/* Raw littlefs storage adapter, shared by host and future target block drivers. */
#include "app_lfs.h"
#include <stdio.h>
#include <string.h>
#define ROOT "/lab-apps"

static int kind(const char *key) {
    if(!key)return -1;
    size_t n=0;while(n<69 && key[n])n++;
    if(n==5 && !memcmp(key,"owner",5))return 0;
    if(n==7 && (!memcmp(key,"index-0",7) || !memcmp(key,"index-1",7)))return 1;
    if(n!=68 || memcmp(key+64,".lab",4))return -1;
    for(unsigned i=0;i<64;i++)if(!((key[i]>='0' && key[i]<='9') || (key[i]>='a' && key[i]<='f')))return -1;
    return 2;
}
static bool path(const char *key,char out[80]) {
    if(kind(key)<0)return false;
    int n=snprintf(out,80,ROOT "/%s",key);return n>0 && n<80;
}
static int read_raw(LabLfs *s,const char *key,uint8_t *out,uint32_t cap,uint32_t *n) {
    char name[80];if(!n || !path(key,name))return -1;
    struct lfs_info info;int err=lfs_stat(s->fs,name,&info);
    if(err==LFS_ERR_NOENT)return 0;
    if(err || info.type!=LFS_TYPE_REG)return -1;
    *n=info.size;if(!out)return 1;
    if(cap<*n)return -1;
    lfs_file_t f;if(lfs_file_open(s->fs,&f,name,LFS_O_RDONLY))return -1;
    bool ok=lfs_file_read(s->fs,&f,out,*n)==(lfs_ssize_t)*n;
    int close=lfs_file_close(s->fs,&f);return ok && !close ? 1 : -1;
}
static bool owned(LabLfs *s) {
    uint8_t owner[sizeof(LAB_STORE_OWNER)];uint32_t n=0;
    return read_raw(s,"owner",owner,sizeof(owner),&n)==1 && n==sizeof(LAB_STORE_OWNER)-1 &&
           !memcmp(owner,LAB_STORE_OWNER,n);
}
static bool usage(LabLfs *s,uint32_t *total,uint32_t *entries) {
    lfs_dir_t dir;if(lfs_dir_open(s->fs,&dir,ROOT))return false;
    struct lfs_info info;int result;bool ok=true;*total=*entries=0;
    while((result=lfs_dir_read(s->fs,&dir,&info))>0) {
        if(!strcmp(info.name,".") || !strcmp(info.name,".."))continue;
        if(info.type!=LFS_TYPE_REG || kind(info.name)<0 || UINT32_MAX-*total<info.size) {ok=false;break;}
        *total+=info.size;(*entries)++;
    }
    if(result<0)ok=false;
    return !lfs_dir_close(s->fs,&dir) && ok;
}
bool lab_lfs_init(LabLfs *s,lfs_t *fs,uint32_t quota,const LabStorage *services,bool create) {
    if(!s || s->collecting || !fs || !services || !services->hash || !services->verify || quota<sizeof(LAB_STORE_OWNER)-1)return false;
    memset(s,0,sizeof(*s));s->fs=fs;s->quota=quota;s->services=*services;
    struct lfs_info info;int err=lfs_stat(fs,ROOT,&info);
    if(err==LFS_ERR_NOENT) {
        if(!create || lfs_mkdir(fs,ROOT))return false;
    } else if(err || info.type!=LFS_TYPE_DIR)return false;
    if(owned(s)) {s->ready=true;return true;}
    uint32_t bytes=0,entries=0;
    if(!create || !usage(s,&bytes,&entries) || entries)return false;
    lfs_file_t f;
    if(lfs_file_open(fs,&f,ROOT "/owner",LFS_O_WRONLY|LFS_O_CREAT|LFS_O_EXCL))return false;
    bool ok=lfs_file_write(fs,&f,LAB_STORE_OWNER,sizeof(LAB_STORE_OWNER)-1)==sizeof(LAB_STORE_OWNER)-1;
    if(ok)ok=lfs_file_sync(fs,&f)==0;
    int close=lfs_file_close(fs,&f);
    s->ready=ok && !close && owned(s);return s->ready;
}
static int io_read(void *context,const char *key,uint8_t *out,uint32_t cap,uint32_t *n) {
    LabLfs *s=context;
    if(!s->ready || kind(key)<0 || !owned(s))return -1;
    return read_raw(s,key,out,cap,n);
}
static bool io_put(void *context,const char *key,const uint8_t *p,uint32_t n) {
    LabLfs *s=context;int type=kind(key);char name[80];
    if(!s->ready || (s->collecting && !s->gc_write) || type<1 || !p || !n || !path(key,name) || !owned(s) ||
       n>(type==1 ? LAB_INDEX_BYTES : LAB_PACKAGE_HEADER+LAB_PACKAGE_MAX_WASM))return false;
    struct lfs_info info;int err=lfs_stat(s->fs,name,&info);uint32_t old=0;
    if(!err) {if(type==2 || info.type!=LFS_TYPE_REG)return false;old=info.size;}
    else if(err!=LFS_ERR_NOENT)return false;
    uint32_t total=0,entries=0;
    if(!usage(s,&total,&entries) || total<old || (uint64_t)total-old+n>s->quota)return false;
    lfs_file_t f;
    if(lfs_file_open(s->fs,&f,name,LFS_O_WRONLY|LFS_O_CREAT|(type==2 ? LFS_O_EXCL : LFS_O_TRUNC)))return false;
    bool ok=lfs_file_write(s->fs,&f,p,n)==(lfs_ssize_t)n;
    if(ok)ok=lfs_file_sync(s->fs,&f)==0;
    int close=lfs_file_close(s->fs,&f);return ok && !close;
}
static bool io_hash(void *context,const uint8_t *p,uint32_t n,uint8_t hash[32]) {
    LabLfs *s=context;return s->services.hash(s->services.context,p,n,hash);
}
static bool io_verify(void *context,uint8_t *p,uint32_t n,uint32_t pages,uint32_t budget,uint32_t caps) {
    LabLfs *s=context;return s->services.verify(s->services.context,p,n,pages,budget,caps);
}
LabStorage lab_lfs_storage(LabLfs *s) {return (LabStorage){s,io_read,io_put,io_hash,io_verify};}

static bool referenced(const LabStore *store,const char *key) {
    static const char hex[]="0123456789abcdef";
    for(uint32_t i=0;i<store->count;i++) {
        const uint8_t *hashes[2]={store->records[i].current,store->records[i].previous};
        for(unsigned j=0;j<2;j++) {
            bool match=true,nonzero=false;
            for(unsigned b=0;b<32;b++)if(hashes[j][b])nonzero=true;
            if(!nonzero)continue;
            for(unsigned b=0;b<32;b++)if(key[2*b]!=hex[hashes[j][b]>>4] || key[2*b+1]!=hex[hashes[j][b]&15]) {match=false;break;}
            if(match)return true;
        }
    }
    return false;
}
bool lab_lfs_gc_close(LabLfsGc *g) {
    if(!g)return false;
    if(g->opened && lfs_dir_close(g->files->fs,&g->dir))return false;
    g->opened=false;
    if(g->files)g->files->collecting=g->files->gc_write=false;
    if(g->store)g->store->maintenance=false;
    g->files=NULL;g->store=NULL;g->active=false;
    if(g->phase!=4 && g->phase!=-1)g->phase=0;
    return true;
}
bool lab_lfs_gc_begin(LabLfsGc *g,LabLfs *s,LabStore *store) {
    if(!g || g->active || g->opened || g->files || g->store || !s || !s->ready || s->collecting ||
       !store || !store->mounted || !store->healthy || store->lease || store->maintenance ||
       store->count>LAB_MAX_APPS || store->io.context!=s || store->io.read!=io_read || store->io.put!=io_put ||
       store->io.hash!=io_hash || store->io.verify!=io_verify || !owned(s))return false;
    memset(g,0,sizeof(*g));g->files=s;g->store=store;
    s->collecting=store->maintenance=g->active=true;
    if(lfs_dir_open(s->fs,&g->dir,ROOT)) {lab_lfs_gc_close(g);return false;}
    g->opened=true;return true;
}
static int gc_failed(LabLfsGc *g) {
    g->files->ready=g->store->healthy=false;g->phase=-1;lab_lfs_gc_close(g);return -1;
}
int lab_lfs_gc_step(LabLfsGc *g) {
    if(!g)return -1;
    if(!g->active)return g->phase==4 ? 1 : -1;
    if(!g->files->ready || !g->store->healthy || !owned(g->files))return gc_failed(g);
    if(g->phase==1) {
        g->files->gc_write=true;
        bool ok=lab_store_gc_checkpoint(g->store);
        g->files->gc_write=false;
        if(!ok)return gc_failed(g);
        g->phase=2;g->entries=0;
        if(lfs_dir_open(g->files->fs,&g->dir,ROOT))return gc_failed(g);
        g->opened=true;return 0;
    }
    for(unsigned budget=0;budget<8;budget++) {
        struct lfs_info info;int result=lfs_dir_read(g->files->fs,&g->dir,&info);
        if(result<0)return gc_failed(g);
        if(!result) {
            if(lfs_dir_close(g->files->fs,&g->dir))return gc_failed(g);
            g->opened=false;
            if(g->phase==0 && g->candidates) {g->phase=1;return 0;}
            if(g->phase==2) {
                g->phase=3;g->entries=0;
                if(lfs_dir_open(g->files->fs,&g->dir,ROOT))return gc_failed(g);
                g->opened=true;return 0;
            }
            if(g->phase==0)g->stats.logical_after=g->stats.logical_before;
            g->phase=4;return lab_lfs_gc_close(g) ? 1 : -1;
        }
        if(!strcmp(info.name,".") || !strcmp(info.name,".."))continue;
        int type=kind(info.name);
        /* A checkpoint may create up to two index files after preflight. */
        uint32_t limit=g->phase==0 ? 1024 : 1026;
        if(++g->entries>limit || info.type!=LFS_TYPE_REG || type<0)return gc_failed(g);
        if(g->phase==0 || g->phase==3) {
            uint32_t *sum=g->phase==0 ? &g->stats.logical_before : &g->stats.logical_after;
            if(UINT32_MAX-*sum<info.size)return gc_failed(g);
            *sum+=info.size;
            if(g->phase==0 && type==2 && !referenced(g->store,info.name))g->candidates++;
        } else if(type==2 && !referenced(g->store,info.name)) {
            char name[80];
            if(!path(info.name,name) || lfs_remove(g->files->fs,name))return gc_failed(g);
            g->stats.removed_files++;g->stats.removed_bytes+=info.size;return 0;
        }
    }
    return 0;
}
