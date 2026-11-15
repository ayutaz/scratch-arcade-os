import ctypes as C
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Sample(C.Structure):
    _fields_ = [('held', C.c_uint32), ('keys', C.c_uint32), ('x', C.c_int32), ('y', C.c_int32)]


class InputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        target = Path(cls.tmp.name) / 'input.so'
        p = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            '-I' + str(ROOT / 'prototypes/lab-os/native'),
                            str(ROOT / 'tests/native/lab_input_bridge.c'),
                            str(ROOT / 'prototypes/lab-os/native/input.c'), '-o', str(target)],
                           text=True, capture_output=True, timeout=30)
        if p.returncode: raise RuntimeError(p.stderr)
        cls.lib = C.CDLL(str(target))
        cls.lib.test_filter_new.restype = C.c_void_p
        cls.lib.test_filter_free.argtypes = [C.c_void_p]
        cls.lib.test_sample.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_int, C.c_uint32, C.POINTER(Sample)]

        cls.lib.test_neutral.argtypes = [C.POINTER(Sample)]

    def setUp(self):
        self.filter = self.lib.test_filter_new()
        self.addCleanup(self.lib.test_filter_free, self.filter)

    def sample(self, keys=0, x=2048, y=2048, now=0):
        out = Sample()
        self.assertTrue(self.lib.test_sample(self.filter, keys, x, y, now, C.byref(out)))
        return out

    def test_known_axis_signs_and_dead_zone(self):
        for raw in range(1928, 2169):
            out = self.sample(x=raw, y=raw)
            self.assertEqual((out.held, out.x, out.y), (0, 0, 0))
        self.assertEqual((self.sample(x=0).held, self.sample(x=4095).held), (1, 2))
        self.assertEqual((self.sample(y=0).held, self.sample(y=4095).held), (4, 8))
        self.assertEqual((self.sample(x=0, y=4095).x, self.sample(x=0, y=4095).y), (-100, 100))

    def test_virtual_direction_uses_strict_40_threshold_after_integer_scaling(self):
        # center + dead zone + 770 => round(77000/1928)=40; +781 =>41.
        self.assertEqual(self.sample(x=2938).held, 0)
        self.assertEqual(self.sample(x=2949).held, 2)
        self.assertEqual(self.sample(x=1158).held, 0)
        self.assertEqual(self.sample(x=1147).held, 1)

    def test_physical_keys_keep_y_and_map_fn_a_b_x_to_abi2(self):
        out = self.sample(keys=31)
        self.assertEqual(out.keys, 31)
        self.assertEqual(out.held, 128 | 16 | 64 | 32)
        other = self.lib.test_filter_new()
        try:
            out = Sample()
            self.assertTrue(self.lib.test_sample(other, 16, 2048, 2048, 0, C.byref(out)))
            self.assertEqual((out.keys, out.held), (16, 0))
        finally: self.lib.test_filter_free(other)

    def test_debounce_press_release_and_bounce(self):
        self.sample(now=0)
        self.assertEqual(self.sample(keys=2, now=10).held, 0)
        self.assertEqual(self.sample(keys=2, now=29).held, 0)
        self.assertEqual(self.sample(keys=2, now=30).held, 16)
        self.assertEqual(self.sample(now=31).held, 16)
        self.assertEqual(self.sample(keys=2, now=40).held, 16)
        self.assertEqual(self.sample(now=50).held, 16)
        self.assertEqual(self.sample(now=70).held, 0)

    def test_key_debounce_is_independent_and_survives_clock_wrap(self):
        self.sample(now=0xfffffff0)
        self.sample(keys=2, now=0xfffffff1)
        self.assertEqual(self.sample(keys=6, now=5).held, 16)
        self.assertEqual(self.sample(keys=6, now=25).held, 16 | 64)

    def test_release_gate_mask_includes_raw_press_and_stable_release_during_debounce(self):
        self.sample(now=0)
        out = self.sample(keys=2, now=1)
        self.assertEqual((out.keys, out.held), (2, 0))
        out = self.sample(keys=2, now=21)
        self.assertEqual((out.keys, out.held), (2, 16))
        out = self.sample(now=22)
        self.assertEqual((out.keys, out.held), (2, 16))
        out = self.sample(now=42)
        self.assertEqual((out.keys, out.held), (0, 0))
        out = self.sample(keys=16, now=43)
        self.assertEqual((out.keys, out.held), (16, 0))

    def test_invalid_sample_is_rejected_without_changing_state_or_output(self):
        self.sample(now=0)
        self.sample(keys=2, now=10)
        for args in [(32, 2048, 2048), (0, -1, 2048), (0, 2048, 4096)]:
            out = Sample(255, 31, 42, -42)
            self.assertFalse(self.lib.test_sample(self.filter, *args, 15, C.byref(out)))
            self.assertEqual((out.held, out.keys, out.x, out.y), (255, 31, 42, -42))
        self.assertEqual(self.sample(keys=2, now=30).held, 16)

    def test_neutral_uses_direction_threshold_without_ignoring_any_physical_key(self):
        for x,y in ((0,-2),(-40,40),(40,-40),(0,0)):
            self.assertTrue(self.lib.test_neutral(C.byref(Sample(0,0,x,y))))
        for sample in (Sample(0,0,41,0),Sample(0,0,0,-41),Sample(1,0,0,0),Sample(0,16,0,0)):
            self.assertFalse(self.lib.test_neutral(C.byref(sample)))
        for x,y in ((1950,1895),(1955,1897)):
            sample=self.sample(x=x,y=y)
            self.assertEqual((sample.held,sample.x,sample.y),(0,0,-2))
            self.assertTrue(self.lib.test_neutral(C.byref(sample)))
