import ctypes as C
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_labos_c_store as contract

ROOT=contract.ROOT
MAIN=ROOT/'firmware/esp-idf/lab-os-core/main'


class Heap(C.Structure):
    _fields_=[('free',C.c_uint32),('largest',C.c_uint32),('minimum',C.c_uint32)]


class Sample(C.Structure):
    _fields_=[('now',C.c_uint32),('stage',C.c_uint32),('flags',C.c_uint32),
              ('heap',Heap*3),('stack',C.c_uint32),('vm_total',C.c_uint32),
              ('vm_used',C.c_uint32),('vm_peak',C.c_uint32),('vm_valid',C.c_bool)]


class ResourceMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        folder=Path(cls.tmp.name)
        (folder/'fixture.c').write_text('''
#include "resource_monitor.h"
#include "esp_heap_caps.h"
#include "freertos/task.h"
#include "wasm_export.h"
#include <stdlib.h>
static uint32_t calls[8],mode;
void fixture_reset(void){for(unsigned i=0;i<8;i++)calls[i]=0;mode=0;}
void fixture_mode(unsigned n){mode=n;}
uint32_t fixture_calls(unsigned i){return calls[i];}
void heap_caps_get_info(multi_heap_info_t *p,uint32_t caps){
 unsigned at=3;
 if(caps==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT))at=0;
 if(caps==(MALLOC_CAP_DMA|MALLOC_CAP_8BIT))at=1;
 if(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT))at=2;
 calls[at]++;*p=(multi_heap_info_t){.total_free_bytes=50000+at,
 .largest_free_block=20000+at,.minimum_free_bytes=10000+at};
}
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t task){if(task)calls[7]++;calls[4]++;return 1234;}
bool wasm_runtime_get_mem_alloc_info(mem_alloc_info_t *p){calls[5]++;
 *p=(mem_alloc_info_t){.total_size=196192,.total_free_size=51192,.highmark_size=145000};
 if(mode==1)return false;
 if(mode==2)p->total_free_size=p->total_size+1;
 if(mode==3)p->highmark_size=p->total_size+1;
 if(mode==4)p->highmark_size=1;
 return true;
}
void *fixture_new(void){return calloc(1,sizeof(LabResourceMonitor));}
void fixture_free(void *p){free(p);}
size_t fixture_bytes(void){return sizeof(LabResourceMonitor);}
''')
        includes=['-I'+str(p) for p in (MAIN,ROOT/'tests/native/resource_fixture',contract.SOURCE/'core/iwasm/include')]
        obj=folder/'monitor.o';lib=folder/'monitor.dylib'
        result=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-fPIC',*includes,
                               '-c',str(MAIN/'resource_monitor.c'),'-o',str(obj)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise RuntimeError(result.stderr)
        cls.undefined=subprocess.check_output(['/usr/bin/nm','-u',str(obj)],text=True)
        subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',*includes,
                        str(obj),str(folder/'fixture.c'),'-o',str(lib)],capture_output=True,text=True,check=True,timeout=30)
        cls.api=C.CDLL(str(lib))
        signatures={'fixture_new':([],C.c_void_p),'fixture_free':([C.c_void_p],None),
                    'fixture_reset':([],None),'fixture_mode':([C.c_uint],None),
                    'fixture_calls':([C.c_uint],C.c_uint32),'fixture_bytes':([],C.c_size_t),
                    'lab_resource_poll':([C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32],C.c_bool),
                    'lab_resource_count':([C.c_void_p],C.c_uint32),
                    'lab_resource_get':([C.c_void_p,C.c_uint32,C.POINTER(Sample)],C.c_bool)}
        for name,(args,result) in signatures.items():
            fn=getattr(cls.api,name);fn.argtypes,fn.restype=args,result

    def setUp(self):
        self.api.fixture_reset();self.handle=self.api.fixture_new();self.assertTrue(self.handle)
        self.addCleanup(self.api.fixture_free,self.handle)

    def poll(self,now,stage=1,flags=0):return self.api.lab_resource_poll(self.handle,now,stage,flags)
    def get(self,at=0):
        row=Sample();self.assertTrue(self.api.lab_resource_get(self.handle,at,C.byref(row)));return row

    def test_first_sample_uses_separate_caps_and_stack_bytes_without_uninitialized_vm(self):
        self.assertTrue(self.poll(0));row=self.get()
        self.assertEqual((row.now,row.stage,row.flags,row.stack),(0,1,0,1234))
        self.assertEqual([(r.free,r.largest,r.minimum) for r in row.heap],[(50000+i,20000+i,10000+i) for i in range(3)])
        self.assertFalse(row.vm_valid);self.assertEqual(row.vm_total,0)
        self.assertEqual([self.api.fixture_calls(i) for i in range(8)],[1,1,1,0,1,0,0,0])

    def test_period_and_state_changes_capture_without_sampling_every_frame(self):
        self.assertTrue(self.poll(100));self.assertFalse(self.poll(1099));self.assertTrue(self.poll(1100))
        self.assertTrue(self.poll(1101,2,1));self.assertTrue(self.poll(1102,2,3));self.assertFalse(self.poll(1103,2,3))
        self.assertEqual(self.api.lab_resource_count(self.handle),4)
        self.assertEqual(self.api.fixture_calls(4),4)

    def test_wraparound_time_uses_unsigned_elapsed(self):
        self.assertTrue(self.poll(0xffffff00));self.assertFalse(self.poll(500));self.assertTrue(self.poll(744))
        self.assertEqual(self.api.lab_resource_count(self.handle),2)

    def test_vm_statistics_require_runtime_and_reject_invalid_or_unavailable_values(self):
        self.assertTrue(self.poll(0,2,1));row=self.get();self.assertTrue(row.vm_valid)
        self.assertEqual((row.vm_total,row.vm_used,row.vm_peak),(196192,145000,145000))
        for i in range(1,5):
            self.api.fixture_mode(i);self.assertTrue(self.poll(i*1000,2,1));row=self.get(i)
            self.assertFalse(row.vm_valid);self.assertEqual((row.vm_total,row.vm_used,row.vm_peak),(0,0,0))
        self.assertTrue(self.poll(5000,6,0));self.assertEqual(self.api.fixture_calls(5),5)

    def test_fixed_ring_keeps_last_32_chronological_samples_and_copy_is_independent(self):
        for i in range(40):self.assertTrue(self.poll(i*1000))
        self.assertEqual(self.api.lab_resource_count(self.handle),32)
        self.assertEqual([self.get(i).now for i in range(32)],list(range(8000,40000,1000)))
        row=self.get();row.now=0;self.assertEqual(self.get().now,8000)
        self.assertLessEqual(self.api.fixture_bytes(),4096)

    def test_invalid_requests_do_not_touch_kernel_or_output(self):
        for handle,stage,flags in ((None,1,0),(self.handle,0,0),(self.handle,7,0),(self.handle,1,32)):
            self.assertFalse(self.api.lab_resource_poll(handle,0,stage,flags))
        self.assertEqual(self.api.fixture_calls(4),0)
        row=Sample();row.now=77
        self.assertFalse(self.api.lab_resource_get(self.handle,0,C.byref(row)));self.assertEqual(row.now,77)
        self.assertFalse(self.api.lab_resource_get(None,0,C.byref(row)))
        self.assertEqual(self.api.lab_resource_count(None),0)
        self.assertTrue(self.poll(0));self.assertFalse(self.api.lab_resource_get(self.handle,32,C.byref(row)))
        self.assertFalse(self.api.lab_resource_get(self.handle,0,None))

    def test_sampler_has_no_dynamic_allocation_console_transfer_or_reset_dependencies(self):
        for forbidden in ('malloc','calloc','realloc','free','printf','usb_serial','esp_restart','esp_partition'):
            self.assertNotIn('_'+forbidden,self.undefined)


if __name__=='__main__':unittest.main()
