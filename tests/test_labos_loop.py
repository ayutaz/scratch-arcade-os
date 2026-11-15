import ctypes as C
import tempfile
import unittest
from pathlib import Path

import wasmtime
import test_labos_lfs as fs
import test_labos_c_store as contract
from labos.ui_assets import generate

ROOT = contract.ROOT


def counter():
    wasm = bytes(wasmtime.wat2wasm('''(module
      (import "os" "rect" (func $rect (param i32 i32 i32 i32 i32)))
      (global $v (mut i32) (i32.const 0))
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "debug_value") (result i32) global.get $v)
      (func (export "tick") (param i32 i32 i32 i32) (result i32)
        local.get 1 i32.const 64 i32.and if i32.const 1 return end
        local.get 1 i32.const 1 i32.and if global.get $v i32.const 1 i32.add global.set $v end
        i32.const 0 i32.const 0 i32.const 320 i32.const 240 i32.const 0 call $rect
        i32.const 10 i32.const 10 i32.const 1 i32.const 16 i32.const 2016 call $rect
        i32.const 0))'''))
    return contract.encode(contract.make_manifest('counter', wasm), wasm)


class LoopTests(fs.LittleFsFixture, unittest.TestCase):
    extra_sources = (ROOT / 'prototypes/lab-os/native/run_loop.c', ROOT / 'prototypes/lab-os/native/ui.c',
                     ROOT / 'tests/native/lab_loop_bridge.c')
    extra_signatures = {
        'test_loop_new': ([C.c_void_p, C.c_uint32], C.c_void_p),
        'test_loop_free': ([C.c_void_p], None),
        'test_loop_input': ([C.c_void_p, C.c_uint32, C.c_uint32, C.c_int, C.c_int, C.c_int], None),
        'test_loop_flags': ([C.c_void_p, C.c_uint32], None),
        'test_loop_paint_ok': ([C.c_void_p, C.c_int], None),
        'test_loop_notice': ([C.c_void_p,C.c_int],None),
        'test_loop_step': ([C.c_void_p, C.c_uint32], C.c_int),
        'test_loop_metric': ([C.c_void_p, C.c_int], C.c_uint32),
        'test_home_mode': ([C.c_void_p], C.c_int),
        'test_home_refresh': ([C.c_void_p], C.c_int),
    }

    @classmethod
    def setUpClass(cls):
        cls.fonts = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fonts.cleanup)
        generate(Path(cls.fonts.name))
        cls.extra_flags = ('-I' + cls.fonts.name, '-I' + str(ROOT / 'assets/fonts'))
        super().setUpClass()

    def setUp(self):
        self.loops = []
        super().setUp()
        self.assertTrue(self.connect())
        self.store = self.open_store()
        self.assertTrue(self.install(self.store, counter()))
        self.assertTrue(self.lib.test_home_start(self.store))
        self.loop = self.lib.test_loop_new(self.store, 0)
        self.assertTrue(self.loop)
        self.loops.append(self.loop)

    def close_all(self):
        for loop in self.loops: self.lib.test_loop_free(loop)
        self.loops.clear()
        super().close_all()

    def input(self, held=0, keys=0, x=0, y=0, valid=True):
        self.lib.test_loop_input(self.loop, held, keys, x, y, int(valid))

    def step(self, now, result=0):
        self.assertEqual(self.lib.test_loop_step(self.loop, now), result)

    def metric(self, key): return self.lib.test_loop_metric(self.loop, key)

    def launch(self):
        self.input();self.step(0)
        self.input(16, 2);self.step(10)
        self.assertEqual(self.lib.test_home_mode(self.store), 1)

    def test_startup_waits_for_all_controls_and_launch_renders_initial_guest_frame(self):
        self.input(16, 2);self.step(0);self.step(10)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.input(keys=16);self.step(20)  # physical Y has no ABI bit but is not neutral.
        self.input(16, 18);self.step(30)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.input();self.step(40)
        self.input(16, 2);self.step(50)
        self.assertEqual(self.lib.test_home_mode(self.store), 1)
        self.assertGreater(self.metric(4), 0)
        self.assertEqual(self.metric(5), 2016)

    def test_small_axis_drift_allows_startup_and_release_before_next_launch(self):
        self.input(x=0,y=-2);self.step(0)
        self.input(16,2,x=0,y=-2);self.step(10)
        self.assertEqual(self.lib.test_home_mode(self.store),1)
        self.input(192,5,y=-2);self.step(20)
        self.input(y=-2);self.step(30)
        self.input(16,2,y=-2);self.step(40)
        self.assertEqual(self.lib.test_home_mode(self.store),1)

    def test_management_transaction_blocks_home_and_requires_release_even_when_already_finished(self):
        self.input();self.step(0)
        self.lib.test_loop_flags(self.loop, 3)
        self.input(16, 2);self.step(10)
        self.lib.test_loop_flags(self.loop, 0)
        self.step(20)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.input();self.step(30)
        self.lib.test_loop_flags(self.loop, 2)  # short transaction completed within the service callback.
        self.input(16, 2);self.step(40)
        self.lib.test_loop_flags(self.loop, 0);self.step(50)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.input();self.step(60)
        self.input(16, 2);self.step(70)
        self.assertEqual(self.lib.test_home_mode(self.store), 1)

    def test_running_app_and_reserved_exit_continue_during_management_session(self):
        self.launch()
        self.lib.test_loop_flags(self.loop, 3)
        self.input(1, x=-100);self.step(20)
        self.assertEqual(self.lib.test_home_value(self.store), 1)
        self.input(192, 5);self.step(30)
        self.assertEqual(self.lib.test_home_mode(self.store), 2)
        self.input();self.step(40)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.input(16, 2);self.step(50)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)

    def test_one_neutral_exit_sample_is_enough_before_next_launch(self):
        self.launch()
        self.input(192, 5);self.step(20)
        self.input();self.step(30)
        self.input(16, 2);self.step(40)
        self.assertEqual(self.lib.test_home_mode(self.store), 1)

    def test_home_selection_is_painted_without_waiting_for_frame_interval(self):
        self.assertTrue(self.install(self.store, contract.package('game')))
        self.assertTrue(self.lib.test_home_refresh(self.store))
        self.input();self.step(0)
        self.input(4, y=-100);self.step(1)
        self.assertEqual((self.metric(1), self.metric(7)), (2, 1))

    def test_input_error_closes_vm_without_using_partial_key_and_waits_for_neutral_after_recovery(self):
        self.launch()
        self.input(16, 2, valid=False);self.step(20, result=1)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.assertTrue(self.install(self.store, contract.package(version='1.0.1')))
        self.input(16, 2);self.step(30)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.input();self.step(40)
        self.input(16, 2);self.step(50)
        self.assertEqual(self.lib.test_home_mode(self.store), 1)

    def test_invalid_sample_is_treated_as_input_fault(self):
        self.input(256);self.step(0, result=1)
        self.input(keys=32);self.step(10, result=1)
        self.input(x=101);self.step(20, result=1)
        self.input();self.step(30)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)

    def test_guest_trap_returns_through_release_to_previous_app_without_stopping_loop(self):
        bad = contract.package(version='1.0.1', body='local.get 1 i32.const 1 i32.and if unreachable end i32.const 0')
        self.assertTrue(self.install(self.store, bad))
        self.launch()
        self.input(1, x=-100);self.step(20)
        self.assertEqual(self.lib.test_home_mode(self.store), 2)
        self.assertEqual(self.version(self.store), '1.0.0')
        self.input();self.step(30)
        self.input(16, 2);self.step(40)
        self.assertEqual(self.lib.test_home_mode(self.store), 1)
        self.assertEqual(self.metric(5), 2016)

    def test_drawing_is_paced_but_mode_changes_paint_immediately(self):
        self.input();self.step(0)
        self.assertEqual((self.metric(1), self.metric(2)), (1, 240))
        self.step(10);self.step(32)
        self.assertEqual(self.metric(1), 1)
        self.step(33)
        self.assertEqual(self.metric(1), 1)
        self.input(16, 2);self.step(34)
        self.assertEqual(self.metric(1), 2)
        self.input();self.step(66);self.assertEqual(self.metric(1),2)
        self.step(67);self.assertEqual(self.metric(1),3)

    def test_unchanged_home_does_not_redraw_during_one_second_of_management_polls(self):
        self.input();self.step(0)
        self.lib.test_loop_flags(self.loop,3)
        for now in range(33,1001,33):self.step(now)
        self.assertEqual(self.metric(1),1)
        self.assertEqual(self.metric(0),31)
        self.assertEqual(self.lib.test_home_mode(self.store),0)

    def test_catalog_add_update_and_unchanged_refresh_paint_only_actual_changes(self):
        self.input();self.step(0)
        self.assertTrue(self.install(self.store,contract.package('game')))
        self.assertTrue(self.lib.test_home_refresh(self.store));self.step(1)
        self.assertEqual((self.metric(1),self.metric(8)),(2,2))
        self.assertTrue(self.install(self.store,contract.package('game',version='1.0.1')))
        self.assertTrue(self.lib.test_home_refresh(self.store));self.step(2)
        self.assertEqual(self.metric(1),3)
        self.assertTrue(self.lib.test_home_refresh(self.store));self.step(1000)
        self.assertEqual(self.metric(1),3)

    def test_notice_changed_outside_step_is_painted_even_before_frame_deadline(self):
        self.input();self.step(0)
        self.lib.test_loop_notice(self.loop,2);self.step(1)
        self.assertEqual(self.metric(1),2)
        self.lib.test_loop_notice(self.loop,2);self.step(34)
        self.assertEqual(self.metric(1),2)
        self.lib.test_loop_notice(self.loop,0);self.step(35)
        self.assertEqual(self.metric(1),3)

    def test_render_failure_stops_and_releases_vm_until_explicit_reinitialization(self):
        self.launch()
        self.lib.test_loop_paint_ok(self.loop, 0)
        self.input();self.step(50, result=2)
        self.assertEqual(self.lib.test_home_mode(self.store), 0)
        self.assertTrue(self.install(self.store, contract.package(version='1.0.1')))
        reads = self.metric(0)
        self.step(60, result=2)
        self.assertEqual(self.metric(0), reads)

    def test_invalid_service_flags_or_large_clock_gap_stop_before_new_input(self):
        self.lib.test_loop_flags(self.loop, 4)
        self.step(0, result=2)
        self.assertEqual(self.metric(0), 0)
        self.loop = self.lib.test_loop_new(self.store, 0xfffffff0)
        self.loops.append(self.loop)
        self.input();self.step(20)
        self.step(60021, result=2)
