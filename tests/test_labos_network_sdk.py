import ctypes as C
import os
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
from labos.build import COMPILER,SDK

IMPORTS='''(import "os" "network_send" (func $send (param i32 i32) (result i32)))
 (import "os" "network_receive" (func $receive (param i32 i32) (result i32)))
 (import "os" "network_state" (func $state (result i32)))'''
def wasm(body,*,memory=True,export_memory=True,init='',shutdown=''):
    mem=('(memory %s 1 2) (data (i32.const 16) "\\00\\ffABC") (data (i32.const 64) "ZZZZ")'%
         ('(export "memory")' if export_memory else '')) if memory else ''
    x='i32.const 64 i32.load' if memory else 'i32.const 0'
    return bytes(wasmtime.wat2wasm(f'''(module {IMPORTS} {mem}
     (global $v (mut i32) (i32.const 0))
     (func (export "sdk_abi") (result i32) i32.const 2)
     (func (export "init") {init})
     (func (export "tick") (param i32 i32 i32 i32) (result i32) {body} global.set $v i32.const 0)
     (func (export "debug_value") (result i32) global.get $v)
     (func (export "debug_x") (result i32) {x})
     (func (export "shutdown") (param i32) {shutdown}))'''))

def build_header_app(folder):
    source=folder/'network.c';target=folder/'network.wasm'
    source.write_text('#include "lab_os.h"\nstatic unsigned char rx[64],tx[]={0,255,42};\nstatic int value;\nuint32_t sdk_abi(void){return LAB_ABI;}\nvoid init(void){}\nint32_t tick(uint32_t h,uint32_t p,uint32_t r,uint32_t dt){(void)h;(void)r;(void)dt;if(p&START)value=network_send(tx,3);else if(p&RESET)value=network_receive(rx,64);else value=network_state();return 0;}\nint32_t debug_value(void){return value;}\n')
    cmd=[str(COMPILER),'cc','-target','wasm32-freestanding','-std=c99','-Oz','-nostdlib','-Werror',
         '-I'+str(SDK),'-Wl,--no-entry','-Wl,--strip-all','-Wl,--initial-memory=131072','-Wl,--max-memory=131072',
         '-Wl,-z,stack-size=16384',*[f'-Wl,--export={n}' for n in ('sdk_abi','init','tick','debug_value')],str(source),'-o',str(target)]
    env={**os.environ,'ZIG_GLOBAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig'),'ZIG_LOCAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig-local')}
    return subprocess.run(cmd,capture_output=True,text=True,timeout=60,env=env),target

class NetworkHeaderTests(unittest.TestCase):
    def test_c_header_declares_all_three_network_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,path=build_header_app(Path(tmp));self.assertEqual(result.returncode,0,result.stderr)
            module=wasmtime.Module(wasmtime.Engine(),path.read_bytes())
            self.assertEqual({i.name for i in module.imports},{'network_send','network_receive','network_state'})

class NetworkSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        native=ROOT/'prototypes/lab-os/native';out=Path(cls.tmp.name)/'net.dylib'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),
             '-I'+str(SOURCE/'core/iwasm/include'),str(native/'guest_vm.c'),str(native/'udp_service.c'),str(native/'network_binding.c'),
             str(ROOT/'tests/native/lab_network_sdk_bridge.c'),str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),
             '-lpthread','-lm','-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.restype=C.c_void_p
        for name in ('test_free','test_frame','test_calls','test_restart','test_release','test_other','test_clean','test_vm_close','test_duplicate_binding'):
            getattr(cls.lib,name).argtypes=[C.c_void_p]
        cls.lib.test_open.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int]
        cls.lib.test_command.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
        cls.lib.test_debug.argtypes=[C.c_void_p,C.c_char_p]
        cls.lib.test_poll.argtypes=[C.c_void_p,C.c_uint]
        cls.lib.test_sent.argtypes=[C.c_void_p,C.c_void_p]
        cls.lib.test_inject.argtypes=[C.c_void_p,C.c_void_p,C.c_uint]
        cls.lib.test_force.argtypes=cls.lib.test_fail_close.argtypes=[C.c_void_p,C.c_int]
        assert cls.lib.test_runtime_start();cls.addClassCleanup(cls.lib.test_runtime_stop)
    def setUp(self):
        self.probe=self.lib.test_new();self.assertTrue(self.probe);self.addCleanup(self.lib.test_free,self.probe)
    def native(self,blob,caps=8,backend=True):
        self.buffer=C.create_string_buffer(blob)
        self.assertTrue(self.lib.test_open(self.probe,self.buffer,len(blob),caps,backend))
    def host(self,blob,caps=8,backend=True):
        lib,p=self.lib,self.probe
        class Backend:
            def call(self,op,data,n):
                raw=(C.c_uint8*n).from_buffer(data) if data is not None else None
                return lib.test_command(p,op,raw,n)
        manifest=make_manifest('network-test',blob,capabilities=['network'] if caps==8 else ['draw'])
        session=Session(blob,manifest,network=Backend() if backend else None);self.addCleanup(session.close)
        return session
    def each(self,blob,check,*,caps=8,backend=True,prepare=None):
        self.assertTrue(self.lib.test_restart(self.probe))
        self.native(blob,caps,backend)
        if prepare:prepare()
        check(False,None)
        self.lib.test_vm_close(self.probe);self.assertTrue(self.lib.test_restart(self.probe))
        session=self.host(blob,caps,backend)
        if prepare:prepare()
        try:check(True,session)
        finally:session.close()
    def step(self,host,session):return session.frame(0,16) if host else self.lib.test_frame(self.probe)
    def value(self,host,session,name='debug_value'):return session.debug(name) if host else self.lib.test_debug(self.probe,name.encode())
    def expect(self,body,value,*,trap=False,caps=8,backend=True,**options):
        def check(host,session):
            if trap:
                if host:
                    with self.assertRaises(RuntimeError):self.step(host,session)
                else:self.assertEqual(self.step(host,session),-1)
            else:
                self.assertFalse(self.step(host,session));self.assertEqual(self.value(host,session),value)
        self.each(wasm(body,**options),check,caps=caps,backend=backend)
    def test_permission_traps_before_any_backend_call(self):
        self.expect('i32.const 16 i32.const 5 call $send',None,caps=1,trap=True)
        self.assertEqual(self.lib.test_calls(self.probe),0)
    def test_missing_backend_is_unavailable_without_trap(self):
        self.expect('i32.const 16 i32.const 5 call $send',-1,backend=False)
    def test_binary_send_uses_common_service_and_copy_before_guest_mutation(self):
        def check(host,session):
            self.assertFalse(self.step(host,session));self.assertEqual(self.value(host,session),1)
            self.assertTrue(self.lib.test_poll(self.probe,16));out=C.create_string_buffer(64)
            self.assertEqual(self.lib.test_sent(self.probe,out),5);self.assertEqual(out.raw[:5],b'\0\xffABC')
        self.each(wasm('i32.const 16 i32.const 5 call $send i32.const 16 i32.const 0 i32.store8'),check)
    def test_receive_writes_exact_span_and_preserves_unwritten_guest_tail(self):
        def prepare():self.lib.test_inject(self.probe,b'\xff\x80\x01',3);self.assertTrue(self.lib.test_poll(self.probe,0))
        def check(host,session):
            self.assertFalse(self.step(host,session));self.assertEqual(self.value(host,session),3)
            self.assertEqual(self.value(host,session,'debug_x'),0x5a0180ff)
        self.each(wasm('i32.const 64 i32.const 64 call $receive'),check,prepare=prepare)
    def test_short_receive_buffer_keeps_packet_for_later_full_read(self):
        def prepare():self.lib.test_inject(self.probe,b'\xff\x80\x01',3);self.lib.test_poll(self.probe,0)
        def check(host,session):
            self.assertFalse(self.step(host,session));self.assertEqual(self.value(host,session),3)
            self.assertEqual(self.value(host,session,'debug_x'),0x5a0180ff)
        self.each(wasm('i32.const 64 i32.const 2 call $receive drop i32.const 64 i32.const 64 call $receive'),check,prepare=prepare)
    def test_invalid_lengths_do_not_call_backend(self):
        self.expect('i32.const 16 i32.const 65 call $send',-1)
        self.assertEqual(self.lib.test_calls(self.probe),0)
    def test_oob_and_unsigned_offset_wrap_trap_before_backend(self):
        for address in (65535,-1):
            with self.subTest(address=address):
                self.expect(f'i32.const {address} i32.const 2 call $send',None,trap=True)
                self.assertEqual(self.lib.test_calls(self.probe),0)
    def test_data_api_requires_exported_memory_and_state_does_not(self):
        self.expect('i32.const 16 i32.const 2 call $send',None,trap=True,export_memory=False)
        self.expect('call $state',1,memory=False)
    def test_per_frame_mutation_and_query_quotas_trap(self):
        self.expect(' '.join(['call $state drop']*8+['call $state']),None,trap=True)
        self.expect(' '.join(['i32.const 16 i32.const 2 call $send drop']*2+['i32.const 16 i32.const 2 call $send']),None,trap=True)
    def test_backend_mutation_cannot_change_the_send_source_in_guest_memory(self):
        def prepare():self.lib.test_force(self.probe,1)
        def check(host,session):
            self.assertFalse(self.step(host,session));self.assertEqual(self.value(host,session,'debug_x'),0x5a5a5a5a)
        self.each(wasm('i32.const 64 i32.const 4 call $send'),check,prepare=prepare)
    def test_out_of_contract_backend_result_traps(self):
        def prepare():self.lib.test_force(self.probe,65)
        def check(host,session):
            if host:
                with self.assertRaises(RuntimeError):self.step(host,session)
            else:self.assertEqual(self.step(host,session),-1)
        self.each(wasm('i32.const 64 i32.const 64 call $receive'),check,prepare=prepare)
    def test_python_backend_cannot_resize_the_fixed_receive_span(self):
        class Backend:
            def call(self,op,data,n):data.clear();return 1
        blob=wasm('i32.const 64 i32.const 64 call $receive')
        session=Session(blob,make_manifest('network-test',blob,capabilities=['network']),network=Backend())
        self.addCleanup(session.close)
        with self.assertRaises(RuntimeError):session.frame(0,16)
    def test_cleanup_failure_retains_lease_and_scrubs_before_another_owner(self):
        packet=C.create_string_buffer(b'private');self.assertEqual(self.lib.test_command(self.probe,1,packet,7),1)
        self.lib.test_vm_close(self.probe);self.lib.test_fail_close(self.probe,1)
        self.assertFalse(self.lib.test_release(self.probe));self.assertTrue(self.lib.test_clean(self.probe))
        self.assertFalse(self.lib.test_other(self.probe));self.lib.test_fail_close(self.probe,0)
        self.assertTrue(self.lib.test_release(self.probe));self.assertTrue(self.lib.test_other(self.probe))
    def test_duplicate_binding_with_same_numeric_owner_cannot_capture_an_existing_lease(self):
        self.assertTrue(self.lib.test_duplicate_binding(self.probe))
    def test_c_header_module_runs_in_both_vms(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,path=build_header_app(Path(tmp));self.assertEqual(result.returncode,0,result.stderr)
            self.each(path.read_bytes(),lambda host,session:(self.assertFalse(self.step(host,session)),self.assertEqual(self.value(host,session),1)))
