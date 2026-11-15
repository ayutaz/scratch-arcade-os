import ctypes as C
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_labos_c_store as contract
import test_labos_lfs as fs
from labos.build import build
from labos.package import encode
from labos.fs_image import create_image
from labos.transfer import Frame, Parser, Client, encode as frame_bytes
from labos.ui_assets import generate
from labos.memory_probe import build_profile

ROOT = contract.ROOT
MAIN = ROOT / 'firmware/esp-idf/lab-os-core/main'
NATIVE = ROOT / 'prototypes/lab-os/native'
HASH = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_uint32, C.c_void_p)


class BootFixture:
    console_flags = ()

    @classmethod
    def setUpClass(cls):
        runtime=build_profile().parent/'liblabos-memory-runtime.a'
        cls.tmp = tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        folder = Path(cls.tmp.name);generate(folder)
        packages = []
        for name in ('counter', 'game'):
            manifest, blob = build(name, folder / 'apps');packages.append(encode(manifest, blob))
        cls.seed, _ = create_image(packages)
        sources = [MAIN / name for name in ('board_boot.c', 'target_storage.c', 'flash_volume.c', 'board_session.c',
                                             'board_input.c', 'board_display.c', 'usb_transfer.c','board_audio.c','board_sound.c','board_wifi.c','board_network.c','board_udp.c')]
        sources += [NATIVE / name for name in ('app_home.c', 'app_store.c', 'app_lfs.c', 'app_transfer.c', 'run_loop.c', 'input.c', 'ui.c','audio_service.c','audio_binding.c','udp_service.c','network_binding.c')]
        sources += [ROOT / 'tests/native' / name for name in ('lab_boot_bridge.c', 'lab_boot_vm_fixture.c', 'lab_store_bridge.c',
                      'lab_session_bridge.c', 'lab_session_input_fixture.c', 'lab_session_display_fixture.c', 'lab_flash_volume_bridge.c','lab_session_audio_fixture.c','lab_session_wifi_fixture.c')]
        flags = ['-I' + str(ROOT / 'tests/native' / name) for name in ('wifi_fixture','udp_fixture','boot_fixture', 'session_fixture', 'display_fixture',
                                                                 'input_fixture', 'usb_fixture', 'flash_fixture','audio_fixture')]
        flags += ['-I' + str(MAIN), '-I' + str(NATIVE), '-I' + str(fs.LFS), '-I' + str(folder),
                  '-I' + str(ROOT / 'assets/fonts'), '-I' + str(contract.SOURCE / 'core/iwasm/include')]
        output = folder / 'boot.dylib'
        p = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR', *cls.console_flags, *flags, *map(str, sources),
                            str(fs.LFS / 'lfs.c'), str(fs.LFS / 'lfs_util.c'),
                            str(runtime), '-lpthread', '-lm', '-o', str(output)],
                           capture_output=True, text=True, timeout=30)
        if p.returncode: raise RuntimeError(p.stderr)
        cls.lib = C.CDLL(str(output))
        signatures = {
            'test_boot_new': ([], C.c_void_p), 'test_boot_free': ([C.c_void_p], None),
            'test_boot_open': ([C.c_void_p, C.c_int, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32], C.c_int),
            'test_boot_close': ([C.c_void_p], C.c_int), 'test_boot_step': ([C.c_void_p, C.c_uint32], C.c_int),
            'test_boot_metric': ([C.c_void_p, C.c_int], C.c_int), 'test_boot_calls': ([C.c_int], C.c_int),
            'test_boot_value': ([C.c_void_p], C.c_int), 'test_boot_stage': ([C.c_int], None),
            'test_boot_pool': ([C.c_void_p,C.c_int], C.c_uint32),
            'test_boot_random': ([C.c_uint32], None), 'test_boot_hash_callback': ([HASH], None),
            'test_boot_hash': ([C.c_void_p, C.c_uint32, C.c_void_p], C.c_int),
            'test_boot_verify': ([C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32], C.c_int),
            'test_flash_seed': ([C.c_void_p, C.c_uint32], C.c_int), 'test_flash_table': ([C.c_int], None),
            'test_flash_calls': ([C.c_int], C.c_int), 'test_flash_fault': ([C.c_int, C.c_int, C.c_int], None),
            'test_session_usb_installed': ([C.c_int], None), 'test_values': ([C.c_int, C.c_int, C.c_int], None),
            'test_session_enqueue': ([C.c_void_p, C.c_uint32], C.c_int),
            'test_session_output': ([C.c_void_p, C.c_uint32], C.c_uint32),
            'test_display_fault': ([C.c_int, C.c_int], None), 'test_display_calls': ([C.c_int], C.c_int),
            'test_fault': ([C.c_int], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(cls.lib, name);fn.argtypes, fn.restype = args, result
        def hash_data(p, n, out):
            C.memmove(out, hashlib.sha256(C.string_at(p, n)).digest(), 32);return True
        cls.hash = HASH(hash_data);cls.lib.test_boot_hash_callback(cls.hash)

    def setUp(self):
        self.boots = []
        self.lib.test_boot_reset();self.lib.test_display_reset();self.lib.test_reset()
        self.lib.test_session_usb_reset();self.lib.test_session_usb_installed(0)
        self.assertTrue(self.lib.test_flash_seed(self.seed, len(self.seed)))
        self.boot = self.lib.test_boot_new();self.boots.append(self.boot)
        self.addCleanup(self.close_all)
        self.now = 0

    def close_all(self):
        for boot in reversed(self.boots): self.lib.test_boot_free(boot)

    def metric(self, i): return self.lib.test_boot_metric(self.boot, i)
    def calls(self, i): return self.lib.test_boot_calls(i)
    def open(self): self.assertTrue(self.lib.test_boot_open(self.boot, 1, 0x400000, len(self.seed), len(self.seed), self.now))
    def step(self, dt=1, result=0):
        self.now += dt;self.assertEqual(self.lib.test_boot_step(self.boot, self.now), result)
    def key(self, keys=0):
        self.lib.test_values(keys, 2048, 2048);self.step();self.step(20)
    def launch(self): self.step();self.key(2);self.assertEqual(self.metric(7), 1)
    def raw(self, op, request, payload=b''):
        out = C.create_string_buffer(8192);self.lib.test_session_output(out, len(out))
        packet = frame_bytes(Frame(op, 999, request, payload))
        self.assertTrue(self.lib.test_session_enqueue(packet, len(packet)))
        for _ in range((len(packet) + 127) // 128): self.step()
        n = self.lib.test_session_output(out, len(out))
        frames = [f for f in Parser().feed(out.raw[:n]) if (f.op, f.session, f.request) == (op, 999, request)]
        self.assertEqual(len(frames), 1);return frames[0]


class BoardBootTests(BootFixture, unittest.TestCase):
    def test_runtime_pool_leaves_32k_more_internal_heap_for_audio_after_wifi(self):
        self.open();total=self.lib.test_boot_pool(self.boot,0)
        self.assertLessEqual(total,163840);self.assertGreater(total,160000)
        self.launch();self.assertEqual(self.lib.test_boot_pool(self.boot,3),1)
        self.assertEqual(self.metric(11),0)

    def test_sdk_memory_is_inside_boot_pool_and_released_before_home(self):
        self.open();baseline=self.lib.test_boot_pool(self.boot,1);self.launch()
        self.assertEqual(self.lib.test_boot_pool(self.boot,3),1)
        self.assertGreaterEqual(self.lib.test_boot_pool(self.boot,1),131072)
        self.key(5);self.key()
        self.assertEqual(self.metric(7),0);self.assertEqual(self.lib.test_boot_pool(self.boot,1),baseline)

    def test_maximum_update_with_lcd_input_and_reopen_keeps_game_and_releases_pool(self):
        # Supplemental integrated regression after test-first scheduler changes;
        # API time is injected, not physical driver latency or device speed.
        from labos.resource_probe import padded_package
        self.open();self.step()
        params=self.lib.test_display_calls(7)
        for _ in range(30):self.step(33)
        self.assertEqual(self.lib.test_display_calls(7),params)
        fixture=self
        class Stream:
            def write(self,data):
                fixture.assertTrue(fixture.lib.test_session_enqueue(data,len(data)));return len(data)
            def read(self,n):
                fixture.step(20);out=C.create_string_buffer(n)
                size=fixture.lib.test_session_output(out,n);return out.raw[:size]
        c=Client(Stream(),clock=lambda:self.now/1000,timeout=.5,session=888)
        c.connect();before=c.list_apps();game=next(r for r in before if r['id']=='game')
        baseline=self.lib.test_boot_pool(self.boot,1)
        with tempfile.TemporaryDirectory() as tmp:
            manifest,blob=build('counter',tmp)
        maximum=padded_package(manifest,blob,version='1.0.1',size=16384)
        # A held during transfer must not start an app or consume the launch edge.
        self.lib.test_values(2,2048,2048);paint_before=self.lib.test_display_calls(7)
        started=self.now;row=c.install(maximum);paint_after=self.lib.test_display_calls(7)
        self.assertEqual(row['version'],'1.0.1');self.assertEqual(self.metric(7),0)
        self.assertEqual(next(r for r in c.list_apps() if r['id']=='game'),game)
        self.assertEqual(self.lib.test_boot_pool(self.boot,1),baseline)
        c.close();self.key(2);self.assertEqual(self.metric(7),0)
        self.key();self.launch();self.key()
        self.lib.test_values(0,0,2048);self.step();self.assertEqual(self.lib.test_boot_value(self.boot),1)
        self.key(5);self.key();self.assertEqual(self.metric(7),0)
        self.assertEqual(self.lib.test_boot_pool(self.boot,1),baseline)
        self.assertTrue(self.lib.test_boot_close(self.boot));self.open()
        c=Client(Stream(),clock=lambda:self.now/1000,timeout=1.2,session=889)
        c.connect();after=c.list_apps();c.close()
        self.assertEqual(next(r for r in after if r['id']=='game'),game)
        self.assertEqual(next(r for r in after if r['id']=='counter')['version'],'1.0.1')
        self.assertEqual(self.metric(11),0)
        self.lib.test_display_metric.argtypes=[C.c_int];self.lib.test_display_metric.restype=C.c_int
        self.assertEqual(self.lib.test_display_metric(0),0)
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual([self.metric(i) for i in (0,1,2,3,4,5,6,8,10,11)],[0]*10)
        self.assertEqual(paint_after-paint_before,720)
        print('LAB_COMBINED_LOAD '+json.dumps(dict(device_tested=False,package_bytes=len(maximum),
              idle_polls=30,idle_param_commands=0,update_param_commands=paint_after-paint_before,
              elapsed_injected_ms=self.now-started,game_unchanged=True,pool_restored=True)))

    def update(self, request, value):
        package=contract.package(value=value,version=f'1.0.{value}')
        self.assertEqual(self.raw(3,request,len(package).to_bytes(4,'little')+hashlib.sha256(package).digest()).status,0)
        self.assertEqual(self.raw(4,request+1,bytes(4)+package).status,0)
        self.assertEqual(self.raw(5,request+2).status,0)
        return request+3

    def test_usb_incremental_collection_replays_ack_keeps_current_and_runs_after_close(self):
        import struct
        self.open();self.assertEqual(self.raw(2,1,(123).to_bytes(4,'little')).status,0)
        request=2
        for value in (9,10,11): request=self.update(request,value)
        for _ in range(100):
            frame=self.raw(12,request);self.assertEqual(frame.status,0)
            values=struct.unpack('<5I',frame.payload)
            state=[self.metric(i) for i in (14,15,16,17,18)]
            self.assertEqual(self.raw(12,request).payload,frame.payload)
            self.assertEqual([self.metric(i) for i in (14,15,16,17,18)],state)
            request+=1
            if values[4]: break
        else: self.fail('GC did not finish')
        self.assertEqual(values[0],2);self.assertGreater(values[1],0)
        self.assertEqual((self.metric(14),self.metric(15)),(0,0))
        self.assertEqual(self.raw(10,request).status,0)
        # Supplemental end-to-end client assertion after the test-first raw protocol contract.
        # raw() consumed the immediate CLOSE beacon; wait for the next 1s beacon.
        self.step(1001)
        fixture=self
        class Stream:
            def write(self,data):
                fixture.assertTrue(fixture.lib.test_session_enqueue(data,len(data)));return len(data)
            def read(self,n):
                fixture.step();out=C.create_string_buffer(n)
                size=fixture.lib.test_session_output(out,n);return out.raw[:size]
        client=Client(Stream(),clock=lambda:self.now/1000,timeout=.2,session=888)
        client.connect();self.assertEqual(client.collect()['removed_files'],0);client.close()
        self.launch()
        self.assertEqual(self.lib.test_boot_value(self.boot),11)

    def test_usb_collection_locks_mutations_and_abort_expiry_shutdown_release_maintenance(self):
        self.open();self.assertEqual(self.raw(2,1,(123).to_bytes(4,'little')).status,0)
        request=self.update(self.update(2,9),10)
        self.assertEqual(self.raw(12,request).status,0);request+=1
        self.assertEqual((self.metric(14),self.metric(15)),(1,1))
        self.assertEqual(self.raw(8,request,b'counter').status,2);request+=1
        self.assertEqual(self.raw(6,request).status,0);request+=1
        self.assertEqual((self.metric(14),self.metric(15)),(0,0))
        self.assertEqual(self.raw(12,request).status,0)
        self.assertEqual((self.metric(14),self.metric(15)),(1,1))
        self.step(5001);self.assertEqual((self.metric(14),self.metric(15)),(0,0))
        self.assertEqual(self.raw(2,1,(123).to_bytes(4,'little')).status,0)
        self.assertEqual(self.raw(12,2).status,0)
        self.assertTrue(self.lib.test_boot_close(self.boot));self.assertEqual((self.metric(14),self.metric(15),self.metric(10)),(0,0,0))

    def test_boot_from_generated_seed_runs_counter_game_and_closes_owned_usb_runtime(self):
        self.open();self.launch()
        self.lib.test_values(0, 0, 2048);self.step()
        self.assertEqual(self.lib.test_boot_value(self.boot), 1)
        self.key(5);self.key()
        self.lib.test_values(0, 2048, 0);self.step();self.key();self.key(2)
        self.key();self.key(2)
        self.lib.test_values(0, 0, 2048);self.step(300)
        self.assertEqual(self.lib.test_boot_value(self.boot), 1)
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual([self.metric(i) for i in (0, 1, 2, 3, 4, 5, 6, 8, 10, 11)], [0] * 10)
        self.assertEqual([self.calls(i) for i in range(4)], [1, 1, 1, 1])
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual([self.calls(i) for i in range(4)], [1, 1, 1, 1])

    def test_invalid_profile_layout_and_foreign_usb_driver_reject_before_runtime(self):
        for profile, address, size, quota in ((0, 0x400000, len(self.seed), len(self.seed)),
                                            (1, 0, len(self.seed), len(self.seed)),
                                            (1, 0x400001, len(self.seed), len(self.seed)),
                                            (1, 0x400000, len(self.seed), 0)):
            self.assertFalse(self.lib.test_boot_open(self.boot, profile, address, size, quota, 0))
        self.lib.test_session_usb_installed(1)
        self.assertFalse(self.lib.test_boot_open(self.boot, 1, 0x400000, len(self.seed), len(self.seed), 0))
        self.assertEqual([self.calls(i) for i in range(4)], [0] * 4)
        self.assertEqual([self.lib.test_flash_calls(i) for i in range(3)], [0] * 3)
        self.assertEqual(self.lib.test_display_calls(0), 0)

    def test_runtime_or_mount_or_hash_failure_unwinds_before_device_initialization(self):
        for stage, table in ((1, 0), (0, 1), (4, 0)):
            self.lib.test_boot_stage(stage);self.lib.test_flash_table(table)
            self.assertFalse(self.lib.test_boot_open(self.boot, 1, 0x400000, len(self.seed), len(self.seed), 0))
            self.assertEqual([self.metric(i) for i in (0, 1, 2, 3, 4, 5, 10)], [0] * 7)
            self.assertEqual(self.lib.test_display_calls(0), 0)
        self.assertEqual(self.calls(2), 0)

    def test_usb_install_failure_still_runs_local_apps_without_uninstalling_foreign_resources(self):
        self.lib.test_boot_stage(2);self.open();self.launch()
        self.assertEqual((self.metric(5), self.metric(6)), (0, 0))
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual((self.calls(2), self.calls(3), self.metric(11)), (1, 0, 0))

    def test_second_object_cannot_reinitialize_runtime_or_steal_usb(self):
        self.open()
        other = self.lib.test_boot_new();self.boots.append(other)
        before = [self.calls(i) for i in range(6)]
        self.assertFalse(self.lib.test_boot_open(other, 1, 0x400000, len(self.seed), len(self.seed), 0))
        self.assertTrue(self.lib.test_boot_close(other))
        self.assertEqual([self.calls(i) for i in range(6)], before)
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertTrue(self.lib.test_boot_open(other, 1, 0x400000, len(self.seed), len(self.seed), 0))

    def test_display_or_input_start_failure_releases_session_usb_fs_then_runtime(self):
        for display_stage, input_stage in ((4, 0), (-1, 3)):
            self.lib.test_display_fault(display_stage, self.lib.test_display_calls(display_stage) + 1 if display_stage >= 0 else 1)
            self.lib.test_fault(input_stage)
            self.assertFalse(self.lib.test_boot_open(self.boot, 1, 0x400000, len(self.seed), len(self.seed), 0))
            self.assertEqual([self.metric(i) for i in (0, 1, 2, 3, 4, 5, 10, 11)], [0] * 8)

    def test_cleanup_retry_keeps_runtime_fs_and_usb_until_child_is_released(self):
        self.open();self.launch()
        self.lib.test_display_fault(12, self.lib.test_display_calls(12) + 1)
        self.assertFalse(self.lib.test_boot_close(self.boot))
        self.assertEqual((self.metric(0), self.metric(1), self.metric(3), self.metric(5), self.metric(8)), (0, 1, 1, 1, 0))
        self.assertEqual((self.calls(1), self.calls(3)), (0, 0))
        self.lib.test_display_fault(-1, 1)
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual((self.calls(1), self.calls(3)), (1, 1))

    def test_usb_uninstall_failure_preserves_parent_ownership_and_does_not_double_destroy(self):
        self.open();self.lib.test_boot_stage(3)
        self.assertFalse(self.lib.test_boot_close(self.boot))
        self.assertEqual((self.metric(1), self.metric(3), self.metric(5)), (1, 1, 1))
        self.assertEqual(self.calls(1), 0)
        self.lib.test_boot_stage(0)
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual((self.calls(1), self.calls(3), self.metric(11)), (1, 2, 0))

    def test_zero_rng_nonce_is_mapped_and_usb_update_persists_across_full_boot(self):
        self.lib.test_boot_random(0);self.open();self.step()
        self.assertEqual(self.metric(12), 1)
        self.assertEqual(self.raw(2, 1, (1).to_bytes(4, 'little')).status, 0)
        package = contract.package(value=9, version='1.0.1')
        self.assertEqual(self.raw(3, 2, len(package).to_bytes(4, 'little') + hashlib.sha256(package).digest()).status, 0)
        self.assertEqual(self.raw(4, 3, bytes(4) + package).status, 0)
        self.assertEqual(self.raw(5, 4).status, 0)
        self.assertEqual(self.raw(10, 5).status, 0)
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.open();self.launch()
        self.assertEqual(self.lib.test_boot_value(self.boot), 9)
        self.assertEqual(self.metric(11), 0)

    def test_sha256_adapter_copies_only_exact_success_and_vm_probe_is_bounded(self):
        for value in (b'', b'abc', bytes(range(256)) * 64):
            out = C.create_string_buffer(bytes([122]) * 32)
            self.assertTrue(self.lib.test_boot_hash(value, len(value), out))
            self.assertEqual(out.raw[:32], hashlib.sha256(value).digest())
        for stage in (4, 5):
            self.lib.test_boot_stage(stage);out = C.create_string_buffer(bytes([122]) * 32)
            self.assertFalse(self.lib.test_boot_hash(b'abc', 3, out))
            self.assertEqual(out.raw[:32], bytes([122]) * 32)
        self.lib.test_boot_stage(0);self.open()
        good = contract.wasm()
        self.assertTrue(self.lib.test_boot_verify(good, len(good), 2, 50000, True))
        loop = contract.wasm(body='(loop $l br $l) i32.const 0')
        self.assertFalse(self.lib.test_boot_verify(loop, len(loop), 2, 50000, True))
        self.assertTrue(self.lib.test_boot_verify(good, len(good), 2, 50000, True))
        self.assertFalse(self.lib.test_boot_verify(good, len(good), 3, 50000, True))


class BootConsoleTests(BootFixture, unittest.TestCase):
    console_flags = ('-DCONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=1',)

    def test_console_driver_is_left_installed_and_ui_works_offline(self):
        self.lib.test_session_usb_installed(1);self.open();self.launch()
        self.assertEqual((self.metric(5), self.metric(6), self.calls(2)), (0, 0, 0))
        self.assertTrue(self.lib.test_boot_close(self.boot))
        self.assertEqual((self.calls(3), self.metric(11)), (0, 0))
