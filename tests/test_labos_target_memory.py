import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'firmware/esp-idf/lab-os-core/components/wamr/platform_memory.c'


class TargetMemoryTests(unittest.TestCase):
    def test_linear_memory_reservation_uses_runtime_pool_and_failed_growth_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'platform_api_extension.h').write_text('/* no extensions */\n')
            (root/'platform_api_vmcore.h').write_text('''
              #include <stddef.h>
              typedef int os_file_handle;
              enum {MMAP_PROT_NONE=0,MMAP_PROT_READ=1,MMAP_PROT_WRITE=2,MMAP_PROT_EXEC=4};
              void *os_malloc(unsigned);void os_free(void *);
              void *os_mmap(void *,size_t,int,int,int);void os_munmap(void *,size_t);
              void *os_mremap(void *,size_t,size_t);int os_mprotect(void *,size_t,int);
              static inline int os_get_invalid_handle(void){return -1;}
            ''')
            (root/'wasm_export.h').write_text('void *wasm_runtime_malloc(unsigned);void wasm_runtime_free(void *);\n')
            (root/'probe.c').write_text('''
              #include "platform_api_vmcore.h"
              #include <assert.h>
              #include <stdint.h>
              #include <stdlib.h>
              typedef union {max_align_t align;size_t size;} Header;
              static size_t live;static unsigned heap_calls;
              void *os_malloc(unsigned n){(void)n;heap_calls++;return NULL;}
              void os_free(void *p){(void)p;heap_calls++;}
              void *wasm_runtime_malloc(unsigned n){
                if(n>196608-live)return NULL;Header *h=malloc(sizeof(*h)+n);
                if(!h)return NULL;h->size=n;live+=n;return h+1;
              }
              void wasm_runtime_free(void *p){if(p){Header *h=(Header *)p-1;live-=h->size;free(h);}}
              int main(void){
                unsigned char *p=os_mmap(NULL,131072,MMAP_PROT_NONE,0,-1);
                assert(p && live==131072 && heap_calls==0);
                for(unsigned i=0;i<131072;i++)assert(p[i]==0);
                assert(os_mprotect(p,131072,3)==0);p[0]=42;p[131071]=7;
                assert(!os_mremap(p,131072,200000));assert(live==131072 && p[0]==42 && p[131071]==7);
                unsigned char *q=os_mremap(p,131072,65536);assert(q && live==65536 && q[0]==42);
                assert(!os_mmap(NULL,16,MMAP_PROT_EXEC,0,-1));
                os_munmap(q,65536);assert(!live && !heap_calls);return 0;
              }
            ''')
            exe=root/'probe'
            p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-I'+str(root),
                              str(SOURCE),str(root/'probe.c'),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=5)
            self.assertEqual(p.returncode,0,p.stderr)

    def test_nonexecutable_mapping_preserves_data_and_rejects_exec_fixed_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'platform_api_extension.h').write_text('/* ABI fixture: no extra declarations. */\n')
            (root / 'wasm_export.h').write_text('void *wasm_runtime_malloc(unsigned);void wasm_runtime_free(void *);\n')
            (root / 'platform_api_vmcore.h').write_text('''
                #include <stddef.h>
                typedef int os_file_handle;
                enum {MMAP_PROT_NONE=0, MMAP_PROT_READ=1, MMAP_PROT_WRITE=2, MMAP_PROT_EXEC=4, MMAP_MAP_FIXED=2};
                void *os_malloc(unsigned size); void os_free(void *ptr);
                void *os_mmap(void *,size_t,int,int,int);
                void os_munmap(void *,size_t); void *os_mremap(void *,size_t,size_t);
                int os_mprotect(void *,size_t,int);
                static inline os_file_handle os_get_invalid_handle(void) {return -1;}
            ''')
            (root / 'probe.c').write_text('''
                #include "platform_api_vmcore.h"
                #include <assert.h>
                #include <stdlib.h>
                #include <stdint.h>
                static int allocated;
                void *os_malloc(unsigned n) {void *p=malloc(n); if(p)++allocated; return p;}
                void os_free(void *p) {if(p)--allocated; free(p);}
                void *wasm_runtime_malloc(unsigned n) {return os_malloc(n);}
                void wasm_runtime_free(void *p) {os_free(p);}
                int main(void) {
                  assert(!os_mmap(0,64,7,0,-1));
                  assert(!os_mmap(0,64,3,MMAP_MAP_FIXED,-1));
                  assert(!os_mmap(0,64,3,0,0));
                  assert(!os_mmap(0,SIZE_MAX,3,0,-1));
                  unsigned char *p=os_mmap(0,64,3,0,-1);
                  assert(p); for(int i=0;i<64;i++)assert(p[i]==0);
                  p[0]=42; p[63]=7;
                  p=os_mremap(p,64,128); assert(p && p[0]==42 && p[63]==7 && p[127]==0);
                  assert(os_mprotect(p,128,MMAP_PROT_EXEC)==-1);
                  assert(os_mprotect(p,128,3)==0);
                  os_munmap(p,128); assert(allocated==0);
                  return 0;
                }
            ''')
            executable = root / 'probe'
            compiled = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                       '-I' + str(root), str(SOURCE), str(root / 'probe.c'),
                                       '-o', str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run([str(executable)], check=True, timeout=5)
