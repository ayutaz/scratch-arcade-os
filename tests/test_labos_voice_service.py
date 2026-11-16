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
                 model/'kws_features.c',model/'kws_inference.c',ROOT/'tests/native/lab_voice_bridge.c']
        run=subprocess.run(['clang','-O2','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                            '-I'+str(native),'-I'+str(model),'-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),
                            *map(str,sources),'-lm','-o',str(out)],capture_output=True,text=True)
        if run.returncode:raise AssertionError(run.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.voice_new.restype=C.c_void_p
        for name in ('voice_free','voice_clean'):getattr(cls.lib,name).argtypes=[C.c_void_p]
        for name in ('voice_poll','voice_value','voice_close'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_uint]
        cls.lib.voice_call.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
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
