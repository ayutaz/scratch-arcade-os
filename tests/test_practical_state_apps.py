"""ゲーム最高得点/タイマー設定を、同じWASMの両VMで検証する。"""
import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.native import build_probe,SOURCE
from labos.project import build_project
from labos.package import decode
from labos.sdk import Session


class State:
    def __init__(self,seed=None):self.values={} if seed is None else {0:seed};self.calls=[];self.result=1
    def call(self,op,slot,value):
        if op==1:return (1,self.values[slot]) if slot in self.values else (0,0)
        self.calls.append((slot,value))
        if self.result==1:self.values[slot]=value
        return self.result,value


class PracticalStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'apps.so';native=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),'-I'+str(SOURCE/'core/iwasm/include'),str(native/'guest_vm.c'),str(ROOT/'tests/native/lab_state_sdk_bridge.c'),str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),'-lpthread','-lm','-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.restype=C.c_void_p
        for n in ('test_free','test_close','test_value','test_calls'):getattr(cls.lib,n).argtypes=[C.c_void_p]
        cls.lib.test_seed.argtypes=[C.c_void_p,C.c_int];cls.lib.test_result.argtypes=[C.c_void_p,C.c_int]
        cls.lib.test_reopen.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int]
        cls.lib.test_frame_input.argtypes=[C.c_void_p,C.c_uint,C.c_uint];cls.lib.test_debug_name.argtypes=[C.c_void_p,C.c_char_p]
        cls.lib.test_draw.argtypes=[C.c_void_p,C.c_uint,C.c_uint];cls.lib.test_draw_count.argtypes=[C.c_void_p]
        cls.apps={name:decode(Path(build_project(ROOT/'apps'/name)['package']).read_bytes()) for name in ('lane-catcher','focus-timer')}
        assert cls.lib.test_start();cls.addClassCleanup(cls.lib.test_stop)
    def pair(self,name,seed=None):
        if hasattr(self,'session'):
            self.session.close();self.lib.test_close(self.native)
        m,b=self.apps[name];self.native=self.lib.test_new();self.addCleanup(self.lib.test_free,self.native)
        if seed is not None:self.lib.test_seed(self.native,seed)
        self.buffer=C.create_string_buffer(b);self.assertTrue(self.lib.test_reopen(self.native,self.buffer,len(b),19,1))
        self.state=State(seed);self.session=Session(b,m,state=self.state);self.addCleanup(self.session.close);self.now=0;self.name=name
    def frame(self,key=0,dt=16):
        self.now+=dt;native=self.lib.test_frame_input(self.native,key,dt);done=self.session.frame(key,self.now)
        self.assertEqual(native,1 if done else 0)
        if not done:
            for n in ('debug_value','debug_x','debug_y','debug_elapsed'):
                self.assertEqual(self.lib.test_debug_name(self.native,n.encode()),self.session.debug(n),n)
            rects=[[self.lib.test_draw(self.native,i,j) for j in range(5)] for i in range(self.lib.test_draw_count(self.native))]
            self.assertEqual(rects,[list(r) for r in self.session.commands]);self.assertLessEqual(len(rects),128)
        return done
    def result(self,value):self.state.result=value;self.lib.test_result(self.native,value)
    def reopen(self):
        self.session.close();self.lib.test_close(self.native);m,b=self.apps[self.name];self.buffer=C.create_string_buffer(b)
        self.assertTrue(self.lib.test_reopen(self.native,self.buffer,len(b),19,1));self.session=Session(b,m,state=self.state);self.addCleanup(self.session.close);self.now=0
    def test_packages_require_new_storage_firmware_and_keep_original_ids(self):
        for name,(m,b) in self.apps.items():
            self.assertEqual((m['id'],m['version'],m['capabilities']),(name,'1.2.0',['draw','speaker','storage']))
    def test_game_saves_improved_best_once_and_loads_it_after_vm_restart(self):
        self.pair('lane-catcher');self.frame(16,0);self.frame(0,5000)
        self.assertEqual(self.session.debug('debug_value'),2);self.assertEqual(self.state.calls,[(0,2)]);self.assertEqual(self.state.values,{0:2})
        self.frame(0,100);self.assertEqual(len(self.state.calls),1);self.frame(32,0);self.frame(0,0);title=self.session.commands.copy()
        self.reopen();self.frame(0,0);self.assertEqual(self.session.commands,title)
        self.frame(16,0);self.frame(0,5000);self.assertEqual(len(self.state.calls),1)
    def test_game_does_not_overwrite_higher_best_and_invalid_data_uses_safe_default(self):
        for seed in (15,-1,2147483647):
            self.pair('lane-catcher',seed);self.frame(16,0);self.frame(0,5000)
            self.assertEqual(self.state.calls,[] if seed==15 else [(0,2)])
    def test_timer_commits_only_on_start_and_reloads_valid_setting(self):
        self.pair('focus-timer',70);self.frame();self.assertEqual(self.session.debug('debug_x'),70)
        self.frame(8);self.frame();self.assertEqual(self.state.calls,[]);self.frame(16)
        self.assertEqual(self.state.calls,[(0,80)]);self.assertEqual(self.state.values,{0:80})
        self.frame();self.frame(16);self.frame();self.frame(16);self.assertEqual(len(self.state.calls),1)
        self.reopen();self.assertEqual(self.session.debug('debug_x'),80);self.frame()
    def test_timer_rejects_out_of_range_and_non_step_saved_settings(self):
        for seed in (-1,0,11,301,2147483647):
            self.pair('focus-timer',seed);self.assertEqual(self.session.debug('debug_x'),60);self.frame()
    def test_busy_retries_are_bounded_and_failure_does_not_block_play_or_exit(self):
        for name in self.apps:
            self.pair(name);self.result(0);self.frame(16,0);self.frame(0,5000 if name=='lane-catcher' else 0)
            self.assertGreater(len(self.state.calls),0);self.frame(0,500);self.frame(0,501);n=len(self.state.calls);self.frame(0,10000);self.assertEqual(len(self.state.calls),n)
            self.assertTrue(self.frame(64));self.assertEqual(len(self.state.calls),n)
            self.pair(name);self.result(-1);self.frame(16,0);self.frame(0,5000 if name=='lane-catcher' else 0);n=len(self.state.calls);self.frame(0,16);self.assertEqual(len(self.state.calls),n);self.assertTrue(self.frame(64))
