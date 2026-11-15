"""両VM比較用probeの権限指定。物理サービスを結び付けない。"""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"prototypes/lab-os"))
import wasmtime
from labos.native import build_probe,run_probe


class ServiceProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.runner=build_probe()
    def test_audio_permission_can_be_tested_without_physical_backend(self):
        b=bytes(wasmtime.wat2wasm('(module (import "os" "audio_state" (func $s (result i32))) (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init")) (func (export "tick") (param i32 i32 i32 i32) (result i32) call $s drop i32.const 0) (func (export "debug_value") (result i32) call $s))'))
        r=run_probe(self.runner,[b],[(0,16)],capabilities=2)
        self.assertEqual((r[0]['status'],r[0]['value']),('running',-1))
        self.assertEqual(run_probe(self.runner,[b],[(0,16)])[0]['status'],'trap')
    def test_noncanonical_capability_masks_are_rejected_before_spawn(self):
        for mask in (True,-1,32,'3'):
            with self.assertRaises(ValueError):run_probe(self.runner,[],[],capabilities=mask)

    def test_storage_permission_can_be_tested_without_a_backend(self):
        b=bytes(wasmtime.wat2wasm('(module (import "os" "state_status" (func $s (result i32))) (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init")) (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0) (func (export "debug_value") (result i32) call $s))'))
        r=run_probe(self.runner,[b],[(0,16)],capabilities=16)
        self.assertEqual((r[0]['status'],r[0]['value']),('running',-1))
