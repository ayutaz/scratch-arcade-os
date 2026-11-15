"""設定APIの権限・型・境界・quotaを両VMで検証。Flashへ接続しない。"""
import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wasmtime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.native import build_probe,SOURCE
from labos.sdk import Session,make_manifest
from labos.package import encode,decode
IMPORTS='''(import "os" "state_read" (func $read (param i32 i32) (result i32)))
(import "os" "state_write" (func $write (param i32 i32) (result i32)))
(import "os" "state_status" (func $status (result i32)))'''


def blob(body,init=''):
    return bytes(wasmtime.wat2wasm('(module '+IMPORTS+' (global $v (mut i32) (i32.const 0)) (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init") '+init+') (func (export "tick") (param i32 i32 i32 i32) (result i32) '+body+' global.set $v i32.const 0) (func (export "debug_value") (result i32) global.get $v))'))


class ManifestTests(unittest.TestCase):
    def test_storage_permission_roundtrips_in_canonical_package(self):
        b=blob('i32.const 0');m=make_manifest('state-app',b,capabilities=['draw','speaker','storage'])
        self.assertEqual(decode(encode(m,b)),(m,b))
        for caps in (['storage','draw'],['storage','storage'],['file']):
            with self.assertRaises(ValueError):make_manifest('state-app',b,capabilities=caps)


class Backend:
    def __init__(self,override=0):self.values={};self.calls=[];self.override=override
    def call(self,op,slot,value):
        self.calls.append((op,slot,value))
        if self.override:return self.override,0
        if op==1:return (1,self.values[slot]) if slot in self.values else (0,0)
        self.values[slot]=value;return 1,value


class StateSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);p=Path(cls.tmp.name)/'state-sdk.so';native=ROOT/'prototypes/lab-os/native'
        r=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),'-I'+str(SOURCE/'core/iwasm/include'),str(native/'guest_vm.c'),str(ROOT/'tests/native/lab_state_sdk_bridge.c'),str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),'-lpthread','-lm','-o',str(p)],capture_output=True,text=True,timeout=30)
        if r.returncode:raise RuntimeError(r.stderr)
        cls.lib=C.CDLL(str(p));cls.lib.test_new.restype=C.c_void_p
        for n in ('test_free','test_frame','test_value','test_close','test_calls'):getattr(cls.lib,n).argtypes=[C.c_void_p]
        cls.lib.test_open.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int];cls.lib.test_override.argtypes=[C.c_void_p,C.c_int]
        assert cls.lib.test_start();cls.addClassCleanup(cls.lib.test_stop)
    def setUp(self):self.p=self.lib.test_new();self.addCleanup(self.lib.test_free,self.p)
    def both(self,body,value=None,*,caps=16,backend=True,trap=False,override=0):
        b=blob(body);memory=C.create_string_buffer(b);self.lib.test_override(self.p,override)
        self.assertTrue(self.lib.test_open(self.p,memory,len(b),caps,backend))
        if trap:self.assertEqual(self.lib.test_frame(self.p),-1)
        else:self.assertEqual(self.lib.test_frame(self.p),0);self.assertEqual(self.lib.test_value(self.p),value)
        count=self.lib.test_calls(self.p);self.lib.test_close(self.p)
        names=['draw'] if caps==1 else ['storage'] if caps==16 else ['draw','speaker','storage']
        m=make_manifest('state-app',b,capabilities=names);io=Backend(override)
        s=Session(b,m,state=io if backend else None);self.addCleanup(s.close)
        if trap:
            with self.assertRaises(RuntimeError):s.frame(0,16)
        else:s.frame(0,16);self.assertEqual(s.debug('debug_value'),value)
        self.assertEqual(len(io.calls),count);return s,io
    def test_missing_permission_traps_before_backend(self):
        _,io=self.both('i32.const 0 i32.const 17 call $read',caps=1,trap=True);self.assertEqual(io.calls,[])
    def test_absent_backend_returns_fallback_and_unavailable_status(self):
        self.both('i32.const 0 i32.const 17 call $read',17,backend=False)
        self.both('call $status',-1,backend=False)
    def test_missing_value_returns_fallback_and_status_zero(self):
        self.both('i32.const 0 i32.const 17 call $read',17)
        self.both('i32.const 0 i32.const 17 call $read drop call $status',0)
    def test_write_read_preserves_signed_values_without_memory_pointer(self):
        for n in (-2147483648,-7,2147483647):
            self.both(f'i32.const 7 i32.const {n} call $write drop i32.const 7 i32.const 99 call $read',n)
    def test_invalid_slot_never_reaches_backend(self):
        _,io=self.both('i32.const 8 i32.const 17 call $read',17);self.assertEqual(io.calls,[])
        _,io=self.both('i32.const -1 i32.const 42 call $write',-1);self.assertEqual(io.calls,[])
    def test_per_frame_query_and_write_limits_trap_before_excess_backend_call(self):
        _,io=self.both(' '.join(['i32.const 0 i32.const 17 call $read drop']*8+['i32.const 0 i32.const 17 call $read']),trap=True);self.assertEqual(len(io.calls),8)
        _,io=self.both('i32.const 0 i32.const 7 call $write drop i32.const 1 i32.const 8 call $write',trap=True);self.assertEqual(len(io.calls),1)
    def test_quota_resets_on_next_frame_and_backend_contract_is_checked(self):
        s,io=self.both('i32.const 0 i32.const 7 call $write',1);s.frame(0,32);self.assertEqual(len(io.calls),2)
        self.both('i32.const 0 i32.const 17 call $read',trap=True,override=3)
    def test_storage_can_coexist_with_speaker_permission(self):
        self.both('i32.const 0 i32.const 42 call $write drop call $status',1,caps=19)
