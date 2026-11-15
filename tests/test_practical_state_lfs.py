"""実アプリ+Home+Store+LittleFSをRAM NOR上で一続きに検証。"""
import ctypes as C
from pathlib import Path
import unittest
import test_labos_lfs as base
from labos.project import build_project
ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'prototypes/lab-os/native'


class PracticalStateLfsTests(base.LittleFsFixture,unittest.TestCase):
    extra_sources=tuple(NATIVE/(n+'.c') for n in ('state_service','state_binding','state_lfs','state_mount'))+(ROOT/'tests/native/lab_state_apps_bridge.c',)
    extra_signatures={
        'test_state_apps_new':([C.c_void_p,C.POINTER(base.contract.Storage)],C.c_void_p),
        'test_state_apps_free':([C.c_void_p],None),
        'test_state_apps_install':([C.c_void_p,C.c_void_p,C.c_uint],C.c_int),
        'test_state_apps_select':([C.c_void_p,C.c_char_p],C.c_int),
        'test_state_apps_frame':([C.c_void_p,C.c_uint,C.c_uint],C.c_int),
        'test_state_apps_debug':([C.c_void_p,C.c_char_p],C.c_int),
        'test_state_apps_draw':([C.c_void_p,C.c_uint,C.c_uint],C.c_int),
        'test_state_apps_draw_count':([C.c_void_p],C.c_uint),
    }
    def new(self,volume=None):
        self.r=self.lib.test_state_apps_new(volume or self.volume,C.byref(self.services.io));self.assertTrue(self.r)
        self.addCleanup(lambda r=self.r:self.lib.test_state_apps_free(r));return self.r
    def frame(self,h=0,dt=16):self.assertTrue(self.lib.test_state_apps_frame(self.r,h,dt))
    def value(self,n):return self.lib.test_state_apps_debug(self.r,n.encode())
    def launch(self,name):self.assertTrue(self.lib.test_state_apps_select(self.r,name.encode()));self.frame(16,0);self.frame(0,0)
    def leave(self):self.frame(192,0);self.frame(0,0)
    def test_two_real_packages_save_then_fresh_mount_loads_each_setting_and_keeps_code(self):
        from labos.package import decode
        from labos.sdk import Session
        import hashlib
        packages={n:Path(build_project(ROOT/'apps'/n)['package']).read_bytes() for n in ('lane-catcher','focus-timer')}
        self.new()
        for p in packages.values():self.assertTrue(self.lib.test_state_apps_install(self.r,p,len(p)))
        self.launch('lane-catcher');self.frame(16,0);self.frame(0,5000);self.assertEqual(self.value('debug_value'),2);self.leave()
        self.launch('focus-timer');self.frame(8,0);self.frame(0,0);self.frame(16,0);self.assertEqual(self.value('debug_x'),70);self.leave()
        before={n:self.raw_get('/lab-apps/'+hashlib.sha256(p).hexdigest()+'.lab') for n,p in packages.items()}
        self.assertEqual(before,packages)
        fresh=self.new_volume(self.snapshot(),False);self.new(fresh)
        self.launch('focus-timer');self.assertEqual(self.value('debug_x'),70);self.leave();self.launch('lane-catcher')
        class Saved:
            def call(self,op,slot,value):return 1,2
        m,b=decode(packages['lane-catcher']);s=Session(b,m,state=Saved());self.addCleanup(s.close);s.frame(0,0)
        rects=[[self.lib.test_state_apps_draw(self.r,i,j) for j in range(5)] for i in range(self.lib.test_state_apps_draw_count(self.r))]
        self.assertEqual(rects,[list(x) for x in s.commands]);self.leave()
        out=C.create_string_buffer(52)
        for name,expected in (('lane-catcher',2),('focus-timer',70)):
            n=self.lib.test_lfs_raw_get(fresh,('/lab-state/'+name+'.0').encode(),out,len(out))
            self.assertEqual(n,52);self.assertEqual(int.from_bytes(out.raw[16:20],'little',signed=True),expected)
        for name,p in packages.items():
            out=C.create_string_buffer(len(p));n=self.lib.test_lfs_raw_get(fresh,('/lab-apps/'+hashlib.sha256(p).hexdigest()+'.lab').encode(),out,len(out));self.assertEqual((n,out.raw),(len(p),p))
