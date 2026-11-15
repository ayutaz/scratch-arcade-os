"""自作appの入口。実コンパイラー/Wasmtimeを使い、実機には接続しない。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.project import create, build_project, check_project, main
from labos.package import decode


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name).resolve() / 'my-app'

    def test_create_build_check_is_reproducible_and_preserves_sources(self):
        create(self.folder, 'my-app', title='My App')
        original = (self.folder / 'app.c').read_bytes()
        first = build_project(self.folder)
        package = Path(first['package']).read_bytes()
        manifest, wasm = decode(package)
        self.assertEqual(manifest['id'], 'my-app')
        self.assertEqual(manifest['title'], 'My App')
        self.assertLessEqual(len(package), 16384)
        self.assertEqual(first['wasm_bytes'], len(wasm))
        second = build_project(self.folder)
        self.assertEqual(Path(second['package']).read_bytes(), package)
        checked = check_project(self.folder)
        self.assertTrue(checked['normal_exit'])
        self.assertTrue(checked['resources_closed'])
        self.assertFalse(checked['device_tested'])
        self.assertEqual((self.folder / 'app.c').read_bytes(), original)

    def test_create_does_not_overwrite_existing_or_linked_directory(self):
        self.folder.mkdir()
        sentinel = self.folder / 'keep'; sentinel.write_text('user')
        with self.assertRaises(ValueError): create(self.folder, 'safe')
        link = self.folder.parent / 'link'; link.symlink_to(self.folder)
        with self.assertRaises(ValueError): create(link, 'safe')
        self.assertEqual(sentinel.read_text(), 'user')

    def test_invalid_identity_does_not_create_a_project(self):
        for app_id in ('../app', 'UPPER', '', 'a'*33):
            with self.subTest(app_id=app_id), self.assertRaises(ValueError):
                create(self.folder, app_id)
        self.assertFalse(self.folder.exists())

    def test_build_refuses_unowned_output_and_source_symlink(self):
        create(self.folder, 'safe')
        out = self.folder / 'build'; out.mkdir(); (out/'keep').write_text('user')
        with self.assertRaises(ValueError): build_project(self.folder)
        self.assertEqual((out/'keep').read_text(), 'user')
        (self.folder/'app.c').unlink()
        (self.folder/'app.c').symlink_to(ROOT/'prototypes/lab-os/sdk/game.c')
        with self.assertRaises(ValueError): build_project(self.folder)

    def test_metadata_rejects_paths_unknown_fields_and_wrong_capability_order(self):
        create(self.folder, 'safe')
        path = self.folder / 'app.json'; config=json.loads(path.read_text())
        for change in ({'source':'../outside.c'}, {'unexpected':1},
                       {'capabilities':['speaker','draw']}, {'id':'bad/path'}):
            path.write_text(json.dumps({**config,**change}))
            with self.subTest(change=change), self.assertRaises(ValueError): build_project(self.folder)

    def test_compile_error_never_replaces_last_good_package(self):
        create(self.folder, 'safe'); result=build_project(self.folder)
        package=Path(result['package']); before=package.read_bytes()
        (self.folder/'app.c').write_text('this is not C;')
        with self.assertRaises((ValueError,RuntimeError)): build_project(self.folder)
        self.assertEqual(package.read_bytes(), before)

    def test_cli_new_and_check_use_the_same_project_contract(self):
        import os
        env={**os.environ,'PYTHONPATH':str(ROOT/'prototypes/lab-os')}
        for args in (['new',str(self.folder),'--id','cli-app'],['check',str(self.folder)]):
            proc=subprocess.run(['uv','run','--locked','python','-m','labos.project',*args],
                                cwd=ROOT,env=env,text=True,capture_output=True,timeout=60)
            self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertTrue(json.loads(proc.stdout)['normal_exit'])

    def test_run_uses_existing_window_and_closes_home_on_window_error(self):
        create(self.folder, 'window-app')
        homes=[]
        def window(home):
            homes.append(home)
            self.assertEqual([app['id'] for app in home.apps],['window-app'])
            home.frame(16,0)
            self.assertEqual(home.ledger.count,1)
            raise RuntimeError('window closed unexpectedly')
        with patch('labos.cli.run_window',side_effect=window):
            with self.assertRaisesRegex(RuntimeError,'window closed unexpectedly'):
                main(['run',str(self.folder)])
        self.assertEqual(homes[0].ledger.count,0)
        self.assertEqual(homes[0].mode,'home')
