import subprocess
import os
import sys
import tempfile
import unittest
from pathlib import Path

import wasmtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.native import build_probe, SOURCE
from labos.build import build, COMPILER
from labos.ui_assets import generate


def wasm(body, prefix=''):
    return wasmtime.wat2wasm('''(module %s
      (global $v (mut i32) (i32.const 0))
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "debug_value") (result i32) global.get $v)
      (func (export "tick") (param $held i32) (param $pressed i32)
        (param $released i32) (param $dt i32) (result i32) %s))''' % (prefix, body))


@unittest.skipUnless((SOURCE / 'CMakeLists.txt').is_file(), '固定WAMR sourceが必要')
class NativeHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        folder = Path(cls.tmp.name)
        generate(folder)
        blobs = {
            'normal': wasm('global.get $v local.get $pressed i32.add global.set $v i32.const 0'),
            'exiting': wasm('local.get $pressed i32.const 64 i32.and i32.eqz i32.eqz'),
            'looping': wasm('local.get $pressed if (loop $l br $l) end i32.const 0'),
            'oob': wasm('local.get $pressed if i32.const 131072 i32.load drop end i32.const 0', '(memory 2)'),
            'oom': wasm('local.get $pressed if i32.const 1 memory.grow i32.const -1 i32.eq if unreachable end end i32.const 0', '(memory 2)'),
            'bad': wasm('unreachable'),
        }
        if COMPILER.exists():
            for name in ('game', 'counter'):
                _, blobs[name] = build(name, folder / 'packages')
        header = ['#define HAS_C_APPS ' + str(int(COMPILER.exists()))]
        for name, blob in blobs.items():
            header.append('static const unsigned char ' + name + '_blob[]={' + ','.join(map(str, blob)) + '};')
        (folder / 'fixture_data.h').write_text('\n'.join(header) + '\n')
        cls.runner = folder / 'home-contract'
        native = ROOT / 'prototypes/lab-os/native'
        proc = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                               '-I' + str(folder), '-I' + str(native),
                               '-I' + str(ROOT / 'assets/fonts'),
                               '-I' + str(SOURCE / 'core/iwasm/include'),
                               str(ROOT / 'tests/native/lab_home_contract.c'),
                               str(native / 'app_home.c'), str(native / 'guest_vm.c'), str(native / 'ui.c'),
                               str(ROOT / 'build/lab-os-native/wamr/libiwasm.a'),
                               '-lpthread', '-lm', '-o', str(cls.runner)],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise RuntimeError(proc.stderr)

    def check(self, case):
        proc = subprocess.run([str(self.runner), case], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_navigation_launch_shield_and_normal_exit(self):
        self.check('navigation')

    def test_system_exit_waits_for_release_and_closes_before_provider_release(self):
        self.check('system-exit')

    def test_faults_rollback_or_disable_and_next_app_runs(self):
        self.check('faults')

    def test_open_or_quarantine_failure_still_frees_owned_image(self):
        self.check('failures')

    def test_invalid_host_input_is_not_blame_on_guest(self):
        self.check('host-input')

    def test_catalog_bounds_duplicate_and_corrupt_metadata(self):
        self.check('catalog')

    def test_repeated_switching_keeps_wamr_pool_and_provider_leases_reusable(self):
        self.check('repeat')

    def test_removed_failed_ids_do_not_exhaust_process_local_disable_table(self):
        self.check('disabled-limit')

    @unittest.skipUnless(COMPILER.exists(), '固定C compilerが必要')
    def test_actual_game_and_counter_use_shared_c_home(self):
        self.check('actual')

    @unittest.skipUnless(COMPILER.exists(), '固定C compilerが必要')
    def test_actual_c_supervisor_and_vm_render_four_raw_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([str(self.runner), 'actual'],
                                    env={**os.environ, 'LAB_HOME_GALLERY': tmp},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            frames = {}
            for name in ('home', 'counter', 'game', 'release'):
                p = Path(tmp) / (name + '.rgb565')
                self.assertTrue(p.is_file(), name)
                self.assertEqual(p.stat().st_size, 320 * 240 * 2)
                frames[name] = p.read_bytes()
            self.assertEqual(frames['counter'][(10 * 320 + 10) * 2:][:2], b'\xe0\x07')
            self.assertEqual(frames['game'][24 * 2:26 * 2], b'\xff\xff\xff\xff')
            self.assertNotEqual(frames['home'], frames['release'])

    @unittest.skipUnless(COMPILER.exists(), '固定C compilerが必要')
    def test_target_entry_runs_shared_supervisor_scenario_before_device_build(self):
        from labos.target import prepare
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            (folder / 'freertos').mkdir()
            (folder / 'freertos/FreeRTOS.h').write_text('#define pdMS_TO_TICKS(ms) (ms)\n')
            (folder / 'freertos/task.h').write_text('static inline void vTaskDelay(unsigned n) {(void)n;}\n')
            (folder / 'esp_heap_caps.h').write_text('''
                #include <stddef.h>
                #define MALLOC_CAP_INTERNAL 1
                static inline size_t heap_caps_get_free_size(unsigned cap){(void)cap;return 0;}
                static inline size_t heap_caps_get_minimum_free_size(unsigned cap){(void)cap;return 0;}
            ''')
            (folder / 'entry.c').write_text('void app_main(void);int main(void){app_main();return 0;}\n')
            native = ROOT / 'prototypes/lab-os/native'
            output = folder / 'target-entry'
            proc = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                   '-I' + str(folder), '-I' + str(folder / 'generated'),
                                   '-I' + str(native), '-I' + str(SOURCE / 'core/iwasm/include'),
                                   '-I' + str(ROOT / 'assets/fonts'),
                                   str(ROOT / 'firmware/esp-idf/lab-os-core/main/main.c'),
                                   str(folder / 'entry.c'), str(native / 'app_home.c'),
                                   str(native / 'guest_vm.c'),
                                   str(native / 'ui.c'),
                                   str(native / 'run_loop.c'),
                                   str(ROOT / 'build/lab-os-native/wamr/libiwasm.a'),
                                   '-lpthread', '-lm', '-o', str(output)],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = subprocess.run([str(output)], capture_output=True, text=True, check=True, timeout=10)
            self.assertIn('LAB_LOOP_CORE cycles=10 leases=0 opens=20 releases=20', result.stdout)
            self.assertIn('ui_frames=101 ui_rows=24240', result.stdout)
            self.assertIn('scenario_ms=3400', result.stdout)
