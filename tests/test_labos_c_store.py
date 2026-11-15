import ctypes as C
import hashlib
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import wasmtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.native import build_probe, SOURCE
from labos.package import encode
from labos.sdk import make_manifest
from labos.build import build, COMPILER

READ = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32))
PUT = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32)
HASH = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p)
VERIFY = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32)


class Storage(C.Structure):
    _fields_ = [('context', C.c_void_p), ('read', READ), ('put', PUT), ('hash', HASH), ('verify', VERIFY)]


def wasm(value=1, body=None):
    body = body or 'local.get 1 if global.get $v i32.const 1 i32.add global.set $v end i32.const 0'
    return bytes(wasmtime.wat2wasm('''(module
      (global $v (mut i32) (i32.const %d))
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "debug_value") (result i32) global.get $v)
      (func (export "tick") (param i32 i32 i32 i32) (result i32) %s))''' % (value, body)))


def package(name='counter', value=1, version='1.0.0', body=None):
    b = wasm(value, body)
    return encode(make_manifest(name, b, version), b)


class DiskFixture:
    """試験用の実ファイルI/O。実機FS driverではない。"""
    def __init__(self, root, lib):
        self.root = Path(root)
        self.lib = lib
        self.failure = None
        self.writes = []
        self.checks = 0
        self.verified_caps = []
        self.callback_errors = []
        self.read_cb = READ(self.read)
        self.put_cb = PUT(self.put)
        self.hash_cb = HASH(self.hash)
        self.verify_cb = VERIFY(self.verify)
        self.io = Storage(None, self.read_cb, self.put_cb, self.hash_cb, self.verify_cb)

    def path(self, key):
        name = key.decode('ascii')
        if not re.fullmatch(r'owner|index-[01]|[0-9a-f]{64}\.lab', name):
            raise ValueError('unsafe storage key')
        return self.root / name

    def read(self, ctx, key, out, capacity, size):
        try:
            p = self.path(key)
            if not p.exists():
                return 0
            data = p.read_bytes()
            size[0] = len(data)
            if out:
                if capacity < len(data):
                    return -1
                C.memmove(out, data, len(data))
            return 1
        except Exception as error:
            self.callback_errors.append(str(error))
            return -1

    def put(self, ctx, key, data, n):
        try:
            p = self.path(key)
            payload = C.string_at(data, n)
            self.writes.append(p.name)
            failure = self.failure if self.failure and self.failure[0] == p.name else None
            if failure and failure[1] == 'before':
                return False
            if failure and failure[1] in ('partial', 'lie'):
                payload = payload[:len(payload) // 2]
            with p.open('wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            return not failure or failure[1] == 'lie'
        except Exception as error:
            self.callback_errors.append(str(error))
            return False

    def hash(self, ctx, data, n, out):
        C.memmove(out, hashlib.sha256(C.string_at(data, n)).digest(), 32)
        return True

    def verify(self, ctx, data, n, pages, budget, draw):
        self.checks += 1
        self.verified_caps.append(draw)
        return bool(self.lib.test_verify(None, data, n, pages, budget, draw))


@unittest.skipUnless((SOURCE / 'CMakeLists.txt').is_file(), '固定WAMR sourceが必要')
class CStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe()
        cls.build_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build_dir.cleanup)
        native = ROOT / 'prototypes/lab-os/native'
        target = Path(cls.build_dir.name) / 'store.so'
        result = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                 '-shared', '-fPIC', '-I' + str(native),
                                 '-I' + str(SOURCE / 'core/iwasm/include'),
                                 str(ROOT / 'tests/native/lab_store_bridge.c'),
                                 str(native / 'app_store.c'), str(native / 'app_home.c'),
                                 str(native / 'guest_vm.c'),
                                 str(ROOT / 'build/lab-os-native/wamr/libiwasm.a'),
                                 '-lpthread', '-lm', '-o', str(target)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = C.CDLL(str(target))
        cls.lib.test_store_new.argtypes = [C.POINTER(Storage)]
        cls.lib.test_store_new.restype = C.c_void_p
        for name, tail in {
            'test_store_free': [], 'test_count': [], 'test_status': [C.c_int],
            'test_install': [C.c_void_p, C.c_uint32], 'test_action': [C.c_char_p, C.c_int],
            'test_info': [C.c_uint32, C.c_void_p], 'test_open': [C.c_char_p], 'test_release': [],
            'test_home_start': [], 'test_home_frame': [C.c_uint32, C.c_uint32],
            'test_home_mode': [], 'test_home_value': [],
            'test_home_refresh': [], 'test_home_count': [],
        }.items():
            getattr(cls.lib, name).argtypes = [C.c_void_p, *tail]
        cls.lib.test_verify.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32]
        if not cls.lib.test_runtime_start():
            raise RuntimeError('WAMR init')
        cls.addClassCleanup(cls.lib.test_runtime_stop)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.disk = DiskFixture(self.tmp.name, self.lib)
        (self.disk.root / 'owner').write_bytes(b'lab-os-c-store-v1\n')
        self.handles = []
        self.addCleanup(self.close_all)
        self.handle = self.open_store()

    def close_all(self):
        for handle in self.handles:
            self.lib.test_store_free(handle)
        self.handles.clear()
        self.assertEqual(self.disk.callback_errors, [])

    def open_store(self):
        handle = self.lib.test_store_new(C.byref(self.disk.io))
        if handle:
            self.handles.append(handle)
        return handle

    def restart(self):
        self.lib.test_store_free(self.handle)
        self.handles.remove(self.handle)
        self.handle = self.open_store()
        self.assertTrue(self.handle)

    def install(self, pack):
        return bool(self.lib.test_install(self.handle, pack, len(pack)))

    def entries(self):
        values = []
        for at in range(self.lib.test_count(self.handle)):
            out = C.create_string_buffer(160)
            self.assertTrue(self.lib.test_info(self.handle, at, out))
            values.append(out.value.decode().split('|'))
        return values

    def action(self, name, action):
        return bool(self.lib.test_action(self.handle, name.encode(), action))

    def test_owner_required_and_foreign_or_broken_index_is_not_adopted(self):
        self.assertTrue(self.handle)
        (self.disk.root / 'owner').write_bytes(b'foreign')
        self.assertFalse(self.open_store())
        (self.disk.root / 'owner').write_bytes(b'lab-os-c-store-v1\n')
        (self.disk.root / 'index-0').write_bytes(b'broken')
        self.assertFalse(self.open_store())
        self.assertEqual(self.disk.writes, [])

    def test_individual_updates_survive_restart_and_keep_previous(self):
        first = package()
        self.assertTrue(self.install(first))
        self.assertTrue(self.install(package('game')))
        game_hash = hashlib.sha256(package('game')).hexdigest() + '.lab'
        game_before = (self.disk.root / game_hash).read_bytes()
        self.assertTrue(self.install(package(value=9, version='1.0.1')))
        self.restart()
        self.assertEqual(self.entries(), [['counter', 'カウンター', '1.0.1'], ['game', 'ゲーム', '1.0.0']])
        self.assertEqual((self.disk.root / game_hash).read_bytes(), game_before)
        self.assertTrue(self.action('counter', 0))
        self.restart()
        self.assertEqual(self.entries()[0][2], '1.0.0')
        writes = list(self.disk.writes)
        self.assertTrue(self.install(first))
        self.assertEqual(self.disk.writes, writes)
        self.assertTrue(self.action('counter', 1))
        self.restart()
        self.assertEqual(self.entries(), [['game', 'ゲーム', '1.0.0']])

    def test_bad_package_and_startup_failure_never_publish(self):
        good = package()
        self.assertTrue(self.install(good))
        writes = list(self.disk.writes)
        for offset in (0, 12, 16, 24, 32, 96, 203, 256):
            bad = bytearray(good)
            bad[offset] ^= 32 if offset == 24 else 1
            self.assertFalse(self.install(bytes(bad)), offset)
        for body in ('unreachable', '(loop $l br $l)', 'i32.const 1'):
            self.assertFalse(self.install(package(version='1.0.1', body=body)))
        self.assertEqual(self.disk.writes, writes)
        self.assertEqual(self.entries()[0][2], '1.0.0')

    def test_image_lease_blocks_mutation_until_vm_has_released_it(self):
        self.assertTrue(self.install(package()))
        self.assertTrue(self.lib.test_open(self.handle, b'counter'))
        self.assertFalse(self.lib.test_open(self.handle, b'counter'))
        self.assertFalse(self.install(package(value=2, version='1.0.1')))
        for action in range(3):
            self.assertFalse(self.action('counter', action))
        self.lib.test_release(self.handle)
        self.lib.test_release(self.handle)  # 二重解放はしない。
        self.assertTrue(self.install(package(value=2, version='1.0.1')))

    def test_failed_index_writes_poison_writer_and_restart_selects_valid_generation(self):
        for failure, expected in [('before', '1.0.0'), ('partial', '1.0.0'),
                                  ('after', '1.0.1'), ('lie', '1.0.0')]:
            with self.subTest(failure=failure):
                # 各失敗を同じ初期状態から評価する。
                for p in self.disk.root.iterdir():
                    if p.name != 'owner':
                        p.unlink()
                self.restart()
                self.assertTrue(self.install(package()))
                self.disk.failure = ('index-1', failure)
                self.assertFalse(self.install(package(value=2, version='1.0.1')))
                self.assertFalse(self.lib.test_status(self.handle, 0))
                self.assertFalse(self.install(package('game')))
                self.disk.failure = None
                self.restart()
                self.assertEqual(self.entries()[0][2], expected)

    def test_failed_package_write_leaves_current_reference_unchanged(self):
        self.assertTrue(self.install(package()))
        next_pack = package(value=2, version='1.0.1')
        self.disk.failure = (hashlib.sha256(next_pack).hexdigest() + '.lab', 'partial')
        self.assertFalse(self.install(next_pack))
        self.disk.failure = None
        self.restart()
        self.assertEqual(self.entries()[0][2], '1.0.0')
        self.assertFalse(self.install(next_pack))  # 同名の破損blobを黙って上書きしない。

    def test_checksum_recovery_and_fail_closed_when_both_copies_are_broken(self):
        self.assertTrue(self.install(package()))
        self.assertTrue(self.install(package(value=2, version='1.0.1')))
        (self.disk.root / 'index-1').write_bytes(b'broken')
        self.restart()
        self.assertTrue(self.lib.test_status(self.handle, 1))
        self.assertEqual(self.entries()[0][2], '1.0.0')
        (self.disk.root / 'index-0').write_bytes(b'broken')
        self.assertFalse(self.open_store())

    def test_interrupted_first_publish_is_not_silently_formatted_as_empty(self):
        self.disk.failure = ('index-0', 'partial')
        self.assertFalse(self.install(package()))
        self.disk.failure = None
        self.assertFalse(self.open_store())

    def test_self_consistent_but_invalid_index_is_rejected(self):
        self.assertTrue(self.install(package()))
        original = (self.disk.root / 'index-0').read_bytes()
        for offset, value in ((12, 17), (16, 1), (32, 46), (65, 1), (104, 0)):
            bad = bytearray(original)
            if offset == 104:
                bad[72:104] = bytes(32)  # current参照なし。
            else:
                bad[offset] = value
            bad[-32:] = hashlib.sha256(bad[:-32]).digest()
            (self.disk.root / 'index-0').write_bytes(bad)
            self.assertFalse(self.open_store(), offset)
        (self.disk.root / 'index-0').write_bytes(original)
        exhausted = bytearray(original)
        struct.pack_into('<I', exhausted, 8, 0xffffffff)
        exhausted[-32:] = hashlib.sha256(exhausted[:-32]).digest()
        (self.disk.root / 'index-0').write_bytes(exhausted)
        self.restart()
        self.assertFalse(self.install(package('game')))

    def test_corrupt_or_wrong_identity_blob_never_becomes_guest_code(self):
        pack = package()
        self.assertTrue(self.install(pack))
        p = self.disk.root / (hashlib.sha256(pack).hexdigest() + '.lab')
        p.write_bytes(package('game'))
        self.assertFalse(self.lib.test_open(self.handle, b'counter'))
        out = C.create_string_buffer(160)
        self.assertFalse(self.lib.test_info(self.handle, 0, out))

    def test_limit_quarantine_and_rollback_do_not_touch_other_apps(self):
        for i in range(16):
            self.assertTrue(self.install(package('a' + str(i))))
        self.assertFalse(self.install(package('overflow')))
        self.assertFalse(self.action('../escape', 1))
        self.assertFalse(self.action('a0', 0))
        self.assertTrue(self.install(package('a0', value=2, version='1.0.1')))
        self.assertTrue(self.action('a0', 2))
        self.assertEqual(self.entries()[0][2], '1.0.0')
        self.assertTrue(self.action('a0', 2))
        self.restart()
        self.assertEqual(len(self.entries()), 15)
        self.assertTrue(self.install(package('overflow')))

    def test_real_c_home_fault_rolls_back_after_releasing_wamr_image(self):
        self.assertTrue(self.install(package(value=7)))
        self.assertTrue(self.install(package(value=8, version='1.0.1',
                                             body='local.get 1 if unreachable end i32.const 0')))
        self.assertTrue(self.lib.test_home_start(self.handle))
        self.assertTrue(self.lib.test_home_frame(self.handle, 16, 0))
        self.assertEqual(self.lib.test_home_mode(self.handle), 1)
        self.lib.test_home_frame(self.handle, 0, 10)
        self.lib.test_home_frame(self.handle, 32, 10)
        self.assertEqual(self.lib.test_home_mode(self.handle), 2)
        self.assertEqual(self.entries()[0][2], '1.0.0')
        self.lib.test_home_frame(self.handle, 0, 10)
        self.lib.test_home_frame(self.handle, 16, 10)
        self.lib.test_home_frame(self.handle, 0, 10)
        self.assertEqual(self.lib.test_home_value(self.handle), 7)

    def test_quarantine_io_failure_keeps_other_apps_usable_in_read_only_snapshot(self):
        self.assertTrue(self.install(package()))
        self.assertTrue(self.install(package(version='1.0.1',
                                             body='local.get 1 if unreachable end i32.const 0')))
        self.assertTrue(self.install(package('game', value=9)))
        self.assertTrue(self.lib.test_home_start(self.handle))
        self.disk.failure = ('index-1', 'before')
        for held in (16, 0, 32):
            self.lib.test_home_frame(self.handle, held, 10)
        self.assertEqual(self.lib.test_home_mode(self.handle), 2)
        self.assertFalse(self.lib.test_status(self.handle, 0))
        self.assertEqual(self.lib.test_home_count(self.handle), 1)
        self.assertFalse(self.action('game', 1))
        for held in (0, 16, 0):
            self.lib.test_home_frame(self.handle, held, 10)
        self.assertEqual(self.lib.test_home_mode(self.handle), 1)
        self.assertEqual(self.lib.test_home_value(self.handle), 9)

    @unittest.skipUnless(COMPILER.exists(), '固定C compilerが必要')
    def test_real_c_games_are_added_and_updated_without_rebuilding_supervisor(self):
        _, counter = build('counter', self.disk.root / 'build')
        _, game = build('game', self.disk.root / 'build')
        self.assertTrue(self.install(encode(make_manifest('counter', counter), counter)))
        self.assertTrue(self.lib.test_home_start(self.handle))
        self.assertEqual(self.lib.test_home_count(self.handle), 1)
        self.assertTrue(self.install(encode(make_manifest('game', game), game)))
        self.assertTrue(self.lib.test_home_refresh(self.handle))
        self.assertEqual(self.lib.test_home_count(self.handle), 2)
        for held in [16, 0, 1]:
            self.lib.test_home_frame(self.handle, held, 16)
        self.assertEqual(self.lib.test_home_value(self.handle), 1)
        for held in [192, 0]:
            self.lib.test_home_frame(self.handle, held, 16)
        self.assertTrue(self.install(encode(make_manifest('counter', counter, '1.0.1'), counter)))
        self.restart()
        self.assertEqual(self.entries()[0][2], '1.0.1')
        self.assertTrue(self.lib.test_home_start(self.handle))
        for held in [4, 0, 16, 0, 16, 1]:
            self.lib.test_home_frame(self.handle, held, 300)
        self.assertEqual(self.lib.test_home_mode(self.handle), 1)
        self.assertEqual(self.lib.test_home_value(self.handle), 1)

    def test_audio_permission_bits_reach_verifier_and_survive_update_rollback_restart(self):
        blob=wasm()
        for flags in range(8):
            caps=[name for bit,name in ((1,'draw'),(2,'speaker'),(4,'microphone')) if flags&bit]
            pack=encode(make_manifest('audio-test',blob,version=f'1.0.{flags}',capabilities=caps),blob)
            self.assertTrue(self.install(pack));self.assertEqual(self.disk.verified_caps[-1],flags)
        self.assertTrue(self.action('audio-test',0));self.restart()
        self.assertEqual(self.entries()[0][2],'1.0.6')
    def test_network_permission_bit_reaches_silent_verifier_and_survives_rollback_restart(self):
        blob=wasm()
        for flags in (8,9,15):
            caps=[name for bit,name in ((1,'draw'),(2,'speaker'),(4,'microphone'),(8,'network')) if flags&bit]
            pack=encode(make_manifest('network-test',blob,version=f'1.0.{flags}',capabilities=caps),blob)
            self.assertTrue(self.install(pack));self.assertEqual(self.disk.verified_caps[-1],flags)
        self.assertTrue(self.action('network-test',0));self.restart()
        self.assertEqual(self.entries()[0][2],'1.0.9')
    def test_audio_init_validation_is_silent_and_catalog_launch_keeps_declared_permissions(self):
        for cap,signature,arguments in [('speaker','(param i32 i32)','i32.const 1000 i32.const 20'),
                                        ('microphone','(param i32)','i32.const 20')]:
            op='audio_tone' if cap=='speaker' else 'audio_record'
            blob=bytes(wasmtime.wat2wasm(f'(module\n              (import "os" "{op}" (func $audio {signature} (result i32)))\n              (func (export "sdk_abi") (result i32) i32.const 2)\n              (func (export "init") {arguments} call $audio drop)\n              (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0))'))
            pack=encode(make_manifest('audio-test',blob,capabilities=[cap]),blob)
            self.assertTrue(self.install(pack));self.assertTrue(self.lib.test_home_start(self.handle))
            self.assertTrue(self.lib.test_home_frame(self.handle,16,0))
            self.assertEqual(self.lib.test_home_mode(self.handle),1)
            self.restart()
    def test_audio_init_without_permission_and_unknown_bits_never_publish(self):
        blob=bytes(wasmtime.wat2wasm('(module\n          (import "os" "audio_record" (func $audio (param i32) (result i32)))\n          (func (export "sdk_abi") (result i32) i32.const 2)\n          (func (export "init") i32.const 20 call $audio drop)\n          (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0))'))
        pack=encode(make_manifest('audio-test',blob,capabilities=[]),blob)
        self.assertFalse(self.install(pack));self.assertEqual(self.disk.writes,[])
        pack=bytearray(encode(make_manifest('audio-test',wasm()),wasm()));struct.pack_into('<I',pack,24,32)
        checks=self.disk.checks;self.assertFalse(self.install(bytes(pack)));self.assertEqual(self.disk.checks,checks)
        self.assertEqual(self.disk.writes,[])
