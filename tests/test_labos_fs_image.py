import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import test_labos_c_store as contract
import test_labos_lfs as fs
import test_labos_flash_volume as volume
from labos.build import build, COMPILER
from labos.package import encode
from labos import fs_image as image

ROOT = contract.ROOT


class SeedPackages:
    @classmethod
    def setUpClass(cls):
        cls.packages_tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.packages_tmp.cleanup)
        cls.packages = []
        for name in ('game', 'counter'):
            manifest, blob = build(name, Path(cls.packages_tmp.name))
            cls.packages.append(encode(manifest, blob))


@unittest.skipUnless(COMPILER.is_file(), '固定Zig compilerが必要')
class FsImageTests(SeedPackages, unittest.TestCase):
    def test_real_sdk_apps_create_identical_image_regardless_of_input_order(self):
        data, meta = image.create_image(self.packages)
        again, other = image.create_image(list(reversed(self.packages)))
        self.assertEqual(data, again)
        self.assertEqual(meta, other)
        self.assertEqual(len(data), 1024 * 1024)
        self.assertEqual(meta['sha256'], hashlib.sha256(data).hexdigest())
        self.assertFalse(meta['device_tested'])
        self.assertIsNone(meta['flash_address'])
        self.assertEqual([app['id'] for app in meta['apps']], ['counter', 'game'])
        self.assertEqual(image.inspect_image(data), meta)

    def test_empty_seed_and_read_only_inspection_reject_damaged_superblocks(self):
        data, meta = image.create_image([], size=65536)
        self.assertEqual(meta['apps'], [])
        mutable = bytearray(data)
        self.assertEqual(image.inspect_image(mutable), meta)
        self.assertEqual(bytes(mutable), data)
        mutable[:8192] = bytes(8192)
        with self.assertRaises(ValueError): image.inspect_image(mutable)
        for raw in (b'', bytes(65537), bytes([255]) * 65536):
            with self.assertRaises(ValueError): image.inspect_image(raw)

    def test_bad_duplicate_oversized_or_nonterminating_packages_fail_without_bundle(self):
        damaged = bytearray(self.packages[0]);damaged[-1] ^= 1
        many = [contract.package('app-' + chr(97 + i)) for i in range(17)]
        looping = contract.package(body='(loop $l br $l) i32.const 0')
        for packages in ([bytes(damaged)], [self.packages[0]] * 2, many, [bytes(16385)], [looping]):
            with self.subTest(packages=len(packages)), self.assertRaises(ValueError): image.create_image(packages)
        for size in (True, 0, 65535, 65537, 8388609):
            with self.assertRaises(ValueError): image.create_image([], size=size)

    def test_bundle_is_create_only_and_contains_hashes_and_no_destination_address(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp:
            out = Path(tmp) / 'seed'
            meta = image.write_bundle(out, self.packages)
            self.assertEqual(json.loads((out / 'image.json').read_text()), meta)
            self.assertEqual(image.inspect_image((out / 'apps.lfs.bin').read_bytes()), meta)
            snapshot = {p.name: p.read_bytes() for p in out.iterdir()}
            with mock.patch.object(image, 'create_image') as create, self.assertRaises(ValueError):
                image.write_bundle(out, self.packages)
            create.assert_not_called()
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, snapshot)

    def test_bundle_rejects_outside_build_and_symlink_ancestors_before_generation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp, tempfile.TemporaryDirectory() as elsewhere:
            link = Path(tmp) / 'redirect';link.symlink_to(elsewhere, target_is_directory=True)
            for path in (Path(elsewhere) / 'seed', Path('/dev/seed'), link / 'seed', ROOT / 'build'):
                with mock.patch.object(image, 'create_image') as create, self.assertRaises(ValueError):
                    image.write_bundle(path, self.packages)
                create.assert_not_called()
            self.assertEqual(list(Path(elsewhere).iterdir()), [])

    def test_failed_metadata_write_removes_only_new_bundle_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp:
            out = Path(tmp) / 'seed'
            original = Path.open
            def fail_metadata(path, *args, **kwargs):
                if path == out / 'image.json': raise OSError('full')
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, 'open', fail_metadata), self.assertRaises(OSError):
                image.write_bundle(out, self.packages)
            self.assertFalse(out.exists())

    def test_cli_and_bounded_regular_package_read(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp:
            folder = Path(tmp);package = folder / 'app.labapp';package.write_bytes(self.packages[0])
            self.assertEqual(image.read_package(package), self.packages[0])
            link = folder / 'link';link.symlink_to(package)
            huge = folder / 'huge';huge.write_bytes(bytes(16385))
            for path in (link, huge, folder, Path('/dev/null')):
                with self.assertRaises(ValueError): image.read_package(path)
            env = {**os.environ, 'PYTHONPATH': str(ROOT / 'prototypes/lab-os')}
            result = subprocess.run(['uv', 'run', '--locked', 'python', '-m', 'labos.fs_image', 'create',
                                     '--output', str(folder / 'seed'), '--package', str(package)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            created = json.loads(result.stdout)
            inspected = subprocess.run(['uv', 'run', '--locked', 'python', '-m', 'labos.fs_image', 'inspect',
                                        str(folder / 'seed/apps.lfs.bin')], cwd=ROOT, env=env,
                                       capture_output=True, text=True, timeout=60)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout), created)

    def test_native_formatter_refuses_target_platform_compile(self):
        source = ROOT / 'prototypes/lab-os/native/fs_image.c'
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(['/usr/bin/clang', '-std=c11', '-DESP_PLATFORM', '-c', str(source),
                                     '-I' + str(ROOT / 'prototypes/lab-os/native'), '-I' + str(fs.LFS),
                                     '-I' + str(contract.SOURCE / 'core/iwasm/include'), '-o', str(Path(tmp) / 'no.o')],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('host-only image builder', result.stderr)

    def test_native_workspace_symlinks_are_rejected_before_compiler_runs(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
            build = Path(tmp) / 'build';build.mkdir()
            workspace = build / 'lab-os-image-tool';workspace.symlink_to(elsewhere, target_is_directory=True)
            with mock.patch.object(image, 'BUILD', build), mock.patch.object(image, 'verify_littlefs'), \
                 mock.patch.object(image.subprocess, 'run', side_effect=AssertionError('compiler reached through symlink')) as compiler, self.assertRaises(ValueError):
                image.create_image([])
            compiler.assert_not_called()
            self.assertEqual(list(Path(elsewhere).iterdir()), [])

    def test_cli_rejects_excess_packages_before_reading_files(self):
        arguments = ['create', '--output', 'build/no-excess-seed'] + ['--package', 'unused'] * 17
        with mock.patch.object(image, 'read_package', side_effect=AssertionError('excess input was read')) as read, \
             self.assertRaises(SystemExit):
            image.main(arguments)
        read.assert_not_called()


class SeedImageTargetTests(SeedPackages, fs.LittleFsFixture, unittest.TestCase):
    extra_sources = volume.FlashVolumeTests.extra_sources
    extra_flags = volume.FlashVolumeTests.extra_flags
    extra_signatures = volume.FlashVolumeTests.extra_signatures

    @classmethod
    def setUpClass(cls):
        SeedPackages.setUpClass.__func__(cls)
        fs.LittleFsFixture.setUpClass.__func__(cls)

    def test_generated_sdk_image_mounts_with_target_driver_and_runs_both_apps(self):
        data, _ = image.create_image(self.packages)
        self.assertTrue(self.lib.test_flash_seed(data, len(data)))
        driver = self.lib.test_flash_new()
        self.addCleanup(self.lib.test_flash_free, driver)
        self.assertTrue(self.lib.test_flash_open(driver, self.services.io, volume.ADDRESS, len(data), len(data)))
        self.assertEqual(self.lib.test_flash_metric(driver, 9), 2)
        self.assertTrue(self.lib.test_flash_home(driver))
        for held in (16, 0, 1): self.assertTrue(self.lib.test_flash_frame(driver, held))
        self.assertEqual(self.lib.test_flash_value(driver), 1)
        self.lib.test_flash_end_home(driver)
        self.assertTrue(self.lib.test_flash_home(driver))
        for held in (4, 0, 16, 0, 16, 0): self.assertTrue(self.lib.test_flash_frame(driver, held))
        for _ in range(30): self.assertTrue(self.lib.test_flash_frame(driver, 1))
        self.assertEqual(self.lib.test_flash_value(driver), 1)
        self.assertFalse(self.lib.test_flash_close(driver))
        self.lib.test_flash_end_home(driver)
        self.assertTrue(self.lib.test_flash_close(driver))
