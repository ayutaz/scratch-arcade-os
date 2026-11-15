"""SDK仕様からAIが作る2課題の受入試験。実機には接続しない。"""
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.project import build_project,check_project
from labos.sdk import Session
from labos.native import build_probe,run_probe
from labos.package import decode
from labos.home import Home
from labos.repository import Repository


class GeneratedAppsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages={}
        for name in ('lane-catcher','focus-timer'):
            result=build_project(ROOT/'tests/fixtures/generated-1.0.0'/name)
            cls.packages[name]=decode(Path(result['package']).read_bytes())
        cls.runner=build_probe()

    def app(self,name):
        manifest,blob=self.packages[name];s=Session(blob,manifest);self.addCleanup(s.close)
        return s

    def state(self,s):return tuple(s.debug(n) for n in ('debug_value','debug_x','debug_y','debug_elapsed'))

    def test_packages_fit_sdk_and_have_only_rect_import(self):
        import wasmtime
        for name,(manifest,blob) in self.packages.items():
            with self.subTest(name=name):
                s=self.app(name)
                self.assertEqual(manifest['capabilities'],['draw'])
                self.assertEqual(manifest['version'],'1.0.0')
                self.assertEqual([(i.module,i.name) for i in wasmtime.Module(s.engine,blob).imports],[('os','rect')])
                self.assertLessEqual((ROOT/'tests/fixtures/generated-1.0.0'/name/'build/app.labapp').stat().st_size,16384)
                self.assertTrue(check_project(ROOT/'tests/fixtures/generated-1.0.0'/name)['normal_exit'])

    def test_lane_catch_miss_finish_reset_and_key_edges(self):
        s=self.app('lane-catcher');s.frame(0,1000);self.assertEqual(self.state(s),(0,1,0,0))
        s.frame(16,1100);s.frame(0,2100);self.assertEqual(self.state(s),(1,1,1,1000))
        s.frame(1,2100);s.frame(1,2100);self.assertEqual(self.state(s)[1],2)
        s.frame(0,3100);self.assertEqual(self.state(s)[0],2)
        s.frame(2,3100);s.frame(0,3100);s.frame(2,3100);s.frame(0,4100)
        self.assertEqual(self.state(s)[0],3)
        s.frame(3,4100);self.assertEqual(self.state(s)[1],0)
        s.frame(0,10100);self.assertEqual(self.state(s)[2],2)
        frozen=self.state(s);s.frame(1,11100);self.assertEqual(self.state(s),frozen)
        s.frame(16,11100);self.assertEqual(self.state(s),(0,1,1,0))
        s.frame(32,11200);self.assertEqual(self.state(s),(0,1,0,0))
        self.assertTrue(s.frame(64,11200))

    def test_lane_time_quantization_and_large_step_have_same_state(self):
        a=self.app('lane-catcher');b=self.app('lane-catcher')
        a.frame(16,0);b.frame(16,0)
        for now in range(1,2501):a.frame(0,now)
        b.frame(0,2500);self.assertEqual(self.state(a),self.state(b))
        self.assertEqual(self.state(a),(1,1,1,2500))

    def test_lane_perfect_route_reaches_fifteen_seconds_without_zero_width_draw(self):
        s=self.app('lane-catcher');now=0;s.frame(16,now)
        for i in range(15):
            target=(1+i)%3
            while self.state(s)[1]!=target:
                s.frame(0,now)
                s.frame(1 if self.state(s)[1]<target else 2,now)
            now+=1000;s.frame(0,now)
        self.assertEqual(self.state(s),(15,0,2,15000))

    def test_timer_bounds_hold_start_pause_resume_completion_and_reset(self):
        s=self.app('focus-timer');s.frame(0,0);self.assertEqual(self.state(s),(60000,60,0,0))
        s.frame(8,10);s.frame(8,20);self.assertEqual(self.state(s)[:2],(70000,70))
        now=20
        for _ in range(40):
            now+=10;s.frame(0,now);now+=10;s.frame(4,now)
        self.assertEqual(self.state(s)[:2],(10000,10))
        now+=10;s.frame(16,now);s.frame(16,now+1000)
        self.assertEqual(self.state(s),(9000,10,1,1000))
        s.frame(8,now+1000);self.assertEqual(self.state(s)[1],10)
        s.frame(16,now+2000);self.assertEqual(self.state(s),(8000,10,2,2000))
        s.frame(0,now+12000);self.assertEqual(self.state(s),(8000,10,2,2000))
        s.frame(16,now+13000);self.assertEqual(self.state(s),(8000,10,1,2000))
        s.frame(0,now+23000);self.assertEqual(self.state(s),(0,10,3,10000))
        frozen=self.state(s);s.frame(0,now+24000);self.assertEqual(self.state(s),frozen)
        s.frame(16,now+25000);self.assertEqual(self.state(s),(10000,10,1,0))
        s.frame(32,now+26000);self.assertEqual(self.state(s),(10000,10,0,0))
        self.assertTrue(s.frame(64,now+26000))

    def test_timer_upper_bound_is_300_seconds(self):
        s=self.app('focus-timer');now=0
        for _ in range(40):
            s.frame(8,now);now+=1;s.frame(0,now);now+=1
        self.assertEqual(self.state(s),(300000,300,0,0))

    def test_timer_last_millisecond_does_not_emit_zero_width_rectangle(self):
        s=self.app('focus-timer');s.frame(16,0);s.frame(0,59999)
        self.assertEqual(self.state(s),(1,60,1,59999))
        s.frame(0,60000);self.assertEqual(self.state(s),(0,60,3,60000))

    def test_both_vms_match_state_and_graphics_for_independent_random_inputs(self):
        rng=random.Random(381)
        frames=[(0,0),(16,0),(0,1000),(1,0),(0,1000),(16,0),(0,2000),(16,0)]
        frames += [(rng.choice((0,1,2,3,4,8,12,16,32)),rng.randrange(0,300)) for _ in range(120)]
        frames += [(64,0)]
        for name,(_,blob) in self.packages.items():
            s=self.app(name);now=0
            rows=run_probe(self.runner,[blob],frames)
            for (held,dt),row in zip(frames,rows,strict=True):
                now+=dt;exited=s.frame(held,now)
                self.assertEqual(row['status'],'exit' if exited else 'running')
                if not exited:
                    self.assertEqual((row['value'],row['x'],row['y'],row['elapsed']),self.state(s))
                    self.assertEqual(row['rects'],[list(c) for c in s.commands])
                    self.assertLessEqual(len(s.commands),128)

    def test_home_individual_update_and_rejected_candidate_preserve_other_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();home=Home(Repository(root/'repository'));self.addCleanup(home.close)
            for manifest,blob in self.packages.values():home.install(manifest,blob)
            before=home.repository.current('focus-timer').copy()
            for name in self.packages:
                home.selected=next(i for i,r in enumerate(home.apps) if r['id']==name)
                home.frame(16,10);home.frame(0,20)
                self.assertEqual(home.active_id,name)
                home.frame(192,30);home.frame(0,40)
                self.assertEqual((home.mode,home.ledger.count),('home',0))
            copy=root/'lane';copy.mkdir()
            for name in ('app.json','app.c'):shutil.copyfile(ROOT/'tests/fixtures/generated-1.0.0/lane-catcher'/name,copy/name)
            config=json.loads((copy/'app.json').read_text());config['version']='1.0.1'
            (copy/'app.json').write_text(json.dumps(config))
            source=copy/'app.c';source.write_text(source.read_text().replace('#define SHIP_COLOR 2016','#define SHIP_COLOR 2047'))
            result=build_project(copy);good=Path(result['package']).read_bytes();m,blob=decode(good)
            home.install(m,blob)
            self.assertEqual(home.repository.current('lane-catcher')['version'],'1.0.1')
            self.assertEqual(home.repository.current('focus-timer'),before)
            # Compile failure must preserve last good package; rejected install keeps current.
            source.write_text('invalid C source')
            with self.assertRaises(RuntimeError):build_project(copy)
            self.assertEqual(Path(result['package']).read_bytes(),good)
            with self.assertRaises(ValueError):home.install({**m,'sha256':'0'*64},blob)
            self.assertEqual(home.repository.current('lane-catcher')['sha256'],m['sha256'])
            self.assertEqual(home.repository.current('focus-timer'),before)
            restarted=Home(Repository(root/'repository'));self.addCleanup(restarted.close)
            self.assertEqual(len(restarted.apps),2)
