"""録音の偏り/歪みを合成PCMで再現。実声の原因確定ではない。"""
import ctypes as C
import math
import random
import unittest
import test_labos_audio_gain as gain_fixture


class AudioQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):gain_fixture.AudioGainTests.setUpClass.__func__(cls)
    setUp=gain_fixture.AudioGainTests.setUp
    capture=gain_fixture.AudioGainTests.capture
    replay=gain_fixture.AudioGainTests.replay
    def test_biased_voice_wave_is_not_flattened_by_amplification(self):
        raw=[1200+round(300*math.sin(2*math.pi*i/16)) for i in range(512)]
        self.capture(raw);out=self.replay(4)
        middle=out[80:-80]
        self.assertGreater(max(middle)-min(middle),2000)
        self.assertLess(abs(sum(middle)/len(middle)),10)
        self.assertEqual([self.lib.test_sample(i) for i in range(512)],raw)

    def test_constant_dc_is_silent_instead_of_a_clipped_output(self):
        self.capture([2000]*512);self.assertEqual(self.replay(8),[0]*512)

    def test_strong_sine_is_attenuated_linearly_without_flat_clipping(self):
        raw=[round(16000*math.sin(2*math.pi*i/16)) for i in range(512)]
        self.capture(raw);out=self.replay(8)
        scale=3277*32768//16000
        expected=[math.trunc(math.trunc(v*scale/32768)*min(i,511-i,80)/80) for i,v in enumerate(raw)]
        self.assertEqual(out,expected)

    def metric(self,owner,field):
        self.lib.test_record_metric.argtypes=[C.c_uint,C.c_uint]
        return self.lib.test_record_metric(owner,field)

    def test_recording_metrics_match_integer_reference_without_pcm_export(self):
        raw=[-32768,32767,0,2000]+[1200]*508;self.capture(raw)
        total=sum(raw);squares=sum(v*v for v in raw);n=len(raw);mean=math.trunc(total/n)
        expected=[n,min(raw),max(raw),mean,math.isqrt(squares//n),math.isqrt((squares*n-total*total)//(n*n)),max(abs(v-mean) for v in raw),2]
        self.assertEqual([self.metric(1,i) for i in range(8)],expected)
        self.assertTrue(self.lib.test_gain(1,8))
        self.assertEqual([self.metric(1,i) for i in range(8)],expected)

    def test_metrics_require_current_mic_lease_complete_recording_and_idle_state(self):
        self.assertTrue(self.lib.test_claim(1,3));self.assertEqual(self.metric(1,0),-1)
        self.assertTrue(self.lib.test_release(1));self.capture([200]*512)
        for owner in (0,2):self.assertEqual(self.metric(owner,0),-1)
        self.assertTrue(self.lib.test_play(1,3));self.assertEqual(self.metric(1,0),-1)
        self.assertTrue(self.lib.test_release(1));self.assertEqual(self.metric(1,0),-1)

    def test_dc_corrected_partial_replay_matches_independent_reference(self):
        rng=random.Random(18);raw=[1000+rng.randrange(-2000,2001) for _ in range(512)]
        self.capture(raw);out=self.replay(4,32)
        mean=math.trunc(sum(raw)/len(raw));peak=max(abs(v-mean) for v in raw)
        scale=min(4*32768,3277*32768//peak)
        expected=[math.trunc(math.trunc((v-mean)*scale/32768)*min(i,511-i,80)/80) for i,v in enumerate(raw)]
        self.assertEqual(out,expected)

    def test_fixed_tone_metrics_distinguish_two_time_ordered_frequencies(self):
        raw=[1100+round(1000*math.sin(2*math.pi*1320*i/16000)) for i in range(256)]
        raw += [1100+round(700*math.sin(2*math.pi*1760*i/16000)) for i in range(256)]
        self.capture(raw)
        values=[self.metric(1,i) for i in range(8,12)]
        self.assertTrue(900<=values[0]<=1100,values)
        self.assertTrue(600<=values[3]<=800,values)
        self.assertTrue(0<=values[1]<100 and 0<=values[2]<100,values)
