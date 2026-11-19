"""先行契約: 固定演算を保った作業領域の寿命共有。実機I/Oなし。"""
import ctypes as C
import math,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CompactFeatureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup);root=Path(cls.temp.name);src=ROOT/'components/voice'
  p=subprocess.run(['clang','-O2','-std=c11','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-shared','-fPIC','-I'+str(src),str(src/'logmel_features.c'),str(src/'logmel_compact.c'),'-lm','-o',str(root/'compact.so')],capture_output=True,text=True,timeout=30)
  if p.returncode:raise AssertionError(p.stderr)
  cls.lib=C.CDLL(str(root/'compact.so'))
  for name in ('pet_logmel_feature_scratch_size','pet_logmel_compact_scratch_size'):getattr(cls.lib,name).restype=C.c_size_t
  for name in ('pet_logmel_features','pet_logmel_features_banked','pet_logmel_compact_features','pet_logmel_compact_features_banked'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t]
 def buffers(self):
  n=self.lib.pet_logmel_compact_scratch_size();self.assertEqual(n,26672)
  b=C.create_string_buffer(b'Z'*(n+32),n+32);base=C.addressof(b)+16
  self.assertEqual(base%8,0);return n,b,base
 def reference(self,pcm):
  out=(C.c_float*2113)();work=C.create_string_buffer(26672)
  self.assertEqual(self.lib.pet_logmel_features(pcm,32000,out,2113,work,26672),1);return bytes(out)
 def test_nonzero_and_silence_outputs_are_bit_identical_and_input_guard_bytes_survive(self):
  for kind in ('silence','tone','chirp','clipped','tail'):
   raw=[0]*32000
   if kind=='tone':raw=[int(3000*math.sin(2*math.pi*220*i/16000)) for i in range(32000)]
   elif kind=='chirp':raw=[int(2200*math.sin(.00009*i*i)) for i in range(32000)]
   elif kind=='clipped':raw=[32767 if i%2 else -32768 for i in range(32000)]
   elif kind=='tail':raw=[0]*28500+[int(2000*math.sin(i*.18)) for i in range(3500)]
   pcm=(C.c_int16*32000)(*raw);saved=bytes(pcm);expected=self.reference(pcm);n,b,base=self.buffers()
   self.assertEqual(self.lib.pet_logmel_compact_features(pcm,32000,base,2113,base,n),1)
   self.assertEqual(C.string_at(base,8452),expected,kind);self.assertEqual(bytes(pcm),saved)
   self.assertEqual(bytes(b)[:16],b'Z'*16);self.assertEqual(bytes(b)[n+16:],b'Z'*16)
 def test_banked_layout_keeps_duration_and_all_features_identical(self):
  raw=[0]*29000+[int(2500*math.sin(i*.19)) for i in range(3000)];pcm=(C.c_int16*32000)(*raw)
  banks=[(C.c_int16*4096)(*raw[i*4096:(i+1)*4096]) for i in range(8)];ptrs=(C.c_void_p*8)(*[C.addressof(b) for b in banks]);n,b,base=self.buffers()
  self.assertEqual(self.lib.pet_logmel_compact_features_banked(ptrs,32000,base,2113,base,n),1)
  self.assertEqual(C.string_at(base,8452),self.reference(pcm));self.assertGreater((C.c_float*2113).from_address(base)[2112],0)
 def test_invalid_alias_alignment_capacity_and_input_overlap_refuse_before_writing(self):
  pcm=(C.c_int16*32000)();n,b,base=self.buffers();saved=bytes(b)
  for samples,out,count,work,size,inputp in ((31999,base,2113,base,n,pcm),(32000,base+4,2113,base,n,pcm),(32000,base,2112,base,n,pcm),(32000,base,2113,base,n-1,pcm),(32000,base+1,2113,base+1,n,pcm),(32000,base,2113,base,n,base),(32000,base,2113,base,n,None)):
   self.assertEqual(self.lib.pet_logmel_compact_features(inputp,samples,out,count,work,size),-1)
   self.assertEqual(bytes(b),saved)
  self.assertEqual(self.lib.pet_logmel_compact_features_banked(None,32000,base,2113,base,n),-1);self.assertEqual(bytes(b),saved)

class CompactVoiceLayoutTests(unittest.TestCase):
 def test_voice_fits_27kb_and_cnn_workspace_does_not_overlap_live_features(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);c=root/'layout.c';c.write_text('''#include "voice_service.h"
#include <stddef.h>
_Static_assert(sizeof(LabVoice)<=27000,"must fit observed fragmented heap");
_Static_assert(offsetof(LabVoice,features)==offsetof(LabVoice,workspace),"features share dead FFT storage");
_Static_assert(offsetof(LabVoice,inference_workspace)>=offsetof(LabVoice,features)+2113*sizeof(float),"live input preserved");
_Static_assert(offsetof(LabVoice,inference_workspace)+12288<=offsetof(LabVoice,workspace)+26672,"same bounded allocation");
int main(void){return 0;}
''')
   p=subprocess.run(['clang','-std=c11','-DLAB_VOICE_LOGMEL=1','-I'+str(ROOT/'prototypes/lab-os/native'),'-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),str(c),'-o',str(root/'layout')],capture_output=True,text=True,timeout=30)
   self.assertEqual(p.returncode,0,p.stderr)
