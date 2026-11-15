import hashlib
import struct
import sys
import unittest
from pathlib import Path

import wasmtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.package import encode, decode
from labos.sdk import make_manifest


def blob():
    return wasmtime.wat2wasm('''(module
      (func (export "sdk_abi") (result i32) i32.const 2)
      (func (export "init"))
      (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0))''')


class PackageTests(unittest.TestCase):
    def test_network_bit_round_trips_with_every_legacy_permission_combination(self):
        wasm=blob()
        for flags in range(8,16):
            caps=[name for bit,name in ((1,'draw'),(2,'speaker'),(4,'microphone'),(8,'network')) if flags&bit]
            manifest=make_manifest('network-test',wasm,capabilities=caps)
            package=encode(manifest,wasm)
            self.assertEqual(struct.unpack_from('<I',package,24)[0],flags)
            self.assertEqual(decode(package),(manifest,bytes(wasm)))
        for caps in (['network','draw'],['network','network'],['unknown']):
            with self.assertRaises(ValueError):make_manifest('network-test',wasm,capabilities=caps)
    def test_canonical_little_endian_package_round_trip(self):
        wasm = blob()
        manifest = make_manifest('counter', wasm)
        pack = encode(manifest, wasm)
        self.assertEqual(len(pack), 256 + len(wasm))
        self.assertEqual(pack[:8], b'LABAPP1\0')
        self.assertEqual(struct.unpack_from('<6I', pack, 8), (1, 2, 2, 50000, 1, len(wasm)))
        self.assertEqual(pack[32:64], hashlib.sha256(wasm).digest())
        self.assertEqual(decode(pack), (manifest, bytes(wasm)))
        self.assertEqual(encode(*decode(pack)), pack)

    def test_corrupt_noncanonical_or_trailing_bytes_are_rejected(self):
        pack = encode(make_manifest('counter', blob()), blob())
        for offset, value in [(0, 1), (12, 1), (16, 1), (24, 32),
                              (32, 1), (64, 46), (96, 1), (203, 1), (256, 1)]:
            bad = bytearray(pack)
            bad[offset] ^= value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode(bad)
        for bad in (pack[:255], pack[:-1], pack + b'\0'):
            with self.assertRaises(ValueError):
                decode(bad)

    def test_target_profile_rejects_unbounded_memory_and_unrepresentable_metadata(self):
        wasm = blob()
        for change in ({'memory_pages': 3}, {'title': 'bad\x7f'}, {'version': '１.0.0'}):
            manifest = {**make_manifest('counter', wasm), **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode(manifest, wasm)
        wasm = bytes(wasm) + b'\0' * 65536
        with self.assertRaises(ValueError):
            encode(make_manifest('counter', wasm), wasm)

    def test_draw_permission_absence_is_preserved(self):
        wasm = blob()
        manifest = {**make_manifest('counter', wasm), 'capabilities': []}
        self.assertEqual(decode(encode(manifest, wasm)), (manifest, bytes(wasm)))

    def test_audio_capability_bits_round_trip_without_changing_legacy_flags(self):
        wasm=blob()
        for flags in range(8):
            caps=[name for bit,name in ((1,'draw'),(2,'speaker'),(4,'microphone')) if flags&bit]
            manifest=make_manifest('audio-test',wasm,capabilities=caps)
            package=encode(manifest,wasm)
            self.assertEqual(struct.unpack_from('<I',package,24)[0],flags)
            self.assertEqual(decode(package),(manifest,bytes(wasm)))
        bad=bytearray(package);struct.pack_into('<I',bad,24,32)
        with self.assertRaises(ValueError):decode(bad)
