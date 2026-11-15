import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_labos_c_store as contract
from labos import memory_probe
from labos.build import build


class MemoryProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner=memory_probe.build_profile()
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.blobs=[build(name,Path(cls.tmp.name))[1] for name in ('counter','game')]

    def test_actual_sdk_linear_memory_lives_in_fixed_pool_and_releases_each_cycle(self):
        result=memory_probe.run_profile(self.runner,self.blobs,cycles=20)
        self.assertFalse(result['device_tested']);self.assertTrue(result['software_bounds'])
        self.assertEqual((result['opened'],result['closed'],result['rejected'],result['traps']),(40,40,0,0))
        self.assertEqual(result['linear_in_pool'],40);self.assertEqual(result['leak_cycles'],0)
        self.assertEqual(result['after_used'],result['baseline_used'])
        self.assertGreaterEqual(result['peak_used'],131072)
        self.assertLessEqual(result['pool_total'],196608)

    def test_small_pool_rejects_apps_without_leaking_or_crashing(self):
        result=memory_probe.run_profile(self.runner,self.blobs,cycles=2,pool_bytes=65536)
        self.assertEqual(result['opened'],0);self.assertEqual(result['rejected'],4)
        self.assertEqual(result['leak_cycles'],0);self.assertEqual(result['after_used'],result['baseline_used'])

    def test_loop_and_oob_traps_do_not_break_following_sdk_app(self):
        import wasmtime
        def wasm(body):
            return bytes(wasmtime.wat2wasm('''(module (memory (export "memory") 2 2)
              (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init"))
              (func (export "tick") (param i32 i32 i32 i32) (result i32) %s))'''%body))
        blobs=[wasm('(loop $x br $x) i32.const 0'),wasm('i32.const 131072 i32.load'),self.blobs[0]]
        result=memory_probe.run_profile(self.runner,blobs,cycles=3)
        self.assertEqual((result['opened'],result['closed'],result['traps']),(9,9,6))
        self.assertEqual(result['leak_cycles'],0);self.assertEqual(result['linear_in_pool'],9)

    def test_normal_exit_is_not_counted_as_a_trap(self):
        import wasmtime
        blob=bytes(wasmtime.wat2wasm('''(module (memory (export "memory") 2 2)
          (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init"))
          (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 1))'''))
        result=memory_probe.run_profile(self.runner,[blob],cycles=2)
        self.assertEqual(result['traps'],0);self.assertEqual(result['normal_exits'],2)

    def test_current_eleven_apps_fit_160k_with_service_imports_but_no_physical_backends(self):
        from labos.project import build_project
        from labos.package import decode
        from labos.build import build
        with tempfile.TemporaryDirectory() as tmp:
            blobs={name:build(name,Path(tmp)/'sdk')[1] for name in ('counter','game','speaker','microphone','network')}
            for name in ('maze-runner','audio-desk','lane-catcher','focus-timer','voice-recorder','remote-timer'):
                blobs[name]=decode(Path(build_project(contract.ROOT/'apps'/name)['package']).read_bytes())[1]
        self.assertEqual(len(blobs),11)
        result=memory_probe.run_profile(self.runner,list(blobs.values()),cycles=3,pool_bytes=163840,capabilities=31)
        self.assertEqual((result['opened'],result['closed'],result['rejected'],result['traps']),(33,33,0,0))
        self.assertEqual(result['linear_in_pool'],33);self.assertEqual(result['leak_cycles'],0)
        self.assertEqual(result['after_used'],result['baseline_used']);self.assertLess(result['peak_used'],163840)

    def test_service_profile_rejects_invalid_permission_mask_before_subprocess(self):
        for mask in (True,-1,32,'31'):
            with mock.patch.object(memory_probe.subprocess,'run') as run,self.assertRaises(ValueError):
                memory_probe.run_profile(self.runner,self.blobs,capabilities=mask)
            run.assert_not_called()

    def test_impossible_or_inconsistent_native_measurements_are_rejected(self):
        valid=dict(capabilities=1,format='lab-os-memory-profile-v1',device_tested=False,software_bounds=True,pool_capacity=196608,
                   pool_total=196192,baseline_used=40,after_used=40,peak_used=150000,opened=1,closed=1,rejected=0,
                   traps=0,normal_exits=0,leak_cycles=0,linear_in_pool=1,input_buffer_peak=len(self.blobs[0]))
        for changes in ({'capabilities':True},{'after_used':0xffffffff},{'peak_used':196193},{'leak_cycles':True},
                        {'opened':0},{'closed':0},{'software_bounds':False}):
            with self.subTest(changes=changes),mock.patch.object(memory_probe.subprocess,'run',
                    return_value=mock.Mock(stdout=json.dumps(valid|changes))),self.assertRaises(ValueError):
                memory_probe.run_profile(self.runner,[self.blobs[0]],cycles=1)

    def test_invalid_work_limits_are_rejected_before_subprocess(self):
        for kwargs in ({'cycles':True},{'cycles':0},{'cycles':201},{'pool_bytes':65535},{'pool_bytes':196609}):
            with self.subTest(kwargs=kwargs),mock.patch.object(memory_probe.subprocess,'run') as run,self.assertRaises(ValueError):
                memory_probe.run_profile(self.runner,self.blobs,**kwargs)
            run.assert_not_called()
        for blobs in ([],[self.blobs[0]]*17,[bytes(65537)],[b'bad']):
            with self.subTest(count=len(blobs)),self.assertRaises(ValueError): memory_probe.run_profile(self.runner,blobs)

    def test_profile_build_rejects_wrong_source_pin_and_symlink_workspace(self):
        with mock.patch.object(memory_probe.subprocess,'run',return_value=mock.Mock(stdout='wrong',returncode=0)),self.assertRaises(ValueError):
            memory_probe.build_profile()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'link').symlink_to(path/'outside',target_is_directory=True)
            with mock.patch.object(memory_probe,'BUILD',path/'link'),self.assertRaises(ValueError):memory_probe.build_profile()

    def test_native_runner_rejects_unbounded_or_malformed_work(self):
        for cycles,pool in (('0','196608'),('201','196608'),('1x','196608'),('1','1'),('1','196609')):
            p=subprocess.run([str(self.runner),cycles,pool,'unused'],capture_output=True,text=True,timeout=5)
            self.assertEqual(p.returncode,64)

    def test_s3_component_selects_explicit_software_checks_with_same_mapping(self):
        source=(contract.ROOT/'firmware/esp-idf/lab-os-core/components/wamr/CMakeLists.txt').read_text()
        self.assertIn('set(WAMR_DISABLE_HW_BOUND_CHECK 1)',source)

    def test_in_place_pool_reallocation_updates_free_and_peak_accounting(self):
        p=subprocess.run([str(self.runner),'--allocator-check'],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
        row=json.loads(p.stdout)
        self.assertEqual(row['consumed_by_growth'],64)
        self.assertEqual(row['after_used'],row['baseline_used'])

    def test_generated_overlay_keeps_license_and_refuses_changed_upstream_copy(self):
        # Supplemental build-safety check; the accounting behavior was test-first.
        upstream=contract.SOURCE/'core/shared/mem-alloc/ems/ems_alloc.c'
        original=upstream.read_text()
        patched=(memory_probe.BUILD/'generated/lab_wamr_ems_alloc.c').read_text()
        self.assertEqual(original.splitlines()[:5],patched.splitlines()[:5])
        self.assertEqual(len(patched.splitlines())-len(original.splitlines()),4)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'wamr/core/shared/mem-alloc/ems/ems_alloc.c'
            source.parent.mkdir(parents=True);source.write_text(original+'\n/* changed */\n')
            helper=contract.ROOT/'firmware/esp-idf/lab-os-core/components/wamr/ems_accounting.cmake'
            script=folder/'test.cmake'
            script.write_text(f'include("{helper}")\nlab_wamr_ems_accounting("{folder}/wamr" "{folder}/out" result)\n')
            p=subprocess.run(['uvx','--from','cmake==4.1.2','cmake','-P',str(script)],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(p.returncode,0);self.assertIn('source hash mismatch',p.stderr)
            self.assertFalse((folder/'out').exists())
