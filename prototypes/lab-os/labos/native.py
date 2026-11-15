"""ESP32-S3と共有するC bridgeのホスト用ビルド・有限試験。"""
import json
import subprocess
import tempfile
from pathlib import Path
from .sdk import CAPABILITY_BITS

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'downloads/os-research/wamr-upstream'
WAMR_COMMIT = '25bd7eb63e828e4bd242cc9b38d260b4b31c6605'


def build_probe():
    sha = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                         capture_output=True, text=True, check=True).stdout.strip()
    if sha != WAMR_COMMIT:
        raise ValueError('WAMR source commit')
    build = ROOT / 'build/lab-os-native'
    cmake = ['uvx', '--from', 'cmake==4.1.2', 'cmake']
    with tempfile.TemporaryFile(mode='w+') as log:
        for args in [
            ['-S', str(ROOT / 'prototypes/lab-os/native'), '-B', str(build)],
            ['--build', str(build), '-j', '4'],
        ]:
            result = subprocess.run(cmake + args, stdout=log, stderr=log, timeout=180)
            if result.returncode:
                log.seek(0)
                raise RuntimeError(log.read()[-12000:])
    return build / 'labos-probe'


def run_probe(runner, blobs, frames, *, capabilities=1):
    if type(capabilities) is not int or not 0<=capabilities<=sum(bit for bit,_ in CAPABILITY_BITS):raise ValueError("capability mask")
    script = ','.join(f'{held}:{dt}' for held, dt in frames)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for n, blob in enumerate(blobs):
            path = Path(tmp) / f'{n}.wasm'
            path.write_bytes(blob)
            paths.append(str(path))
        result = subprocess.run([str(runner), *([] if capabilities==1 else ["--caps="+str(capabilities)]), script, *paths],
                                capture_output=True, text=True, check=True, timeout=10)
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
