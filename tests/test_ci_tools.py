"""リポジトリ検査と再現可能なソース配布の異常系を先に定義する。"""
import gzip
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class RepositoryCheckTests(unittest.TestCase):
    def test_links_accept_local_files_and_skip_code_examples_and_web_links(self):
        checker = module('check_repository')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'target.md').write_text('# Target\n')
            (root / 'README.md').write_text('[local](target.md#target)\n[web](https://example.invalid)\n```md\n[example](missing.md)\n```\n')
            self.assertEqual(checker.check_markdown(root, ['README.md']), 1)

    def test_links_reject_missing_targets_and_escape_even_when_file_exists(self):
        checker = module('check_repository')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            root.mkdir()
            (root.parent / 'outside.md').write_text('outside')
            for link in ['missing.md', '../outside.md', 'target.md#missing']:
                (root / 'target.md').write_text('# Target\n')
                (root / 'README.md').write_text(f'[broken]({link})\n')
                with self.subTest(link=link), self.assertRaises(ValueError):
                    checker.check_markdown(root, ['README.md'])


class SourceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / '.gitignore').write_text('dist/\n')
        (self.root / 'LICENSE').write_text('Apache License\n')
        (self.root / 'pyproject.toml').write_text('[project]\nversion="0.1.0"\n')
        (self.root / 'README.md').write_text('source\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.git('tag', 'v0.1.0')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def test_source_tarball_is_repeatable_and_manifest_matches_archive(self):
        release = module('source_release')
        first = release.create_release(self.root, 'v0.1.0', self.root / 'dist/one')
        second = release.create_release(self.root, 'v0.1.0', self.root / 'dist/two')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(first.read_bytes())), mode='r:') as archive:
            self.assertIn('scratch-arcade-os-0.1.0/LICENSE', archive.getnames())
            self.assertFalse(any(name.endswith(('.bin', '.pcm')) for name in archive.getnames()))
        manifest = first.with_name('SHA256SUMS').read_text()
        self.assertEqual(manifest, hashlib.sha256(first.read_bytes()).hexdigest() + '  ' + first.name + '\n')

    def test_release_rejects_dirty_sources_version_mismatch_and_wrong_tag_commit(self):
        release = module('source_release')
        for tag in ['v0.2.0', '../main', 'v0.1.0;echo bad']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.create_release(self.root, tag, self.root / 'dist/bad')
        (self.root / 'README.md').write_text('dirty')
        with self.assertRaises(ValueError):
            release.create_release(self.root, 'v0.1.0', self.root / 'dist/dirty')
        self.git('add', '.')
        self.git('commit', '-qm', 'next')
        with self.assertRaises(ValueError):
            release.create_release(self.root, 'v0.1.0', self.root / 'dist/wrong')

    def test_release_rejects_tracked_binary_and_refuses_overwrite_or_alias(self):
        release = module('source_release')
        target = self.root / 'dist/one'
        release.create_release(self.root, 'v0.1.0', target)
        with self.assertRaises(ValueError):
            release.create_release(self.root, 'v0.1.0', target)
        (self.root / 'dist/link').symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            release.create_release(self.root, 'v0.1.0', self.root / 'dist/link/child')
        (self.root / 'firmware.bin').write_bytes(b'not public')
        self.git('add', 'firmware.bin')
        self.git('commit', '-qm', 'binary')
        # A new fixture repo tag/version pair isolates the actual source-boundary rejection.
        (self.root / 'pyproject.toml').write_text('[project]\nversion="0.1.1"\n')
        self.git('add', 'pyproject.toml')
        self.git('commit', '-qm', 'version')
        self.git('tag', 'v0.1.1')
        with self.assertRaisesRegex(ValueError, 'private/generated'):
            release.create_release(self.root, 'v0.1.1', self.root / 'dist/binary')

class IdfSecurityTests(unittest.TestCase):
    def test_idf_environment_keeps_python_checks_with_uv_managed_versions(self):
        import sys
        sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
        from labos.target import environment
        # Official idf_tools self-managed mode skips upstream version caps, not dependency checks.
        env = environment({})
        self.assertEqual(env.get('IDF_PYTHON_CHECK_CONSTRAINTS'), '0')
        self.assertNotIn('IDF_SKIP_CHECK', env)

    def test_idf_lock_uses_fixed_cryptography_without_known_48_series_findings(self):
        import tomllib
        lock = tomllib.loads((ROOT / 'firmware/esp-idf/host-tools/uv.lock').read_text())
        package = next(p for p in lock['package'] if p['name'] == 'cryptography')
        self.assertEqual(package['version'], '50.0.2')
