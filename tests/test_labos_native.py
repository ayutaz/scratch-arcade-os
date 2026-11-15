import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import wasmtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.native import build_probe, run_probe
from labos.build import build, COMPILER
from labos.sdk import Session


def module(body='i32.const 0', prefix='', abi=2, tick_params='i32 i32 i32 i32'):
    return wasmtime.wat2wasm('''(module %s
      (func (export "sdk_abi") (result i32) i32.const %d)
      (func (export "init"))
      (func (export "tick") (param %s) (result i32) %s))''' % (prefix, abi, tick_params, body))


@unittest.skipUnless((ROOT / 'downloads/os-research/wamr-upstream/CMakeLists.txt').exists(),
                     '固定WAMR sourceが必要')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = build_probe()

    def test_budget_trap_then_next_app_and_repeated_cleanup(self):
        looping = module('(loop $spin br $spin) i32.const 0')
        normal = module()
        for _ in range(10):
            result = run_probe(self.runner, [looping, normal], [(0, 16)])
            self.assertEqual([row['status'] for row in result], ['trap', 'running'])
            self.assertEqual(result[-1]['pool_bytes'], 196608)

    def test_oob_and_memory_growth_cap(self):
        oob = module('i32.const 131072 i32.load drop i32.const 0', '(memory 2)')
        oom = module('i32.const 1 memory.grow i32.const -1 i32.eq if unreachable end i32.const 0', '(memory 2)')
        result = run_probe(self.runner, [oob, oom, module()], [(0, 16)])
        self.assertEqual([row['status'] for row in result], ['trap', 'trap', 'running'])

    def test_abi_signature_draw_bounds_and_start_hooks_are_rejected(self):
        bad = [module(abi=1), module(tick_params='i32'),
               module(prefix='(func $spin (loop $l br $l)) (start $spin)'),
               module(prefix='(func (export "__post_instantiate") (loop $l br $l))'),
               module(prefix='(func (export "__wasm_call_ctors") (loop $l br $l))')]
        result = run_probe(self.runner, bad + [module()], [(0, 16)])
        self.assertEqual([row['status'] for row in result], ['rejected'] * len(bad) + ['running'])
        draw = module('i32.const 319 i32.const 0 i32.const 2 i32.const 1 i32.const 1 call $r i32.const 0',
                      '(import "os" "rect" (func $r (param i32 i32 i32 i32 i32)))')
        self.assertEqual(run_probe(self.runner, [draw], [(0, 16)])[0]['status'], 'trap')

    def test_shutdown_budget_and_next_instance(self):
        b = module(prefix='(func (export "shutdown") (param i32) (loop $l br $l))')
        self.assertEqual([r['status'] for r in run_probe(self.runner, [b, module()], [(0, 0)])],
                         ['running', 'running'])

    @unittest.skipUnless(COMPILER.exists(), '固定C compilerが必要')
    def test_both_c_apps_match_wasmtime_every_frame(self):
        frames = [(16, 0), (1, 300), (0, 10), (1, 10), (0, 10), (2, 10), (64, 0)]
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('game', 'counter'):
                with self.subTest(name=name):
                    m, b = build(name, Path(tmp))
                    rows = run_probe(self.runner, [b], frames)
                    s = Session(b, m)
                    now = 0
                    for (held, dt), row in zip(frames, rows, strict=True):
                        now += dt
                        exited = s.frame(held, now)
                        self.assertEqual(row['status'], 'exit' if exited else 'running')
                        if not exited:
                            self.assertEqual(row['value'], s.debug('debug_value'))
                            self.assertEqual(row['x'], s.debug('debug_x'))
                            self.assertEqual(row['y'], s.debug('debug_y'))
                            self.assertEqual(row['elapsed'], s.debug('debug_elapsed'))
                            self.assertEqual(row['rects'], [list(c) for c in s.commands])
                    s.close()

    def test_bad_frame_input_is_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'app.wasm'
            f.write_bytes(module())
            for text in ('256:0', '0:60001', '0:-1', '-1:0', '', '0:0,', '1:1junk'):
                proc = subprocess.run([str(self.runner), text, str(f)], capture_output=True,
                                      text=True, timeout=5)
                self.assertEqual(proc.returncode, 64, text)
