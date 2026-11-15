"""Cカタログへ渡す固定ヘッダーのパッケージ。署名・配信認証は含まない。"""
import hashlib
import re
import struct

from .sdk import validate,CAPABILITY_BITS

HEADER_SIZE = 256
MAX_WASM = 65536


def encode(manifest, wasm):
    validate(manifest, wasm)
    if len(wasm) > MAX_WASM or manifest['memory_pages'] > 2:
        raise ValueError('target resource profile')
    if not re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', manifest['version']):
        raise ValueError('ASCII version required')
    if '\x7f' in manifest['title']:
        raise ValueError('title control character')
    header = bytearray(HEADER_SIZE)
    header[:8] = b'LABAPP1\0'
    struct.pack_into('<6I', header, 8, 1, 2, manifest['memory_pages'],
                     manifest['fuel'], sum(bit for bit,name in CAPABILITY_BITS if name in manifest['capabilities']), len(wasm))
    header[32:64] = hashlib.sha256(wasm).digest()
    for start, width, key in ((64, 33, 'id'), (97, 81, 'title'), (178, 25, 'version')):
        data = manifest[key].encode('utf-8')
        if len(data) >= width:
            raise ValueError('metadata size')
        header[start:start + len(data)] = data
    return bytes(header) + bytes(wasm)


def decode(package):
    package = bytes(package)
    if len(package) < HEADER_SIZE or package[:8] != b'LABAPP1\0':
        raise ValueError('package header')
    fmt, abi, pages, fuel, flags, size = struct.unpack_from('<6I', package, 8)
    if fmt != 1 or abi != 2 or flags > sum(bit for bit,_ in CAPABILITY_BITS) or len(package) != HEADER_SIZE + size:
        raise ValueError('package schema')
    manifest = {'abi': abi, 'runtime': 'wasm', 'memory_pages': pages, 'fuel': fuel,
                'capabilities': [name for bit,name in CAPABILITY_BITS if flags&bit], 'sha256': package[32:64].hex()}
    try:
        for start, width, key in ((64, 33, 'id'), (97, 81, 'title'), (178, 25, 'version')):
            data = package[start:start + width]
            manifest[key] = data[:data.index(0)].decode('utf-8')
    except (ValueError, UnicodeError) as error:
        raise ValueError('package string') from error
    wasm = package[HEADER_SIZE:]
    # 再エンコード比較でゼロpadding・予約領域・余分な情報も拒否する。
    if encode(manifest, wasm) != package:
        raise ValueError('noncanonical package')
    return manifest, wasm
