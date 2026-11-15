"""30秒で3個を集めるゲーム。実C→WASMを両VMで操作する。"""
import json
from pathlib import Path
import random
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.project import build_project
from labos.package import decode
from labos.sdk import Session
from labos.native import build_probe,run_probe


class MazeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result=build_project(ROOT/'apps/maze-runner')
        cls.manifest,cls.blob=decode(Path(result['package']).read_bytes())
        cls.runner=build_probe()

    def setUp(self):
        self.app=Session(self.blob,self.manifest);self.addCleanup(self.app.close);self.now=0

    def step(self,held=0,dt=0):
        self.now+=dt;return self.app.frame(held,self.now)

    def state(self):
        return tuple(self.app.debug(n) for n in ('debug_value','debug_x','debug_y','debug_elapsed'))

    def test_cover_requires_start_and_package_fits_device(self):
        self.step(1,1000);self.assertEqual(self.state(),(0,16,104,0))
        self.assertEqual(self.manifest['id'],'maze-runner')
        self.assertEqual(self.manifest['capabilities'],['draw'])
        self.assertLessEqual(len(self.blob)+256,16384)
        result=build_project(ROOT/'apps/maze-runner')
        self.assertEqual(decode(Path(result['package']).read_bytes())[1],self.blob)

    def test_swept_pickup_wall_and_route_to_three_targets(self):
        self.step(16);self.step(1,500)
        self.assertEqual(self.state()[:3],(1,66,104))
        self.step(1,5000);self.assertEqual(self.state()[1],144)
        self.step(4,1040);self.step(1,1040)
        self.assertEqual(self.state()[:3],(2,248,208))
        self.step(2,2160);self.assertEqual(self.state()[:3],(3,32,208))
        completed=self.state();self.step(1,1000);self.assertEqual(self.state(),completed)
        self.step(16);self.assertEqual(self.state(),(0,16,104,0))

    def test_time_over_freezes_game_and_reset_returns_to_cover(self):
        self.step(16);self.step(0,30000)
        self.assertEqual(self.state(),(0,16,104,30000))
        self.step(1,60000);self.assertEqual(self.state(),(0,16,104,30000))
        self.step(32);self.step(1,1000);self.assertEqual(self.state(),(0,16,104,0))
        self.step(16);self.step(1,100);self.assertEqual(self.state()[1],26)
        self.assertTrue(self.step(64));self.assertTrue(self.app.closed)

    def test_opposite_directions_cancel_and_fractional_motion_preserves_time(self):
        self.step(16);self.step(3|12,1000);self.assertEqual(self.state()[1:3],(16,104))
        for _ in range(100):self.step(1,1)
        self.assertEqual(self.state()[1],26)

    def test_reverse_vertical_sweep_cannot_enter_wall_from_gap(self):
        self.step(16);self.step(4,1040);self.step(1,1400)
        self.assertEqual(self.state()[1:3],(156,208))
        self.step(8,1000);self.assertEqual(self.state()[1:3],(156,192))

    def test_both_vms_match_route_and_random_valid_input_without_trap(self):
        route=[(0,0),(16,0),(1,500),(1,5000),(4,1040),(1,1040),(2,2160),(16,0),(0,0)]
        rng=random.Random(17)
        frames=route+[(rng.choice([0,1,2,4,8,3,12,32,16]),rng.randrange(0,300)) for _ in range(100)]+[(64,0)]
        rows=run_probe(self.runner,[self.blob],frames)
        for (held,dt),row in zip(frames,rows,strict=True):
            exited=self.step(held,dt)
            self.assertEqual(row['status'],'exit' if exited else 'running')
            if not exited:
                self.assertEqual((row['value'],row['x'],row['y'],row['elapsed']),self.state())
                self.assertEqual(row['rects'],[list(c) for c in self.app.commands])
                self.assertLessEqual(len(row['rects']),128)
