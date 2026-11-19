import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class BoardSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'sound.so'
        main=ROOT/'firmware/esp-idf/lab-os-core/main';native=ROOT/'prototypes/lab-os/native'
        sources=[main/'board_sound.c',main/'board_audio.c',native/'audio_service.c',native/'audio_binding.c',
                 ROOT/'tests/native/lab_session_audio_fixture.c',ROOT/'tests/native/lab_board_sound_bridge.c']
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
             '-I'+str(ROOT/'tests/native/audio_fixture'),'-I'+str(main),'-I'+str(native),
             '-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),*map(str,sources),'-o',str(out)],
             capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_sound_new.restype=C.c_void_p
        for name in ('test_sound_free','test_sound_close'):getattr(cls.lib,name).argtypes=[C.c_void_p]
        for name in ('test_sound_init','test_sound_open','test_sound_poll','test_sound_metric'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_uint]
        cls.lib.test_sound_command.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint]
    def setUp(self):
        self.rig=self.lib.test_sound_new();self.addCleanup(self.lib.test_sound_free,self.rig)
    def init(self):self.assertTrue(self.lib.test_sound_init(self.rig,1))
    def metric(self,n):return self.lib.test_sound_metric(self.rig,n)
    def mem(self,n):return self.lib.test_audio_memory(n)
    def test_voice_extension_can_only_be_bound_while_closed_and_survives_app_cleanup(self):
        self.lib.test_sound_voice.argtypes=[C.c_void_p]
        self.assertFalse(self.lib.test_sound_voice(self.rig));self.init()
        self.assertTrue(self.lib.test_sound_voice(self.rig))
        self.assertTrue(self.lib.test_sound_open(self.rig,7))
        self.assertFalse(self.lib.test_sound_voice(self.rig))
        self.assertEqual(self.lib.test_sound_command(self.rig,9,0,0),6)
        self.assertTrue(self.lib.test_sound_close(self.rig))
        self.assertTrue(self.lib.test_sound_open(self.rig,7))
        self.assertEqual(self.lib.test_sound_command(self.rig,9,0,0),6)

    def test_configuration_is_lazy_and_unknown_profile_or_caps_never_allocates_or_opens_i2s(self):
        for profile in (0,2):self.assertFalse(self.lib.test_sound_init(self.rig,profile))
        self.init()
        for caps in (0,1,8,0xffffffff):self.assertFalse(self.lib.test_sound_open(self.rig,caps))
        self.assertEqual((self.mem(0),self.lib.test_audio_calls(0)),(0,0))
    def test_speaker_lease_reserves_only_32kb_and_opens_known_output_on_request(self):
        self.init();self.assertTrue(self.lib.test_sound_open(self.rig,3))
        self.assertEqual((self.metric(0),self.mem(2),self.lib.test_audio_calls(0)),(16000,32000,0))
        self.assertEqual(self.lib.test_sound_command(self.rig,1,1000,20),1)
        self.assertEqual(self.lib.test_audio_calls(0),1);self.assertEqual(self.lib.test_audio_bad(),0)
        self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual((self.mem(1),self.mem(2),self.mem(4)),(1,0,1))
    def test_network_permission_does_not_change_audio_permission_or_pcm_size(self):
        self.init()
        for caps,expected in ((10,32000),(15,64000)):
            self.assertTrue(self.lib.test_sound_open(self.rig,caps));self.assertEqual(self.mem(2),expected)
            self.assertEqual(self.lib.test_audio_calls(0),0);self.assertTrue(self.lib.test_sound_close(self.rig))
    def test_microphone_lease_records_and_replays_via_real_driver_adapter_then_frees_64kb(self):
        self.init();self.assertTrue(self.lib.test_sound_open(self.rig,7));first_owner=self.metric(1)
        self.assertEqual((self.metric(0),self.mem(2)),(32000,64000))
        self.assertEqual(self.lib.test_sound_command(self.rig,2,16,0),1)
        self.lib.test_audio_io(0,512)
        for _ in range(7):self.lib.test_sound_poll(self.rig,1)
        self.assertEqual(self.metric(3),0)
        self.lib.test_audio_io(0,128);self.lib.test_sound_poll(self.rig,1);self.assertEqual(self.metric(3),256)
        self.lib.test_audio_io(0,512)
        self.assertEqual(self.lib.test_sound_command(self.rig,3,0,0),1)
        self.lib.test_sound_poll(self.rig,2);self.lib.test_audio_sent(5);self.lib.test_sound_poll(self.rig,3)
        self.assertEqual(self.lib.test_audio_calls(0),2);self.assertTrue(self.lib.test_sound_close(self.rig))
        self.assertEqual((self.mem(2),self.mem(4)),(0,1));self.assertEqual(self.lib.test_audio_bad(),0)
        self.assertTrue(self.lib.test_sound_open(self.rig,3));self.assertNotEqual(self.metric(1),first_owner)
    def test_allocation_failure_reports_unavailable_and_retry_does_not_touch_gpio(self):
        self.init();self.lib.test_audio_memory_fault(1,0)
        self.assertFalse(self.lib.test_sound_open(self.rig,7));self.assertEqual(self.mem(2),0)
        self.assertEqual(self.lib.test_audio_calls(0),0);self.assertTrue(self.lib.test_sound_close(self.rig))
        self.lib.test_audio_memory_fault(0,0);self.assertTrue(self.lib.test_sound_open(self.rig,3))
    def test_driver_cleanup_failure_keeps_pcm_and_owner_until_retry(self):
        self.init();self.assertTrue(self.lib.test_sound_open(self.rig,3));self.lib.test_sound_command(self.rig,1,1000,20)
        self.lib.test_audio_fault(7);self.assertFalse(self.lib.test_sound_close(self.rig))
        self.assertEqual((self.mem(1),self.mem(2)),(0,32000));self.assertFalse(self.lib.test_sound_open(self.rig,7))
        self.lib.test_audio_fault(0);self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual(self.mem(2),0)
    def test_failed_pcm_free_keeps_ownership_of_buffer_and_blocks_reopen(self):
        self.init();self.assertTrue(self.lib.test_sound_open(self.rig,7));self.lib.test_audio_memory_fault(0,1)
        self.assertFalse(self.lib.test_sound_close(self.rig));self.assertEqual((self.mem(2),self.metric(2)),(64000,0))
        self.assertFalse(self.lib.test_sound_open(self.rig,3));self.lib.test_audio_memory_fault(0,0)
        self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual((self.mem(2),self.mem(4)),(0,1))

    def test_two_second_microphone_capacity_uses_at_most_8kb_per_allocation(self):
        self.init();self.assertTrue(self.lib.test_sound_open(self.rig,7))
        self.assertEqual((self.metric(0),self.mem(2)),(32000,64000))
        self.assertLessEqual(self.mem(5),8192)
        self.assertTrue(self.lib.test_sound_close(self.rig))

class LazyVoiceFactoryTests(unittest.TestCase):
    setUp=BoardSoundTests.setUp
    init=BoardSoundTests.init
    metric=BoardSoundTests.metric
    mem=BoardSoundTests.mem
    @classmethod
    def setUpClass(cls):
        BoardSoundTests.setUpClass.__func__(cls)
        cls.lib.test_sound_voice.argtypes=[C.c_void_p]
        for name in ('test_sound_factory','test_sound_factory_metric','test_sound_factory_fault'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_uint]
    def factory(self):self.assertTrue(self.lib.test_sound_factory(self.rig,0))
    def voice(self,i):return self.lib.test_sound_factory_metric(self.rig,i)
    def test_factory_is_lazy_and_speaker_network_apps_never_reserve_recognition_memory(self):
        self.init();self.factory();self.assertEqual(self.voice(0),0)
        self.assertTrue(self.lib.test_sound_open(self.rig,10));self.assertEqual(self.voice(0),0);self.assertEqual(self.mem(2),32000);self.assertTrue(self.lib.test_sound_close(self.rig))
        self.assertTrue(self.lib.test_sound_open(self.rig,7));self.assertEqual(self.voice(0),1);self.assertEqual(self.lib.test_sound_command(self.rig,9,0,0),6);self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual((self.voice(1),self.voice(2),self.voice(3)),(1,0,0))
    def test_factory_acquire_failure_never_allocates_pcm_or_opens_gpio(self):
        self.init();self.factory();self.lib.test_sound_factory_fault(self.rig,1)
        self.assertFalse(self.lib.test_sound_open(self.rig,7));self.assertEqual((self.mem(2),self.lib.test_audio_calls(0)),(0,0));self.assertTrue(self.lib.test_sound_close(self.rig))
    def test_partial_pcm_failure_retains_owned_context_until_close(self):
        self.init();self.factory();self.lib.test_audio_memory_fault(1,0)
        self.assertFalse(self.lib.test_sound_open(self.rig,7));self.assertEqual(self.voice(2),1);self.assertFalse(self.lib.test_sound_open(self.rig,3));self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual((self.voice(1),self.voice(2)),(1,0))
    def test_driver_cleanup_failure_retains_context_and_pcm_until_retry(self):
        self.init();self.factory();self.assertTrue(self.lib.test_sound_open(self.rig,7));self.lib.test_sound_command(self.rig,1,1000,20);self.lib.test_audio_fault(7)
        self.assertFalse(self.lib.test_sound_close(self.rig));self.assertEqual((self.voice(1),self.voice(2),self.mem(2)),(0,1,64000));self.lib.test_audio_fault(0);self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual((self.voice(1),self.voice(3)),(1,0))
    def test_factory_release_failure_blocks_reopen_and_retains_remaining_resources(self):
        self.init();self.factory();self.assertTrue(self.lib.test_sound_open(self.rig,7));self.lib.test_sound_factory_fault(self.rig,2)
        self.assertFalse(self.lib.test_sound_close(self.rig));self.assertEqual((self.voice(2),self.mem(2)),(1,64000));self.assertFalse(self.lib.test_sound_open(self.rig,3));self.lib.test_sound_factory_fault(self.rig,0);self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual(self.voice(1),1)
    def test_pcm_free_retry_never_frees_recognition_context_twice(self):
        self.init();self.factory();self.assertTrue(self.lib.test_sound_open(self.rig,7));self.lib.test_audio_memory_fault(0,1)
        self.assertFalse(self.lib.test_sound_close(self.rig));self.assertEqual((self.voice(1),self.voice(2)),(1,0));self.lib.test_audio_memory_fault(0,0);self.assertTrue(self.lib.test_sound_close(self.rig));self.assertEqual(self.voice(1),1)
    def test_factory_requires_complete_callbacks_and_cannot_rebind_live_owner(self):
        self.assertFalse(self.lib.test_sound_factory(self.rig,0));self.init()
        for kind in (1,2,3,4):self.assertFalse(self.lib.test_sound_factory(self.rig,kind))
        self.factory();self.assertTrue(self.lib.test_sound_open(self.rig,7));self.assertFalse(self.lib.test_sound_factory(self.rig,0));self.assertFalse(self.lib.test_sound_voice(self.rig));self.assertTrue(self.lib.test_sound_close(self.rig));self.assertTrue(self.lib.test_sound_voice(self.rig));self.factory()

class CandidateVoiceStorageTests(unittest.TestCase):
    def test_candidate_uses_internal_lazy_factory_instead_of_large_static_voice(self):
        text=(ROOT/'firmware/esp-idf/lab-os-core/main/candidate_main.c').read_text();self.assertNotIn('static LabVoice voice;',text);self.assertIn('lab_board_sound_set_voice_factory',text);self.assertIn('lab_audio_pcm_alloc',text);self.assertIn('lab_audio_pcm_free',text)
