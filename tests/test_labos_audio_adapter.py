import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class AudioAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'adapter.so'
        main=ROOT/'firmware/esp-idf/lab-os-core/main';native=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I'+str(ROOT/'tests/native/audio_fixture'),'-I'+str(main),'-I'+str(native),
            str(main/'board_audio.c'),str(native/'audio_service.c'),str(ROOT/'tests/native/lab_board_audio_bridge.c'),
            str(ROOT/'tests/native/lab_audio_adapter_bridge.c'),'-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out))
    def test_two_app_owners_play_record_replay_release_and_scrub_through_real_c_adapter(self):
        self.assertEqual(self.lib.audio_scenario(0),0);self.assertEqual(self.lib.test_bad(),0)
    def test_driver_cleanup_failure_propagates_to_service_owner_and_recovers_by_retry(self):
        self.assertEqual(self.lib.audio_scenario(1),0);self.assertEqual(self.lib.test_bad(),0)
