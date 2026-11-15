"""実LittleFS+RAM NORで設定の分離/上限/電断合成を検証。実Flashではない。"""
import ctypes as C
from pathlib import Path
import test_labos_lfs as base
import unittest
ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'prototypes/lab-os/native'
OWNER=b'lab-os-app-state-v1\n'


class StateLfsTests(base.LittleFsFixture,unittest.TestCase):
    extra_sources=tuple(NATIVE/(n+'.c') for n in ('state_lfs','state_service','state_binding'))+(ROOT/'tests/native/lab_state_lfs_bridge.c',)
    extra_signatures={
        'test_state_new':([C.c_void_p,C.c_int],C.c_void_p),
        'test_state_free':([C.c_void_p],None),
        'test_state_ready':([C.c_void_p],C.c_int),
        'test_state_open':([C.c_void_p,C.c_char_p],C.c_int),
        'test_state_close':([C.c_void_p],C.c_int),
        'test_state_read':([C.c_void_p,C.c_uint,C.c_int],C.c_int),
        'test_state_write':([C.c_void_p,C.c_uint,C.c_int,C.c_uint],C.c_int),
        'test_state_io_read':([C.c_void_p,C.c_char_p,C.c_uint],C.c_int),
        'test_state_io_put':([C.c_void_p,C.c_char_p,C.c_uint],C.c_int),
    }
    def state(self,create=True,volume=None):
        p=self.lib.test_state_new(volume or self.volume,create);self.assertTrue(p);self.addCleanup(self.lib.test_state_free,p);return p
    def ready(self,p):return bool(self.lib.test_state_ready(p))
    def raw_put(self,path,data):self.assertTrue(self.lib.test_lfs_raw_put(self.volume,path.encode(),data,len(data)))
    def test_missing_namespace_requires_explicit_create_and_correct_owner(self):
        self.assertFalse(self.ready(self.state(False)));s=self.state();self.assertTrue(self.ready(s));self.assertEqual(self.raw_get('/lab-state/owner'),OWNER)
        self.assertTrue(self.ready(self.state(False)));self.raw_put('/lab-state/owner',b'foreign\n');image=self.snapshot()
        self.assertFalse(self.ready(self.state()));self.assertEqual(self.snapshot(),image)
    def test_nonempty_unowned_namespace_and_foreign_entry_are_never_adopted(self):
        self.assertEqual(self.lib.test_lfs_mkdir(self.volume,b'/lab-state'),0);self.raw_put('/lab-state/alpha.0',b'old');image=self.snapshot()
        self.assertFalse(self.ready(self.state()));self.assertEqual(self.snapshot(),image)
        self.raw_put('/lab-state/owner',OWNER);self.raw_put('/lab-state/unknown',b'foreign');image=self.snapshot()
        self.assertFalse(self.ready(self.state()));self.assertEqual(self.snapshot(),image)
    def test_two_apps_and_two_banks_survive_fresh_mount_without_touching_packages(self):
        self.assertTrue(self.connect());store=self.open_store();self.assertTrue(self.install(store,base.contract.package()));before=self.raw_get('/lab-apps/index-0')
        s=self.state();self.assertTrue(self.ready(s));self.assertTrue(self.lib.test_state_open(s,b'alpha'))
        self.assertEqual(self.lib.test_state_write(s,0,41,0),1);self.assertEqual(self.lib.test_state_write(s,0,42,1000),1);self.lib.test_state_close(s)
        self.assertTrue(self.lib.test_state_open(s,b'beta'));self.assertEqual(self.lib.test_state_read(s,0,17),17);self.assertEqual(self.lib.test_state_write(s,0,-7,0),1)
        self.assertEqual(self.raw_get('/lab-apps/index-0'),before)
        fresh=self.new_volume(self.snapshot(),False);s2=self.state(False,fresh);self.assertTrue(self.ready(s2));self.assertTrue(self.lib.test_state_open(s2,b'alpha'));self.assertEqual(self.lib.test_state_read(s2,0,17),42)
        self.lib.test_state_close(s2);self.assertTrue(self.lib.test_state_open(s2,b'beta'));self.assertEqual(self.lib.test_state_read(s2,0,17),-7)
    def test_invalid_ids_bank_and_owner_changes_never_write(self):
        s=self.state();before=self.snapshot()
        for ident,bank in ((b'../lab-apps/owner',0),(b'Alpha',0),(b'a/b',0),(b'a'*33,0),(b'alpha',2)):
            self.assertEqual(self.lib.test_state_io_read(s,ident,bank),-1);self.assertFalse(self.lib.test_state_io_put(s,ident,bank))
        self.assertEqual(self.snapshot(),before);self.raw_put('/lab-state/owner',b'foreign\n');before=self.snapshot()
        self.assertFalse(self.lib.test_state_io_put(s,b'alpha',0));self.assertEqual(self.snapshot(),before)
    def test_namespace_quota_allows_existing_app_but_refuses_33rd_identity(self):
        s=self.state();self.assertTrue(self.ready(s))
        for i in range(32):
            self.assertTrue(self.lib.test_state_open(s,f'app-{i}'.encode()));self.assertEqual(self.lib.test_state_write(s,0,i,0),1);self.lib.test_state_close(s)
        self.assertTrue(self.lib.test_state_open(s,b'app-0'));self.assertEqual(self.lib.test_state_write(s,0,99,0),1);self.lib.test_state_close(s)
        self.assertTrue(self.lib.test_state_open(s,b'app-32'));self.assertEqual(self.lib.test_state_write(s,0,1,0),-1);self.assertIsNone(self.raw_get('/lab-state/app-32.0'))
    def test_short_or_corrupt_newest_record_recovers_previous_but_oversize_fails_namespace(self):
        s=self.state();self.lib.test_state_open(s,b'alpha');self.lib.test_state_write(s,0,41,0);self.lib.test_state_write(s,0,42,1000);self.lib.test_state_close(s)
        self.raw_put('/lab-state/alpha.1',b'partial');self.assertTrue(self.lib.test_state_open(s,b'alpha'));self.assertEqual(self.lib.test_state_read(s,0,17),41);self.lib.test_state_close(s)
        self.raw_put('/lab-state/alpha.1',b'x'*53);self.assertFalse(self.ready(self.state(False)));self.assertFalse(self.lib.test_state_open(s,b'alpha'))
    def test_interrupted_alternate_commit_reopens_as_previous_or_completed_value(self):
        s=self.state();self.lib.test_state_open(s,b'alpha');self.assertEqual(self.lib.test_state_write(s,0,41,0),1);self.lib.test_state_close(s);image=self.snapshot()
        failures=0
        for cut in range(12):
            volume=self.new_volume(image,False);p=self.state(False,volume);self.assertTrue(self.ready(p));self.assertTrue(self.lib.test_state_open(p,b'alpha'))
            self.lib.test_lfs_cut(volume,cut,True);result=self.lib.test_state_write(p,0,42,1000);failures+=result==-1
            out=C.create_string_buffer(1024*1024);self.lib.test_lfs_dump(volume,out)
            fresh=self.new_volume(out.raw,False);reopened=self.state(False,fresh);self.assertTrue(self.ready(reopened));self.assertTrue(self.lib.test_state_open(reopened,b'alpha'))
            self.assertIn(self.lib.test_state_read(reopened,0,17),(41,42))
        self.assertGreater(failures,0)
