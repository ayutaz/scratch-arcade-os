import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.sdk import FrameInput,Clock,Session,make_manifest

class InputTests(unittest.TestCase):
 def test_press_hold_release_and_initial_shield(self):
  i=FrameInput(initial=16)
  self.assertEqual(i.sample(16),(16,0,0))
  self.assertEqual(i.sample(0),(0,0,16))
  self.assertEqual(i.sample(1),(1,1,0))
  self.assertEqual(i.sample(1),(1,0,0))
  self.assertEqual(i.sample(4),(4,4,1))
  for bad in (-1,256,True,1.5):
   with self.assertRaises(ValueError):i.sample(bad)
 def test_monotonic_clock_preserves_elapsed(self):
  c=Clock(100);self.assertEqual(c.step(117),17);self.assertEqual(c.step(150),33)
  self.assertEqual(c.step(150),0)
  for bad in (149,True,100000):
   with self.assertRaises(ValueError):c.step(bad)
  self.assertEqual(c.step(160),10)

class SessionTests(unittest.TestCase):
 def module(self,body,abi=2):
  import wasmtime
  return wasmtime.wat2wasm('(module (func (export "sdk_abi") (result i32) i32.const '+str(abi)+') (func (export "init")) '+body+')')
 def test_dt_and_edges_reach_guest(self):
  b=self.module('(global $v (mut i32) (i32.const 0)) (func (export "debug_value") (result i32) global.get $v) (func (export "tick") (param i32 i32 i32 i32) (result i32) global.get $v local.get 1 i32.add local.get 3 i32.add global.set $v i32.const 0)')
  s=Session(b,make_manifest('counter',b),now_ms=100)
  self.assertFalse(s.frame(1,117));self.assertFalse(s.frame(1,150))
  self.assertEqual(s.debug('debug_value'),51)
  s.close();self.assertTrue(s.closed)
  with self.assertRaises(RuntimeError):s.frame(0,160)
 def test_exit_and_fault_close_vm(self):
  b=self.module('(func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 1)')
  s=Session(b,make_manifest('counter',b));self.assertTrue(s.frame(0,10));self.assertTrue(s.closed)
  for body in ('unreachable','(loop $l br $l) i32.const 0'):
   b=self.module('(func (export "tick") (param i32 i32 i32 i32) (result i32) '+body+')')
   s=Session(b,make_manifest('counter',b))
   with self.assertRaises(RuntimeError):s.frame(0,20)
   self.assertTrue(s.closed);self.assertEqual(s.commands,[])
 def test_abi_and_signature_are_checked(self):
  for abi,body in [(1,'(func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0)'),(2,'(func (export "tick") (param i32))')]:
   b=self.module(body,abi)
   with self.assertRaises(RuntimeError):Session(b,make_manifest('counter',b))
 def test_draw_bounds_and_quota(self):
  import wasmtime
  for x,w,repeat in [(319,2,1),(0,1,129)]:
   calls=' '.join(f'i32.const {x} i32.const 0 i32.const {w} i32.const 1 i32.const 1 call $r' for _ in range(repeat))
   b=wasmtime.wat2wasm('(module (import "os" "rect" (func $r (param i32 i32 i32 i32 i32))) (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init")) (func (export "tick") (param i32 i32 i32 i32) (result i32) '+calls+' i32.const 0))')
   s=Session(b,make_manifest('counter',b))
   with self.assertRaises(RuntimeError):s.frame(0,16)
   self.assertTrue(s.closed)
 def test_portable_package_rejects_automatic_start_and_constructor_exports(self):
  import wasmtime
  for extra in ('(func $f (loop $l br $l)) (start $f)',
                '(func (export "__post_instantiate") (loop $l br $l))',
                '(func (export "__wasm_call_ctors") (loop $l br $l))'):
   b=wasmtime.wat2wasm('(module '+extra+' (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init")) (func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0))')
   with self.assertRaises(ValueError):make_manifest('unsafe',b)
  for b in (b'',b'not wasm',b'\x00asm\x01\x00\x00\x00\x00\xff'):
   with self.assertRaises(ValueError):make_manifest('broken',b)
 def test_close_releases_engine_handle_and_is_idempotent(self):
  b=self.module('(func (export "tick") (param i32 i32 i32 i32) (result i32) i32.const 0)')
  s=Session(b,make_manifest('counter',b));s.close();s.close()
  with self.assertRaises(ValueError):s.engine.ptr()
