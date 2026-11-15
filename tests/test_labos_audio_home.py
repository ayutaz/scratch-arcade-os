import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
import wasmtime
import test_labos_c_store as contract
from labos.native import build_probe,SOURCE
from labos.build import build
from labos.sdk import make_manifest
from labos.package import encode
from labos.ui_assets import generate
ROOT=contract.ROOT

def audio_package(name,caps,body,imports=''):
    blob=bytes(wasmtime.wat2wasm(f'''(module {imports}
      (global $v (mut i32) (i32.const 0))
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "debug_value") (result i32) global.get $v)
      (func (export "tick") (param $h i32) (param $p i32) (param i32 i32) (result i32)
        local.get $p i32.const 64 i32.and if i32.const 1 return end {body} i32.const 0))'''))
    return encode(make_manifest(name,blob,capabilities=caps),blob)
SPEAKER=audio_package('a-speaker',['speaker'],
    'local.get $p i32.const 1 i32.and if i32.const 1000 i32.const 32 call $tone global.set $v end',
    '(import "os" "audio_tone" (func $tone (param i32 i32) (result i32)))')
RECORDER=audio_package('b-recorder',['speaker','microphone'],
    '''local.get $p i32.const 16 i32.and if i32.const 32 call $rec global.set $v end
       local.get $p i32.const 1 i32.and if call $level global.set $v end
       local.get $p i32.const 32 i32.and if call $play global.set $v end''',
    '''(import "os" "audio_record" (func $rec (param i32) (result i32)))
       (import "os" "audio_level" (func $level (result i32)))
       (import "os" "audio_play" (func $play (result i32)))''')
class AudioHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);folder=Path(cls.tmp.name)
        generate(folder);native=ROOT/'prototypes/lab-os/native';out=folder/'home.so'
        sources=[native/(n+'.c') for n in ('guest_vm','app_home','app_store','run_loop','ui','audio_service','audio_binding')]
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),
            '-I'+str(SOURCE/'core/iwasm/include'),'-I'+str(folder),'-I'+str(ROOT/'assets/fonts'),
            *map(str,sources),str(ROOT/'tests/native/lab_audio_home_bridge.c'),str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),
            '-lpthread','-lm','-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.argtypes=[C.POINTER(contract.Storage)];cls.lib.test_new.restype=C.c_void_p
        for name in ('test_free','test_start','test_mode','test_value','test_loop_close','test_clean'):getattr(cls.lib,name).argtypes=[C.c_void_p]
        cls.lib.test_install.argtypes=[C.c_void_p,C.c_void_p,C.c_uint];cls.lib.test_step.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        cls.lib.test_metric.argtypes=[C.c_void_p,C.c_uint];cls.lib.test_fault.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
        cls.lib.test_configure.argtypes=[C.c_void_p,C.c_int]
        cls.lib.test_audio_block.argtypes=[C.c_void_p,C.c_int]
        cls.lib.test_verify.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
        assert cls.lib.test_runtime_start();cls.addClassCleanup(cls.lib.test_runtime_stop)
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.disk=contract.DiskFixture(tmp.name,self.lib)
        (Path(tmp.name)/'owner').write_bytes(b'lab-os-c-store-v1\n');self.rig=self.lib.test_new(C.byref(self.disk.io))
        self.assertTrue(self.rig);self.addCleanup(self.lib.test_free,self.rig)
    def metric(self,n):return self.lib.test_metric(self.rig,n)
    def step(self,held=0,dt=16):self.assertEqual(self.lib.test_step(self.rig,held,dt),0)
    def install(self,p):self.assertTrue(self.lib.test_install(self.rig,p,len(p)))
    def start(self):self.assertTrue(self.lib.test_start(self.rig));self.step()
    def launch(self):self.step(16);self.assertEqual(self.lib.test_mode(self.rig),1);self.step()
    def exit(self):self.step(192);self.step();self.assertEqual(self.lib.test_mode(self.rig),0)
    def test_two_catalog_apps_use_audio_and_exit_without_rebuilding_os(self):
        self.install(SPEAKER);self.install(RECORDER);self.start();self.launch();self.step(1)
        self.assertEqual((self.lib.test_value(self.rig),self.metric(5)),(1,1))
        self.assertEqual(self.metric(0),1);self.exit();self.assertEqual(self.metric(4),0)
        self.step(4);self.step();self.launch();self.step(16)
        self.assertEqual((self.lib.test_value(self.rig),self.metric(5)),(1,3))
        self.step();self.step(1);self.assertEqual(self.lib.test_value(self.rig),3000)
        self.step();self.step(32);self.assertEqual(self.lib.test_value(self.rig),1)
        self.exit();self.assertTrue(self.lib.test_clean(self.rig));self.assertEqual(self.metric(2),0)
    def test_cleanup_wait_keeps_image_lease_and_blocks_next_launch_until_released(self):
        self.install(SPEAKER);self.install(RECORDER);self.start();self.launch();self.step(1)
        self.lib.test_fault(self.rig,1,0,0);self.step(192)
        self.assertEqual(self.lib.test_mode(self.rig),3);self.assertEqual((self.metric(2),self.metric(3)),(1,0))
        for held in (0,16,4,16):self.step(held);self.assertEqual(self.lib.test_mode(self.rig),3)
        self.assertEqual(self.metric(0),1);self.assertFalse(self.lib.test_install(self.rig,SPEAKER,len(SPEAKER)))
        self.lib.test_fault(self.rig,0,0,0);self.step();self.assertEqual(self.lib.test_mode(self.rig),2)
        self.step();self.assertEqual(self.lib.test_mode(self.rig),0);self.assertEqual(self.metric(2),0)
        self.launch()
    def test_host_close_propagates_pending_audio_cleanup_instead_of_abandoning_owner(self):
        self.install(SPEAKER);self.start();self.launch();self.step(1);self.lib.test_fault(self.rig,1,0,0)
        self.assertFalse(self.lib.test_loop_close(self.rig));self.assertEqual((self.metric(2),self.metric(7)),(1,0))
        self.lib.test_fault(self.rig,0,0,0);self.assertTrue(self.lib.test_loop_close(self.rig))
        self.assertEqual((self.metric(2),self.metric(4)),(0,0))
    def test_guest_trap_defers_quarantine_until_audio_and_image_are_released(self):
        broken=audio_package('a-speaker',['speaker'],
            'local.get $p i32.const 1 i32.and if i32.const 1000 i32.const 32 call $tone drop unreachable end',
            '(import "os" "audio_tone" (func $tone (param i32 i32) (result i32)))')
        self.install(broken);self.install(RECORDER);self.start();self.launch();self.lib.test_fault(self.rig,1,0,0);self.step(1)
        self.assertEqual((self.lib.test_mode(self.rig),self.metric(6),self.metric(2)),(3,2,1))
        self.lib.test_fault(self.rig,0,0,0);self.step();self.step()
        self.assertEqual((self.lib.test_mode(self.rig),self.metric(6),self.metric(2)),(0,1,0));self.launch()
    def test_service_configuration_cannot_change_while_guest_owns_audio(self):
        self.install(SPEAKER);self.start();self.assertFalse(self.lib.test_configure(self.rig,1))
        self.launch();self.assertFalse(self.lib.test_configure(self.rig,0));self.exit()
        self.assertTrue(self.lib.test_configure(self.rig,0))
    def test_legacy_draw_app_never_claims_audio_or_changes_existing_capabilities(self):
        self.install(contract.package());self.start();self.launch()
        self.assertEqual((self.metric(0),self.metric(4),self.metric(10)),(0,0,0));self.exit()

    def test_actual_c_speaker_and_microphone_apps_install_use_shared_services_and_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            speaker,spk=build('speaker',Path(tmp));mic,pcm=build('microphone',Path(tmp))
            self.assertEqual(speaker['capabilities'],['draw','speaker'])
            self.assertEqual(mic['capabilities'],['draw','speaker','microphone'])
            self.install(encode(speaker,spk));self.install(encode(mic,pcm));self.start()
            self.step(4);self.step();self.launch();self.step(16)
            self.assertEqual((self.lib.test_value(self.rig),self.metric(0)),(1,1));self.exit()
            self.step(4);self.step();self.launch();self.step(16)
            self.assertEqual(self.lib.test_value(self.rig),1)
            for _ in range(40):self.step()
            self.step(32);self.assertEqual(self.lib.test_value(self.rig),1)
            for _ in range(40):self.step()
            self.assertEqual(self.metric(0),3);self.exit()
            self.assertTrue(self.lib.test_clean(self.rig));self.assertEqual(self.metric(4),0)

    def test_audio_unavailable_is_retriable_without_storage_error_or_quarantine(self):
        self.install(SPEAKER);self.start();self.assertTrue(self.lib.test_audio_block(self.rig,1))
        self.step(16);self.assertEqual((self.lib.test_mode(self.rig),self.metric(9),self.metric(6)),(2,self.lib.test_notice_audio(),1))
        self.assertEqual((self.metric(2),self.metric(0)),(0,0));self.step()
        self.assertTrue(self.lib.test_audio_block(self.rig,0));self.launch()

    def test_custom_audio_desk_records_replays_and_releases_through_real_home(self):
        from labos.project import build_project
        result=build_project(ROOT/'apps/audio-desk')
        self.install(Path(result['package']).read_bytes());self.start();self.launch()
        self.step(16);self.assertEqual(self.lib.test_value(self.rig),1)
        for _ in range(40):self.step()
        self.step(1);self.step();self.step(16)
        self.assertEqual(self.lib.test_value(self.rig),1)
        for _ in range(40):self.step()
        self.step(1);self.step();self.step(16)
        self.assertEqual(self.lib.test_value(self.rig),1)
        for _ in range(40):self.step()
        self.assertEqual(self.metric(0),3)
        self.exit();self.assertTrue(self.lib.test_clean(self.rig))
        self.assertEqual((self.metric(2),self.metric(3),self.metric(4)),(0,0,0))
