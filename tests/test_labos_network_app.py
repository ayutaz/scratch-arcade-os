"""通信診断C appの契約。合成packet、実Wasmtime。実機I/Oなし。"""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import wasmtime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.build import build
from labos.package import encode,decode
from labos.sdk import Session


def request(sequence=7,tag=b'\x00\xffAB'):
    return b'LBN1'+struct.pack('<I',sequence)+tag


class Channel:
    def __init__(self):
        self.state=1;self.incoming=[];self.sent=[];self.calls=[];self.send_result=1
    def call(self,op,data,length):
        self.calls.append(op)
        if op==3:return self.state
        if op==1:
            self.sent.append(bytes(data));return self.send_result
        if not self.incoming:return 0
        packet=self.incoming.pop(0)
        if packet is None:return -1
        data[:len(packet)]=packet;return len(packet)


class NetworkAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.manifest,cls.blob=build('network',Path(cls.tmp.name))
    def setUp(self):
        self.channel=Channel();self.now=0
        self.app=Session(self.blob,self.manifest,network=self.channel)
        self.addCleanup(self.app.close)
    def frame(self,held=0):
        self.now+=16;return self.app.frame(held,self.now)
    def value(self,name='debug_value'):return self.app.debug(name)
    def test_bounded_reproducible_package_has_only_draw_and_network_imports(self):
        self.assertEqual(self.manifest['capabilities'],['draw','network'])
        self.assertEqual(decode(encode(self.manifest,self.blob)),(self.manifest,self.blob))
        _,again=build('network',Path(self.tmp.name));self.assertEqual(again,self.blob)
        self.assertLess(len(encode(self.manifest,self.blob)),4096)
        module=wasmtime.Module(self.app.engine,self.blob)
        self.assertEqual({(i.module,i.name) for i in module.imports},
                         {('os',n) for n in ('rect','network_state','network_send','network_receive')})
    def test_receive_draw_and_reply_on_press_not_on_hold(self):
        self.channel.incoming.append(request());self.frame()
        self.assertEqual((self.value(),self.value('debug_x'),self.value('debug_y'),self.value('debug_elapsed')),(1,0,7,1))
        self.assertTrue(self.app.commands);self.assertEqual(self.channel.sent,[])
        self.frame(16);self.assertEqual(self.channel.sent,[b'LBA1'+request()[4:]])
        self.assertEqual(self.value('debug_x'),1)
        self.frame(16);self.assertEqual(len(self.channel.sent),1)
        self.assertLessEqual(len(self.app.commands),128)
    def test_malformed_packets_are_ignored_without_erasing_a_pending_reply(self):
        self.channel.incoming.append(request());self.frame()
        for bad in (b'',b'LBN1',b'BAD!'+request()[4:],request(0),request(0x80000000),request()+b'x',bytes(64)):
            self.channel.incoming.append(bad);self.frame()
            self.assertEqual((self.value(),self.value('debug_y')),(1,7))
        self.frame(16);self.assertEqual(self.channel.sent,[b'LBA1'+request()[4:]])
    def test_duplicate_is_idempotent_and_new_challenge_replaces_pending_reply(self):
        self.channel.incoming.extend([request(),request(),request(8,b'WXYZ')])
        for _ in range(3):self.frame()
        self.assertEqual((self.value(),self.value('debug_y')),(2,8))
        self.frame(16);self.assertEqual(self.channel.sent,[b'LBA1'+request(8,b'WXYZ')[4:]])
        self.frame();self.channel.incoming.append(request(8,b'WXYZ'));self.frame(16)
        self.assertEqual(self.value(),2);self.assertEqual(self.value('debug_x'),2)
    def test_backpressure_waits_for_another_press_without_background_retry(self):
        self.channel.incoming.append(request());self.frame();self.channel.send_result=0
        self.frame(16);self.frame();self.assertEqual(self.value('debug_x'),0)
        self.channel.send_result=1;self.frame();self.assertEqual(len(self.channel.sent),1)
        self.frame(16);self.assertEqual(self.value('debug_x'),1)
        self.assertEqual(self.channel.sent,[b'LBA1'+request()[4:]]*2)
    def test_link_loss_and_receive_failure_discard_the_pending_reply(self):
        for failure in ('link','receive','send'):
            with self.subTest(failure=failure):
                self.channel.incoming.append(request());self.frame()
                if failure=='link':self.channel.state=-1;self.frame()
                elif failure=='receive':self.channel.incoming.append(None);self.frame()
                else:self.channel.send_result=-1;self.frame(16)
                self.assertEqual(self.value('debug_elapsed'),-1)
                self.channel.state=1;self.channel.send_result=1;self.frame()
                before=len(self.channel.sent);self.frame(16)
                self.assertEqual(len(self.channel.sent),before);self.frame()
    def test_back_exits_before_any_network_action_and_relaunch_clears_state(self):
        self.channel.incoming.append(request());self.frame();self.channel.calls=[]
        self.assertTrue(self.frame(64));self.assertEqual(self.channel.calls,[])
        self.app=Session(self.blob,self.manifest,network=self.channel);self.addCleanup(self.app.close)
        self.now=0;self.frame(16)
        self.assertEqual((self.value(),self.value('debug_x'),self.value('debug_y')),(0,0,0))
        self.assertEqual(self.channel.sent,[])
    def test_missing_backend_is_unavailable_and_does_not_trap_or_emit_data(self):
        app=Session(self.blob,self.manifest);self.addCleanup(app.close)
        self.assertFalse(app.frame(16,16));self.assertEqual(app.debug('debug_elapsed'),-1)
        self.assertTrue(app.commands);self.assertTrue(app.frame(64,32))
