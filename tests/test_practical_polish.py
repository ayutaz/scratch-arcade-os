"""日本語案内と音声。合成backendであり実音を保証しない。"""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.project import build_project,check_project
from labos.package import decode
from labos.sdk import Session
from labos.app_labels import bitmap,LABELS


class Audio:
    def __init__(self):self.calls=[];self.result=1
    def call(self,op,a,b):
        if op==1:self.calls.append((a,b));return self.result
        return 0


class PolishTests(unittest.TestCase):
    def app(self,name,audio=None):
        m,b=decode(Path(build_project(ROOT/'tests/fixtures/practical-polish-v1'/name)['package']).read_bytes())
        s=Session(b,m,audio=audio);self.addCleanup(s.close);return s,m
    def test_new_packages_use_speaker_and_still_exit_without_backend(self):
        for name in ('lane-catcher','focus-timer'):
            s,m=self.app(name)
            self.assertEqual(m['version'],'1.1.0');self.assertEqual(m['capabilities'],['draw','speaker'])
            self.assertTrue(check_project(ROOT/'tests/fixtures/practical-polish-v1'/name)['normal_exit'])
    def test_timer_completion_tone_is_once_and_not_retriggered_by_idle_frames(self):
        a=Audio();s,_=self.app('focus-timer',a);s.frame(16,0);s.frame(0,60000)
        self.assertEqual(a.calls,[(1320,200)])
        for now in (60016,60100,61000):s.frame(0,now)
        self.assertEqual(len(a.calls),1)
        s.frame(32,61001);s.frame(0,61002);s.frame(16,61003);s.frame(0,121003)
        self.assertEqual(len(a.calls),2)
    def test_busy_alarm_retries_boundedly_and_exit_has_no_new_audio(self):
        a=Audio();a.result=0;s,_=self.app('focus-timer',a);s.frame(16,0);s.frame(0,60000)
        self.assertEqual(len(a.calls),1);s.frame(0,60500);self.assertEqual(len(a.calls),2)
        s.frame(0,61001);n=len(a.calls);s.frame(0,62000);self.assertEqual(len(a.calls),n)
        self.assertTrue(s.frame(64,62001));self.assertEqual(len(a.calls),n)
    def test_game_feedback_coalesces_many_events_into_one_request_per_frame(self):
        a=Audio();s,_=self.app('lane-catcher',a);s.frame(16,0);s.frame(0,1000)
        self.assertEqual(a.calls,[(880,60)])
        s.frame(0,10000);self.assertEqual(len(a.calls),2);self.assertEqual(a.calls[-1],(440,120))
        s.frame(0,10100);self.assertEqual(len(a.calls),2)
    def test_japanese_start_pixels_and_all_scenes_fit_original_draw_quota(self):
        for name,(x,y) in (('lane-catcher',(16,1)),('focus-timer',(20,184))):
            s,_=self.app(name);s.frame(0,0);pixels=bitmap(LABELS['START']);canvas=[[0]*len(pixels[0]) for _ in pixels]
            for rx,ry,w,h,color in s.commands:
                for yy in range(max(ry,y),min(ry+h,y+len(canvas))):
                    for xx in range(max(rx,x),min(rx+w,x+len(canvas[0]))):canvas[yy-y][xx-x]=int(color==65535)
            self.assertEqual(canvas,pixels)
            now=0
            for key,dt in ((16,0),(0,1000),(1,1000),(0,60000),(32,0),(0,1)):
                now+=dt;s.frame(key,now);self.assertLessEqual(len(s.commands),128)

    def test_both_vms_match_soundless_fallback_state_and_japanese_draws(self):
        from labos.native import build_probe,run_probe
        runner=build_probe();frames=[(0,0),(16,0),(0,1000),(1,1000),(16,0),(0,60000),(32,0),(0,1),(64,0)]
        for name in ('lane-catcher','focus-timer'):
            s,m=self.app(name);blob=Path(build_project(ROOT/'tests/fixtures/practical-polish-v1'/name)['package']).read_bytes();_,wasm=decode(blob)
            rows=run_probe(runner,[wasm],frames,capabilities=3);now=0
            for row,(held,dt) in zip(rows,frames,strict=True):
                now+=dt;done=s.frame(held,now)
                self.assertEqual(row['status'],'exit' if done else 'running')
                if not done:
                    self.assertEqual(row['rects'],[list(c) for c in s.commands])
                    self.assertEqual(row['value'],s.debug('debug_value'))
