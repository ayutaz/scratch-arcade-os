"""音声ツールのUI/要求/失敗。合成backendであり実音は出さない。"""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.project import build_project
from labos.package import decode
from labos.sdk import Session


class Audio:
    def __init__(self):
        self.calls=[];self.state=0;self.peak=0;self.result=1;self.position=0;self.gain=1;self.gain_result=1
    def call(self,op,a,b):
        self.calls.append((op,a,b))
        if op==4:return self.state
        if op==5:return self.peak
        if op==7:return self.position
        if op==8:
            if self.gain_result==1:self.gain=a
            return self.gain_result
        if op==6:self.state=0;self.position=0;return self.result
        if self.result==1:self.state=2 if op==2 else 1
        return self.result


class AudioDeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result=build_project(ROOT/'apps/audio-desk')
        cls.manifest,cls.blob=decode(Path(result['package']).read_bytes())
    def setUp(self):
        self.audio=Audio();self.app=Session(self.blob,self.manifest,audio=self.audio)
        self.addCleanup(self.app.close);self.now=0
    def step(self,held=0,dt=16):
        self.now+=dt;return self.app.frame(held,self.now)
    def value(self,name='debug_value'):return self.app.debug(name)
    def mutations(self):return [c for c in self.audio.calls if c[0] not in (4,5,7)]
    def test_lazy_tone_record_play_and_no_repeat_on_hold(self):
        self.assertEqual(self.audio.calls,[]);self.step();self.assertEqual(self.mutations(),[])
        self.step(16);self.assertEqual(self.mutations(),[(1,1000,200)])
        self.step(16);self.assertEqual(len(self.mutations()),1)
        self.step(1);self.assertEqual(self.value('debug_y'),0) # busy: cannot switch
        self.audio.state=0;self.step();self.step(1);self.assertEqual(self.value('debug_y'),1)
        self.step(16);self.assertEqual(self.mutations()[-1],(2,500,0))
        self.audio.peak=32000;self.step();self.assertEqual(self.value('debug_x'),32000)
        self.audio.state=0;self.step(1);self.assertEqual(self.value('debug_y'),2)
        self.step(16);self.assertEqual(self.mutations()[-1],(3,0,0))
    def test_stop_has_priority_and_timeout_cancels_once(self):
        self.step(16|32);self.assertEqual(self.mutations(),[(6,0,0)])
        self.step();self.step(16);self.step(0,3000)
        self.assertEqual(self.mutations()[-1],(6,0,0));self.assertEqual(self.value(),-2)
        n=len(self.mutations());self.step(0,1000);self.assertEqual(len(self.mutations()),n)
        self.step(32);self.assertEqual(self.value(),1)
    def test_exit_precedes_io_even_during_recording(self):
        self.step(1);self.step(16);before=list(self.audio.calls)
        self.assertTrue(self.step(64));self.assertTrue(self.app.closed)
        self.assertEqual(self.audio.calls,before)
    def test_service_failure_and_absent_backend_remain_exitable(self):
        self.audio.result=-1;self.step(16);self.assertEqual(self.value(),-1)
        self.assertTrue(self.app.commands)
        session=Session(self.blob,self.manifest);self.addCleanup(session.close)
        session.frame(16,16);self.assertEqual(session.debug('debug_value'),-1)
        self.assertTrue(session.frame(64,32))
    def test_mode_wrap_and_package_has_only_authorized_audio_imports(self):
        self.step(2);self.assertEqual(self.value('debug_y'),2)
        self.step();self.step(1);self.assertEqual(self.value('debug_y'),0)
        self.assertEqual(self.manifest['capabilities'],['draw','speaker','microphone'])
        self.assertLessEqual(len(self.blob)+256,16384)
        import wasmtime
        module=wasmtime.Module(self.app.engine,self.blob)
        self.assertTrue(all(i.module=='os' and (i.name=='rect' or i.name.startswith('audio_')) for i in module.imports))

    def test_progress_uses_serviced_frames_instead_of_elapsed_time_or_loudness(self):
        self.step(1);self.step(16)
        self.audio.position=512;self.audio.peak=0;self.step(0,200)
        self.assertIn((20,156,17,12,2047),self.app.commands)
        self.audio.position=8000;self.audio.state=0;self.step()
        self.assertIn((20,156,280,12,2047),self.app.commands)
        self.step(32)
        self.assertNotIn((20,156,280,12,2047),self.app.commands)

    def replay_mode(self):
        self.step(2);self.step();self.assertEqual(self.value('debug_y'),2)

    def test_default_gain_four_is_applied_before_replay_within_two_mutations(self):
        self.replay_mode();self.step(16)
        self.assertEqual(self.mutations(),[(8,4,0),(3,0,0)])
        self.assertEqual(self.manifest['version'],'1.2.0')

    def test_up_down_adjust_replay_gain_on_edges_and_clamp_to_one_eight(self):
        self.replay_mode()
        self.step(8);self.step(8);self.step();self.step(8);self.step();self.step(16)
        self.assertEqual(self.mutations()[-2:],[(8,8,0),(3,0,0)])
        self.audio.state=0
        for _ in range(6):self.step(4);self.step()
        self.step(16);self.assertEqual(self.mutations()[-2:],[(8,1,0),(3,0,0)])

    def test_busy_gain_buttons_are_ignored_and_selected_gain_is_reapplied_after_stop(self):
        self.replay_mode();self.step(16);self.step(8)
        self.step(32);self.step();self.step(16)
        self.assertEqual(self.mutations(),[(8,4,0),(3,0,0),(6,0,0),(8,4,0),(3,0,0)])

    def test_rejected_gain_never_starts_replay(self):
        self.replay_mode()
        for rejected in (0,-1):
            self.audio.gain_result=rejected;self.step();self.step(16)
            self.assertEqual(self.value(),rejected)
        self.assertEqual(self.mutations(),[(8,4,0),(8,4,0)])

    def test_multiplier_fits_between_top_numbers_and_peak_bar(self):
        self.step()
        self.assertIn((54,106,2,8,65535),self.app.commands)
        for x,y,w,h,color in self.app.commands:
            if color==65535:self.assertLessEqual(y+h,130)
