import ctypes as C
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'prototypes/lab-os/native/resource-profile'


class HeapTrackerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        output=Path(cls.tmp.name)/'heap.dylib'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                          str(SOURCE/'heap_track.c'),'-o',str(output)],capture_output=True,text=True,timeout=30)
        if p.returncode: raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(output))
        for name,args,result in (
            ('reset',[C.c_size_t,C.c_uint64],C.c_bool),('window',[C.c_size_t,C.c_uint64],None),
            ('malloc',[C.c_size_t],C.c_void_p),('calloc',[C.c_size_t,C.c_size_t],C.c_void_p),
            ('realloc',[C.c_void_p,C.c_size_t],C.c_void_p),('free',[C.c_void_p],None),
            ('metric',[C.c_uint],C.c_uint64)):
            fn=getattr(cls.lib,'lab_heap_'+name);fn.argtypes,fn.restype=args,result

    def setUp(self):
        self.assertTrue(self.lib.lab_heap_reset(1024,0));self.pointers=[]
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for p in self.pointers: self.lib.lab_heap_free(p)

    def alloc(self,n):
        p=self.lib.lab_heap_malloc(n)
        if p:self.pointers.append(p)
        return p

    def release(self,p): self.lib.lab_heap_free(p);self.pointers.remove(p)
    def metric(self,i):return self.lib.lab_heap_metric(i)

    def test_payload_counts_zero_initialization_alignment_and_cleanup(self):
        a=self.alloc(128);b=self.lib.lab_heap_calloc(16,8);self.pointers.append(b)
        self.assertTrue(a and b);self.assertEqual(a%8,0);self.assertEqual(b%8,0)
        self.assertEqual(C.string_at(b,128),bytes(128))
        self.assertEqual([self.metric(i) for i in (0,1,4)],[256,256,2])
        self.release(a);self.release(b);self.assertEqual(self.metric(0),0)

    def test_budget_rejection_does_not_consume_capacity(self):
        self.lib.lab_heap_window(128,0);a=self.alloc(96);b=self.alloc(32)
        self.assertTrue(a and b);self.assertFalse(self.alloc(1));self.assertEqual(self.metric(0),128)
        self.release(a);c=self.alloc(64);self.assertTrue(c);self.assertEqual(self.metric(0),96)
        self.assertEqual(self.metric(3),1)

    def test_failed_realloc_retains_original_data_and_success_updates_counts(self):
        self.lib.lab_heap_window(128,0);p=self.alloc(64);C.memmove(p,b'keep',4)
        self.assertFalse(self.lib.lab_heap_realloc(p,160));self.assertEqual(C.string_at(p,4),b'keep')
        self.assertEqual(self.metric(0),64)
        self.lib.lab_heap_window(256,0);q=self.lib.lab_heap_realloc(p,160)
        self.assertTrue(q);self.pointers.remove(p);self.pointers.append(q)
        self.assertEqual(C.string_at(q,4),b'keep');self.assertEqual([self.metric(i) for i in (0,1)],[160,160])

    def test_one_shot_failure_and_window_preserve_live_ownership(self):
        self.lib.lab_heap_window(128,2);a=self.alloc(8);self.assertTrue(a)
        self.assertFalse(self.alloc(8));self.assertTrue(self.alloc(8))
        self.assertFalse(self.lib.lab_heap_reset(128,0));self.assertEqual(self.metric(0),16)
        self.lib.lab_heap_window(128,0);self.assertEqual([self.metric(i) for i in (0,1,2)],[16,16,0])

    def test_overflow_and_unowned_or_double_free_are_detected_without_dereference(self):
        self.assertFalse(self.lib.lab_heap_calloc(C.c_size_t(-1).value,2))
        self.lib.lab_heap_free(C.c_void_p(123));self.assertEqual(self.metric(5),1)
        p=self.alloc(8);self.release(p);self.lib.lab_heap_free(p);self.assertEqual(self.metric(5),2)

    def test_zero_budget_and_realloc_zero_release(self):
        p=self.alloc(16);self.pointers.remove(p)
        self.assertFalse(self.lib.lab_heap_realloc(p,0));self.assertEqual(self.metric(0),0)
        self.lib.lab_heap_window(0,0);self.assertFalse(self.alloc(1));self.assertEqual(self.metric(4),0)
