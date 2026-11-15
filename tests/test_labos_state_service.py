"""専用設定8slotの分離・保存失敗・交互recordを合成永続I/Oで検証。"""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class StateServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'state.so';native=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),str(native/'state_service.c'),str(ROOT/'tests/native/lab_state_bridge.c'),'-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.restype=C.c_void_p
        cls.lib.test_free.argtypes=[C.c_void_p];cls.lib.test_open.argtypes=[C.c_void_p,C.c_char_p,C.c_uint]
        cls.lib.test_close.argtypes=[C.c_void_p];cls.lib.test_read.argtypes=[C.c_void_p,C.c_uint,C.c_int]
        cls.lib.test_write.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_uint];cls.lib.test_scrubbed.argtypes=[C.c_void_p]
        cls.lib.test_corrupt.argtypes=[C.c_uint,C.c_uint,C.c_uint]
    def setUp(self):
        self.lib.test_disk_reset();self.s=self.lib.test_new();self.addCleanup(self.lib.test_free,self.s)
    def open(self,name=b'alpha',now=0):return self.lib.test_open(self.s,name,now)
    def read(self,slot=0,default=17):return self.lib.test_read(self.s,slot,default)
    def write(self,slot,value,now=0):return self.lib.test_write(self.s,slot,value,now)
    def test_init_no_io_invalid_identity_and_missing_slot_use_default(self):
        self.assertEqual(self.lib.test_io_count(),0)
        for name in (b'',b'../alpha',b'A',b'a/b',b'a'*33):self.assertFalse(self.open(name))
        self.assertEqual(self.lib.test_io_count(),0);self.assertTrue(self.open());self.assertEqual(self.read(),17)
        self.assertEqual(self.lib.test_last_read(),0)
        self.assertFalse(self.open(b'beta'));self.assertEqual(self.write(8,2),-1)
    def test_app_identity_is_bound_across_reopen_and_close_scrubs_cache(self):
        self.assertTrue(self.open());self.assertEqual(self.write(0,42),1)
        self.assertEqual(self.read(),42);self.assertTrue(self.lib.test_close(self.s));self.assertTrue(self.lib.test_scrubbed(self.s))
        self.assertTrue(self.open(b'beta'));self.assertEqual(self.read(),17);self.assertEqual(self.write(0,99),1)
        self.lib.test_close(self.s);self.assertTrue(self.open());self.assertEqual(self.read(),42)
    def test_changed_commits_are_rate_limited_and_identical_value_does_not_write(self):
        self.assertTrue(self.open());self.assertEqual(self.write(0,1),1)
        count=self.lib.test_writes();self.assertEqual(self.write(0,1,1),1);self.assertEqual(self.lib.test_writes(),count)
        self.assertEqual(self.write(1,2,999),0);self.assertEqual(self.lib.test_writes(),count)
        self.assertEqual(self.write(1,2,1000),1);self.assertEqual(self.read(1),2)
    def test_partial_failed_alternate_preserves_previous_and_blocks_more_writes(self):
        self.assertTrue(self.open());self.assertEqual(self.write(0,7),1)
        self.lib.test_write_fault(2);self.assertEqual(self.write(0,8,1000),-1);self.assertEqual(self.read(),7)
        count=self.lib.test_writes();self.assertEqual(self.write(0,9,2000),-1);self.assertEqual(self.lib.test_writes(),count)
        self.lib.test_close(self.s);self.lib.test_write_fault(0);self.assertTrue(self.open());self.assertEqual(self.read(),7)
        self.assertEqual(self.write(0,9,2000),1)
    def test_corrupt_newest_rolls_back_but_two_corrupt_records_fail_closed(self):
        self.assertTrue(self.open());self.write(0,7);self.write(0,8,1000);self.lib.test_close(self.s)
        self.lib.test_corrupt(0,1,20);self.assertTrue(self.open());self.assertEqual(self.read(),7);self.lib.test_close(self.s)
        self.lib.test_corrupt(0,0,20);self.assertFalse(self.open());self.assertEqual(self.read(),17)
    def test_all_eight_slots_preserve_signed_extremes_through_alternating_records(self):
        self.assertTrue(self.open())
        for i in range(8):self.assertEqual(self.write(i,-2147483648 if i&1 else 2147483647,i*1000),1)
        self.lib.test_close(self.s);self.assertTrue(self.open())
        for i in range(8):self.assertEqual(self.read(i),-2147483648 if i&1 else 2147483647)
    def test_read_io_failure_is_not_treated_as_empty_storage(self):
        self.lib.test_read_fault(1);self.assertFalse(self.open());self.assertEqual(self.lib.test_writes(),0)

    def test_record_bytes_match_independent_little_endian_and_crc_reference(self):
        import struct,zlib
        self.assertTrue(self.open());self.assertEqual(self.write(0,-7),1)
        self.lib.test_record_byte.argtypes=[C.c_uint,C.c_uint,C.c_uint]
        data=bytes(self.lib.test_record_byte(0,0,i) for i in range(52))
        expected=b'LABST01\n'+struct.pack('<II8i',1,1,-7,0,0,0,0,0,0,0)
        self.assertEqual(data[:48],expected)
        self.assertEqual(data[48:],struct.pack('<I',zlib.crc32(expected)))
