import ctypes as C
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.ui_assets import generate


class BoardDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        folder = Path(cls.tmp.name)
        generate(folder)
        main = ROOT / 'firmware/esp-idf/lab-os-core/main'
        native = ROOT / 'prototypes/lab-os/native'
        output = folder / 'display.so'
        p = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            '-I' + str(ROOT / 'tests/native/display_fixture'), '-I' + str(main),
                            '-I' + str(native), '-I' + str(folder), '-I' + str(ROOT / 'assets/fonts'),
                            '-I' + str(ROOT / 'downloads/os-research/wamr-upstream/core/iwasm/include'),
                            str(ROOT / 'tests/native/lab_board_display_bridge.c'), str(main / 'board_display.c'),
                            str(native / 'ui.c'), '-o', str(output)], capture_output=True, text=True, timeout=30)
        if p.returncode: raise RuntimeError(p.stderr)
        cls.lib = C.CDLL(str(output))
        cls.lib.test_display_new.restype = C.c_void_p
        for name in ('free', 'close'):
            getattr(cls.lib, 'test_display_' + name).argtypes = [C.c_void_p]
        for name in ('open', 'paint', 'serviced_paint'):
            getattr(cls.lib, 'test_display_' + name).argtypes = [C.c_void_p, C.c_int]
        cls.lib.test_display_row.argtypes = [C.c_void_p, C.c_uint, C.POINTER(C.c_uint16)]

    def setUp(self):
        self.lib.test_display_reset()
        self.display = self.lib.test_display_new()
        self.addCleanup(self.lib.test_display_free, self.display)

    def metric(self, i): return self.lib.test_display_metric(i)
    def calls(self, i): return self.lib.test_display_calls(i)
    def open(self): self.assertTrue(self.lib.test_display_open(self.display, 1))
    def payload(self, i):
        return bytes(self.lib.test_display_byte(i, j) for j in range(self.lib.test_display_length(i)))

    def test_unknown_profile_and_closed_display_never_touch_io(self):
        for profile in (0, 2, -1): self.assertFalse(self.lib.test_display_open(self.display, profile))
        self.assertFalse(self.lib.test_display_row(self.display, 0, None))
        self.assertFalse(self.lib.test_display_paint(self.display, 0))
        self.assertTrue(self.lib.test_display_close(self.display))
        self.assertEqual([self.calls(i) for i in range(20)], [0] * 20)

    def test_fixed_profile_matches_stock_evidence_without_pwm_timer_or_async_buffer(self):
        self.open()
        meta = json.loads((ROOT / 'boards/scratch-arcade/profile.json').read_text())
        lcd = meta['parts']['LCD']
        expected = [lcd['mosi'], -1, lcd['sck'], -1, -1, -1, -1, -1, -1, 640,
                    lcd['cs'], lcd['dc'], 0, meta['lcd']['default_pclk_hz'], 1, 8, 8, lcd['reset'],
                    16, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0]
        self.assertEqual([self.lib.test_display_config(i) for i in range(len(expected))], expected)
        self.assertEqual(self.metric(0), 0)
        self.assertEqual([self.calls(i) for i in (3, 6, 8, 9, 10, 11)], [1] * 6)
        self.assertEqual(self.calls(18), 0)  # stock custom branch bypasses generic panel init.
        before = [self.calls(i) for i in range(20)]
        self.assertFalse(self.lib.test_display_open(self.display, 1))
        self.assertEqual([self.calls(i) for i in range(20)], before)

    def test_custom_commands_and_delays_match_saved_metadata_exactly(self):
        self.open()
        meta = json.loads((ROOT / 'boards/scratch-arcade/profile.json').read_text())['lcd']
        waits = []
        for i, row in enumerate(meta['custom_init']):
            command = bytes.fromhex(row['data_hex'])
            self.assertEqual((self.lib.test_display_command(i), self.payload(i)), (command[0], command[1:]))
            waits.append(2)  # one extra tick preserves the minimum across tick phase.
            if row['explicit_delay_ms']: waits.append(row['explicit_delay_ms'] // 10 + 1)
        waits.append(11)  # minimum 100ms despite an imminent scheduler tick.
        self.assertEqual([self.lib.test_display_wait(i) for i in range(self.metric(9))], waits)

    def test_full_black_frame_finishes_before_backlight_is_enabled(self):
        self.open()
        self.assertGreater(self.metric(6), self.metric(7))
        self.assertEqual((self.metric(8), self.metric(10)), (13 + 240 * 3,) * 2)
        for y in range(240):
            i = 13 + y * 3
            self.assertEqual(self.lib.test_display_command(i), 0x2a)
            self.assertEqual(self.payload(i), b'\x00\x00\x01\x3f')
            self.assertEqual((self.lib.test_display_command(i + 1), self.payload(i + 1)), (0x2b, bytes([0, y, 0, y])))
            self.assertEqual((self.lib.test_display_command(i + 2), self.payload(i + 2)), (0x2c, bytes(640)))
        self.assertEqual(self.metric(1), 1)

    def test_row_is_big_endian_rgb565_and_borrowed_pixels_remain_unchanged(self):
        self.open()
        values = [0xf800, 0x07e0, 0x001f, 0x1234] * 80
        pixels = (C.c_uint16 * 320)(*values)
        i = self.metric(8)
        self.assertTrue(self.lib.test_display_row(self.display, 239, pixels))
        self.assertEqual(self.payload(i + 1), bytes([0, 239, 0, 239]))
        self.assertEqual(self.payload(i + 2), b'\xf8\x00\x07\xe0\x00\x1f\x12\x34' * 80)
        pixels[0] = 0
        self.assertEqual(self.lib.test_display_byte(i + 2, 0), 0xf8)
        self.assertEqual(list(pixels)[1:], values[1:])
        before = self.metric(8)
        self.assertFalse(self.lib.test_display_row(self.display, 240, pixels))
        self.assertFalse(self.lib.test_display_row(self.display, 0, None))
        self.assertEqual(self.metric(8), before)
        self.assertTrue(self.lib.test_display_row(self.display, 0, pixels))

    def test_real_c_renderer_reaches_display_and_invalid_scene_blanks_and_stops(self):
        self.open()
        i = self.metric(8)
        self.assertTrue(self.lib.test_display_paint(self.display, 0))
        self.assertEqual(self.metric(8), i + 720)
        self.assertEqual(self.payload(i + 2), b'\x12\x34' * 320)
        self.assertFalse(self.lib.test_display_paint(self.display, 1))
        self.assertEqual(self.metric(1), 0)
        self.assertFalse(self.lib.test_display_paint(self.display, 0))

    def test_partial_initialization_failures_release_only_owned_resources(self):
        for api, occurrence in [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1),
                                (7, 1), (7, 14), (7, 100), (8, 1), (9, 1), (10, 1), (11, 1), (0, 2)]:
            with self.subTest(api=api, occurrence=occurrence):
                self.lib.test_display_reset()
                self.lib.test_display_fault(api, occurrence)
                self.assertFalse(self.lib.test_display_open(self.display, 1))
                self.lib.test_display_fault(-1, 1)
                self.assertTrue(self.lib.test_display_close(self.display))
                self.assertEqual([self.metric(i) for i in range(6)], [0] * 6)

    def test_row_failure_turns_backlight_off_and_prevents_more_transfers(self):
        for part in range(1, 4):
            with self.subTest(part=part):
                self.open()
                self.lib.test_display_fault(7, self.calls(7) + part)
                pixels = (C.c_uint16 * 320)()
                self.assertFalse(self.lib.test_display_row(self.display, 10, pixels))
                self.assertEqual(self.metric(1), 0)
                before = self.metric(8)
                self.assertFalse(self.lib.test_display_row(self.display, 11, pixels))
                self.assertEqual(self.metric(8), before)
                self.lib.test_display_fault(-1, 1)
                self.assertTrue(self.lib.test_display_close(self.display))
                self.assertEqual(self.metric(0), 0)
                self.lib.test_display_reset()

    def test_cleanup_failure_retains_ownership_for_retry_without_double_release(self):
        for api in (0, 12, 13, 14, 15):
            with self.subTest(api=api):
                self.open()
                self.lib.test_display_fault(api, self.calls(api) + 1)
                self.assertFalse(self.lib.test_display_close(self.display))
                before = [self.calls(i) for i in range(20)]
                self.assertFalse(self.lib.test_display_open(self.display, 1))
                self.assertEqual([self.calls(i) for i in range(20)], before)
                self.lib.test_display_fault(-1, 1)
                self.assertTrue(self.lib.test_display_close(self.display))
                self.assertEqual([self.metric(i) for i in range(6)], [0] * 6)
                self.assertEqual((self.calls(12), self.calls(13), self.calls(14), self.calls(15), self.calls(16)),
                                 tuple(2 if i == api else 1 for i in (12, 13, 14, 15, 16)))
                self.assertTrue(self.lib.test_display_close(self.display))
                self.lib.test_display_reset()

    def test_second_object_cannot_change_live_display_or_release_its_owner(self):
        self.open()
        other = self.lib.test_display_new()
        self.addCleanup(self.lib.test_display_free, other)
        before = [self.calls(i) for i in range(20)]
        self.assertFalse(self.lib.test_display_open(other, 1))
        self.assertTrue(self.lib.test_display_close(other))
        self.assertEqual([self.calls(i) for i in range(20)], before)
        self.assertTrue(self.lib.test_display_paint(self.display, 0))
        self.assertTrue(self.lib.test_display_close(self.display))
        self.assertTrue(self.lib.test_display_open(other, 1))
        self.assertEqual(self.metric(0), 0)

    def test_serviced_frame_calls_only_trusted_hook_after_each_eight_completed_rows(self):
        self.assertFalse(self.lib.test_display_serviced_paint(self.display,0))
        self.assertEqual(self.lib.test_display_service_metric(0),0)
        self.open();start=self.metric(8)
        self.assertTrue(self.lib.test_display_serviced_paint(self.display,0))
        self.assertEqual((self.lib.test_display_service_metric(0),self.lib.test_display_service_metric(1)),(30,0))
        self.assertEqual(self.metric(8)-start,720)
        self.assertEqual(self.payload(start+2),bytes([0x12,0x34])*320)

    def test_serviced_frame_stops_callbacks_on_row_failure_or_invalid_home(self):
        self.open();self.lib.test_display_fault(7,self.calls(7)+30)
        self.assertFalse(self.lib.test_display_serviced_paint(self.display,0))
        self.assertEqual((self.lib.test_display_service_metric(0),self.lib.test_display_service_metric(1)),(1,0))
        self.assertFalse(self.lib.test_display_serviced_paint(self.display,0))
        self.assertEqual(self.lib.test_display_service_metric(0),0)

    def test_invalid_home_never_calls_render_service_or_submits_pixel_rows(self):
        self.open();before=self.metric(8)
        self.assertFalse(self.lib.test_display_serviced_paint(self.display,1))
        self.assertEqual((self.metric(8),self.lib.test_display_service_metric(0)),(before,0))
