import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class VoiceServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        out=Path(cls.temp.name)/'voice.so';native=ROOT/'prototypes/lab-os/native';model=ROOT/'components/voice'
        sources=[native/'audio_service.c',native/'audio_binding.c',native/'voice_service.c',
                 model/'channel_features.c',model/'channel_prepare.c',model/'kws_inference.c',ROOT/'tests/native/lab_voice_bridge.c']
        run=subprocess.run(['clang','-O2','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                            '-I'+str(native),'-I'+str(model),'-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),
                            *map(str,sources),'-lm','-o',str(out)],capture_output=True,text=True)
        if run.returncode:raise AssertionError(run.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.voice_new.restype=C.c_void_p
        for name in ('voice_free','voice_clean'):getattr(cls.lib,name).argtypes=[C.c_void_p]
        for name in ('voice_poll','voice_value','voice_close'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_uint]
        cls.lib.voice_call.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        cls.lib.voice_fill_offset.argtypes=[C.c_void_p,C.c_int,C.c_int]
    def rig(self,caps=7):
        rig=self.lib.voice_new(caps);self.assertTrue(rig);self.addCleanup(self.lib.voice_free,rig);return rig
    def test_completed_recording_is_classified_once_then_pcm_and_workspace_are_scrubbed(self):
        rig=self.rig();self.assertEqual(self.lib.voice_call(rig,9,0),-1)
        self.assertEqual(self.lib.voice_call(rig,2,2000),1)
        self.assertEqual(self.lib.voice_call(rig,9,0),-1)
        for i in range(125):self.lib.voice_poll(rig,i*16)
        self.assertEqual(self.lib.voice_value(rig,1),32000)
        self.assertEqual(self.lib.voice_call(rig,9,0),6)
        self.assertEqual(self.lib.voice_call(rig,9,0),-1)
        self.assertEqual(self.lib.voice_value(rig,1),0);self.assertTrue(self.lib.voice_clean(rig))
    def test_replies_use_speaker_permission_and_complete_or_cancel_with_existing_audio_lease(self):
        for response in range(5):
            rig=self.rig(3)
            self.assertEqual(self.lib.voice_call(rig,9,0),-1)
            self.assertEqual(self.lib.voice_call(rig,10,5),-1)
            self.assertEqual(self.lib.voice_call(rig,10,response),1)
            self.assertEqual(self.lib.voice_call(rig,10,response),0)
            for i in range(130):self.lib.voice_poll(rig,i*16)
            self.assertGreater(self.lib.voice_value(rig,2),0);self.assertEqual(self.lib.voice_value(rig,3),0)
            self.assertEqual(self.lib.voice_value(rig,4),0)
            self.assertTrue(self.lib.voice_close(rig,0));self.assertTrue(self.lib.voice_clean(rig))
        mic=self.rig(5);self.assertEqual(self.lib.voice_call(mic,10,0),-1);self.assertEqual(self.lib.voice_value(mic,0),0)
    def test_failed_driver_close_retains_owner_and_blocks_reply_until_cleanup_retry(self):
        rig=self.rig();self.assertEqual(self.lib.voice_call(rig,10,0),1)
        self.assertFalse(self.lib.voice_close(rig,1));self.assertEqual(self.lib.voice_value(rig,5),1)
        self.assertEqual(self.lib.voice_call(rig,10,0),-1)
        self.assertTrue(self.lib.voice_clean(rig));self.assertTrue(self.lib.voice_close(rig,0))

    def test_constant_microphone_offset_is_silence_in_banked_and_contiguous_pcm(self):
        for contiguous in (0,1):
            for offset in (1600,-1600,32767,-32768):
                with self.subTest(contiguous=contiguous,offset=offset):
                    rig=self.rig();self.assertEqual(self.lib.voice_call(rig,2,2000),1)
                    for i in range(125):self.lib.voice_poll(rig,i*16)
                    self.assertEqual(self.lib.voice_fill_offset(rig,offset,contiguous),1)
                    self.assertEqual(self.lib.voice_call(rig,9,0),6)
                    self.assertEqual(self.lib.voice_value(rig,1),0)
                    self.assertTrue(self.lib.voice_clean(rig))

    def test_completed_pcm_injection_is_bounded_and_consumed(self):
        from array import array
        fn=self.lib.voice_fill_pcm;fn.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_int]
        pcm=array('h',[1200]*32000);pointer=(C.c_int16*32000).from_buffer(pcm)
        for contiguous in (0,1):
            rig=self.rig();self.assertEqual(fn(rig,pointer,32000,contiguous),0)
            self.assertEqual(self.lib.voice_call(rig,2,2000),1)
            for i in range(125):self.lib.voice_poll(rig,i*16)
            self.assertEqual(fn(rig,pointer,31999,contiguous),0)
            self.assertEqual(fn(rig,None,32000,contiguous),0)
            self.assertEqual(fn(rig,pointer,32000,2),0)
            self.assertEqual(fn(rig,pointer,32000,contiguous),1)
            self.assertEqual(self.lib.voice_call(rig,9,0),6)
            self.assertTrue(self.lib.voice_clean(rig))

    def test_time_varying_microphone_offset_is_silence_in_both_memory_layouts(self):
        from array import array
        import math
        pcm=array('h',[round(1600+480*math.exp(-i/4800)) for i in range(32000)])
        pointer=(C.c_int16*32000).from_buffer(pcm)
        self.lib.voice_fill_pcm.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_int]
        for contiguous in (0,1):
            with self.subTest(contiguous=contiguous):
                rig=self.rig();self.assertEqual(self.lib.voice_call(rig,2,2000),1)
                for i in range(125):self.lib.voice_poll(rig,i*16)
                self.assertEqual(self.lib.voice_fill_pcm(rig,pointer,32000,contiguous),1)
                self.assertEqual(self.lib.voice_call(rig,9,0),6)
                self.assertEqual(self.lib.voice_value(rig,1),0);self.assertTrue(self.lib.voice_clean(rig))

    def test_private_snapshot_retains_only_metrics_and_isolated_current_lease(self):
        get=self.lib.voice_native_status;get.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        rig=self.rig();self.assertEqual(get(rig,1,0),0)
        self.assertEqual(self.lib.voice_call(rig,65536,0),-1)  # Not a guest API.
        self.assertEqual(self.lib.voice_call(rig,2,2000),1)
        for i in range(125):self.lib.voice_poll(rig,i*16)
        self.assertEqual(self.lib.voice_fill_offset(rig,1600,0),1)
        self.assertEqual(self.lib.voice_call(rig,9,0),6)
        self.assertEqual(get(rig,1,0),1);self.assertEqual(get(rig,1,1),1)
        self.assertEqual(get(rig,1,2),6);self.assertEqual(get(rig,1,3),0)
        self.assertEqual(get(rig,1,4),32000)
        for index in (5,6,7,8,12,13):self.assertEqual(get(rig,1,index),1600)
        for index in (9,10,11):self.assertEqual(get(rig,1,index),0)
        self.assertEqual(get(rig,1,14),1);self.assertEqual(get(rig,1,15),3)
        self.assertEqual(get(rig,1,17),1);self.assertEqual(get(rig,2,0),-1)
        self.assertEqual(get(rig,1,18),-1)
        self.assertTrue(self.lib.voice_clean(rig));self.assertEqual(self.lib.voice_value(rig,1),0)
        self.assertEqual(self.lib.voice_call(rig,6,0),1)
        self.assertEqual(get(rig,1,0),0);self.assertEqual(get(rig,1,1),-1)
        self.assertEqual(self.lib.voice_call(rig,2,2000),1)
        for i in range(125):self.lib.voice_poll(rig,2000+i*16)
        self.assertEqual(self.lib.voice_call(rig,9,0),6)
        self.assertEqual(get(rig,1,1),1);self.assertEqual(get(rig,1,17),2)
        self.assertEqual(self.lib.voice_call(rig,9,0),-1)
        self.assertEqual(get(rig,1,1),2);self.assertEqual(get(rig,1,2),-1)
        self.assertEqual(get(rig,1,3),1);self.assertEqual(get(rig,1,4),0)
        self.assertEqual(get(rig,1,14),0);self.assertTrue(self.lib.voice_clean(rig))
        speaker=self.rig(3);self.assertEqual(get(speaker,1,0),-1)


class VoiceScoreSummaryTests(unittest.TestCase):
    setUpClass=classmethod(VoiceServiceTests.setUpClass.__func__)
    def test_ranked_scores_keep_signed_values_ties_and_full_uint32_margin(self):
        class Summary(C.Structure):
            _fields_=[('top1',C.c_uint32),('top2',C.c_uint32),('first',C.c_int32),('second',C.c_int32),('margin',C.c_uint32)]
        fn=self.lib.lab_voice_rank;fn.argtypes=[C.POINTER(C.c_int32),C.c_size_t,C.POINTER(Summary)]
        for raw,expected in [([-20,100,99,7,-8,-4,-5],(1,2,100,99,1)),
                             ([8]*7,(0,1,8,8,0)),
                             ([2147483647]+[-2147483648]*6,(0,1,2147483647,-2147483648,4294967295))]:
            with self.subTest(raw=raw):
                out=Summary();self.assertEqual(fn((C.c_int32*7)(*raw),7,C.byref(out)),1)
                self.assertEqual((out.top1,out.top2,out.first,out.second,out.margin),expected)
        out=Summary(1,2,3,4,5);self.assertEqual(fn((C.c_int32*7)(),6,C.byref(out)),0)
        self.assertEqual(bytes(out),bytes(C.sizeof(out)))
    def test_threshold_is_the_same_frozen_rejection_margin_used_by_inference(self):
        self.assertEqual(self.lib.pet_rejection_threshold(),995)


class VoiceScoreLeaseTests(unittest.TestCase):
    setUpClass=classmethod(VoiceServiceTests.setUpClass.__func__)
    rig=VoiceServiceTests.rig
    def test_score_query_is_read_only_scrubbed_on_failure_and_current_lease_only(self):
        fn=self.lib.voice_native_score_status;fn.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        rig=self.rig();self.assertEqual(fn(rig,1,0),0)
        self.assertEqual(self.lib.voice_call(rig,65537,0),-1)
        self.assertEqual(self.lib.voice_call(rig,2,2000),1)
        for i in range(125):self.lib.voice_poll(rig,i*16)
        self.assertEqual(self.lib.voice_call(rig,9,0),6)
        self.assertEqual(fn(rig,1,0),1);self.assertEqual(fn(rig,1,1),1)
        self.assertEqual(fn(rig,1,2),6);self.assertEqual(fn(rig,1,3),6)
        self.assertEqual(fn(rig,1,8),995);self.assertEqual(fn(rig,1,9),3);self.assertEqual(fn(rig,1,11),1)
        self.assertNotEqual(fn(rig,1,3),fn(rig,1,4));self.assertTrue(self.lib.voice_clean(rig))
        self.assertEqual(fn(rig,2,0),-1);self.assertEqual(fn(rig,1,12),-1)
        self.assertEqual(self.lib.voice_call(rig,9,0),-1);self.assertEqual(fn(rig,1,0),0)
        self.assertEqual(fn(rig,1,1),-1)
        self.assertEqual(self.lib.voice_call(rig,6,0),1);self.assertEqual(fn(rig,1,0),0)
        speaker=self.rig(3);self.assertEqual(fn(speaker,1,0),-1)
