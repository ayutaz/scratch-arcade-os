import sys
import hashlib
import json
import tempfile
import tomllib
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.target import environment, command, prepare, IDF_COMMIT
from labos.build import COMPILER
from labos.package import decode
from labos import target
from labos.fs_image import inspect_image


class TargetTests(unittest.TestCase):
    def test_radio_config_disables_persistence_in_existing_and_fresh_builds(self):
        keys = ('CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE',
                'CONFIG_ESP_WIFI_NVS_ENABLED', 'CONFIG_ESP_PHY_INIT_DATA_IN_PARTITION')
        for existing in (False, True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'candidate'
                if existing:
                    output.mkdir()
                    (output / 'sdkconfig').write_text('CONFIG_UNRELATED=y\n' +
                        ''.join(f'{key}=y\n' for key in keys))
                target.enforce_volatile_radio_config(output)
                config = (output / 'sdkconfig').read_text()
                for key in keys:
                    self.assertIn(f'# {key} is not set\n', config)
                    self.assertNotIn(f'{key}=y', config)
                if existing:
                    self.assertIn('CONFIG_UNRELATED=y\n', config)
                target.enforce_volatile_radio_config(output)
                self.assertEqual((output / 'sdkconfig').read_text(), config)

    def test_radio_config_refuses_symlinked_build_or_config_without_modifying_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            config = source / 'sdkconfig'
            config.write_text('CONFIG_ESP_WIFI_NVS_ENABLED=y\n')
            link = root / 'linked'
            link.symlink_to(source, target_is_directory=True)
            with self.assertRaises(ValueError):
                target.enforce_volatile_radio_config(link)
            other = root / 'other'
            other.mkdir()
            (other / 'sdkconfig').symlink_to(config)
            with self.assertRaises(ValueError):
                target.enforce_volatile_radio_config(other)
            self.assertEqual(config.read_text(), 'CONFIG_ESP_WIFI_NVS_ENABLED=y\n')

    def test_both_build_actions_override_unsafe_generated_radio_config_before_idf(self):
        for action in ('build', 'build-candidate'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)
                config = output / 'sdkconfig'
                config.write_text('CONFIG_ESP_WIFI_NVS_ENABLED=y\n')
                def run(cmd, **kwargs):
                    if cmd[0] == 'git':
                        return mock.Mock(stdout=IDF_COMMIT+'\n', returncode=0)
                    self.assertIn('# CONFIG_ESP_WIFI_NVS_ENABLED is not set', config.read_text())
                    return mock.Mock(returncode=0)
                with mock.patch.object(target, 'BUILD', output), \
                     mock.patch.object(target, 'CANDIDATE_BUILD', output), \
                     mock.patch.object(target, 'prepare'), \
                     mock.patch.object(target, 'prepare_candidate'), \
                     mock.patch.object(target, 'verify_littlefs'), \
                     mock.patch.object(target.subprocess, 'run', side_effect=run):
                    self.assertEqual(target.main([action]), 0)

    def test_python_environment_is_separate_and_fixed(self):
        path = ROOT / 'firmware/esp-idf/host-tools'
        project = tomllib.loads((path / 'pyproject.toml').read_text())
        self.assertEqual(project['project']['requires-python'], '>=3.12.13,<3.13')
        self.assertEqual((path / '.python-version').read_text().strip(), '3.12.13')

    def test_environment_only_selects_project_tools(self):
        env = environment({'PATH': '/usr/bin:/bin', 'IDF_PATH': '/foreign',
                           'IDF_TOOLS_PATH': '/foreign', 'ESP_IDF_VERSION': 'wrong'})
        self.assertEqual(env['IDF_PATH'], str(ROOT / '.cache/os-idf-v6.1'))
        self.assertEqual(env['IDF_TOOLS_PATH'], str(ROOT / '.cache/os-idf-tools'))
        self.assertEqual(env['ESP_IDF_VERSION'], '6.1')
        self.assertEqual(env['IDF_TARGET'], 'esp32s3')
        self.assertEqual(env['ESP_ROM_ELF_DIR'], str(ROOT / '.cache/os-idf-tools/tools/esp-rom-elfs/20241011'))
        self.assertEqual(env['IDF_PYTHON_ENV_PATH'], str(ROOT / 'firmware/esp-idf/host-tools/.venv'))
        self.assertNotIn('/foreign', env['PATH'])
        self.assertEqual(IDF_COMMIT, 'fff9895c82d744c7237be8847347bdd1b07c6643')

    def test_only_non_flashing_commands_exist(self):
        for action in ('flash', 'erase-flash', 'monitor', 'efuse', 'write-flash', 'build flash', '', '../flash'):
            with self.assertRaises(ValueError):
                command(action)
        for action in ('build', 'size', '--version'):
            cmd = command(action)
            self.assertEqual(cmd[0], 'uv')
            self.assertIn('--locked', cmd)
            self.assertIn('--python', cmd)
            self.assertIn('3.12.13', cmd)
            self.assertEqual(cmd[-1], action)
            self.assertNotIn('flash', cmd)

    def test_littlefs_source_pin_rejects_wrong_commit_or_modified_build_sources(self):
        def response(stdout='', returncode=0):
            return mock.Mock(stdout=stdout, returncode=returncode)
        with mock.patch.object(target.subprocess, 'run', side_effect=[
            response('6cb4e86540eca0d9ba62500a298385c9d863c8be\n'), response()]):
            target.verify_littlefs()
        for responses in ([response('wrong')],
                          [response('6cb4e86540eca0d9ba62500a298385c9d863c8be'), response(returncode=1)]):
            with mock.patch.object(target.subprocess, 'run', side_effect=responses), self.assertRaises(ValueError):
                target.verify_littlefs()

    @unittest.skipUnless(COMPILER.is_file(), '固定C compilerが必要')
    def test_prepare_embeds_verified_packages_and_records_build_only_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = prepare(Path(tmp))
            self.assertFalse(result['device_tested'])
            self.assertFalse(result['deployable_board_profile'])
            self.assertEqual(set(result['apps']), {'game', 'counter'})
            header = (Path(tmp) / 'generated/lab_apps.h').read_text()
            self.assertTrue((Path(tmp) / 'generated/lab_ui_font.h').is_file())
            self.assertEqual(result['ui_assets']['bitmap_bytes'], 3120)
            seed = (Path(tmp) / 'generated/lab_seed_image.bin').read_bytes()
            self.assertEqual(result['seed_image'], inspect_image(seed))
            self.assertEqual([app['id'] for app in result['seed_image']['apps']], ['counter', 'game'])
            self.assertIsNone(result['seed_image']['flash_address'])
            for name, row in result['apps'].items():
                blob = (Path(tmp) / 'packages' / name / 'app.wasm').read_bytes()
                self.assertEqual(row['bytes'], len(blob))
                self.assertEqual(row['sha256'], hashlib.sha256(blob).hexdigest())
                self.assertIn('lab_' + name, header)
                package = (Path(tmp) / 'packages' / name / 'app.labapp').read_bytes()
                manifest, unpacked = decode(package)
                self.assertEqual(unpacked, blob)
                self.assertEqual(manifest['id'], name)
                self.assertEqual(row['package_bytes'], len(package))
                self.assertEqual(row['package_sha256'], hashlib.sha256(package).hexdigest())
            self.assertEqual(json.loads((Path(tmp) / 'prepared.json').read_text()), result)
