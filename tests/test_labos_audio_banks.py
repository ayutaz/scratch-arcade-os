"""分割PCMの実allocator/service。GPIO・DMA・実機RAMの試験は含まない。"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AudioBanksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        directory = Path(cls.tmp.name)
        (directory / 'esp_heap_caps.h').write_text('''#include <stddef.h>
#include <stdint.h>
#define MALLOC_CAP_INTERNAL (1u<<11)
#define MALLOC_CAP_8BIT (1u<<2)
void *heap_caps_malloc(size_t,uint32_t);void heap_caps_free(void *);
''')
        cls.executable = directory / 'probe'
        main = ROOT / 'firmware/esp-idf/lab-os-core/main'
        native = ROOT / 'prototypes/lab-os/native'
        result = subprocess.run([
            '/usr/bin/clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-I' + str(directory), '-I' + str(main), '-I' + str(native),
            str(main / 'audio_memory.c'), str(native / 'audio_service.c'),
            str(ROOT / 'tests/native/lab_audio_banks_probe.c'), '-o', str(cls.executable),
        ], text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def test_fragmented_heap_keeps_two_second_record_replay_peak_and_scrub(self):
        result = subprocess.run([str(self.executable), 'record'], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_partial_allocation_failure_scrubs_and_releases_all_owned_banks(self):
        result = subprocess.run([str(self.executable), 'failure'], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_banked_tone_matches_pcm_across_boundaries_and_invalid_layout_is_rejected(self):
        result = subprocess.run([str(self.executable), 'tone'], text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
