"""固定ESP-IDFの非書込み専用コマンド。Flash/monitor経路を作らない。"""
import os
import json
import hashlib
import csv
import subprocess
import sys
from pathlib import Path
from .build import build
from .ui_assets import generate
from .package import encode

ROOT = Path(__file__).resolve().parents[3]
IDF_COMMIT = 'fff9895c82d744c7237be8847347bdd1b07c6643'
IDF = ROOT / '.cache/os-idf-v6.1'
TOOLS = ROOT / '.cache/os-idf-tools'
HOST = ROOT / 'firmware/esp-idf/host-tools'
PROJECT = ROOT / 'firmware/esp-idf/lab-os-core'
BUILD = ROOT / 'build/lab-os-target'
CANDIDATE_PROJECT = ROOT / 'firmware/esp-idf/lab-os-candidate'
CANDIDATE_BUILD = ROOT / 'build/lab-os-candidate'
LITTLEFS = ROOT / '.cache/os-littlefs-v2.11.3'
LITTLEFS_COMMIT = '6cb4e86540eca0d9ba62500a298385c9d863c8be'


def enforce_volatile_radio_config(output):
    """生成済みsdkconfigにも適用。無線初期化によるNVS保存を許さない。"""
    output = Path(output)
    config = output / 'sdkconfig'
    if output.is_symlink() or config.is_symlink():
        raise ValueError('radio config must not follow a build/config symlink')
    keys = ('CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE',
            'CONFIG_ESP_WIFI_NVS_ENABLED', 'CONFIG_ESP_PHY_INIT_DATA_IN_PARTITION')
    previous = config.read_text() if config.exists() else ''
    lines = [line for line in previous.splitlines()
             if not any(line.startswith(key + '=') or line == f'# {key} is not set'
                        for key in keys)]
    lines += [f'# {key} is not set' for key in keys]
    updated = '\n'.join(lines) + '\n'
    output.mkdir(parents=True, exist_ok=True)
    if previous != updated:
        config.write_text(updated)


def verify_littlefs():
    result = subprocess.run(['git', '-C', str(LITTLEFS), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, check=False)
    if result.returncode or result.stdout.strip() != LITTLEFS_COMMIT:
        raise ValueError('LittleFS source commit mismatch')
    result = subprocess.run(['git', '-C', str(LITTLEFS), 'diff', '--quiet', 'HEAD', '--',
                             'lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md'],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError('LittleFS build sources modified')


def environment(base=None):
    env = dict(os.environ if base is None else base)
    bins = [TOOLS / 'tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin',
            TOOLS / 'tools/esp32ulp-elf/2.38_20240113/esp32ulp-elf/bin',
            TOOLS / 'tools/cmake/4.0.3/CMake.app/Contents/bin',
            TOOLS / 'tools/ninja/1.12.1']
    env.update(IDF_PATH=str(IDF), IDF_TOOLS_PATH=str(TOOLS),
               ESP_IDF_VERSION='6.1', IDF_TARGET='esp32s3',
               ESP_ROM_ELF_DIR=str(TOOLS / 'tools/esp-rom-elfs/20241011'),
               IDF_PYTHON_ENV_PATH=str(HOST / '.venv'),
               PATH=os.pathsep.join(map(str, bins)) + os.pathsep + env.get('PATH', '/usr/bin:/bin'))
    env.pop('VIRTUAL_ENV', None)
    return env


def command(action):
    if action not in ('build', 'size', '--version', 'build-candidate', 'size-candidate'):
        raise ValueError('non-flashing actions only')
    candidate = action in ('build-candidate', 'size-candidate')
    project, output = (CANDIDATE_PROJECT, CANDIDATE_BUILD) if candidate else (PROJECT, BUILD)
    prefix = ['uv', 'run', '--project', str(HOST), '--python', '3.12.13', '--locked',
              'python', str(IDF / 'tools/idf.py')]
    if action != '--version':
        prefix += ['-C', str(project), '-B', str(output), '-D', 'SDKCONFIG=' + str(output / 'sdkconfig')]
    return prefix + [action.removesuffix('-candidate')]


def candidate_layout(path=None):
    """Validate the new v1 proposal; never read the device's stock table."""
    path = CANDIDATE_PROJECT / 'partitions.csv' if path is None else Path(path)
    rows = list(csv.reader(line for line in path.read_text().splitlines()
                           if line.strip() and not line.lstrip().startswith('#')))
    expected = [('nvs', 'data', 'nvs'), ('phy_init', 'data', 'phy'),
                ('factory', 'app', 'factory'), ('lab_apps', 'data', 'littlefs')]
    if len(rows) != len(expected):
        raise ValueError('candidate partition shape')
    previous = 0x9000
    for row, shape in zip(rows, expected):
        row = [item.strip() for item in row]
        if len(row) != 6 or tuple(row[:3]) != shape or row[5]:
            raise ValueError('candidate partition type/flags')
        address, size = int(row[3], 0), int(row[4], 0)
        if address < previous or address % 4096 or size <= 0 or size % 4096 or address + size > 8 * 1024 * 1024:
            raise ValueError('candidate partition bounds/overlap')
        if row[1] == 'app' and address % 65536:
            raise ValueError('candidate app alignment')
        previous = address + size
    # Seed geometry is fixed at 1MiB for this first link-only profile.
    if size != 1024 * 1024:
        raise ValueError('candidate seed geometry')
    return {'status': 'proposal-only-not-approved-for-flash',
            'csv_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'lab_apps': {'address': address, 'bytes': size, 'quota': size * 7 // 8}}


def prepare_candidate(output=CANDIDATE_BUILD):
    layout = candidate_layout()
    result = prepare(output)
    result['candidate_layout'] = layout
    app = layout['lab_apps']
    lines = ['/* New layout proposal; no device write approved. */']
    for name, key in (('ADDRESS', 'address'), ('BYTES', 'bytes'), ('QUOTA', 'quota')):
        lines.append(f'#define LAB_CANDIDATE_{name} 0x{app[key]:x}u')
    (Path(output) / 'generated/lab_candidate.h').write_text('\n'.join(lines) + '\n')
    (Path(output) / 'prepared.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def prepare(output=BUILD):
    from .fs_image import create_image
    output = Path(output)
    result = {'device_tested': False, 'deployable_board_profile': False,
              'idf_commit': IDF_COMMIT, 'apps': {}}
    lines = ['/* Generated ABI 2 fixtures. No board configuration. */', '#include <stdint.h>']
    seed_packages = []
    for name in ('game', 'counter'):
        manifest, blob = build(name, output / 'packages')
        package = encode(manifest, blob)
        seed_packages.append(package)
        (output / 'packages' / name / 'app.labapp').write_bytes(package)
        result['apps'][name] = {'bytes': len(blob), 'sha256': manifest['sha256'],
                                'package_bytes': len(package),
                                'package_sha256': hashlib.sha256(package).hexdigest()}
        lines.append('static const uint8_t lab_' + name + '[] = {' +
                     ','.join(str(value) for value in blob) + '};')
    generated = output / 'generated'
    generated.mkdir(parents=True, exist_ok=True)
    (generated / 'lab_apps.h').write_text('\n'.join(lines) + '\n')
    result['ui_assets'] = generate(generated)
    seed, result['seed_image'] = create_image(seed_packages)
    seed_path = generated / 'lab_seed_image.bin'
    if seed_path.is_symlink():
        raise ValueError('generated seed image must not be a symlink')
    seed_path.write_bytes(seed)
    (output / 'prepared.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise ValueError('one non-flashing action required')
    cmd = command(argv[0])
    actual = subprocess.run(['git', '-C', str(IDF), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, check=True).stdout.strip()
    if actual != IDF_COMMIT:
        raise ValueError('ESP-IDF source commit mismatch')
    if argv[0] != '--version':
        verify_littlefs()
    if argv[0] == 'build':
        enforce_volatile_radio_config(BUILD)
        prepare()
    elif argv[0] == 'build-candidate':
        enforce_volatile_radio_config(CANDIDATE_BUILD)
        prepare_candidate()
    return subprocess.run(cmd, env=environment(), cwd=ROOT, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
