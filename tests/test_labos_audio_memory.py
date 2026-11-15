from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class AudioMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);p=Path(cls.tmp.name)
        (p/'esp_heap_caps.h').write_text('''#include <stddef.h>
#include <stdint.h>
#define MALLOC_CAP_INTERNAL (1u<<11)
#define MALLOC_CAP_8BIT (1u<<2)
void *heap_caps_malloc(size_t,uint32_t);void heap_caps_free(void *);
''')
        (p/'probe.c').write_text('''#include "audio_memory.h"
#include "esp_heap_caps.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
static unsigned calls,frees,frames;static int fail;static void *live;
void *heap_caps_malloc(size_t n,uint32_t caps){calls++;assert(caps==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
 if(fail)return NULL;frames=(unsigned)n/2;live=malloc(n);memset(live,0x55,n);return live;}
void heap_caps_free(void *p){assert(p==live);for(unsigned i=0;i<frames;i++)assert(((int16_t *)p)[i]==0);frees++;free(p);live=NULL;}
int main(int argc,char **argv){(void)argc;
 if(argv[1][0]=='s'){int16_t *p=lab_audio_pcm_alloc(32000);assert(p && frames==32000 && calls==1);
  p[0]=-32768;p[31999]=32767;assert(lab_audio_pcm_free(p,32000));assert(frees==1 && !live);
 }else{assert(!lab_audio_pcm_alloc(0));assert(!lab_audio_pcm_alloc(32001));assert(!calls);
  fail=1;assert(!lab_audio_pcm_alloc(16000));assert(calls==1 && !frees);fail=0;
  int16_t *p=lab_audio_pcm_alloc(16000);assert(p);assert(!lab_audio_pcm_free(p,0));assert(!lab_audio_pcm_free(NULL,16000));
  assert(!frees && live==p);assert(lab_audio_pcm_free(p,16000));}
 return 0;}
''')
        cls.executable=p/'probe';main=ROOT/'firmware/esp-idf/lab-os-core/main'
        r=subprocess.run(['/usr/bin/clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(main),'-I'+str(ROOT/'prototypes/lab-os/native'),
            str(main/'audio_memory.c'),str(p/'probe.c'),'-o',str(cls.executable)],capture_output=True,text=True,timeout=30)
        if r.returncode:raise RuntimeError(r.stderr)
    def test_internal_8bit_allocation_and_nonoptimized_scrub_before_free(self):
        r=subprocess.run([str(self.executable),'scrub'],capture_output=True,text=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr)
    def test_invalid_sizes_and_oom_do_not_free_unknown_or_live_buffers(self):
        r=subprocess.run([str(self.executable),'invalid'],capture_output=True,text=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr)
