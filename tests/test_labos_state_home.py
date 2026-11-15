"""OS由来app IDの束縛・終了順序・保存失敗をホストHomeで検証。"""
import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wasmtime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.native import SOURCE,build_probe


def wasm(legacy=False):
    imports='' if legacy else '''(import "os" "state_read" (func $read (param i32 i32) (result i32)))
    (import "os" "state_write" (func $write (param i32 i32) (result i32)))'''
    initial='' if legacy else 'i32.const 0 i32.const 17 call $read global.set $v'
    body='' if legacy else '''local.get $p i32.const 1 i32.and if i32.const 0 i32.const 41 call $write global.set $s end
    local.get $p i32.const 2 i32.and if i32.const 0 i32.const 42 call $write global.set $s end
    i32.const 0 i32.const 17 call $read global.set $v'''
    return bytes(wasmtime.wat2wasm(f'''(module {imports}
    (global $v (mut i32) (i32.const 0)) (global $s (mut i32) (i32.const 0))
    (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init") {initial})
    (func (export "tick") (param i32) (param $p i32) (param i32 i32) (result i32)
     local.get $p i32.const 64 i32.and if i32.const 1 return end
     local.get $p i32.const 32 i32.and if unreachable end {body} i32.const 0)
    (func (export "debug_value") (result i32) global.get $v)
    (func (export "debug_x") (result i32) global.get $s))'''))


class StateHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'home.so';native=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),'-I'+str(SOURCE/'core/iwasm/include'),*[str(native/(n+'.c')) for n in ('guest_vm','app_home','state_service','state_binding')],str(ROOT/'tests/native/lab_state_home_bridge.c'),str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),'-lpthread','-lm','-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.argtypes=[C.c_void_p,C.c_uint,C.c_uint];cls.lib.test_new.restype=C.c_void_p
        for n in ('test_free','test_value','test_status','test_close','test_scrubbed'):getattr(cls.lib,n).argtypes=[C.c_void_p]
        cls.lib.test_step.argtypes=[C.c_void_p,C.c_uint,C.c_uint];cls.lib.test_metric.argtypes=[C.c_void_p,C.c_uint]
        cls.lib.test_fault.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int];cls.lib.test_configure.argtypes=[C.c_void_p,C.c_int];cls.lib.test_bound.argtypes=[C.c_void_p,C.c_char_p]
        assert cls.lib.test_runtime_start();cls.addClassCleanup(cls.lib.test_runtime_stop)
    def setUp(self):self.new()
    def new(self,legacy=False):
        b=wasm(legacy);self.r=self.lib.test_new(b,len(b),1 if legacy else 16);self.assertTrue(self.r);self.addCleanup(self.lib.test_free,self.r)
    def step(self,h=0,dt=16):self.assertTrue(self.lib.test_step(self.r,h,dt))
    def metric(self,n):return self.lib.test_metric(self.r,n)
    def launch(self):self.step(16);self.assertEqual(self.metric(0),1);self.step()
    def exit(self,h=192):self.step(h);self.step();self.assertEqual(self.metric(0),0)
    def test_identity_is_bound_before_init_and_each_app_has_independent_values(self):
        self.assertEqual(self.metric(1),0);self.launch();self.assertTrue(self.lib.test_bound(self.r,b'alpha'));self.assertEqual(self.lib.test_value(self.r),17)
        self.step(1);self.assertEqual(self.lib.test_value(self.r),41);self.exit();self.assertTrue(self.lib.test_scrubbed(self.r))
        self.step(4);self.step();self.launch();self.assertTrue(self.lib.test_bound(self.r,b'beta'));self.assertEqual(self.lib.test_value(self.r),17)
        self.step(2);self.exit();self.step(4);self.step();self.launch();self.assertEqual(self.lib.test_value(self.r),41)
    def test_normal_exit_and_fault_close_vm_before_storage_and_image(self):
        for h in (64,32):
            self.launch();self.step(1);self.exit(h);self.assertEqual(self.metric(5),0);self.assertEqual(self.metric(8),0);self.assertTrue(self.lib.test_scrubbed(self.r))
        self.assertEqual(self.metric(4),2);self.assertEqual(self.metric(6),1)
    def test_partial_open_failure_returns_storage_notice_without_quarantine(self):
        self.lib.test_fault(self.r,1,0,0);self.step(16)
        self.assertEqual((self.metric(0),self.metric(7),self.metric(6),self.metric(4)),(2,3,0,1))
        self.step();self.lib.test_fault(self.r,0,0,0);self.launch()
    def test_failed_close_blocks_new_launch_and_configuration_until_retry(self):
        self.launch();self.lib.test_fault(self.r,0,0,1);self.step(192)
        self.assertEqual((self.metric(0),self.metric(8),self.metric(9),self.metric(4)),(3,1,1,0))
        self.assertFalse(self.lib.test_configure(self.r,0));self.assertFalse(self.lib.test_close(self.r))
        self.lib.test_fault(self.r,0,0,0);self.step();self.step();self.assertEqual((self.metric(0),self.metric(4)),(0,1));self.launch()
    def test_failed_write_keeps_app_running_and_cache_then_reopen_recovers(self):
        self.launch();self.lib.test_fault(self.r,0,1,0);self.step(1)
        self.assertEqual((self.metric(0),self.lib.test_status(self.r),self.lib.test_value(self.r)),(1,-1,17))
        writes=self.metric(2);self.step();self.step(2,1200);self.assertEqual(self.metric(2),writes)
        self.exit();self.lib.test_fault(self.r,0,0,0);self.launch();self.step(2);self.assertEqual(self.lib.test_value(self.r),42)
    def test_trusted_clock_controls_write_rate_and_same_value_is_free(self):
        self.launch();self.step(1);self.step();self.step(2)
        self.assertEqual((self.lib.test_status(self.r),self.lib.test_value(self.r),self.metric(2)),(0,41,1))
        self.step();self.step(2,1000);self.assertEqual((self.lib.test_status(self.r),self.lib.test_value(self.r)),(1,42))
    def test_legacy_app_never_opens_state_and_partial_hooks_are_rejected(self):
        self.assertFalse(self.lib.test_configure(self.r,1));self.new(legacy=True);self.launch();self.exit();self.assertEqual((self.metric(1),self.metric(2),self.metric(3)),(0,0,0))
