"""Public source release boundaries and fresh-checkout entry points."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def module(name):
 p=ROOT/'tools'/(name+'.py')
 spec=importlib.util.spec_from_file_location('release_'+name,p)
 result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

class DistributionTests(unittest.TestCase):
 def test_source_distribution_contains_complete_os_sdk_apps_and_licenses(self):
  for path in ['LICENSE','NOTICE','README.md','uv.lock','AGENTS.md',
   'prototypes/lab-os/native/guest_vm.c','prototypes/lab-os/native/state_service.c',
   'firmware/esp-idf/lab-os-core/main/candidate_main.c',
   'firmware/esp-idf/lab-os-candidate/CMakeLists.txt','prototypes/lab-os/sdk/lab_os.h',
   'apps/lane-catcher/app.c','apps/focus-timer/app.c','apps/voice-recorder/app.c',
   'apps/remote-timer/app.c','boards/scratch-arcade/profile.json']:
   self.assertTrue((ROOT/path).is_file(),path)
  self.assertIn('Apache License',(ROOT/'LICENSE').read_text())
 def test_profile_has_board_settings_without_backup_or_extracted_code(self):
  p=json.loads((ROOT/'boards/scratch-arcade/profile.json').read_text())
  self.assertEqual(p['parts']['Keys'],dict(fn=0,a=39,b=5,x=9,y=4))
  self.assertEqual(p['lcd']['logical_size'],[320,240])
  self.assertFalse(any(k in p for k in ['backup_sha256','source_sha256','local_evidence_sha256','native_trace_sha256','frozen_qstr_count']))
 def test_bootstrap_is_version_pinned_and_import_has_no_download_side_effect(self):
  b=module('bootstrap')
  self.assertEqual(set(b.SOURCES),{'wamr','littlefs','idf'})
  for v in b.SOURCES.values():
   self.assertEqual(len(v['commit']),40);self.assertTrue(v['url'].startswith('https://github.com/'))
  self.assertEqual(b.ZIG['sha256'],'3cc2bab367e185cdfb27501c4b30b1b0653c28d9f73df8dc91488e66ece5fa6b')
 def test_bootstrap_rejects_unsafe_archive_paths_and_links(self):
  import tarfile
  b=module('bootstrap')
  for name,kind in [('ok/../../outside',tarfile.REGTYPE),('/outside',tarfile.REGTYPE),('ok/link',tarfile.SYMTYPE),('ok/hard',tarfile.LNKTYPE)]:
   with self.subTest(name=name),self.assertRaises(ValueError):
    entry=tarfile.TarInfo(name);entry.type=kind;b.safe_members([entry], 'ok')
  entry=tarfile.TarInfo('ok/zig');self.assertEqual(b.safe_members([entry],'ok'),[entry])
 def test_publication_check_rejects_private_files_binaries_and_credentials(self):
  c=module('publication_check')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name,data in [('build/notes.md',b'generated'),('apps/example/build/notes.md',b'generated'),('backups/x.bin',b'private'),('secrets/network.json',b'{}'),('app.bin',b'firmware'),('src/frozen.py',b'x=1'),('src/leak.py',('token="'+'gh'+'p_'+'a'*36+'"').encode())]:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    with self.subTest(name=name),self.assertRaises(ValueError):c.check_paths(root,[name])
   (root/'good.c').write_text('int answer(void){return 42;}\n')
   self.assertEqual(c.check_paths(root,['good.c']),1)

 def test_complete_public_tree_passes_its_own_boundary_check(self):
  import os
  c=module('publication_check');paths=[]
  for folder,dirs,files in os.walk(ROOT):
   dirs[:]=[d for d in dirs if d not in c.FORBIDDEN]
   paths.extend((Path(folder)/name).relative_to(ROOT).as_posix() for name in files)
  self.assertGreater(c.check_paths(ROOT,paths),100)
 def test_existing_wrong_revision_and_modified_dependency_are_rejected(self):
  import subprocess
  b=module('bootstrap')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'dependency';p.mkdir();subprocess.run(['git','init','-q',str(p)],check=True)
   (p/'source.c').write_text('int x;')
   subprocess.run(['git','-C',str(p),'add','source.c'],check=True)
   subprocess.run(['git','-C',str(p),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)
   sha=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
   spec=dict(path='dependency',commit='0'*40)
   with self.assertRaises(ValueError):b.ensure_source(spec,root)
   spec['commit']=sha;self.assertEqual(b.ensure_source(spec,root),p.resolve())
   (p/'source.c').write_text('int changed;')
   with self.assertRaises(ValueError):b.ensure_source(spec,root)
 def test_test_runner_fails_for_skipped_tests_and_passes_real_success(self):
  import subprocess,sys
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test_example.py';p.write_text('import unittest\nclass Example(unittest.TestCase):\n @unittest.skip("missing prerequisite")\n def test_one(self):pass\n')
   run=lambda:subprocess.run([sys.executable,str(ROOT/'tools/test.py'),'--start-directory',d],capture_output=True,text=True)
   result=run();self.assertEqual(result.returncode,1);self.assertIn('Skipped tests are not accepted',result.stderr)
   p.write_text('import unittest\nclass Example(unittest.TestCase):\n def test_one(self):self.assertEqual(2+2,4)\n')
   result=run();self.assertEqual(result.returncode,0,result.stderr)

 def test_dependency_path_rejects_traversal_and_existing_symlink(self):
  b=module('bootstrap')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'link').symlink_to('/tmp',target_is_directory=True)
   for name in ['../outside','/outside','link/source']:
    with self.subTest(name=name),self.assertRaises(ValueError):b.checked_path(root,name)

 def test_flash_entry_refuses_even_when_a_port_and_image_are_given(self):
  import subprocess
  result=subprocess.run(['bash',str(ROOT/'scripts/flash.sh'),'--port','fixture','app.bin'],capture_output=True,text=True)
  self.assertEqual(result.returncode,2);self.assertIn('refused',result.stderr.lower())

 def test_idf_constraints_are_created_once_and_changed_cache_is_rejected(self):
  from unittest import mock
  import hashlib
  b=module('bootstrap');data=b'checked public dependency constraints\n'
  info=dict(url='https://dl.espressif.com/dl/esp-idf/espidf.constraints.v6.1.txt',sha256=hashlib.sha256(data).hexdigest())
  with tempfile.TemporaryDirectory() as d,mock.patch.object(b,'CONSTRAINTS',info),mock.patch.object(b,'download',return_value=data) as fetch:
   p=b.ensure_constraints(Path(d));self.assertEqual(p.read_bytes(),data)
   self.assertEqual(b.ensure_constraints(Path(d)),p);fetch.assert_called_once_with(info['url'],info['sha256'])
   p.write_bytes(b'changed')
   with self.assertRaises(ValueError):b.ensure_constraints(Path(d))
