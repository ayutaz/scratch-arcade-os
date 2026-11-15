import ctypes as C
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_labos_input as model

ROOT = model.ROOT


class BoardInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.lib = Path(cls.tmp.name) / 'board-input.so'
        main = ROOT / 'firmware/esp-idf/lab-os-core/main'
        p = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            '-I' + str(ROOT / 'tests/native/input_fixture'), '-I' + str(main),
                            '-I' + str(ROOT / 'prototypes/lab-os/native'),
                            str(ROOT / 'tests/native/lab_board_input_bridge.c'),
                            str(main / 'board_input.c'), str(ROOT / 'prototypes/lab-os/native/input.c'),
                            '-o', str(cls.lib)], capture_output=True, text=True, timeout=30)
        if p.returncode: raise RuntimeError(p.stderr)
        cls.lib = C.CDLL(str(cls.lib))
        cls.lib.test_driver_new.restype = C.c_void_p
        cls.lib.test_driver_free.argtypes = [C.c_void_p]
        cls.lib.test_driver_open.argtypes = [C.c_void_p, C.c_int]
        cls.lib.test_driver_read.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(model.Sample)]
        cls.lib.test_driver_close.argtypes = [C.c_void_p]
        cls.lib.test_values.argtypes = [C.c_int] * 3
        cls.lib.test_mask.restype = C.c_uint64

    def setUp(self):
        self.lib.test_reset()
        self.driver = self.lib.test_driver_new()
        self.addCleanup(self.lib.test_driver_free, self.driver)

    def test_unknown_profile_performs_no_io(self):
        for profile in (0, 2, -1): self.assertFalse(self.lib.test_driver_open(self.driver, profile))
        self.assertEqual([self.lib.test_calls(i) for i in range(8)], [0] * 8)

    def test_gpio_and_adc_configuration_matches_saved_stock_evidence(self):
        self.assertTrue(self.lib.test_driver_open(self.driver, 1))
        meta = json.loads((ROOT / 'boards/scratch-arcade/profile.json').read_text())
        expected = sum(1 << pin for pin in meta['parts']['Keys'].values())
        self.assertEqual(self.lib.test_mask(), expected)
        self.assertEqual([self.lib.test_calls(i) for i in range(4)], [2, 1, 2, 1])
        self.assertEqual(self.lib.test_bad(), 0)
        self.assertFalse(self.lib.test_driver_open(self.driver, 1))  # live ownership is not overwritten.

    def test_two_axes_and_all_physical_buttons_reach_common_filter(self):
        self.assertTrue(self.lib.test_driver_open(self.driver, 1))
        self.lib.test_values(31, 0, 4095)
        out = model.Sample()
        self.assertTrue(self.lib.test_driver_read(self.driver, 0, C.byref(out)))
        self.assertEqual((out.held, out.keys, out.x, out.y), (1 | 8 | 16 | 32 | 64 | 128, 31, -100, 100))
        self.assertEqual(self.lib.test_bad(), 0)

    def test_partial_initialization_failures_release_only_acquired_resources(self):
        for stage, resets, deletes in ((1, 0, 0), (2, 0, 0), (3, 0, 1), (4, 5, 1), (5, 0, 0)):
            self.lib.test_reset();self.lib.test_fault(stage)
            self.assertFalse(self.lib.test_driver_open(self.driver, 1), stage)
            self.assertEqual((self.lib.test_calls(4), self.lib.test_calls(5)), (resets, deletes), stage)
            self.lib.test_fault(0)
            self.assertTrue(self.lib.test_driver_close(self.driver))

    def test_read_failure_never_exposes_partial_input_and_retry_is_possible(self):
        self.assertTrue(self.lib.test_driver_open(self.driver, 1))
        for stage, x, y in ((6, 0, 4095), (10, 2048, 2048), (0, -1, 2048), (0, 2048, 4096)):
            self.lib.test_fault(stage);self.lib.test_values(2, x, y)
            out = model.Sample(255, 31, 100, 100)
            self.assertFalse(self.lib.test_driver_read(self.driver, 10, C.byref(out)))
            self.assertEqual((out.held, out.keys, out.x, out.y), (0, 0, 0, 0))
        self.lib.test_fault(0);self.lib.test_values(0, 2048, 2048)
        self.assertTrue(self.lib.test_driver_read(self.driver, 30, C.byref(out)))
        self.assertEqual(out.held, 0)

    def test_close_is_idempotent_and_failed_cleanup_keeps_ownership_for_retry(self):
        self.assertTrue(self.lib.test_driver_open(self.driver, 1))
        self.lib.test_fault(7)
        self.assertFalse(self.lib.test_driver_close(self.driver))
        self.assertFalse(self.lib.test_driver_open(self.driver, 1))
        self.assertEqual((self.lib.test_calls(4), self.lib.test_calls(5)), (5, 1))
        self.lib.test_fault(0)
        self.assertTrue(self.lib.test_driver_close(self.driver))
        self.assertTrue(self.lib.test_driver_close(self.driver))
        self.assertEqual((self.lib.test_calls(4), self.lib.test_calls(5)), (5, 2))
        self.assertTrue(self.lib.test_driver_open(self.driver, 1))
        self.lib.test_fault(8)
        self.assertFalse(self.lib.test_driver_close(self.driver))
        self.lib.test_fault(0)
        resets = self.lib.test_calls(4)
        self.assertTrue(self.lib.test_driver_close(self.driver))
        self.assertEqual(self.lib.test_calls(4), resets + 1)
