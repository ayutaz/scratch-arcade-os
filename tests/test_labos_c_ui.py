import ctypes
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.ui_assets import generate
from labos.display import FONT_PATH


@unittest.skipUnless((ROOT / 'downloads/os-research/wamr-upstream/core/iwasm/include/wasm_export.h').is_file(),
                     '固定WAMR headerが必要')
class CUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        folder = Path(cls.tmp.name)
        generate(folder)
        (folder / 'view.c').write_text('''
          #include "ui.h"
          #include <limits.h>
          #include <string.h>
          unsigned audio_notice(void){return LAB_NOTICE_AUDIO;}
          unsigned network_notice(void){return LAB_NOTICE_NETWORK;}
          bool view(unsigned scene,unsigned selected,unsigned notice,unsigned y,uint16_t *pixels) {
            LabHome home={0};home.mode=LAB_HOME;home.selected=selected;home.notice=notice;home.count=2;
            home.apps[0]=(LabAppInfo){.id="counter",.title="カウンター",.version="1.0.0",.enabled=true};
            home.apps[1]=(LabAppInfo){.id="game",.title="ゲーム",.version="1.0.0",.enabled=true};
            if(scene==1 || scene==9) {
              home.mode=LAB_RUNNING;home.vm.draw_count=2;
              int32_t bg[5]={0,0,320,240,0}, red[5]={10,20,5,3,63488};
              memcpy(home.vm.draws[0],bg,sizeof(bg));memcpy(home.vm.draws[1],red,sizeof(red));
              if(scene==9)home.vm.draws[1][0]=INT_MAX;
            } else if(scene==2)home.mode=LAB_RELEASE;
            else if(scene==3)strcpy(home.apps[0].title,"未知の文字");
            else if(scene==4)home.count=0;
            else if(scene==5)home.count=LAB_MAX_APPS+1;
            else if(scene==7){home.mode=LAB_RUNNING;home.vm.draw_count=129;}
            else if(scene==8)home.mode=(LabHomeMode)99;
            return lab_ui_row(&home,y,pixels);
          }
          typedef struct {unsigned rows,fail;} Sink;
          static bool sink(void *ctx,unsigned y,const uint16_t *pixels) {
            Sink *s=ctx;(void)pixels;++s->rows;return y!=s->fail;
          }
          bool scanout(unsigned invalid,unsigned fail,unsigned *rows) {
            LabHome home={0};home.mode=invalid ? (LabHomeMode)99 : LAB_HOME;
            Sink s={0,fail};bool ok=lab_ui_render(&home,sink,&s);*rows=s.rows;return ok;
          }
        ''')
        native = ROOT / 'prototypes/lab-os/native'
        library = folder / 'ui.dylib'
        proc = subprocess.run(['/usr/bin/clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                               '-shared', '-fPIC', '-I' + str(folder), '-I' + str(native),
                               '-I' + str(ROOT / 'downloads/os-research/wamr-upstream/core/iwasm/include'),
                               '-I' + str(ROOT / 'assets/fonts'), str(folder / 'view.c'),
                               str(native / 'ui.c'), '-o', str(library)],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise RuntimeError(proc.stderr)
        cls.library = ctypes.CDLL(str(library))
        cls.view = cls.library.view
        cls.view.argtypes = [ctypes.c_uint] * 4 + [ctypes.POINTER(ctypes.c_uint16)]
        cls.view.restype = ctypes.c_bool
        cls.scanout = cls.library.scanout
        cls.scanout.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        cls.scanout.restype = ctypes.c_bool

    def row(self, scene, y, selected=0, notice=0, valid=True):
        buffer = (ctypes.c_uint16 * 322)(*([0x1234] * 322))
        ptr = ctypes.cast(ctypes.byref(buffer, 2), ctypes.POINTER(ctypes.c_uint16))
        self.assertEqual(self.view(scene, selected, notice, y, ptr), valid)
        self.assertEqual(buffer[0], 0x1234)
        self.assertEqual(buffer[321], 0x1234)
        if not valid:
            self.assertEqual(list(buffer), [0x1234] * 322)
        return list(buffer)[1:321]

    def test_each_row_stays_in_320_pixel_buffer_and_is_deterministic(self):
        for scene in range(5):
            for y in range(240):
                first = self.row(scene, y)
                self.assertEqual(first, self.row(scene, y))

    def test_japanese_header_pixels_match_committed_glyph(self):
        glyph = bytes.fromhex(json.loads(FONT_PATH.read_text())['glyphs']['ホ'])
        fg, bg = ((237 >> 3) << 11) | ((245 >> 2) << 5) | (255 >> 3), ((29 >> 3) << 11) | ((48 >> 2) << 5) | (72 >> 3)
        for y in range(20):
            row = self.row(0, 10 + y)
            for x in range(20):
                on = glyph[y * 3 + x // 8] & (128 >> (x % 8))
                self.assertEqual(row[244 + x], fg if on else bg)

    def test_selection_and_empty_home_are_distinct(self):
        self.assertNotEqual(self.row(0, 56, selected=0), self.row(0, 56, selected=1))
        self.assertNotEqual(self.row(0, 85), self.row(4, 85))

    def test_running_screen_preserves_all_guest_pixels_without_host_overlay(self):
        for y in (0, 19, 20, 21, 22, 23, 239):
            expected = [0] * 320
            if 20 <= y <= 22:
                expected[10:15] = [63488] * 5
            self.assertEqual(self.row(1, y), expected)

    def test_release_and_fault_notices_are_rendered(self):
        normal = [self.row(2, y, notice=1) for y in range(80, 140)]
        fault = [self.row(2, y, notice=2) for y in range(80, 140)]
        self.assertNotEqual(normal, fault)

    def test_unknown_characters_use_visible_missing_glyph(self):
        fg = ((237 >> 3) << 11) | ((245 >> 2) << 5) | (255 >> 3)
        self.assertEqual(self.row(3, 62)[26], fg)
        self.assertNotEqual(self.row(3, 68)[32], fg)

    def test_invalid_y_state_and_commands_fail_without_writing(self):
        for y in (240, 2**32 - 1):
            self.row(0, y, valid=False)
        for scene in (5, 7, 8, 9):
            self.row(scene, 20, valid=False)
        self.row(0, 20, selected=100, valid=False)

    def test_full_scanout_uses_240_rows(self):
        rows = ctypes.c_uint()
        self.assertTrue(self.scanout(0, 999, ctypes.byref(rows)))
        self.assertEqual(rows.value, 240)

    def test_scanout_stops_after_sink_failure_and_never_writes_invalid_state(self):
        rows = ctypes.c_uint()
        self.assertFalse(self.scanout(0, 5, ctypes.byref(rows)))
        self.assertEqual(rows.value, 6)
        self.assertFalse(self.scanout(1, 999, ctypes.byref(rows)))
        self.assertEqual(rows.value, 0)

    def test_audio_unavailable_notice_is_visible_and_distinct_from_storage_error(self):
        audio=self.row(0,186,notice=self.library.audio_notice())
        self.assertNotEqual(audio,self.row(0,186,notice=0))
        self.assertNotEqual(audio,self.row(0,186,notice=3))
    def test_network_unavailable_notice_is_visible_and_distinct_from_audio_and_storage(self):
        network=self.row(0,186,notice=self.library.network_notice())
        self.assertNotEqual(network,self.row(0,186,notice=0))
        self.assertNotEqual(network,self.row(0,186,notice=self.library.audio_notice()))
        self.assertNotEqual(network,self.row(0,186,notice=3))
