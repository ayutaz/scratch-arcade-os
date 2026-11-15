import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.capture import decode_frame


class CaptureTests(unittest.TestCase):
    def test_fixed_little_endian_rgb565_to_rgb_pixels(self):
        data = bytearray(320 * 240 * 2)
        data[:6] = b'\x00\xf8\xe0\x07\x1f\x00'
        image = decode_frame(data)
        self.assertEqual(image.size, (320, 240))
        self.assertEqual([image.getpixel((x, 0)) for x in range(3)],
                         [(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        self.assertEqual(image.getpixel((319, 239)), (0, 0, 0))

    def test_incomplete_or_extra_frame_is_refused(self):
        import array
        typed_view = memoryview(array.array('I', [0] * 153600))
        for data in (b'', bytes(153599), bytes(153601), '0' * 153600, typed_view):
            with self.assertRaises(ValueError):
                decode_frame(data)
