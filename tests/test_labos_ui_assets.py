import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.ui_assets import generate
from labos.display import FONT_PATH


class UiAssetsTests(unittest.TestCase):
    def test_generate_fixed_rom_glyphs_without_full_ttf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = generate(out)
            self.assertEqual(result['glyphs'], 52)
            self.assertEqual(result['bitmap_bytes'], 3120)
            data = (out / 'lab_ui_font.h').read_text()
            self.assertIn('LAB_UI_GLYPH_COUNT 52', data)
            self.assertIn('0x30db', data)  # ホ
            self.assertIn('SIL OFL 1.1', data)
            self.assertNotIn(str(ROOT), data)

    def test_reject_corrupt_source_or_bitmap_before_header_is_written(self):
        original = json.loads(FONT_PATH.read_text())
        for field in ('source', 'size', 'missing', 'bad_hex'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                data = json.loads(json.dumps(original))
                if field == 'source':
                    data['source_sha256'] = '0' * 64
                elif field == 'size':
                    data['size'] = 21
                elif field == 'missing':
                    data['glyphs'].pop('ホ')
                else:
                    data['glyphs']['ホ'] = 'not hex'
                source = out / 'glyphs.json'
                source.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    generate(out, source)
                self.assertFalse((out / 'lab_ui_font.h').exists())
