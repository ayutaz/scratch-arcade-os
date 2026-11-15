import ctypes as C
import unittest

import test_labos_lfs as fs
import test_labos_c_store as contract

ROOT = contract.ROOT
MAIN = ROOT / 'firmware/esp-idf/lab-os-core/main'
BYTES = 1024 * 1024
# Deliberately fictional table in the host shim. Never a real flash plan.
ADDRESS = 0x400000


class FlashVolumeTests(fs.LittleFsFixture, unittest.TestCase):
    extra_sources = (MAIN / 'flash_volume.c', ROOT / 'tests/native/lab_flash_volume_bridge.c')
    extra_flags = ('-I' + str(MAIN), '-I' + str(ROOT / 'tests/native/flash_fixture'))
    extra_signatures = {
        'test_flash_new': ([], C.c_void_p),
        'test_flash_free': ([C.c_void_p], None),
        'test_flash_seed': ([C.c_void_p, C.c_uint32], C.c_int),
        'test_flash_table': ([C.c_int], None),
        'test_flash_fault': ([C.c_int, C.c_int, C.c_int], None),
        'test_flash_open': ([C.c_void_p, C.POINTER(contract.Storage), C.c_uint32, C.c_uint32, C.c_uint32], C.c_int),
        'test_flash_close': ([C.c_void_p], C.c_int),
        'test_flash_install': ([C.c_void_p, C.c_void_p, C.c_uint32], C.c_int),
        'test_flash_home': ([C.c_void_p], C.c_int),
        'test_flash_end_home': ([C.c_void_p], None),
        'test_flash_frame': ([C.c_void_p, C.c_uint32], C.c_int),
        'test_flash_value': ([C.c_void_p], C.c_int),
        'test_flash_metric': ([C.c_void_p, C.c_int], C.c_int),
        'test_flash_calls': ([C.c_int], C.c_int),
        'test_flash_block': ([C.c_void_p, C.c_int, C.c_uint32, C.c_uint32, C.c_uint32], C.c_int),
        'test_flash_dump': ([C.c_void_p], None),
    }

    def setUp(self):
        self.flash = []
        super().setUp()
        self.assertTrue(self.connect())
        store = self.open_store()
        self.assertTrue(self.install(store, contract.package(value=7)))
        self.seed = self.snapshot()
        self.assertTrue(self.lib.test_flash_seed(self.seed, len(self.seed)))
        self.driver = self.new_flash()

    def close_all(self):
        for driver in self.flash: self.lib.test_flash_free(driver)
        self.flash.clear()
        super().close_all()

    def new_flash(self):
        driver = self.lib.test_flash_new()
        self.assertTrue(driver)
        self.flash.append(driver)
        return driver

    def open(self, driver=None):
        return bool(self.lib.test_flash_open(driver or self.driver, C.byref(self.services.io), ADDRESS, BYTES, BYTES))

    def metric(self, i): return self.lib.test_flash_metric(self.driver, i)
    def calls(self, i): return self.lib.test_flash_calls(i)
    def dump(self):
        out = C.create_string_buffer(BYTES)
        self.lib.test_flash_dump(out)
        return out.raw

    def install_pack(self, pack): return bool(self.lib.test_flash_install(self.driver, pack, len(pack)))
    def run_app(self, value):
        self.assertTrue(self.lib.test_flash_home(self.driver))
        self.assertTrue(self.lib.test_flash_frame(self.driver, 16))
        self.assertTrue(self.lib.test_flash_frame(self.driver, 0))
        self.assertEqual(self.lib.test_flash_value(self.driver), value)

    def test_invalid_layout_or_services_reject_before_partition_queries(self):
        for address, size, quota in ((0, BYTES, BYTES), (ADDRESS + 1, BYTES, BYTES),
                                      (ADDRESS, BYTES - 1, BYTES - 1), (ADDRESS, 4096, 4096),
                                      (0xfffff000, BYTES, BYTES), (ADDRESS, BYTES, 0), (ADDRESS, BYTES, BYTES + 1)):
            self.assertFalse(self.lib.test_flash_open(self.driver, C.byref(self.services.io), address, size, quota))
        self.assertFalse(self.lib.test_flash_open(self.driver, None, ADDRESS, BYTES, BYTES))
        self.assertEqual([self.calls(i) for i in range(6)], [0] * 6)
        self.assertEqual(self.dump(), self.seed)

    def test_table_mismatch_foreign_flags_overlap_and_query_errors_never_write(self):
        for mode in list(range(1, 17)) + [18, 19, 20]:
            with self.subTest(mode=mode):
                self.lib.test_flash_table(mode)
                self.assertFalse(self.open())
                self.assertEqual((self.calls(1), self.calls(2), self.metric(8)), (0, 0, 0))
                self.assertEqual(self.dump(), self.seed)
                self.assertTrue(self.lib.test_flash_close(self.driver))
        self.lib.test_flash_table(0)
        self.assertTrue(self.open())

    def test_valid_owned_volume_mounts_read_only_then_enables_store_without_rewrite(self):
        self.assertTrue(self.open())
        self.assertEqual([self.metric(i) for i in range(6)], [1, 1, 1, 0, 1, 1])
        self.assertEqual((self.calls(1), self.calls(2), self.metric(7), self.metric(8)), (0, 0, 0, 0))
        self.assertEqual(self.dump(), self.seed)
        self.run_app(7)

    def test_optional_state_directory_preserves_read_only_mount_and_legacy_apps(self):
        self.assertEqual(self.lib.test_lfs_mkdir(self.volume,b'/lab-state'),0)
        for owner in (b'lab-os-app-state-v1\n',b'foreign\n'):
            self.assertTrue(self.lib.test_lfs_raw_put(self.volume,b'/lab-state/owner',owner,len(owner)))
            image=self.snapshot();self.assertTrue(self.lib.test_flash_seed(image,len(image)))
            self.assertTrue(self.open());self.assertEqual(self.dump(),image)
            self.assertEqual((self.calls(1),self.calls(2)),(0,0));self.run_app(7)
            self.lib.test_flash_end_home(self.driver);self.assertTrue(self.lib.test_flash_close(self.driver))

    def test_unformatted_or_unowned_or_foreign_owner_is_never_formatted_or_adopted(self):
        images = [bytes([255]) * BYTES]
        self.assertTrue(self.lib.test_lfs_raw_put(self.volume, b'/outside', b'keep', 4))
        images.append(self.snapshot())  # an owner marker alone cannot adopt a mixed root.
        unowned = self.new_volume()
        self.volume = unowned
        images.append(self.snapshot())
        self.assertEqual(self.lib.test_lfs_mkdir(unowned, b'/lab-apps'), 0)
        self.assertTrue(self.lib.test_lfs_raw_put(unowned, b'/lab-apps/owner', b'foreign', 7))
        images.append(self.snapshot())
        for image in images:
            self.assertTrue(self.lib.test_flash_seed(image, len(image)))
            self.assertFalse(self.open())
            self.assertEqual((self.calls(1), self.calls(2), self.metric(8)), (0, 0, 0))
            self.assertEqual(self.dump(), image)
            self.assertTrue(self.lib.test_flash_close(self.driver))

    def test_store_update_survives_close_and_remount_and_executes_real_wasm(self):
        self.assertTrue(self.open())
        self.assertTrue(self.install_pack(contract.package(value=9, version='1.0.1')))
        self.assertGreater(self.calls(1), 0)
        self.assertGreater(self.calls(2), 0)
        self.assertTrue(self.lib.test_flash_close(self.driver))
        self.assertTrue(self.open())
        self.run_app(9)
        self.assertEqual((self.metric(7), self.metric(8)), (0, 0))

    def test_callback_bounds_and_alignment_deny_io_before_touching_fake_flash(self):
        self.assertTrue(self.open())
        before = [self.calls(i) for i in range(3)]
        for op in (0, 1):
            for block, off, n in ((256, 0, 16), (0xffffffff, 0, 16), (0, 4096, 16), (0, 4090, 16),
                                   (0, 1, 16), (0, 0, 15), (0, 0, 0), (0, 0xfffffff0, 32), (0, 0, 0xfffffff0)):
                self.assertLess(self.lib.test_flash_block(self.driver, op, block, off, n), 0)
        self.assertLess(self.lib.test_flash_block(self.driver, 2, 256, 0, 0), 0)
        self.assertEqual([self.calls(i) for i in range(3)], before)
        self.assertEqual(self.lib.test_flash_block(self.driver, 0, 255, 4080, 16), 0)
        self.assertEqual(self.metric(3), 0)
        self.assertEqual(self.dump(), self.seed)

    def test_physical_read_failure_latches_offline_and_cached_store_is_not_reused(self):
        self.assertTrue(self.open())
        self.lib.test_flash_fault(0, self.calls(0) + 1, 0)
        self.assertLess(self.lib.test_flash_block(self.driver, 0, 100, 0, 16), 0)
        before = [self.calls(i) for i in range(3)]
        self.assertEqual((self.metric(0), self.metric(2), self.metric(3), self.metric(4)), (0, 0, 1, 0))
        self.assertFalse(self.install_pack(contract.package(version='1.0.1')))
        self.assertLess(self.lib.test_flash_block(self.driver, 3, 0, 0, 0), 0)
        self.assertLess(self.lib.test_flash_block(self.driver, 0, 100, 0, 16), 0)
        self.assertEqual([self.calls(i) for i in range(3)], before)
        self.lib.test_flash_fault(-1, 1, 0)
        self.assertTrue(self.lib.test_flash_close(self.driver))
        self.assertTrue(self.open())
        self.run_app(7)

    def test_partial_program_failure_stops_writes_and_remount_keeps_previous_app(self):
        self.assertTrue(self.open())
        self.lib.test_flash_fault(1, self.calls(1) + 1, 1)
        self.assertFalse(self.install_pack(contract.package(value=9, version='1.0.1')))
        self.assertEqual((self.metric(0), self.metric(2), self.metric(3)), (0, 0, 1))
        writes = self.calls(1)
        self.assertFalse(self.install_pack(contract.package(value=11, version='1.0.2')))
        self.assertEqual(self.calls(1), writes)
        self.lib.test_flash_fault(-1, 1, 0)
        self.assertTrue(self.lib.test_flash_close(self.driver))
        self.assertTrue(self.open())
        self.run_app(7)

    def test_live_lease_prevents_unmount_and_second_object_cannot_claim_volume(self):
        self.assertTrue(self.open())
        other = self.new_flash()
        before = [self.calls(i) for i in range(6)]
        self.assertFalse(self.open(other))
        self.assertTrue(self.lib.test_flash_close(other))
        self.assertFalse(self.open())
        self.assertEqual([self.calls(i) for i in range(6)], before)
        self.run_app(7)
        self.assertFalse(self.lib.test_flash_close(self.driver))
        self.assertEqual((self.metric(0), self.metric(1), self.metric(6)), (1, 1, 1))
        self.lib.test_flash_end_home(self.driver)
        self.assertTrue(self.lib.test_flash_close(self.driver))
        self.assertTrue(self.open(other))

    def test_mount_read_error_unwinds_without_program_erase_or_iterator_leak(self):
        self.lib.test_flash_fault(0, 1, 0)
        self.assertFalse(self.open())
        self.assertEqual((self.calls(1), self.calls(2), self.metric(8)), (0, 0, 0))
        self.assertEqual(self.dump(), self.seed)
        self.lib.test_flash_fault(-1, 1, 0)
        self.assertTrue(self.open())
