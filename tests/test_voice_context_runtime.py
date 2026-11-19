"""Opt-in 261-feature runtime: actual C service, CMake selection and scalar client."""
import ctypes as C
import hashlib,json,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.transfer import Client,TransferError

TABLE=[977,2531,1780,181,768]


def assets(directory):
    directory.mkdir();weights=[0]*260+[1]
    text='''#include <stdint.h>
enum {PET_DECISION_HIDDEN=1,PET_DECISION_SHIFT0=0,PET_DECISION_SHIFT1=0};
'''
    text+='static const int8_t pet_decision_weight0[1][261]={{'+','.join(map(str,weights))+'}};\n'
    text+='static const int32_t pet_decision_bias0[1]={0};\n'
    text+='static const int8_t pet_decision_weight1[7][1]={{1},{0},{0},{0},{0},{0},{0}};\n'
    text+='static const int32_t pet_decision_bias1[7]={0,0,0,0,0,0,3120};\n'
    text+='static const int32_t pet_decision_thresholds[5]={'+','.join(map(str,TABLE))+'};\n'
    (directory/'decision_model.h').write_text(text)
    (directory/'feature_tables.h').write_bytes((ROOT/'components/voice/feature_tables.h').read_bytes())
    meta=dict(runtime='context-duration-class-v1',input_contract=dict(conditioning='hp160',frontend='context-duration',peak=4096,samples=32000,rate=16000,features=261,context_frames=10,duration_scale=4),thresholds_q10=TABLE,
              header_sha256={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('feature_tables.h','decision_model.h')})
    (directory/'decision-metadata.json').write_text(json.dumps(meta));return directory


def compile_service(directory):
    model=assets(directory/'assets');native=ROOT/'prototypes/lab-os/native';component=ROOT/'components/voice'
    sources=[native/'audio_service.c',native/'audio_binding.c',native/'voice_service.c',
             component/'decision_features.c',component/'channel_prepare.c',component/'decision_inference.c',ROOT/'tests/native/lab_voice_bridge.c']
    command=['clang','-O2','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC','-DLAB_VOICE_CONTEXT_DURATION=1',
             '-I'+str(native),'-I'+str(component),'-I'+str(model),'-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),*map(str,sources),'-lm','-o',str(directory/'voice.so')]
    run=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if run.returncode:raise AssertionError(run.stderr)
    lib=C.CDLL(str(directory/'voice.so'));lib.voice_new.restype=C.c_void_p
    for name in ('voice_free','voice_clean'):getattr(lib,name).argtypes=[C.c_void_p]
    for name in ('voice_poll','voice_value','voice_close'):getattr(lib,name).argtypes=[C.c_void_p,C.c_uint]
    for name in ('voice_call','voice_native_score_status','voice_native_status'):getattr(lib,name).argtypes=[C.c_void_p,C.c_uint,C.c_uint]
    lib.voice_fill_pcm.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_int]
    lib.lab_voice_rejection_threshold.argtypes=[C.c_uint];lib.lab_voice_rejection_threshold.restype=C.c_uint
    return lib


class ContextVoiceServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.lib=compile_service(Path(cls.temp.name).resolve())

    def rig(self):
        r=self.lib.voice_new(7);self.assertTrue(r);self.addCleanup(self.lib.voice_free,r);return r

    def record(self,r):
        self.assertEqual(self.lib.voice_call(r,2,2000),1)
        for i in range(125):self.lib.voice_poll(r,i*16)

    def test_silence_reports_revision_four_and_no_command_threshold_then_scrubs(self):
        r=self.rig();self.record(r);self.assertEqual(self.lib.voice_call(r,9,0),6)
        self.assertEqual(self.lib.voice_native_score_status(r,1,8),0)
        self.assertEqual(self.lib.voice_native_score_status(r,1,9),4)
        self.assertEqual(self.lib.voice_native_status(r,1,15),4)
        self.assertTrue(self.lib.voice_clean(r));self.assertEqual(self.lib.voice_value(r,1),0)
        self.assertEqual(self.lib.voice_native_score_status(r,2,0),-1)
        self.assertEqual(self.lib.voice_call(r,65537,0),-1)
        self.assertEqual(self.lib.voice_call(r,9,0),-1)
        self.assertEqual(self.lib.voice_native_score_status(r,1,0),0)

    def test_actual_tail_feature_and_top_class_threshold_work_in_both_pcm_layouts(self):
        pcm=(C.c_int16*32000)(*([-32768,32767]*16000))
        for contiguous in (0,1):
            r=self.rig();self.record(r);self.assertEqual(self.lib.voice_fill_pcm(r,pcm,32000,contiguous),1)
            # Tail=4 => logit0=4096, logit6=3120, margin976 < class0 threshold977.
            self.assertEqual(self.lib.voice_call(r,9,0),5)
            for field,value in ((3,0),(4,6),(5,4096),(6,3120),(7,976),(8,977),(9,4)):
                self.assertEqual(self.lib.voice_native_score_status(r,1,field),value)
            self.assertTrue(self.lib.voice_clean(r));self.assertTrue(self.lib.voice_close(r,0))
            self.assertEqual(self.lib.voice_native_score_status(r,1,0),-1)

    def test_each_command_has_its_own_threshold_without_a_global_fallback(self):
        for i,value in enumerate(TABLE):self.assertEqual(self.lib.lab_voice_rejection_threshold(i),value)
        for i in (5,6):self.assertEqual(self.lib.lab_voice_rejection_threshold(i),0)
        self.assertEqual(self.lib.lab_voice_rejection_threshold(7),2**32-1)


class ContextVoiceClientTests(unittest.TestCase):
    def client(self,data):
        c=Client.__new__(Client);c.failed=False;c._request=Mock(return_value=data);return c

    def test_revision_four_status_and_class_specific_scores_are_accepted(self):
        values=[1,1,1,6,0,32000,0,0,0,0,0,0,0,0,0,1,4,2000,1]
        self.assertEqual(self.client(struct.pack('<3Ii2I3i4I2i4I',*values)+bytes(4)).voice_status()['model_revision'],4)
        for top1,threshold,result in ((0,977,5),(1,2531,5),(4,768,5),(5,0,5),(6,0,6)):
            top2=2 if top1!=2 else 3;v=[1,1,1,result,top1,top2,100,99,1,threshold,4,2000,1]
            r=self.client(struct.pack('<3Ii2I2i5I',*v)+bytes(28)).voice_scores()
            self.assertEqual(r['threshold_q10'],threshold)

    def test_unknown_revision_out_of_range_or_noncommand_threshold_are_refused(self):
        for revision,top1,threshold in ((5,0,977),(4,0,4097),(4,6,1)):
            v=[1,1,1,5 if top1<5 else top1,top1,2,100,99,1,threshold,revision,2000,1]
            c=self.client(struct.pack('<3Ii2I2i5I',*v)+bytes(28))
            with self.assertRaises(TransferError):c.voice_scores()
            self.assertTrue(c.failed)


class ContextVoiceCMakeTests(unittest.TestCase):
    def configure(self,root,model=None):
        project=root/'project';project.mkdir();(project/'dummy.c').write_text('int dummy(void){return 0;}\n')
        path=(ROOT/'firmware/esp-idf/lab-os-core/main/CMakeLists.txt').as_posix()
        (project/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.22)
project(voice_config C)
set(LAB_OS_CANDIDATE TRUE)
function(idf_component_register)
  cmake_parse_arguments(ARG "" "" "SRCS;INCLUDE_DIRS;REQUIRES" ${ARGN})
  add_library(voice_fixture STATIC "${CMAKE_SOURCE_DIR}/dummy.c")
  set(COMPONENT_LIB voice_fixture PARENT_SCOPE)
  file(WRITE "${CMAKE_BINARY_DIR}/selected.txt" "${ARG_SRCS}")
endfunction()
include("'''+path+'''")
get_target_property(flags voice_fixture COMPILE_DEFINITIONS)
file(WRITE "${CMAKE_BINARY_DIR}/flags.txt" "${flags}")
''')
        command=['cmake','-S',str(project),'-B',str(root/'build')]
        if model is not None:command.append('-DLAB_VOICE_CONTEXT_ASSETS='+str(model))
        return subprocess.run(command,capture_output=True,text=True,timeout=30)

    def test_default_build_retains_legacy_model_and_context_build_selects_new_runtime(self):
        for enabled in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();model=assets(root/'assets') if enabled else None
                run=self.configure(root,model);self.assertEqual(run.returncode,0,run.stderr)
                selected=(root/'build/selected.txt').read_text();flags=(root/'build/flags.txt').read_text()
                if enabled:
                    self.assertIn('decision_features.c',selected);self.assertIn('decision_inference.c',selected)
                    self.assertNotIn('/channel_features.c',selected);self.assertNotIn('kws_inference.c',selected)
                    self.assertIn('LAB_VOICE_CONTEXT_DURATION=1',flags)
                else:
                    self.assertIn('/channel_features.c',selected);self.assertIn('kws_inference.c',selected)
                    self.assertNotIn('decision_inference.c',selected);self.assertNotIn('LAB_VOICE_CONTEXT_DURATION=1',flags)

    def test_incomplete_wrong_contract_or_changed_headers_fail_at_configuration(self):
        for mode in ('missing','runtime','features','threshold','header','tables'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();model=assets(root/'assets');p=model/'decision-metadata.json';m=json.loads(p.read_text())
                if mode=='missing':p.unlink()
                elif mode=='runtime':m['runtime']='legacy';p.write_text(json.dumps(m))
                elif mode=='features':m['input_contract']['features']=260;p.write_text(json.dumps(m))
                elif mode=='threshold':m['thresholds_q10']=[True]*5;p.write_text(json.dumps(m))
                elif mode=='header':(model/'decision_model.h').write_text('changed')
                else:
                    (model/'feature_tables.h').write_text('changed')
                    m['header_sha256']['feature_tables.h']=hashlib.sha256(b'changed').hexdigest();p.write_text(json.dumps(m))
                run=self.configure(root,model);self.assertNotEqual(run.returncode,0,run.stdout)

    def test_runtime_sources_match_the_pinned_upstream_without_new_model_weights(self):
        base=ROOT/'components/voice';p=json.loads((base/'decision-runtime-provenance.json').read_text())
        self.assertEqual(p['commit'],'727f9d663e22af125ea122928e73b83bc72045e7')
        self.assertEqual(set(p['files']),{'decision_features.c','decision_features.h','decision_inference.c'})
        for name,digest in p['files'].items():self.assertEqual(hashlib.sha256((base/name).read_bytes()).hexdigest(),digest)
        self.assertFalse((base/'decision_model.h').exists())


if __name__=='__main__':unittest.main()
