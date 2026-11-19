"""先行契約: 明示選択のlog-mel CNN、同じ音声API・消去・scalar診断。"""
import ctypes as C
import hashlib,json,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.transfer import Client,TransferError

TABLE=[3505,1220,3063,552,1052]


def assets(directory):
    directory.mkdir();text='#include "dscnn.h"\n'
    sizes=[72,72,128,144,384,21959];rows=[8,8,16,16,24,7]
    for i,(size,count) in enumerate(zip(sizes,rows,strict=True)):
        value='[3136]=32' if i==5 else '0';bias='[6]=512' if i==5 else '0'
        text+=f'static const int8_t w{i}[{size}]={{{value}}};\nstatic const int32_t b{i}[{count}]={{{bias}}};\n'
        text+=f'static const int32_t s{i}[{count}]={{'+(','.join(['5']*7) if i==5 else '0')+'};\n'
    text+='static const int32_t pet_logmel_thresholds[5]={'+','.join(map(str,TABLE))+'};\n'
    text+='static const PetDscnnLayer pet_logmel_layers[6]={'+','.join('{w'+str(i)+',b'+str(i)+',s'+str(i)+','+str(sizes[i])+','+str(rows[i])+','+str(rows[i])+'}' for i in range(6))+'};\n'
    (directory/'logmel_model.h').write_text(text)
    (directory/'logmel_tables.h').write_bytes((ROOT/'components/voice/logmel_tables.h').read_bytes())
    (directory/'weights.npz').write_bytes(b'test-only numeric identity; the fixture weights are in its trusted C header')
    contract=dict(conditioning='hp160',frontend='context-logmel64',peak=4096,samples=32000,rate=16000,features=2113,context_frames=10,time_bins=64,mel_bands=32,duration_scale=4,pooling='fractional_frame_overlap',band_normalization='per_band_mean_divide4',activation='signed_Q5_then_uint8_Q5_ReLU6',logits='signed_int32_Q10')
    meta=dict(runtime='context-logmel-dscnn-v1',input_contract=contract,thresholds_q10=TABLE,numeric_bytes=23411,weights_sha256=hashlib.sha256((directory/'weights.npz').read_bytes()).hexdigest(),header_sha256={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('logmel_tables.h','logmel_model.h')})
    (directory/'decision-metadata.json').write_text(json.dumps(meta));return directory


def compile_service(directory):
    model=assets(directory/'assets');native=ROOT/'prototypes/lab-os/native';component=ROOT/'components/voice'
    sources=[native/'audio_service.c',native/'audio_binding.c',native/'voice_service.c',component/'logmel_features.c',component/'channel_prepare.c',component/'dscnn.c',ROOT/'tests/native/lab_voice_bridge.c']
    command=['clang','-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-shared','-fPIC','-DLAB_VOICE_LOGMEL=1','-I'+str(native),'-I'+str(component),'-I'+str(model),'-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),*map(str,sources),'-lm','-o',str(directory/'voice.so')]
    run=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if run.returncode:raise AssertionError(run.stderr)
    lib=C.CDLL(str(directory/'voice.so'));lib.voice_new.restype=C.c_void_p
    for name in ('voice_free','voice_clean'):getattr(lib,name).argtypes=[C.c_void_p]
    for name in ('voice_poll','voice_value','voice_close'):getattr(lib,name).argtypes=[C.c_void_p,C.c_uint]
    for name in ('voice_call','voice_native_score_status','voice_native_status'):getattr(lib,name).argtypes=[C.c_void_p,C.c_uint,C.c_uint]
    lib.voice_fill_pcm.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_int]
    lib.lab_voice_rejection_threshold.argtypes=[C.c_uint];lib.lab_voice_rejection_threshold.restype=C.c_uint
    return lib


class LogmelVoiceServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup);cls.lib=compile_service(Path(cls.temp.name).resolve())
    def rig(self):
        r=self.lib.voice_new(7);self.assertTrue(r);self.addCleanup(self.lib.voice_free,r);return r
    def record(self,r):
        self.assertEqual(self.lib.voice_call(r,2,2000),1)
        for i in range(125):self.lib.voice_poll(r,i*16)
    def test_silence_reports_revision_five_and_scrubs_pcm_features_and_workspace(self):
        r=self.rig();self.record(r);self.assertEqual(self.lib.voice_call(r,9,0),6)
        self.assertEqual(self.lib.voice_native_status(r,1,15),5);self.assertEqual(self.lib.voice_native_score_status(r,1,9),5)
        self.assertEqual(self.lib.voice_native_score_status(r,1,8),0);self.assertTrue(self.lib.voice_clean(r))
        self.assertEqual(self.lib.voice_native_score_status(r,2,0),-1);self.assertEqual(self.lib.voice_call(r,65537,0),-1)
        self.assertEqual(self.lib.voice_call(r,9,0),-1);self.assertEqual(self.lib.voice_native_score_status(r,1,0),0)
    def test_full_duration_cnn_score_is_identical_in_both_pcm_layouts_and_release_clears_it(self):
        pcm=(C.c_int16*32000)(*([-32768,32767]*16000))
        for contiguous in (0,1):
            r=self.rig();self.record(r);self.assertEqual(self.lib.voice_fill_pcm(r,pcm,32000,contiguous),1)
            self.assertEqual(self.lib.voice_call(r,9,0),0)
            for field,value in ((3,0),(4,6),(5,4096),(6,512),(7,3584),(8,3505),(9,5)):self.assertEqual(self.lib.voice_native_score_status(r,1,field),value)
            self.assertTrue(self.lib.voice_clean(r));self.assertTrue(self.lib.voice_close(r,0));self.assertEqual(self.lib.voice_native_score_status(r,1,0),-1)
    def test_class_specific_thresholds_have_no_legacy_fallback(self):
        for i,v in enumerate(TABLE):self.assertEqual(self.lib.lab_voice_rejection_threshold(i),v)
        for i in (5,6):self.assertEqual(self.lib.lab_voice_rejection_threshold(i),0)
        self.assertEqual(self.lib.lab_voice_rejection_threshold(7),2**32-1)


class LogmelVoiceClientTests(unittest.TestCase):
    def client(self,data):c=Client.__new__(Client);c.failed=False;c._request=Mock(return_value=data);return c
    def test_revision_five_is_accepted_for_status_and_class_specific_scores(self):
        v=[1,1,1,6,0,32000,0,0,0,0,0,0,0,0,0,1,5,2000,1]
        self.assertEqual(self.client(struct.pack('<3Ii2I3i4I2i4I',*v)+bytes(4)).voice_status()['model_revision'],5)
        for top,threshold,result in ((0,3505,5),(4,1052,5),(5,0,5),(6,0,6)):
            v=[1,1,1,result,top,2,100,99,1,threshold,5,2000,1]
            self.assertEqual(self.client(struct.pack('<3Ii2I2i5I',*v)+bytes(28)).voice_scores()['threshold_q10'],threshold)
    def test_future_revision_bad_threshold_and_negative_class_threshold_are_rejected(self):
        for revision,top,threshold in ((6,0,3505),(5,0,4097),(5,6,1)):
            v=[1,1,1,5 if top<5 else top,top,2,100,99,1,threshold,revision,2000,1];c=self.client(struct.pack('<3Ii2I2i5I',*v)+bytes(28))
            with self.assertRaises(TransferError):c.voice_scores()


class LogmelVoiceCMakeTests(unittest.TestCase):
    def configure(self,root,model=None,context=False):
        project=root/'project';project.mkdir();(project/'dummy.c').write_text('int dummy(void){return 0;}\n');path=(ROOT/'firmware/esp-idf/lab-os-core/main/CMakeLists.txt').as_posix()
        (project/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.22)\nproject(voice_config C)\nset(LAB_OS_CANDIDATE TRUE)\nfunction(idf_component_register)\n cmake_parse_arguments(ARG "" "" "SRCS;INCLUDE_DIRS;REQUIRES" ${ARGN})\n add_library(voice_fixture STATIC "${CMAKE_SOURCE_DIR}/dummy.c")\n set(COMPONENT_LIB voice_fixture PARENT_SCOPE)\n file(WRITE "${CMAKE_BINARY_DIR}/selected.txt" "${ARG_SRCS}")\nendfunction()\ninclude("'+path+'")\nget_target_property(flags voice_fixture COMPILE_DEFINITIONS)\nfile(WRITE "${CMAKE_BINARY_DIR}/flags.txt" "${flags}")\n')
        command=['cmake','-S',str(project),'-B',str(root/'build')]
        if model is not None:command.append('-DLAB_VOICE_LOGMEL_ASSETS='+str(model))
        if context:command.append('-DLAB_VOICE_CONTEXT_ASSETS='+str(model if context is True else context))
        return subprocess.run(command,capture_output=True,text=True,timeout=30)
    def test_opt_in_selects_cnn_sources_and_default_retains_legacy(self):
        for enabled in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();model=assets(root/'assets') if enabled else None;r=self.configure(root,model);self.assertEqual(r.returncode,0,r.stderr)
                selected=(root/'build/selected.txt').read_text();flags=(root/'build/flags.txt').read_text()
                if enabled:
                    self.assertIn('/dscnn.c',selected);self.assertIn('/logmel_features.c',selected);self.assertNotIn('/kws_inference.c',selected);self.assertIn('LAB_VOICE_LOGMEL=1',flags)
                else:self.assertIn('/kws_inference.c',selected);self.assertNotIn('/dscnn.c',selected)
    def test_missing_wrong_contract_hash_or_conflicting_runtime_refuses_configuration(self):
        for kind in ('missing','runtime','features','threshold','header','tables','numeric','weights','conflict'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();model=assets(root/'assets');p=model/'decision-metadata.json';m=json.loads(p.read_text())
                if kind=='missing':p.unlink()
                elif kind=='runtime':m['runtime']='legacy'
                elif kind=='features':m['input_contract']['features']=261
                elif kind=='threshold':m['thresholds_q10']=[True]*5
                elif kind=='numeric':m['numeric_bytes']=24577
                elif kind=='header':(model/'logmel_model.h').write_text('bad')
                elif kind=='weights':(model/'weights.npz').write_text('bad')
                elif kind=='tables':
                    (model/'logmel_tables.h').write_text('bad');m['header_sha256']['logmel_tables.h']=hashlib.sha256(b'bad').hexdigest()
                if kind!='missing':p.write_text(json.dumps(m))
                other=False
                if kind=='conflict':
                    from test_voice_context_runtime import assets as context_assets
                    other=context_assets(root/'context')
                self.assertNotEqual(self.configure(root,model,context=other).returncode,0)
    def test_pinned_runtime_sources_and_math_tables_have_no_model_weights(self):
        base=ROOT/'components/voice';p=json.loads((base/'logmel-runtime-provenance.json').read_text());self.assertEqual(p['commit'],'b5e3dce6fae2fd96d01089310f23196bf3d1c55c')
        self.assertEqual(set(p['files']),{'dscnn.c','dscnn.h','logmel_features.c','logmel_features.h','logmel_tables.h'})
        for name,digest in p['files'].items():self.assertEqual(hashlib.sha256((base/name).read_bytes()).hexdigest(),digest)
        self.assertFalse((base/'logmel_model.h').exists());self.assertFalse(p['model_weights_included'])

if __name__=='__main__':unittest.main()

class StatelessSpeakerReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):LogmelVoiceServiceTests.setUpClass.__func__(cls)
    def test_speaker_only_reply_needs_no_recognition_context_but_cannot_classify(self):
        self.lib.voice_detach_context.argtypes=[C.c_void_p]
        r=self.lib.voice_new(3);self.assertTrue(r);self.addCleanup(self.lib.voice_free,r);self.lib.voice_detach_context(r)
        self.assertEqual(self.lib.voice_call(r,9,0),-1);self.assertEqual(self.lib.voice_native_status(r,1,0),-1)
        self.assertEqual(self.lib.voice_call(r,10,0),1);self.assertTrue(self.lib.voice_close(r,0))
