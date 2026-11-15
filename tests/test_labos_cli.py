import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.cli import replay, run_window, main
from labos.build import COMPILER
from labos.home import Home
from labos.repository import Repository


class CliTests(unittest.TestCase):
    @unittest.skipUnless(COMPILER.is_file(), '固定Zig compilerが必要')
    def test_replay_builds_same_packages_and_completes_both_app_lifecycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = replay(root / 'apps', root / 'output')
            self.assertEqual(result['runtime'], 'Wasmtime host / ABI 2')
            self.assertFalse(result['device_tested'])
            self.assertEqual(result['counter'], 1)
            self.assertEqual(result['game_score'], 1)
            self.assertEqual(result['game_position'], [24, 0])
            self.assertEqual(result['trace'][0]['active'], 'counter')
            self.assertEqual(result['trace'][8]['active'], 'game')
            self.assertEqual(result['active_resources'], 0)
            self.assertEqual(result['final_mode'], 'home')
            from PIL import Image
            for name in ('home', 'counter', 'game', 'release'):
                with Image.open(root / 'output' / (name + '.png')) as image:
                    self.assertEqual(image.size, (320, 240))
            self.assertEqual(json.loads((root / 'output/replay.json').read_text()), result)
            repo = Repository(root / 'apps')
            before = repo.load('game')
            self.assertEqual(main(['remove', '--repository', str(root / 'apps'), 'counter']), 0)
            self.assertEqual(Repository(root / 'apps').load('game'), before)

    def test_dummy_window_initializes_renders_and_closes_without_device(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(Repository(Path(tmp) / 'apps'))
            with patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}):
                frames = run_window(home, scale=1, max_frames=3)
            self.assertEqual(frames, 3)
            self.assertEqual(home.ledger.count, 0)

    def test_no_flash_or_serial_subcommand(self):
        proc = subprocess.run([sys.executable, '-m', 'labos.cli', 'flash'],
                              env={**os.environ, 'PYTHONPATH': str(ROOT / 'prototypes/lab-os')},
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 2)
        self.assertIn('invalid choice', proc.stderr)
