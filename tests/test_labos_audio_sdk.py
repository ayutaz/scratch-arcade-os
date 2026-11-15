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
from labos.build import COMPILER,SDK
from labos.sdk import Session,make_manifest,validate
from labos.package import encode,decode

CAPS={1:['draw'],2:['speaker'],4:['microphone'],6:['speaker','microphone'],7:['draw','speaker','microphone']}
def wasm(body,imports):
    return bytes(wasmtime.wat2wasm('''(module %s
      (global $v (mut i32) (i32.const 0))
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "debug_value") (result i32) global.get $v)
      (func (export "tick") (param i32 i32 i32 i32) (result i32) %s global.set $v i32.const 0))'''%(imports,body)))
IMPORTS={
 'tone':'(import "os" "audio_tone" (func $f (param i32 i32) (result i32)))',
 'record':'(import "os" "audio_record" (func $f (param i32) (result i32)))',
 'play':'(import "os" "audio_play" (func $f (result i32)))',
 'state':'(import "os" "audio_state" (func $f (result i32)))',
 'level':'(import "os" "audio_level" (func $f (result i32)))',
 'stop':'(import "os" "audio_stop" (func $f (result i32)))',
 'position':'(import "os" "audio_position" (func $f (result i32)))',
 'gain':'(import "os" "audio_set_gain" (func $f (param i32) (result i32)))',
}
class AudioSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'sdk.so'
        native=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(native),
            '-I'+str(SOURCE/'core/iwasm/include'),str(native/'guest_vm.c'),str(native/'audio_service.c'),
            str(native/'audio_binding.c'),str(ROOT/'tests/native/lab_audio_sdk_bridge.c'),
            str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),'-lpthread','-lm','-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.restype=C.c_void_p
        for name in ('test_free','test_frame','test_value','test_opens','test_release','test_claim_other','test_clean','test_vm_close','test_rebind','test_gain_value','test_gain_calls'):
            getattr(cls.lib,name).argtypes=[C.c_void_p]
        cls.lib.test_open.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int]
        cls.lib.test_command.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint]
        cls.lib.test_poll.argtypes=[C.c_void_p,C.c_uint];cls.lib.test_fail_close.argtypes=[C.c_void_p,C.c_int]
        assert cls.lib.test_runtime_start();cls.addClassCleanup(cls.lib.test_runtime_stop)
    def setUp(self):
        self.probe=self.lib.test_new();self.assertTrue(self.probe);self.addCleanup(self.lib.test_free,self.probe)
    def native(self,blob,caps,backend=True):
        self.buffer=C.create_string_buffer(blob)
        self.assertTrue(self.lib.test_open(self.probe,self.buffer,len(blob),caps,backend))
    def host(self,blob,caps,backend=True):
        lib=self.lib;p=self.probe
        class Backend:
            def call(self,op,a,b):return lib.test_command(p,op,a,b)
        manifest=make_manifest('audio-test',blob,capabilities=CAPS[caps])
        session=Session(blob,manifest,audio=Backend() if backend else None);self.addCleanup(session.close)
        return session
    def check_both(self,op,body,caps,expected,backend=True,trap=False):
        blob=wasm(body,IMPORTS[op]);self.native(blob,caps,backend)
        if trap:self.assertEqual(self.lib.test_frame(self.probe),-1)
        else:self.assertEqual(self.lib.test_frame(self.probe),0);self.assertEqual(self.lib.test_value(self.probe),expected)
        self.lib.test_vm_close(self.probe)
        session=self.host(blob,caps,backend)
        if trap:
            with self.assertRaises(RuntimeError):session.frame(0,16)
        else:session.frame(0,16);self.assertEqual(session.debug('debug_value'),expected)
        session.close()
    def test_missing_permission_traps_before_any_backend_io_in_both_vms(self):
        self.check_both('tone','i32.const 1000 i32.const 20 call $f',1,None,trap=True)
        self.assertEqual(self.lib.test_opens(self.probe),0)
    def test_microphone_permission_is_independent_from_speaker(self):
        self.check_both('record','i32.const 20 call $f',2,None,trap=True)
        self.assertEqual(self.lib.test_opens(self.probe),0)
    def test_allowed_api_without_backend_returns_unavailable_without_trap(self):
        self.check_both('tone','i32.const 1000 i32.const 20 call $f',2,-1,backend=False)
        self.assertEqual(self.lib.test_opens(self.probe),0)
    def test_bounded_tone_calls_common_c_service_through_wamr_and_wasmtime(self):
        blob=wasm('i32.const 1000 i32.const 20 call $f',IMPORTS['tone']);self.native(blob,2)
        self.assertEqual(self.lib.test_frame(self.probe),0);self.assertEqual(self.lib.test_value(self.probe),1)
        for now in (16,32):self.assertEqual(self.lib.test_poll(self.probe,now),0)
        self.assertEqual(self.lib.test_poll(self.probe,48),1);self.lib.test_vm_close(self.probe)
        session=self.host(blob,2);session.frame(0,16);self.assertEqual(session.debug('debug_value'),1)
        self.assertEqual(self.lib.test_opens(self.probe),2)
    def test_invalid_tone_parameters_never_reach_backend(self):
        self.check_both('tone','i32.const -1 i32.const 20 call $f',2,-1)
        self.assertEqual(self.lib.test_opens(self.probe),0)
    def test_per_frame_query_quota_traps_in_both_vms(self):
        self.check_both('state',' '.join(['call $f drop']*8+['call $f']),6,None,trap=True)
    def test_per_frame_mutation_quota_traps_even_for_valid_requests(self):
        self.check_both('stop','call $f drop call $f drop call $f',6,None,trap=True)
    def test_level_reads_peak_without_exporting_pcm_and_handles_negative_full_scale(self):
        self.assertEqual(self.lib.test_command(self.probe,2,20,0),1)
        self.assertEqual(self.lib.test_poll(self.probe,16),0)
        self.check_both('level','call $f',4,32768)
    def test_cleanup_failure_keeps_lease_and_scrubs_before_other_app_can_claim(self):
        self.assertEqual(self.lib.test_command(self.probe,2,20,0),1);self.lib.test_poll(self.probe,16)
        self.lib.test_vm_close(self.probe);self.lib.test_fail_close(self.probe,1)
        self.assertFalse(self.lib.test_release(self.probe));self.assertTrue(self.lib.test_clean(self.probe))
        self.assertFalse(self.lib.test_claim_other(self.probe));self.lib.test_fail_close(self.probe,0)
        self.assertTrue(self.lib.test_release(self.probe));self.assertTrue(self.lib.test_claim_other(self.probe))
    def test_manifest_capabilities_are_canonical_and_package_preserves_audio(self):
        blob=wasm('i32.const 0','');manifest=make_manifest('audio-test',blob,capabilities=['draw','speaker','microphone'])
        validate(manifest,blob)
        for caps in (['speaker','draw'],['speaker','speaker'],['unknown'],True):
            with self.assertRaises(ValueError):validate({**manifest,'capabilities':caps},blob)
        self.assertEqual(decode(encode(manifest,blob)),(manifest,blob))

    def test_c_sdk_header_builds_all_audio_imports_and_runs_on_both_vms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);source=path/'audio.c';target=path/'audio.wasm'
            source.write_text('#include "lab_os.h"\nstatic int32_t value;\nuint32_t sdk_abi(void){return LAB_ABI;}\nvoid init(void){value=0;}\nint32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){\n(void)held;(void)released;(void)dt;\nif(pressed&START)value=audio_tone(1000,20);\nelse if(pressed&RESET)value=audio_record(20);\nelse if(pressed&BACK)value=audio_play();\nelse if(pressed&RIGHT)value=audio_level();\nelse if(pressed&LEFT)value=audio_stop();\nelse if(pressed&UP)value=audio_set_gain(4);\nelse value=audio_state();return 0;\n}\nint32_t debug_value(void){return value;}\n')
            cmd=[str(COMPILER),'cc','-target','wasm32-freestanding','-std=c99','-Oz','-nostdlib','-Werror',
                '-I'+str(SDK),'-Wl,--no-entry','-Wl,--strip-all','-Wl,--initial-memory=131072','-Wl,--max-memory=131072',
                '-Wl,-z,stack-size=16384',*[f'-Wl,--export={n}' for n in ('sdk_abi','init','tick','debug_value')],str(source),'-o',str(target)]
            env={**os.environ,'ZIG_GLOBAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig'),'ZIG_LOCAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig-local')}
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=60,env=env);self.assertEqual(p.returncode,0,p.stderr)
            blob=target.read_bytes();self.native(blob,6);self.assertEqual(self.lib.test_frame(self.probe),0)
            self.assertEqual(self.lib.test_value(self.probe),0);self.lib.test_vm_close(self.probe)
            session=self.host(blob,6);session.frame(0,16);self.assertEqual(session.debug('debug_value'),0)

    def check_failed_audio_shutdown(self,failed_init):
        blob=bytes(wasmtime.wat2wasm('(module\n          (import "os" "audio_tone" (func $tone (param i32 i32) (result i32)))\n          (func (export "sdk_abi") (result i32) i32.const 2)\n          (func (export "init") %s)\n          (func (export "tick") (param i32 i32 i32 i32) (result i32) %s i32.const 0)\n          (func (export "shutdown") (param i32) i32.const 1000 i32.const 20 call $tone drop))'%('unreachable' if failed_init else '', '' if failed_init else 'unreachable')))
        self.buffer=C.create_string_buffer(blob)
        opened=self.lib.test_open(self.probe,self.buffer,len(blob),2,1)
        if failed_init:self.assertFalse(opened)
        else:self.assertTrue(opened);self.assertEqual(self.lib.test_frame(self.probe),-1)
        self.assertEqual(self.lib.test_opens(self.probe),0)
        manifest=make_manifest('audio-test',blob,capabilities=['speaker']);lib=self.lib;p=self.probe
        class Backend:
            def call(self,op,a,b):return lib.test_command(p,op,a,b)
        if failed_init:
            with self.assertRaises(RuntimeError):Session(blob,manifest,audio=Backend())
        else:
            session=Session(blob,manifest,audio=Backend());self.addCleanup(session.close)
            with self.assertRaises(RuntimeError):session.frame(0,16)
        self.assertEqual(self.lib.test_opens(self.probe),0)
    def test_failed_init_skips_guest_shutdown_and_never_starts_audio(self):
        self.check_failed_audio_shutdown(True)
    def test_trapped_tick_skips_guest_shutdown_and_never_starts_audio(self):
        self.check_failed_audio_shutdown(False)

    def test_position_requires_audio_permission_and_no_backend_is_unavailable(self):
        self.check_both('position','call $f',1,None,trap=True)
        self.check_both('position','call $f',2,-1,backend=False)
        self.assertEqual(self.lib.test_opens(self.probe),0)

    def test_position_reports_actual_captured_frames_through_both_vms(self):
        self.assertEqual(self.lib.test_command(self.probe,2,500,0),1)
        self.lib.test_poll(self.probe,16);self.lib.test_poll(self.probe,32)
        self.check_both('position','call $f',6,512)

    def test_position_counts_as_query_and_shares_existing_eight_call_limit(self):
        self.check_both('position','call $f drop call $f drop call $f',2,0)
        self.check_both('position',' '.join(['call $f drop']*8+['call $f']),6,None,trap=True)

    def test_position_is_zero_after_stop_and_unavailable_after_lease_release(self):
        self.lib.test_command(self.probe,2,500,0);self.lib.test_poll(self.probe,16)
        self.assertEqual(self.lib.test_command(self.probe,6,0,0),1)
        self.check_both('position','call $f',6,0)
        self.assertTrue(self.lib.test_release(self.probe))
        self.assertEqual(self.lib.test_command(self.probe,7,0,0),-1)
        self.check_both('position','call $f',6,-1,backend=False)

    def test_position_rejects_corrupt_backend_range_instead_of_exposing_it(self):
        self.lib.test_position_override.argtypes=[C.c_void_p,C.c_uint]
        self.lib.test_position_override(self.probe,32001)
        self.check_both('position','call $f',6,None,trap=True)

    def test_new_owner_never_inherits_previous_apps_progress(self):
        self.lib.test_rebind.argtypes=[C.c_void_p]
        self.lib.test_command(self.probe,2,500,0);self.lib.test_poll(self.probe,16)
        self.assertTrue(self.lib.test_rebind(self.probe))
        self.check_both('position','call $f',6,0)

    def test_gain_requires_speaker_and_without_backend_is_unavailable(self):
        self.check_both('gain','i32.const 4 call $f',4,None,trap=True)
        self.check_both('gain','i32.const 4 call $f',2,-1,backend=False)

    def test_gain_accepts_mute_and_eight_and_stops_reset_to_unity_in_both_vms(self):
        self.lib.test_gain_value.argtypes=[C.c_void_p]
        for gain in (0,4,8):
            self.check_both('gain',f'i32.const {gain} call $f',2,1)
            self.assertEqual(self.lib.test_gain_value(self.probe),gain)
        self.assertEqual(self.lib.test_command(self.probe,6,0,0),1)
        self.assertEqual(self.lib.test_gain_value(self.probe),1)
        self.assertTrue(self.lib.test_rebind(self.probe))
        self.assertEqual(self.lib.test_gain_value(self.probe),1)

    def test_gain_rejects_invalid_signed_range_before_backend_dispatch(self):
        self.lib.test_gain_calls.argtypes=[C.c_void_p]
        for gain in (-1,9,2147483647):
            self.check_both('gain',f'i32.const {gain} call $f',2,-1)
        self.assertEqual(self.lib.test_gain_calls(self.probe),0)

    def test_gain_shares_two_mutation_limit_instead_of_query_budget(self):
        self.check_both('gain','i32.const 4 call $f drop i32.const 4 call $f drop i32.const 4 call $f',2,None,trap=True)

    def test_gain_during_recording_is_busy_and_does_not_change_current_value(self):
        self.assertEqual(self.lib.test_command(self.probe,2,500,0),1)
        self.check_both('gain','i32.const 4 call $f',2,0)

    def test_gain_rejects_out_of_contract_backend_result_in_both_vms(self):
        self.lib.test_gain_override.argtypes=[C.c_void_p,C.c_int]
        self.lib.test_gain_override(self.probe,2)
        self.check_both('gain','i32.const 4 call $f',2,None,trap=True)
