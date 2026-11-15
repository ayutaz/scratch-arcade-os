"""MacのRAMで初期LittleFSを生成する。実機I/O・Flash操作は持たない。"""
import argparse
from contextlib import contextmanager
import ctypes as C
import hashlib
import itertools
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from .package import decode
from .sdk import Session, make_manifest
from .target import verify_littlefs, LITTLEFS, LITTLEFS_COMMIT

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / 'prototypes/lab-os/native'
HEADERS = ROOT / 'downloads/os-research/wamr-upstream/core/iwasm/include'
BUILD = ROOT / 'build'
MAX_PACKAGE = 16384
HASH = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p)
VERIFY = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_bool)


class Storage(C.Structure):
    _fields_ = [('context', C.c_void_p), ('read', C.c_void_p), ('put', C.c_void_p), ('hash', HASH), ('verify', VERIFY)]


def _size(size):
    if type(size) is not int or not 65536 <= size <= 8388608 or size % 4096:
        raise ValueError('FS size must be 64KiB..8MiB on a 4KiB boundary')


def _verify(blob, pages, fuel, draw):
    manifest = make_manifest('seed', blob)
    manifest.update(memory_pages=pages, fuel=fuel, capabilities=['draw'] if draw else [])
    session = Session(blob, manifest)
    try:
        return not session.frame(0, 0)
    finally:
        session.close()


def _services():
    def digest(context, data, n, out):
        del context
        if n > MAX_PACKAGE or not out or (n and not data): return False
        C.memmove(out, hashlib.sha256(C.string_at(data, n)).digest(), 32)
        return True
    def verify(context, data, n, pages, fuel, draw):
        del context
        if not data or not 8 <= n <= MAX_PACKAGE - 256 or not 1 <= pages <= 2: return False
        try: return _verify(C.string_at(data, n), pages, fuel, draw)
        except Exception: return False
    return Storage(None, None, None, HASH(digest), VERIFY(verify))


@contextmanager
def _native():
    verify_littlefs()
    workspace = BUILD / 'lab-os-image-tool'
    for folder in (BUILD, workspace):
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise ValueError('native workspace must be a real directory')
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as tmp:
        library = Path(tmp) / 'image.dylib'
        result = subprocess.run(['/usr/bin/clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                 '-shared', '-fPIC', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR',
                                 '-I' + str(NATIVE), '-I' + str(LITTLEFS), '-I' + str(HEADERS),
                                 str(NATIVE / 'fs_image.c'), str(NATIVE / 'app_lfs.c'), str(NATIVE / 'app_store.c'),
                                 str(LITTLEFS / 'lfs.c'), str(LITTLEFS / 'lfs_util.c'), '-o', str(library)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode: raise RuntimeError(result.stderr)
        lib = C.CDLL(str(library))
        for name, args, restype in (
            ('new', [C.c_uint32, C.c_void_p, C.POINTER(Storage)], C.c_void_p),
            ('free', [C.c_void_p], None), ('count', [C.c_void_p], C.c_int),
            ('install', [C.c_void_p, C.c_void_p, C.c_uint32], C.c_int),
            ('package', [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32], C.c_int),
            ('dump', [C.c_void_p, C.c_void_p, C.c_uint32], C.c_int)):
            fn = getattr(lib, 'lab_seed_' + name)
            fn.argtypes, fn.restype = args, restype
        yield lib


def _metadata(lib, handle, data):
    count = lib.lab_seed_count(handle)
    if not 0 <= count <= 16: raise ValueError('FS catalog')
    apps = []
    for at in range(count):
        buffer = C.create_string_buffer(MAX_PACKAGE)
        n = lib.lab_seed_package(handle, at, buffer, len(buffer))
        if not 264 <= n <= MAX_PACKAGE: raise ValueError('FS package')
        package = buffer.raw[:n]
        manifest, wasm = decode(package)
        if not _verify(wasm, manifest['memory_pages'], manifest['fuel'], bool(manifest['capabilities'])):
            raise ValueError('package exits during validation')
        apps.append({key: manifest[key] for key in ('id', 'title', 'version', 'memory_pages', 'fuel', 'capabilities')}
                    | {'package_bytes': n, 'package_sha256': hashlib.sha256(package).hexdigest(),
                       'wasm_bytes': len(wasm), 'wasm_sha256': hashlib.sha256(wasm).hexdigest()})
    return {'format': 'lab-os-littlefs-seed-v1', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'littlefs_commit': LITTLEFS_COMMIT, 'geometry': {'read': 16, 'prog': 16, 'block': 4096,
            'cache': 256, 'lookahead': 32, 'block_cycles': 100}, 'apps': apps,
            'flash_address': None, 'device_tested': False, 'current_catalog_only': True}


def create_image(packages, *, size=1048576):
    _size(size)
    try: packages = list(itertools.islice(packages, 17))
    except TypeError as error: raise ValueError('packages required') from error
    if len(packages) > 16: raise ValueError('app count')
    ordered = []
    for package in packages:
        if not isinstance(package, (bytes, bytearray)) or not 264 <= len(package) <= MAX_PACKAGE:
            raise ValueError('package size/type')
        package = bytes(package)
        manifest, _ = decode(package)
        ordered.append((manifest['id'], package))
    ordered.sort()
    if len({key for key, _ in ordered}) != len(ordered): raise ValueError('duplicate app id')
    services = _services()
    with _native() as lib:
        handle = lib.lab_seed_new(size, None, C.byref(services))
        if not handle: raise ValueError('cannot create RAM filesystem')
        try:
            for _, package in ordered:
                if not lib.lab_seed_install(handle, package, len(package)): raise ValueError('package verification or capacity')
            buffer = C.create_string_buffer(size)
            if not lib.lab_seed_dump(handle, buffer, size): raise ValueError('cannot read RAM filesystem')
            data = buffer.raw
            return data, _metadata(lib, handle, data)
        finally:
            lib.lab_seed_free(handle)


def inspect_image(data):
    if not isinstance(data, (bytes, bytearray)): raise ValueError('image bytes required')
    _size(len(data));data = bytes(data)
    services = _services()
    with _native() as lib:
        handle = lib.lab_seed_new(len(data), data, C.byref(services))
        if not handle: raise ValueError('invalid/unowned filesystem')
        try: return _metadata(lib, handle, data)
        finally: lib.lab_seed_free(handle)


def _target(output):
    path = Path(os.path.abspath(output if Path(output).is_absolute() else ROOT / output))
    if path == BUILD or not path.is_relative_to(BUILD): raise ValueError('output must be a new directory under project build/')
    for parent in (BUILD, *reversed(path.parents)):
        if parent == BUILD or parent.is_relative_to(BUILD):
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()): raise ValueError('output parent must be a real directory')
    if path.exists() or path.is_symlink(): raise ValueError('output already exists')
    return path


def write_bundle(output, packages, *, size=1048576):
    path = _target(output)
    data, metadata = create_image(packages, size=size)
    _target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _target(path)
    path.mkdir()
    created = []
    try:
        image = path / 'apps.lfs.bin'
        with image.open('xb') as stream:
            created.append(image);stream.write(data)
        record = path / 'image.json'
        with record.open('x') as stream:
            created.append(record);stream.write(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    except Exception:
        for artifact in reversed(created): artifact.unlink()
        try: path.rmdir()
        except OSError: pass
        raise
    return metadata


def _read_regular(path, limit):
    path = Path(path);info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit: raise ValueError('bounded regular file required')
    with path.open('rb') as stream: data = stream.read(limit + 1)
    if len(data) != info.st_size: raise ValueError('file changed while reading')
    return data


def read_package(path):
    data = _read_regular(path, MAX_PACKAGE)
    decode(data)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mac上だけで初期FSを生成/検査。実機I/Oなし')
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('create')
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--package', type=Path, action='append', default=[])
    create.add_argument('--size', type=int, default=1048576)
    inspect = sub.add_parser('inspect');inspect.add_argument('image', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'create' and len(args.package) > 16:
        parser.error('app count exceeds 16')
    try:
        result = write_bundle(args.output, [read_package(p) for p in args.package], size=args.size) if args.action == 'create' else inspect_image(_read_regular(args.image, 8388608))
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
