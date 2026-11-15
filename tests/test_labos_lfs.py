import ctypes as C
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_labos_c_store as contract

ROOT = Path(__file__).resolve().parents[1]
LFS = ROOT / '.cache/os-littlefs-v2.11.3'
LFS_COMMIT = '6cb4e86540eca0d9ba62500a298385c9d863c8be'


@unittest.skipUnless((LFS / 'lfs.c').is_file() and (contract.SOURCE / 'CMakeLists.txt').is_file(),
                     '固定LittleFS/WAMR sourceが必要')
class LittleFsFixture:
    extra_sources = ()
    extra_signatures = {}
    extra_flags = ()
    @classmethod
    def setUpClass(cls):
        actual = subprocess.check_output(['git', '-C', str(LFS), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != LFS_COMMIT:
            raise RuntimeError('LittleFS source commit')
        contract.build_probe()
        cls.tmp_build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp_build.cleanup)
        target = Path(cls.tmp_build.name) / 'lfs.so'
        native = ROOT / 'prototypes/lab-os/native'
        result = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                 '-shared', '-fPIC', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR',
                                 *cls.extra_flags,
                                 '-I' + str(native), '-I' + str(LFS),
                                 '-I' + str(contract.SOURCE / 'core/iwasm/include'),
                                 str(ROOT / 'tests/native/lab_store_bridge.c'),
                                 str(ROOT / 'tests/native/lab_lfs_bridge.c'),
                                 str(native / 'app_lfs.c'), str(native / 'app_store.c'),
                                 str(native / 'app_home.c'), str(native / 'guest_vm.c'),
                                 str(LFS / 'lfs.c'), str(LFS / 'lfs_util.c'),
                                 *map(str, cls.extra_sources),
                                 str(ROOT / 'build/lab-os-native/wamr/libiwasm.a'),
                                 '-lpthread', '-lm', '-o', str(target)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = C.CDLL(str(target))
        signatures = {
            'test_lfs_new': ([C.c_void_p, C.c_uint32, C.c_bool], C.c_void_p),
            'test_lfs_free': ([C.c_void_p], None),
            'test_lfs_mounted': ([C.c_void_p], C.c_int),
            'test_lfs_connect': ([C.c_void_p, C.POINTER(contract.Storage), C.c_uint32, C.c_bool,
                                  C.POINTER(contract.Storage)], C.c_int),
            'test_lfs_dump': ([C.c_void_p, C.c_void_p], None),
            'test_lfs_cut': ([C.c_void_p, C.c_int, C.c_bool], None),
            'test_lfs_operations': ([C.c_void_p], C.c_int),
            'test_lfs_mkdir': ([C.c_void_p, C.c_char_p], C.c_int),
            'test_lfs_raw_put': ([C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32], C.c_int),
            'test_lfs_raw_get': ([C.c_void_p, C.c_char_p, C.c_void_p, C.c_uint32], C.c_int),
            'test_store_new': ([C.POINTER(contract.Storage)], C.c_void_p),
            'test_store_free': ([C.c_void_p], None),
            'test_install': ([C.c_void_p, C.c_void_p, C.c_uint32], C.c_int),
            'test_info': ([C.c_void_p, C.c_uint32, C.c_void_p], C.c_int),
            'test_count': ([C.c_void_p], C.c_int),
            'test_status': ([C.c_void_p, C.c_int], C.c_int),
            'test_verify': ([C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32], C.c_int),
            'test_home_start': ([C.c_void_p], C.c_int),
            'test_home_frame': ([C.c_void_p, C.c_uint32, C.c_uint32], C.c_int),
            'test_home_value': ([C.c_void_p], C.c_int),
        }
        for name, (args, result_type) in (signatures | cls.extra_signatures).items():
            fn = getattr(cls.lib, name)
            fn.argtypes, fn.restype = args, result_type
        if not cls.lib.test_runtime_start():
            raise RuntimeError('WAMR init')
        cls.addClassCleanup(cls.lib.test_runtime_stop)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.services = contract.DiskFixture(self.tmp.name, self.lib)
        self.volumes, self.stores = [], []
        self.addCleanup(self.close_all)
        self.volume = self.new_volume()

    def close_all(self):
        for store in self.stores:
            self.lib.test_store_free(store)
        for volume in self.volumes:
            self.lib.test_lfs_free(volume)
        self.stores.clear()
        self.volumes.clear()

    def new_volume(self, image=None, format=True):
        volume = self.lib.test_lfs_new(image, len(image) if image else 0, format)
        self.assertTrue(volume)
        self.volumes.append(volume)
        return volume

    def connect(self, create=True, quota=1024 * 1024):
        self.io = contract.Storage()
        return bool(self.lib.test_lfs_connect(self.volume, C.byref(self.services.io), quota,
                                              create, C.byref(self.io)))

    def open_store(self):
        store = self.lib.test_store_new(C.byref(self.io))
        self.assertTrue(store)
        self.stores.append(store)
        return store

    def install(self, store, pack):
        return bool(self.lib.test_install(store, pack, len(pack)))

    def snapshot(self):
        out = C.create_string_buffer(1024 * 1024)
        self.lib.test_lfs_dump(self.volume, out)
        return out.raw

    def raw_get(self, path):
        out = C.create_string_buffer(65536 + 256)
        n = self.lib.test_lfs_raw_get(self.volume, path.encode(), out, len(out))
        return out.raw[:n] if n >= 0 else None

    def version(self, store, at=0):
        out = C.create_string_buffer(160)
        self.assertTrue(self.lib.test_info(store, at, out))
        return out.value.decode().split('|')[2]


class LittleFsTests(LittleFsFixture, unittest.TestCase):

    def test_real_littlefs_round_trip_and_vm_execution_after_remount(self):
        self.assertTrue(self.connect())
        store = self.open_store()
        self.assertTrue(self.install(store, contract.package(value=7)))
        self.assertTrue(self.install(store, contract.package('game')))
        self.assertTrue(self.install(store, contract.package(value=9, version='1.0.1')))
        self.volume = self.new_volume(self.snapshot(), format=False)
        self.assertTrue(self.lib.test_lfs_mounted(self.volume))
        self.assertTrue(self.connect(create=False))
        reopened = self.open_store()
        self.assertEqual(self.lib.test_count(reopened), 2)
        self.assertEqual(self.version(reopened), '1.0.1')
        self.assertTrue(self.lib.test_home_start(reopened))
        for held in (16, 0):
            self.lib.test_home_frame(reopened, held, 10)
        self.assertEqual(self.lib.test_home_value(reopened), 9)

    def test_unformatted_device_is_not_automatically_erased(self):
        self.volume = self.new_volume(format=False)
        self.assertFalse(self.lib.test_lfs_mounted(self.volume))
        self.assertEqual(self.snapshot(), b'\xff' * (1024 * 1024))
        self.assertFalse(self.connect())

    def test_unowned_nonempty_directory_and_foreign_owner_are_not_adopted(self):
        self.assertFalse(self.connect(create=False))
        self.assertEqual(self.lib.test_lfs_mkdir(self.volume, b'/lab-apps'), 0)
        self.assertTrue(self.lib.test_lfs_raw_put(self.volume, b'/lab-apps/existing', b'keep', 4))
        before = self.snapshot()
        self.assertFalse(self.connect())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.raw_get('/lab-apps/existing'), b'keep')
        self.volume = self.new_volume()
        self.assertEqual(self.lib.test_lfs_mkdir(self.volume, b'/lab-apps'), 0)
        self.assertTrue(self.lib.test_lfs_raw_put(self.volume, b'/lab-apps/owner', b'foreign', 7))
        before = self.snapshot()
        self.assertFalse(self.connect())
        self.assertEqual(self.snapshot(), before)

    def test_callback_paths_owner_and_immutable_blobs_are_protected(self):
        self.assertTrue(self.connect())
        self.assertTrue(self.lib.test_lfs_raw_put(self.volume, b'/outside', b'keep', 4))
        for key in (b'../outside', b'/outside', b'owner', b'INDEX-0', b'a/b', b''):
            self.assertFalse(self.io.put(self.io.context, key, b'bad', 3), key)
        key = b'a' * 64 + b'.lab'
        self.assertTrue(self.io.put(self.io.context, key, b'first', 5))
        self.assertFalse(self.io.put(self.io.context, key, b'other', 5))
        self.assertEqual(self.raw_get('/outside'), b'keep')
        self.assertEqual(self.raw_get('/lab-apps/' + key.decode()), b'first')
        n = C.c_uint32()
        self.assertEqual(self.io.read(self.io.context, b'../outside', None, 0, C.byref(n)), -1)
        self.assertEqual(self.io.read(self.io.context, b'index-1', None, 0, C.byref(n)), 0)

    def test_logical_quota_failure_preserves_current_app_and_disables_mutations(self):
        self.assertTrue(self.connect(quota=3800))
        store = self.open_store()
        self.assertTrue(self.install(store, contract.package(value=7)))
        before = self.raw_get('/lab-apps/index-0')
        self.assertFalse(self.install(store, contract.package('game')))
        self.assertFalse(self.lib.test_status(store, 0))
        self.assertEqual(self.raw_get('/lab-apps/index-0'), before)
        self.assertIsNone(self.raw_get('/lab-apps/index-1'))
        self.assertTrue(self.lib.test_home_start(store))
        for held in (16, 0):
            self.lib.test_home_frame(store, held, 10)
        self.assertEqual(self.lib.test_home_value(store), 7)

    def test_unknown_files_inside_owned_directory_block_writes(self):
        self.assertTrue(self.connect())
        self.assertTrue(self.lib.test_lfs_raw_put(self.volume, b'/lab-apps/unknown', b'keep', 4))
        self.assertFalse(self.io.put(self.io.context, b'index-0', b'x', 1))
        self.assertEqual(self.raw_get('/lab-apps/unknown'), b'keep')

    def test_each_block_write_boundary_recovers_old_or_new_version_with_other_app_intact(self):
        self.assertTrue(self.connect())
        store = self.open_store()
        self.assertTrue(self.install(store, contract.package()))
        game = contract.package('game')
        self.assertTrue(self.install(store, game))
        baseline = self.snapshot()
        game_path = '/lab-apps/' + hashlib.sha256(game).hexdigest() + '.lab'
        update = contract.package(value=9, version='1.0.1')
        self.lib.test_lfs_cut(self.volume, 1000000, False)
        self.assertTrue(self.install(store, update))
        operations = self.lib.test_lfs_operations(self.volume)
        self.assertGreater(operations, 0)
        for partial in (False, True):
            for at in range(operations + 1):
                with self.subTest(cut=at, partial=partial):
                    self.volume = self.new_volume(baseline, format=False)
                    self.assertTrue(self.connect(create=False))
                    candidate = self.open_store()
                    self.lib.test_lfs_cut(self.volume, at, partial)
                    self.install(candidate, update)
                    self.volume = self.new_volume(self.snapshot(), format=False)
                    self.assertTrue(self.lib.test_lfs_mounted(self.volume))
                    self.assertTrue(self.connect(create=False))
                    reopened = self.open_store()
                    self.assertIn(self.version(reopened), ('1.0.0', '1.0.1'))
                    self.assertEqual(self.version(reopened, 1), '1.0.0')
                    self.assertEqual(self.raw_get(game_path), game)
        type(self).cut_summary = {'operations': operations, 'cases': 2 * (operations + 1),
                                   'volume_bytes': 1024 * 1024, 'partial_modes': 2}
