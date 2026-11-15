"""2秒録音専用appの有限契約。PCMや実音は扱わない。"""
from pathlib import Path
import sys
import unittest
import test_labos_audio_desk as fixture
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.project import build_project
from labos.package import decode
from labos.sdk import Session


class RecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest,cls.blob=decode(Path(build_project(ROOT/'apps/voice-recorder')['package']).read_bytes())
    def setUp(self):
        self.audio=fixture.Audio();self.s=Session(self.blob,self.manifest,audio=self.audio);self.addCleanup(self.s.close);self.now=0
    def step(self,key=0,dt=16):self.now+=dt;return self.s.frame(key,self.now)
    def mutations(self):return [c for c in self.audio.calls if c[0] not in (4,5,7)]
    def complete(self):
        self.step(16);self.audio.position=32000;self.audio.state=0;self.step()
    def test_lazy_two_seconds_record_and_no_repeated_capture_on_hold(self):
        self.assertEqual(self.audio.calls,[]);self.step(16);self.step(16)
        self.assertEqual(self.mutations(),[(2,2000,0)])
        self.assertEqual(self.manifest['capabilities'],['draw','speaker','microphone'])
    def test_progress_uses_serviced_samples_and_no_play_before_complete(self):
        self.step(32);self.assertEqual(self.mutations(),[])
        self.step(16);self.audio.position=16000;self.step(0,900)
        self.assertIn((20,154,140,12,2047),self.s.commands)
        self.assertEqual(self.s.debug('debug_y'),0)
        self.audio.position=32000;self.audio.state=0;self.step()
        self.assertEqual(self.s.debug('debug_y'),1)
        self.assertIn((20,154,280,12,2047),self.s.commands)
    def test_replay_applies_four_gain_before_play_and_refusal_prevents_play(self):
        self.complete();self.step(32)
        self.assertEqual(self.mutations()[-2:],[(8,4,0),(3,0,0)])
        self.assertLessEqual(len(self.s.commands),128)
    def test_stop_and_timeout_clear_recording_without_repeated_stop(self):
        self.complete();self.step(4);self.assertEqual(self.mutations()[-1],(6,0,0));self.assertEqual(self.s.debug('debug_y'),0)
        self.step();self.step(16);self.step(0,4000)
        self.assertEqual(self.s.debug('debug_value'),-2);n=len(self.mutations());self.step(0,1000)
        self.assertEqual(len(self.mutations()),n)
    def test_exit_has_priority_and_invalid_gain_never_replays(self):
        self.complete();self.audio.gain_result=-1;self.step(32)
        self.assertEqual(self.mutations()[-1],(8,4,0))
        before=list(self.audio.calls);self.assertTrue(self.step(64|16));self.assertEqual(self.audio.calls,before)
    def test_both_vms_without_backend_have_identical_bounded_ui_and_exit(self):
        from labos.native import build_probe,run_probe
        s=Session(self.blob,self.manifest);self.addCleanup(s.close);frames=[(0,0),(16,0),(0,2000),(32,0),(4,0),(64,0)]
        rows=run_probe(build_probe(),[self.blob],frames,capabilities=7);now=0
        for row,(held,dt) in zip(rows,frames,strict=True):
            now+=dt;done=s.frame(held,now);self.assertEqual(row['status'],'exit' if done else 'running')
            if not done:self.assertEqual(row['rects'],[list(r) for r in s.commands])
