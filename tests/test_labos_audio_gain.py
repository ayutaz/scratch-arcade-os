"""合成PCMだけで再生ゲインを検証。実声・実音圧の測定ではない。"""
import ctypes as C
import random
import math
import unittest
import test_labos_audio_service as service_fixture


class AudioGainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service_fixture.AudioServiceTests.setUpClass.__func__(cls)
        cls.lib.test_gain.argtypes=[C.c_uint,C.c_uint]
        cls.lib.test_set_sample.argtypes=[C.c_uint,C.c_int]

    def setUp(self):
        self.assertTrue(self.lib.test_init(32000))

    def capture(self,values):
        self.assertTrue(self.lib.test_claim(1,3))
        self.assertTrue(self.lib.test_record(1,32,0))
        self.lib.test_results(1,1,256,1)
        self.assertEqual(self.lib.test_poll(1),0)
        self.assertEqual(self.lib.test_poll(2),1)
        for i,v in enumerate(values):self.lib.test_set_sample(i,v)

    def replay(self,gain,chunk=256):
        self.assertTrue(self.lib.test_gain(1,gain))
        self.assertTrue(self.lib.test_play(1,3))
        self.lib.test_results(1,1,0,1)
        self.assertEqual(self.lib.test_poll(4),0)
        self.assertEqual(self.lib.test_output_frames(),0)
        self.lib.test_results(1,1,chunk,1)
        for now in range(5,5+512//chunk):self.assertEqual(self.lib.test_poll(now),0)
        self.assertEqual(self.lib.test_poll(5+512//chunk),1)
        return [self.lib.test_output(i) for i in range(512)]

    def test_weak_signed_samples_are_amplified_without_altering_recording(self):
        raw=[128 if i&1 else -128 for i in range(512)]
        self.capture(raw);out=self.replay(4)
        self.assertEqual(out[100:102],[-512,512])
        self.assertEqual((out[0],out[-1]),(0,0))
        self.assertEqual([self.lib.test_sample(i) for i in range(512)],raw)

    def test_all_gains_preserve_ceiling_fade_silence_and_exact_partial_offsets(self):
        rng=random.Random(74)
        raw=[-32768,32767,0,-128,128]+[rng.randint(-32768,32767) for _ in range(507)]
        for gain in range(9):
            with self.subTest(gain=gain):
                self.assertTrue(self.lib.test_init(32000));self.capture(raw)
                out=self.replay(gain,32)
                mean=math.trunc(sum(raw)/len(raw));peak=max(abs(v-mean) for v in raw)
                scale=min(gain,3277/peak) if peak else 0
                expected=[int((v-mean)*scale*min(i,511-i,80)/80) for i,v in enumerate(raw)]
                self.assertTrue(all(abs(a-b)<=3 for a,b in zip(out,expected,strict=True)))
                self.assertLessEqual(max(map(abs,out)),3277)
                if gain==0:self.assertEqual(out,[0]*512)

    def test_lease_defaults_to_unity_and_previous_app_gain_is_not_inherited(self):
        self.assertTrue(self.lib.test_claim(1,3));self.assertEqual(self.lib.test_gain_value(),1)
        self.assertTrue(self.lib.test_gain(1,8));self.assertTrue(self.lib.test_release(1))
        self.assertTrue(self.lib.test_claim(2,3));self.assertEqual(self.lib.test_gain_value(),1)
        self.assertFalse(self.lib.test_gain(1,4));self.assertEqual(self.lib.test_gain_value(),1)

    def test_invalid_owner_permission_range_and_busy_do_not_change_gain_or_open_io(self):
        self.assertFalse(self.lib.test_gain(0,4));self.assertTrue(self.lib.test_claim(1,2))
        self.assertFalse(self.lib.test_gain(1,4));self.assertTrue(self.lib.test_release(1))
        self.assertTrue(self.lib.test_claim(1,3))
        for owner,gain in ((0,4),(2,4),(1,9),(1,0xffffffff)):
            self.assertFalse(self.lib.test_gain(owner,gain))
        self.assertEqual(self.lib.test_gain_value(),1);self.assertEqual(self.lib.test_calls(0),0)
        self.assertTrue(self.lib.test_record(1,32,0))
        self.assertFalse(self.lib.test_gain(1,4));self.assertEqual(self.lib.test_gain_value(),1)

    def test_gain_does_not_scale_tone_or_capture_and_old_default_replay_is_unchanged(self):
        self.assertTrue(self.lib.test_claim(1,3));self.assertTrue(self.lib.test_gain(1,8))
        self.assertTrue(self.lib.test_tone(1,1000,32,0))
        self.assertLessEqual(max(abs(self.lib.test_sample(i)) for i in range(512)),2048)
        self.assertTrue(self.lib.test_release(1));self.assertTrue(self.lib.test_init(32000))
        self.assertTrue(self.lib.test_claim(1,3));self.assertTrue(self.lib.test_gain(1,8))
        self.assertTrue(self.lib.test_record(1,32,0));self.lib.test_results(1,1,256,1)
        self.lib.test_poll(1);self.lib.test_poll(2)
        self.assertEqual(self.lib.test_sample(127),128)

    def test_failed_cleanup_keeps_gain_locked_and_new_lease_resets_it(self):
        self.assertTrue(self.lib.test_claim(1,3));self.assertTrue(self.lib.test_gain(1,4))
        self.assertTrue(self.lib.test_record(1,32,0));self.lib.test_results(1,0,0,0)
        self.assertFalse(self.lib.test_release(1));self.assertFalse(self.lib.test_gain(1,8))
        self.assertFalse(self.lib.test_claim(2,3));self.lib.test_results(1,1,0,0)
        self.assertTrue(self.lib.test_release(1));self.assertTrue(self.lib.test_claim(2,3))
        self.assertEqual(self.lib.test_gain_value(),1)
