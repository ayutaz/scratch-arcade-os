"""小さい固定日本語ラベルを矩形へ分解。OS描画上限を緩めない。"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos import app_labels


class LabelTests(unittest.TestCase):
    def test_rectangles_reconstruct_source_pixels_without_overlap_or_budget_overrun(self):
        for key,text in app_labels.LABELS.items():
            pixels=app_labels.bitmap(text);rects=app_labels.rectangles(pixels)
            self.assertTrue(rects);self.assertLessEqual(len(rects),55,(key,len(rects)))
            canvas=[[0]*len(pixels[0]) for _ in pixels]
            for x,y,w,h in rects:
                self.assertTrue(0<=x<x+w<=len(canvas[0]) and 0<=y<y+h<=len(canvas))
                for row in range(y,y+h):
                    for col in range(x,x+w):
                        self.assertEqual(canvas[row][col],0);canvas[row][col]=1
            self.assertEqual(canvas,pixels)
    def test_header_is_repeatable_and_carries_font_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'labels.h';app_labels.generate(p);a=p.read_bytes();app_labels.generate(p)
            self.assertEqual(p.read_bytes(),a)
            self.assertIn(b'lab_label(',a);self.assertIn(b'SIL OFL',a)
            self.assertIn(app_labels.FONT_SHA.encode(),a)

    def test_offline_generation_uses_checked_derived_glyphs_without_original_ttf(self):
        with mock.patch.object(app_labels,'FONT',Path('/missing-original-font.ttf')):
            self.assertTrue(app_labels.bitmap(app_labels.LABELS['START']))
            with tempfile.TemporaryDirectory() as tmp:app_labels.generate(Path(tmp)/'labels.h')

    def test_optional_original_font_matches_committed_derived_pixels(self):
        if not app_labels.FONT.exists():self.skipTest('original OFL font unavailable')
        for text in app_labels.LABELS.values():self.assertEqual(app_labels.rasterize_font(text),app_labels.bitmap(text))
