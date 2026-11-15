import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import wasmtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.home import Home, ResourceLedger
from labos.repository import Repository
from labos.sdk import make_manifest


def guest(body='i32.const 0', memory=''):
    return wasmtime.wat2wasm('''(module
      %s
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "tick") (param $held i32) (param $pressed i32)
        (param $released i32) (param $dt i32) (result i32) %s))''' % (memory, body))


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Repository(Path(self.tmp.name) / 'apps')
        for name in ('game', 'counter'):
            blob = guest()
            self.repo.install(make_manifest(name, blob), blob)
        self.home = Home(self.repo)

    def test_navigation_is_edge_triggered_and_launch_keys_are_shielded(self):
        self.home.frame(4, 0)
        self.assertEqual(self.home.selected_id, 'game')
        self.home.frame(4, 10)
        self.assertEqual(self.home.selected_id, 'game')
        self.home.frame(0, 20)
        self.home.frame(16, 30)
        self.assertEqual(self.home.mode, 'running')
        self.home.frame(16, 40)
        self.assertEqual(self.home.session.input.previous, 16)
        self.assertEqual(self.home.ledger.count, 1)
        self.home.close()
        self.assertEqual(self.home.ledger.count, 0)

    def test_chord_releases_vm_then_waits_for_all_keys_up(self):
        self.home.frame(16, 0)
        session = self.home.session
        self.home.frame(192, 10)
        self.assertTrue(session.closed)
        self.assertEqual(self.home.mode, 'release')
        self.assertIsNone(self.home.session)
        self.assertEqual(self.home.ledger.count, 0)
        self.home.frame(16, 20)
        self.assertEqual(self.home.mode, 'release')
        self.home.frame(0, 30)
        self.assertEqual(self.home.mode, 'home')
        self.home.frame(16, 40)
        self.assertEqual(self.home.mode, 'running')
        self.home.close()

    def test_guest_normal_exit_does_not_quarantine(self):
        blob = guest('local.get $pressed i32.const 64 i32.and i32.eqz i32.eqz')
        self.home.install(make_manifest('counter', blob, '1.1.0'), blob)
        self.home.frame(16, 0)
        self.home.frame(0, 1)
        self.home.frame(64, 2)
        self.assertEqual(self.home.mode, 'release')
        self.home.frame(0, 3)
        self.assertEqual(self.repo.current('counter')['version'], '1.1.0')
        self.assertEqual(self.home.ledger.count, 0)

    def test_loop_out_of_bounds_and_memory_limit_return_to_previous_app(self):
        bodies = [
            ('local.get $pressed if (loop $spin br $spin) end i32.const 0', ''),
            ('local.get $pressed if i32.const 131072 i32.load drop end i32.const 0',
             '(memory 2 2)'),
            ('local.get $pressed if i32.const 1 memory.grow i32.const -1 i32.eq if unreachable end end i32.const 0',
             '(memory 2)'),
        ]
        for body, memory in bodies:
            with self.subTest(body=body):
                blob = guest(body, memory)
                self.home.install(make_manifest('counter', blob, '2.0.0'), blob)
                self.home.frame(16, 0)
                session = self.home.session
                self.home.frame(0, 1)
                self.home.frame(1, 2)
                self.assertTrue(session.closed)
                self.assertEqual(self.home.mode, 'release')
                self.assertEqual(self.home.ledger.count, 0)
                self.assertIn('counter', self.home.failures)
                self.assertEqual(self.repo.current('counter')['version'], '1.0.0')
                self.home.frame(0, 3)
                self.home.frame(4, 4)
                self.home.frame(0, 5)
                self.home.frame(16, 6)
                self.assertEqual(self.home.active_id, 'game')
                self.home.frame(192, 7)
                self.home.frame(0, 8)
                self.home.frame(8, 9)
                self.home.frame(0, 10)

    def test_bad_package_does_not_remove_healthy_home_entries(self):
        target = self.repo._dir('counter', self.repo.index['counter']['current'])
        (target / 'app.wasm').write_bytes(b'broken')
        home = Home(Repository(self.repo.root))
        self.assertEqual([x['id'] for x in home.apps], ['game'])
        self.assertIn('counter', home.failures)

    def test_failed_quarantine_still_releases_vm_and_other_app_can_start(self):
        blob = guest('local.get $pressed if unreachable end i32.const 0')
        self.home.install(make_manifest('counter', blob, '2.0.0'), blob)
        self.home.frame(16, 0)
        session = self.home.session
        self.home.frame(0, 1)
        with patch.object(self.repo, 'quarantine', side_effect=OSError('disk full')):
            self.home.frame(1, 2)
        self.assertTrue(session.closed)
        self.assertEqual(self.home.ledger.count, 0)
        self.assertEqual([x['id'] for x in self.home.apps], ['game'])
        self.home.frame(0, 3)
        self.home.frame(16, 4)
        self.assertEqual(self.home.active_id, 'game')
        self.home.close()

    def test_management_requires_home_and_failed_update_keeps_both_apps(self):
        before = self.repo.load('game')
        self.home.frame(16, 0)
        for method, args in [(self.home.uninstall, ('game',)),
                             (self.home.install, (before[0], before[1]))]:
            with self.assertRaises(RuntimeError):
                method(*args)
        self.home.close()
        bad = guest('unreachable')
        with self.assertRaises(RuntimeError):
            self.home.install(make_manifest('game', bad, '2.0.0'), bad)
        self.assertEqual(self.repo.load('game'), before)
        self.home.uninstall('game')
        self.assertEqual([x['id'] for x in self.home.apps], ['counter'])

    def test_repeated_switching_releases_every_session(self):
        for n in range(30):
            self.home.frame(16, n * 10)
            session = self.home.session
            self.home.frame(192, n * 10 + 1)
            self.assertTrue(session.closed)
            self.home.frame(0, n * 10 + 2)
            self.assertEqual(self.home.ledger.count, 0)
        self.home.close()

    def test_ledger_releases_all_even_if_one_cleanup_fails(self):
        ledger = ResourceLedger()
        events = []
        ledger.acquire('app', 'good', lambda: events.append('closed'))
        ledger.acquire('app', 'bad', lambda: (_ for _ in ()).throw(RuntimeError('cleanup')))
        ledger.acquire('other', 'kept', lambda: events.append('other'))
        errors = ledger.release('app')
        self.assertEqual(len(errors), 1)
        self.assertEqual(events, ['closed'])
        self.assertEqual(ledger.count, 1)
        ledger.release('other')
        self.assertEqual(ledger.count, 0)
