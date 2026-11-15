#include "app_lfs.h"
#include <stdlib.h>
#include <string.h>
/* Match the test-only Volume prefix; no physical block device is used. */
typedef struct {lfs_t fs;struct lfs_config cfg;LabLfs files;} VolumePrefix;
LabStore *test_store_pointer(void *);
void *test_gc_new(void) {return calloc(1,sizeof(LabLfsGc));}
int test_gc_begin(LabLfsGc *g,VolumePrefix *v,void *f) {
 return lab_lfs_gc_begin(g,&v->files,test_store_pointer(f));
}
int test_gc_step(LabLfsGc *g) {return lab_lfs_gc_step(g);}
int test_gc_close(LabLfsGc *g) {return lab_lfs_gc_close(g);}
void test_gc_free(LabLfsGc *g) {lab_lfs_gc_close(g);free(g);}
uint32_t test_gc_stat(LabLfsGc *g,int i) {
 uint32_t values[]={g->stats.removed_files,g->stats.removed_bytes,g->stats.logical_before,g->stats.logical_after,g->active};
 return values[i];
}
int test_gc_store_close(void *f) {return lab_store_close(test_store_pointer(f));}
int test_gc_store_reinit(void *f) {LabStore *s=test_store_pointer(f);LabStorage io=s->io;return lab_store_init(s,&io);}
int test_gc_blocks(VolumePrefix *v) {return lfs_fs_size(&v->fs);}
