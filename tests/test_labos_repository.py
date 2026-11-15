import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.repository import Repository
from labos.sdk import make_manifest
import wasmtime

def app(exit_code='i32.const 0'):
 return wasmtime.wat2wasm('(module (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init")) (func (export "tick") (param i32 i32 i32 i32) (result i32) '+exit_code+'))')

class RepositoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'apps';self.repo=Repository(self.root)
  self.blob=app();self.m=make_manifest('counter',self.blob)
 def test_install_reopen_update_rollback(self):
  self.repo.install(self.m,self.blob)
  self.repo.install({**self.m,'version':'1.0.1'},self.blob)
  self.assertEqual(self.repo.current('counter')['version'],'1.0.1')
  self.repo.rollback('counter');self.assertEqual(self.repo.current('counter')['version'],'1.0.0')
  r=Repository(self.root);m,b=r.load('counter');self.assertEqual(m['version'],'1.0.0');self.assertEqual(b,self.blob)
 def test_invalid_candidate_keeps_old_and_other_app(self):
  self.repo.install(self.m,self.blob)
  self.repo.install(make_manifest('game',self.blob),self.blob)
  bad=app('unreachable')
  with self.assertRaises(RuntimeError):self.repo.install(make_manifest('counter',bad,'2.0.0'),bad)
  self.assertEqual(self.repo.current('counter')['version'],'1.0.0')
  self.assertEqual(self.repo.current('game')['version'],'1.0.0')
 def test_late_failure_quarantines_and_selects_previous(self):
  self.repo.install(self.m,self.blob);self.repo.install({**self.m,'version':'1.0.1'},self.blob)
  self.repo.quarantine('counter')
  self.assertEqual(self.repo.current('counter')['version'],'1.0.0')
  self.repo.quarantine('counter');self.assertIsNone(self.repo.current('counter'))
  self.assertEqual(Repository(self.root).list_apps(),[])
 def test_failed_index_commit_keeps_current(self):
  self.repo.install(self.m,self.blob)
  before=self.repo.load('counter')
  with patch.object(self.repo,'_write_index',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):self.repo.install({**self.m,'version':'2.0.0'},self.blob)
  self.assertEqual(Repository(self.root).load('counter'),before)
 def test_uninstall_and_gc_only_owned_app(self):
  self.repo.install(self.m,self.blob);self.repo.install(make_manifest('game',self.blob),self.blob)
  for n in range(1,6):self.repo.install({**self.m,'version':f'1.0.{n}'},self.blob)
  self.repo.gc();self.assertLessEqual(len(list((self.root/'packages/counter').iterdir())),2)
  before=self.repo.load('game');self.repo.uninstall('counter')
  self.assertFalse((self.root/'packages/counter').exists());self.assertEqual(self.repo.load('game'),before)
 def test_nonempty_unowned_and_symlink_rejected(self):
  foreign=Path(self.tmp.name)/'foreign';foreign.mkdir();(foreign/'keep').write_text('keep')
  with self.assertRaises(ValueError):Repository(foreign)
  link=Path(self.tmp.name)/'link';link.symlink_to(foreign,target_is_directory=True)
  with self.assertRaises(ValueError):Repository(link)
  self.repo.install(self.m,self.blob)
  package=next((self.root/'packages/counter').iterdir());(package/'app.wasm').unlink();(package/'app.wasm').symlink_to(foreign/'keep')
  with self.assertRaises(ValueError):self.repo.load('counter')
 def test_corruption_rejected_and_index_backup_used(self):
  self.repo.install(self.m,self.blob);self.repo.install({**self.m,'version':'1.0.1'},self.blob)
  (self.root/'index.json').write_text('{broken')
  r=Repository(self.root);self.assertEqual(r.current('counter')['version'],'1.0.0');self.assertTrue(r.recovered)
  m,b=r.load('counter');bad=dict(m);bad['id']='../escape'
  with self.assertRaises(ValueError):r.install(bad,b)
 def test_storage_quota_refuses_without_losing_current(self):
  self.repo.install(self.m,self.blob);before=self.repo.load('counter');self.repo.quota=1
  with self.assertRaises(ValueError):self.repo.install({**self.m,'version':'2.0.0'},self.blob)
  self.assertEqual(self.repo.load('counter'),before)
 def test_identical_reinstall_does_not_need_duplicate_storage(self):
  self.repo.install(self.m,self.blob)
  self.repo.quota=sum(p.stat().st_size for p in (self.root/'packages').rglob('*') if p.is_file())
  self.repo.install(self.m,self.blob)
  self.assertEqual(self.repo.load('counter'),(self.m,self.blob))
 def test_malformed_index_types_recover_from_last_valid_index(self):
  self.repo.install(self.m,self.blob)
  self.repo.install({**self.m,'version':'1.0.1'},self.blob)
  path=self.root/'index.json';original=json.loads(path.read_text())
  for kind in ('bool-version','string-quarantine','null-quarantine','too-many'):
   import copy
   data=copy.deepcopy(original)
   if kind=='bool-version':data['v']=True
   else:data['apps']['counter']['quarantined']={'string-quarantine':'','null-quarantine':[None],'too-many':['a'*64]*9}[kind]
   path.write_text(json.dumps(data))
   recovered=Repository(self.root)
   self.assertTrue(recovered.recovered,kind)
   self.assertEqual(recovered.current('counter')['version'],'1.0.0')
