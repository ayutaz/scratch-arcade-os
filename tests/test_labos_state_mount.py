"""candidateで使う保存接続を実LittleFS fixtureで検証。"""
import ctypes as C
from pathlib import Path
import unittest
import test_labos_lfs as base
ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'prototypes/lab-os/native'


class StateMountTests(base.LittleFsFixture,unittest.TestCase):
    extra_sources=tuple(NATIVE/(n+'.c') for n in ('state_service','state_binding','state_lfs','state_mount'))+(ROOT/'tests/native/lab_state_mount_bridge.c',)
    extra_signatures={'test_state_mount':([C.c_void_p,C.c_int],C.c_uint)}
    def test_owned_or_fresh_state_connects_and_closes_without_other_namespace_writes(self):
        self.assertEqual(self.lib.test_state_mount(self.volume,0),127)
        self.assertEqual(self.raw_get('/lab-state/owner'),b'lab-os-app-state-v1\n')
        self.assertEqual(self.lib.test_state_mount(self.volume,0),127)
    def test_foreign_state_is_unavailable_but_home_still_usable_without_adoption(self):
        self.assertEqual(self.lib.test_lfs_mkdir(self.volume,b'/lab-state'),0)
        self.assertTrue(self.lib.test_lfs_raw_put(self.volume,b'/lab-state/owner',b'foreign',7));before=self.snapshot()
        self.assertEqual(self.lib.test_state_mount(self.volume,0),113)
        self.assertEqual(self.snapshot(),before)
    def test_busy_home_is_rejected_before_any_namespace_creation(self):
        before=self.snapshot();self.assertEqual(self.lib.test_state_mount(self.volume,1),0);self.assertEqual(self.snapshot(),before)
