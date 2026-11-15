"""検査済みタグからsource-only archiveとSHA-256を作成。公開操作はしない。"""
import argparse
import gzip
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def create_release(root, tag, output):
    root = Path(root).resolve()
    if not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', tag):
        raise ValueError('release tag must be vMAJOR.MINOR.PATCH')
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    if tag != 'v' + version:
        raise ValueError('release tag/version mismatch')

    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])

    if git('status', '--porcelain').strip():
        raise ValueError('release requires a clean source checkout')
    try:
        tagged = git('rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}').strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError('release tag missing') from exc
    if tagged != git('rev-parse', 'HEAD').strip():
        raise ValueError('release tag must point at HEAD')
    spec = importlib.util.spec_from_file_location('release_boundary', ROOT / 'tools/publication_check.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    paths = git('ls-files', '-z').decode().strip('\0').split('\0')
    checker.check_paths(root, paths)
    output = Path(output).absolute()
    if not output.is_relative_to(root / 'dist'):
        raise ValueError('release output must be inside dist')
    if '..' in output.parts or any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError('release output may not follow a symlink')
    if output.exists():
        raise ValueError('release output already exists')
    archive = git('archive', '--format=tar', f'--prefix=scratch-arcade-os-{version}/', 'HEAD')
    data = gzip.compress(archive, mtime=0)
    output.mkdir(parents=True)
    filename = output / f'scratch-arcade-os-{version}-source.tar.gz'
    filename.write_bytes(data)
    (output / 'SHA256SUMS').write_text(hashlib.sha256(data).hexdigest() + '  ' + filename.name + '\n')
    return filename


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args(argv)
    path = create_release(ROOT, args.tag, ROOT / 'dist/source-release')
    print(path.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
