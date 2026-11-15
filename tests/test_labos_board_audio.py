"""新OS音声driverの契約。fixture成功は実機の発音/録音を保証しない。"""
import ctypes as C
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'firmware/esp-idf/lab-os-core/main'
class BoardAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'audio.so'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I'+str(ROOT/'tests/native/audio_fixture'),'-I'+str(MAIN),'-I'+str(ROOT/'prototypes/lab-os/native'),str(MAIN/'board_audio.c'),
            str(ROOT/'tests/native/lab_board_audio_bridge.c'),'-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.restype=C.c_void_p
        for name in ('test_free','test_close','test_ready','test_drained'):getattr(cls.lib,name).argtypes=[C.c_void_p]
        cls.lib.test_open.argtypes=[C.c_void_p,C.c_int,C.c_int]
        for name in ('test_read','test_write'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.POINTER(C.c_int16),C.c_uint]
    def setUp(self):
        self.lib.test_reset();self.driver=self.lib.test_new();self.addCleanup(self.lib.test_free,self.driver)
    def test_invalid_profile_or_mode_performs_no_io(self):
        for profile,mode in ((0,1),(2,1),(1,0),(1,3),(-1,1)):
            self.assertFalse(self.lib.test_open(self.driver,profile,mode))
        self.assertEqual([self.lib.test_calls(i) for i in range(8)],[0]*8)

    def test_fixture_output_budget_paces_each_synthetic_hardware_interval(self):
        self.lib.test_output_budget.argtypes=[C.c_uint]
        pcm=(C.c_int16*256)();self.assertTrue(self.lib.test_open(self.driver,1,1))
        self.lib.test_auto_io(1);self.lib.test_output_budget(80)
        self.assertEqual(self.lib.test_write(self.driver,pcm,256),80)
        self.assertEqual(self.lib.test_write(self.driver,pcm,256),0)
        self.lib.test_output_budget(16)
        self.assertEqual(self.lib.test_write(self.driver,pcm,8),8)
        self.assertEqual(self.lib.test_write(self.driver,pcm,256),8)

    def test_os_input_service_discards_first_1600_frames_without_blocking_or_exposing_them(self):
        self.lib.test_service_open.argtypes=[C.c_void_p,C.c_int]
        self.lib.test_priming_left.argtypes=[C.c_void_p]
        pcm=(C.c_int16*256)();self.lib.test_auto_io(1)
        self.assertTrue(self.lib.test_service_open(self.driver,2))
        self.assertEqual(self.lib.test_priming_left(self.driver),1600)
        for _ in range(6):
            self.assertEqual(self.lib.test_read(self.driver,pcm,256),0)
            self.assertEqual(list(pcm),[0]*256)
        self.assertEqual(self.lib.test_priming_left(self.driver),64)
        self.assertEqual(self.lib.test_read(self.driver,pcm,256),192)
        self.assertEqual(self.lib.test_priming_left(self.driver),0)
        self.assertEqual(self.lib.test_read(self.driver,pcm,256),256)
        self.assertEqual(list(pcm)[:3],[10,-20,30])
        self.assertTrue(self.lib.test_close(self.driver))
        self.assertTrue(self.lib.test_service_open(self.driver,2))
        self.assertEqual(self.lib.test_priming_left(self.driver),1600)

    def test_output_service_does_not_prime_and_empty_input_does_not_consume_warmup(self):
        self.lib.test_service_open.argtypes=[C.c_void_p,C.c_int]
        self.lib.test_priming_left.argtypes=[C.c_void_p]
        pcm=(C.c_int16*256)()
        self.assertTrue(self.lib.test_service_open(self.driver,1));self.assertEqual(self.lib.test_priming_left(self.driver),0)
        self.assertTrue(self.lib.test_close(self.driver));self.assertTrue(self.lib.test_service_open(self.driver,2))
        self.lib.test_io(2,0);self.assertEqual(self.lib.test_read(self.driver,pcm,256),0)
        self.assertEqual(self.lib.test_priming_left(self.driver),1600)
    def test_fixed_output_and_input_pins_match_saved_stock_metadata(self):
        parts=json.loads((ROOT/'boards/scratch-arcade/profile.json').read_text())['parts']
        self.assertTrue(self.lib.test_open(self.driver,1,1))
        self.assertEqual([self.lib.test_pin(i) for i in range(5)],list(parts['Sound'].values())+[-1,-1])
        self.assertEqual(self.lib.test_bad(),0);self.assertTrue(self.lib.test_close(self.driver))
        self.assertTrue(self.lib.test_open(self.driver,1,2))
        self.assertEqual([self.lib.test_pin(i) for i in range(2)],list(parts['Microphone'].values()))
        self.assertEqual(self.lib.test_bad(),0)
    def test_only_one_owner_and_one_direction_until_cleanup(self):
        other=self.lib.test_new();self.addCleanup(self.lib.test_free,other)
        self.assertTrue(self.lib.test_open(self.driver,1,1))
        self.assertFalse(self.lib.test_open(self.driver,1,2));self.assertFalse(self.lib.test_open(other,1,2))
        self.assertEqual(self.lib.test_calls(0),1);self.assertTrue(self.lib.test_close(self.driver))
        self.assertTrue(self.lib.test_open(other,1,2))
    def test_partial_open_failures_delete_only_acquired_channels(self):
        for mode,stage,deletes in ((1,1,0),(1,2,1),(1,4,1),(1,9,1),(2,3,1),(2,4,1)):
            self.lib.test_reset();self.lib.test_fault(stage)
            self.assertFalse(self.lib.test_open(self.driver,1,mode))
            self.assertEqual((self.lib.test_calls(6),self.lib.test_calls(7)),(0,deletes))
            self.assertEqual(self.lib.test_bad(),0);self.lib.test_fault(0)
            self.assertTrue(self.lib.test_close(self.driver))
    def test_nonblocking_partial_io_and_wrong_direction_never_reaches_driver(self):
        pcm=(C.c_int16*8)(*[9]*8);self.assertTrue(self.lib.test_open(self.driver,1,1))
        self.lib.test_io(2,6);self.assertEqual(self.lib.test_write(self.driver,pcm,8),3)
        self.assertEqual(self.lib.test_read(self.driver,pcm,8),-1)
        for count in (0,257):self.assertEqual(self.lib.test_write(self.driver,pcm,count),-1)
        self.assertEqual(self.lib.test_calls(5),1);self.assertTrue(self.lib.test_close(self.driver))
        self.assertTrue(self.lib.test_open(self.driver,1,2));self.lib.test_io(2,6)
        self.assertEqual(self.lib.test_read(self.driver,pcm,8),3)
        self.assertEqual(list(pcm),[10,-20,30,0,0,0,0,0])
        self.assertEqual(self.lib.test_write(self.driver,pcm,8),-1)
        self.assertEqual(self.lib.test_bad(),0)
    def test_bad_io_counts_and_driver_errors_stop_further_io_and_clear_input(self):
        pcm=(C.c_int16*8)()
        for code,n in ((0,3),(0,18),(-1,6)):
            self.assertTrue(self.lib.test_open(self.driver,1,2));self.lib.test_io(code,n)
            self.assertEqual(self.lib.test_read(self.driver,pcm,8),-1);self.assertEqual(list(pcm),[0]*8)
            self.assertFalse(self.lib.test_ready(self.driver));calls=self.lib.test_calls(4)
            self.assertEqual(self.lib.test_read(self.driver,pcm,8),-1);self.assertEqual(self.lib.test_calls(4),calls)
            self.assertTrue(self.lib.test_close(self.driver))
    def test_failed_close_retains_ownership_and_retries_only_unreleased_resources(self):
        for stage in (7,8):
            self.lib.test_reset();self.assertTrue(self.lib.test_open(self.driver,1,1));self.lib.test_fault(stage)
            self.assertFalse(self.lib.test_close(self.driver));self.assertFalse(self.lib.test_ready(self.driver))
            self.assertFalse(self.lib.test_open(self.driver,1,1));self.lib.test_fault(0)
            self.assertTrue(self.lib.test_close(self.driver));self.assertTrue(self.lib.test_close(self.driver))
            self.assertEqual(self.lib.test_calls(6),2 if stage==7 else 1)
            self.assertEqual(self.lib.test_calls(7),1 if stage==7 else 2)

    def test_output_completion_waits_for_dma_events_after_last_accepted_write(self):
        pcm=(C.c_int16*8)();self.assertTrue(self.lib.test_open(self.driver,1,1))
        self.assertEqual(self.lib.test_drained(self.driver),1)
        self.lib.test_io(0,16);self.assertEqual(self.lib.test_write(self.driver,pcm,8),8)
        self.assertEqual(self.lib.test_drained(self.driver),0)
        self.lib.test_sent(4);self.assertEqual(self.lib.test_drained(self.driver),0)
        self.lib.test_sent(1);self.assertEqual(self.lib.test_drained(self.driver),1)
        self.assertEqual(self.lib.test_bad(),0)
    def test_backpressure_does_not_extend_drain_but_new_accepted_data_does(self):
        pcm=(C.c_int16*8)();self.assertTrue(self.lib.test_open(self.driver,1,1))
        self.lib.test_io(0,16);self.lib.test_write(self.driver,pcm,8);self.lib.test_sent(4)
        self.lib.test_io(2,0);self.assertEqual(self.lib.test_write(self.driver,pcm,8),0)
        self.lib.test_sent(1);self.assertEqual(self.lib.test_drained(self.driver),1)
        self.lib.test_io(2,4);self.assertEqual(self.lib.test_write(self.driver,pcm,8),2)
        self.assertEqual(self.lib.test_drained(self.driver),0)
        self.lib.test_sent(5);self.assertEqual(self.lib.test_drained(self.driver),1)
        self.assertTrue(self.lib.test_close(self.driver));self.assertEqual(self.lib.test_drained(self.driver),-1)
