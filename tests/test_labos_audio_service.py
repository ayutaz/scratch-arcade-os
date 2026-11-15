import ctypes as C
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class AudioServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'service.so'
        source=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(source),
            str(source/'audio_service.c'),str(ROOT/'tests/native/lab_audio_service_bridge.c'),'-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_tone.argtypes=[C.c_uint]*4;cls.lib.test_record.argtypes=[C.c_uint]*3
        cls.lib.test_poll.argtypes=[C.c_uint];cls.lib.test_play.argtypes=[C.c_uint]*2
    def setUp(self):self.assertTrue(self.lib.test_init(32000))
    def test_claim_permissions_and_ownership_gate_all_operations(self):
        self.assertFalse(self.lib.test_claim(0,3));self.assertFalse(self.lib.test_claim(1,4))
        self.assertTrue(self.lib.test_claim(1,1));self.assertFalse(self.lib.test_claim(2,3))
        self.assertFalse(self.lib.test_record(1,100,0));self.assertFalse(self.lib.test_tone(2,1000,100,0))
        self.assertFalse(self.lib.test_release(2));self.assertEqual(self.lib.test_calls(0),0)
    def test_bounded_tone_fades_limits_peak_and_waits_for_dma_completion(self):
        self.assertTrue(self.lib.test_claim(1,1));self.assertTrue(self.lib.test_tone(1,1000,32,0))
        samples=[self.lib.test_sample(i) for i in range(512)]
        self.assertEqual((samples[0],samples[-1]),(0,0));self.assertLessEqual(max(map(abs,samples)),2048)
        self.assertGreater(max(samples),0);self.assertLess(min(samples),0)
        self.lib.test_results(1,1,256,0)
        self.assertEqual(self.lib.test_poll(1),0);self.assertEqual(self.lib.test_position(),256)
        self.assertEqual(self.lib.test_poll(2),0);self.assertEqual(self.lib.test_position(),512)
        self.assertEqual(self.lib.test_poll(3),0);self.assertEqual(self.lib.test_calls(4),0)
        self.lib.test_results(1,1,256,1);self.assertEqual(self.lib.test_poll(4),1)
        self.assertEqual(self.lib.test_calls(4),1);self.assertEqual(self.lib.test_calls(2),2)
    def test_invalid_or_oversize_requests_never_open_driver(self):
        self.assertFalse(self.lib.test_init(0));self.assertTrue(self.lib.test_init(64));self.assertTrue(self.lib.test_claim(1,3))
        for hz,ms in ((0,20),(199,20),(4001,20),(1000,0),(1000,1001),(1000,20)):
            self.assertFalse(self.lib.test_tone(1,hz,ms,0))
        self.assertFalse(self.lib.test_record(1,0,0));self.assertFalse(self.lib.test_record(1,2001,0))
        self.assertFalse(self.lib.test_record(1,5,0));self.assertEqual(self.lib.test_calls(0),0)
    def test_record_partial_reads_and_playback_use_shared_buffer_only_for_same_app(self):
        self.assertTrue(self.lib.test_claim(1,3));self.assertTrue(self.lib.test_record(1,32,0))
        self.lib.test_results(1,1,0,0);self.assertEqual(self.lib.test_poll(1),0)
        self.lib.test_results(1,1,128,0)
        for i in range(2,5):self.assertEqual(self.lib.test_poll(i),0)
        self.assertEqual(self.lib.test_poll(5),1);self.assertEqual(self.lib.test_recorded(),512)
        self.assertFalse(self.lib.test_play(2,6));self.assertTrue(self.lib.test_play(1,6))
        self.lib.test_results(1,1,256,1)
        self.assertEqual(self.lib.test_poll(7),0);self.assertEqual(self.lib.test_poll(8),0);self.assertEqual(self.lib.test_poll(9),1)
        self.assertEqual(self.lib.test_recorded(),512)
    def test_exit_scrubs_recording_and_failed_cleanup_blocks_other_app_until_retry(self):
        self.assertTrue(self.lib.test_claim(1,3));self.assertTrue(self.lib.test_record(1,16,0))
        self.lib.test_results(1,0,256,0);self.assertEqual(self.lib.test_poll(1),0)
        self.assertFalse(self.lib.test_release(1));self.assertEqual(self.lib.test_owner(),1)
        self.assertTrue(all(self.lib.test_sample(i)==0 for i in range(32000)))
        self.assertEqual(self.lib.test_recorded(),0);self.assertFalse(self.lib.test_claim(2,3))
        self.lib.test_results(1,1,0,0);self.assertTrue(self.lib.test_release(1))
        self.assertTrue(self.lib.test_claim(2,3));self.assertFalse(self.lib.test_play(2,2))
    def test_stalled_io_deadline_wraps_and_scrubs_partial_recording(self):
        self.assertTrue(self.lib.test_claim(1,2));start=0xfffffff0
        self.assertTrue(self.lib.test_record(1,16,start));self.lib.test_results(1,1,128,0)
        self.assertEqual(self.lib.test_poll(0),0)
        self.lib.test_results(1,1,0,0);self.assertEqual(self.lib.test_poll(1001),-1)
        self.assertEqual(self.lib.test_recorded(),0);self.assertTrue(all(self.lib.test_sample(i)==0 for i in range(256)))
        self.assertEqual(self.lib.test_calls(4),1)
    def test_open_and_invalid_io_failures_keep_ownership_until_cleanup(self):
        for result in (-1,257):
            self.assertTrue(self.lib.test_init(32000));self.assertTrue(self.lib.test_claim(1,3))
            self.lib.test_results(1,1,result,0);self.assertTrue(self.lib.test_record(1,32,0))
            self.assertEqual(self.lib.test_poll(1),-1);self.assertEqual(self.lib.test_calls(4),1)
            self.assertEqual(self.lib.test_recorded(),0)
        self.assertTrue(self.lib.test_init(32000));self.assertTrue(self.lib.test_claim(1,3))
        self.lib.test_results(0,0,0,0);self.assertFalse(self.lib.test_record(1,32,0))
        self.assertEqual(self.lib.test_calls(4),1);self.assertFalse(self.lib.test_claim(2,3))
        self.lib.test_results(1,1,0,0);self.assertTrue(self.lib.test_release(1));self.assertTrue(self.lib.test_claim(2,1))

    def record_full_scale(self):
        self.assertTrue(self.lib.test_claim(1,3));self.lib.test_full_scale(1)
        self.assertTrue(self.lib.test_record(1,32,0));self.lib.test_results(1,1,256,1)
        self.assertEqual(self.lib.test_poll(1),0);self.assertEqual(self.lib.test_poll(2),1)
        return [self.lib.test_sample(i) for i in range(512)]
    def test_recording_replay_limits_peak_and_fades_without_modifying_original_pcm(self):
        raw=self.record_full_scale();self.assertTrue(self.lib.test_play(1,3))
        self.assertEqual(self.lib.test_poll(4),0);self.assertEqual(self.lib.test_poll(5),0)
        self.assertEqual(self.lib.test_poll(6),1)
        out=[self.lib.test_output(i) for i in range(512)]
        self.assertLessEqual(max(map(abs,out)),3277);self.assertEqual((out[0],out[-1]),(0,0))
        self.assertEqual([self.lib.test_sample(i) for i in range(512)],raw)
    def test_partial_and_backpressured_replay_preserves_exact_frame_offsets(self):
        raw=self.record_full_scale();self.assertTrue(self.lib.test_play(1,3))
        self.lib.test_results(1,1,0,1);self.assertEqual(self.lib.test_poll(4),0)
        self.assertEqual(self.lib.test_output_frames(),0)
        self.lib.test_results(1,1,32,1)
        for now in range(5,21):self.assertEqual(self.lib.test_poll(now),0)
        self.assertEqual(self.lib.test_poll(21),1);self.assertEqual(self.lib.test_output_frames(),512)
        mean=math.trunc(sum(raw)/len(raw));peak=max(abs(v-mean) for v in raw)
        scale=min(1,3277/peak)
        expected=[int((v-mean)*scale*min(i,511-i,80)/80) for i,v in enumerate(raw)]
        self.assertTrue(all(abs(self.lib.test_output(i)-value)<=3 for i,value in enumerate(expected)))
