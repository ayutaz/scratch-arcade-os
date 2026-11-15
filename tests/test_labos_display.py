import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.display import LABELS, render, key_mask, build_font, load_font
from labos.home import Home
from labos.repository import Repository
from labos.sdk import make_manifest
import wasmtime


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Repository(Path(self.tmp.name) / 'apps')
        blob = wasmtime.wat2wasm('''(module
          (import "os" "rect" (func $rect (param i32 i32 i32 i32 i32)))
          (func (export "sdk_abi") (result i32) i32.const 2)
          (func (export "init"))
          (func (export "tick") (param i32 i32 i32 i32) (result i32)
            i32.const 1 i32.const 2 i32.const 8 i32.const 8
            i32.const 63488 call $rect i32.const 0))''')
        for name in ('counter', 'game'):
            self.repo.install(make_manifest(name, blob), blob)
        self.home = Home(self.repo)

    def test_committed_font_covers_fixed_japanese_labels(self):
        font = load_font()
        needed = {c for c in ''.join(LABELS) if ord(c) > 127}
        self.assertTrue(needed <= set(font['glyphs']))
        self.assertEqual(font['source_sha256'],
                         'c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f')
        for bits in font['glyphs'].values():
            self.assertEqual(len(bytes.fromhex(bits)), 60)
            self.assertTrue(any(bytes.fromhex(bits)))

    def test_generator_rejects_unpinned_font_before_output(self):
        wrong = Path(self.tmp.name) / 'font.ttf'
        wrong.write_bytes(b'wrong source')
        target = Path(self.tmp.name) / 'glyphs.json'
        with self.assertRaises(ValueError):
            build_font(wrong, target)
        self.assertFalse(target.exists())

    def test_selection_running_and_release_are_distinct_320x240_images(self):
        first = render(self.home)
        self.assertEqual(first.size, (320, 240))
        self.home.frame(4, 0)
        second = render(self.home)
        self.assertNotEqual(first.tobytes(), second.tobytes())
        self.home.frame(0, 1)
        self.home.frame(16, 2)
        self.home.frame(0, 3)
        running = render(self.home)
        self.assertEqual(running.getpixel((2, 3)), (255, 0, 0))
        self.home.frame(192, 4)
        released = render(self.home)
        self.assertNotEqual(running.tobytes(), released.tobytes())
        self.home.frame(0, 5)
        self.assertEqual(render(self.home).size, (320, 240))

    def test_empty_home_and_unknown_title_are_renderable(self):
        self.home.uninstall('counter')
        self.home.uninstall('game')
        self.assertEqual(render(self.home).size, (320, 240))
        blob = wasmtime.wat2wasm('''(module
          (func (export "sdk_abi") (result i32) i32.const 2)
          (func (export "init"))
          (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0))''')
        self.home.install(make_manifest('sample', blob, title='未知の文字'), blob)
        self.assertEqual(render(self.home).size, (320, 240))

    def test_keyboard_contract_has_system_chord_and_no_stuck_release(self):
        self.assertEqual(key_mask({'f', 'x'}), 192)
        self.assertEqual(key_mask({'right', 'z'}), 17)
        self.assertEqual(key_mask(set()), 0)
        self.assertEqual(key_mask({'unmapped'}), 0)

    def test_running_app_owns_full_canvas_without_simulator_help_overlay(self):
        self.home.frame(16, 0)
        self.home.frame(0, 1)
        image = render(self.home)
        self.assertEqual(set(image.crop((100, 20, 300, 160)).getdata()), {(0, 0, 0)})
