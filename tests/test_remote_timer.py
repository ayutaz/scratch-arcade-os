"""Mac向け固定UDP timer protocolと実Cアプリの契約。"""
from pathlib import Path
import socket
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.remote_timer import encode_request,decode_reply,exchange
from labos.project import build_project
from labos.package import decode
from labos.sdk import Session


def reply(seq=1,phase=1,remaining=10000,seconds=10):return b'LRA1'+struct.pack('<5I',seq,phase,remaining,seconds,seconds*1000-remaining)


class CodecTests(unittest.TestCase):
    def test_canonical_packets_and_invalid_arguments(self):
        self.assertEqual(encode_request(7,1,10),b'LRT1'+struct.pack('<III',7,1,10))
        self.assertEqual(decode_reply(reply()),dict(sequence=1,phase=1,remaining_ms=10000,seconds=10,elapsed_ms=0))
        for seq,op,seconds in ((0,1,10),(True,1,10),(1,5,0),(1,1,9),(1,1,301),(1,2,10),(1,1,10.0),(1,True,10)):
            with self.assertRaises(ValueError):encode_request(seq,op,seconds)
        for data in (reply()[:-1],reply()+b'\0',b'bad!'+reply()[4:],reply(0),reply(phase=5),reply(phase=0,remaining=1),reply(phase=3,remaining=1)):
            with self.assertRaises(ValueError):decode_reply(data)
    def test_exchange_retries_same_sequence_and_ignores_foreign_or_mismatched_reply(self):
        class Peer:
            def __init__(self):self.sent=[];self.replies=[(reply(),('127.0.0.2',5000)),(reply(2),('127.0.0.1',5000)),(reply(),('127.0.0.1',5000))]
            def settimeout(self,t):pass
            def sendto(self,b,p):self.sent.append((b,p))
            def recvfrom(self,n):return self.replies.pop(0)
        peer=Peer();calls=[];result=exchange(peer,('127.0.0.1',5000),1,1,10,keepalive=lambda:calls.append(1))
        self.assertEqual(result['sequence'],1);self.assertTrue(calls);self.assertEqual(peer.sent[0][0],encode_request(1,1,10))
    def test_exchange_timeout_is_bounded_and_retransmits_identical_packet(self):
        class Peer:
            now=0
            def __init__(self):self.sent=[]
            def settimeout(self,t):self.wait=t
            def sendto(self,b,p):self.sent.append(b)
            def recvfrom(self,n):self.now+=self.wait;raise socket.timeout()
        peer=Peer()
        with self.assertRaises(TimeoutError):exchange(peer,('127.0.0.1',5000),7,1,10,timeout=.1,clock=lambda:peer.now)
        self.assertEqual(len(peer.sent),3);self.assertEqual(set(peer.sent),{encode_request(7,1,10)})


class Network:
    def __init__(self):self.incoming=[];self.sent=[];self.calls=[];self.send_result=1
    def call(self,op,data,capacity):
        self.calls.append(op)
        if op==3:return 1
        if op==1:
            if self.send_result==1:self.sent.append(bytes(data))
            return self.send_result
        if not self.incoming:return 0
        msg=self.incoming.pop(0);data[:len(msg)]=msg;return len(msg)


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.manifest,cls.blob=decode(Path(build_project(ROOT/'apps/remote-timer')['package']).read_bytes())
    def setUp(self):self.net=Network();self.s=Session(self.blob,self.manifest,network=self.net);self.addCleanup(self.s.close);self.now=0
    def frame(self,key=0,dt=0):self.now+=dt;return self.s.frame(key,self.now)
    def command(self,seq,op,seconds=0,dt=0):
        self.net.incoming.append(encode_request(seq,op,seconds));self.frame(dt=dt);return decode_reply(self.net.sent[-1])
    def test_package_has_only_draw_and_network_and_exit_does_no_io(self):
        self.assertEqual((self.manifest['id'],self.manifest['version'],self.manifest['capabilities']),('remote-timer','1.0.0',['draw','network']))
        n=len(self.net.calls);self.assertTrue(self.frame(64));self.assertEqual(len(self.net.calls),n)
    def test_start_stop_status_reset_and_completion(self):
        self.assertEqual(self.command(1,1,10)['remaining_ms'],10000);self.frame(dt=1500)
        r=self.command(2,2);self.assertEqual((r['phase'],r['remaining_ms']),(2,8500));self.frame(dt=1000)
        self.assertEqual(self.command(3,3)['remaining_ms'],8500);self.assertEqual(self.command(4,4)['phase'],0)
        self.command(5,1,10);self.frame(dt=10000);r=self.command(6,3);self.assertEqual((r['phase'],r['remaining_ms'],r['elapsed_ms']),(3,0,10000))
    def test_duplicate_start_does_not_reset_progress_and_conflicting_old_packets_are_ignored(self):
        self.command(1,1,10);self.frame(dt=1000);self.assertEqual(self.command(1,1,10)['remaining_ms'],9000)
        count=len(self.net.sent)
        for p in (encode_request(1,1,20),encode_request(0xffffffff,1,10),encode_request(0x80000001,1,10)):
            self.net.incoming.append(p);self.frame();self.assertEqual(len(self.net.sent),count)
        self.assertEqual(self.command(2,3)['remaining_ms'],9000)
    def test_invalid_packets_leave_timer_unchanged(self):
        base=encode_request(1,1,10)
        bad=[base[:-1],base+b'x',b'bad!'+base[4:]]
        for offset,value in ((4,0),(8,5),(9,1),(12,9),(12,301)):
            p=bytearray(base);struct.pack_into('<I',p,offset,value);bad.append(bytes(p))
        for p in bad:self.net.incoming.append(p);self.frame()
        self.assertEqual(self.net.sent,[]);self.assertEqual(self.s.debug('debug_y'),0)
    def test_sequence_wrap_and_local_controls_work_without_repeated_edges(self):
        self.command(0xffffffff,1,10);self.assertEqual(self.command(1,1,20)['seconds'],20)
        self.frame(16);self.assertEqual(self.s.debug('debug_y'),2);self.frame(16);self.assertEqual(self.s.debug('debug_y'),2)
        self.frame();self.frame(16);self.assertEqual(self.s.debug('debug_y'),1);self.frame(32);self.assertEqual(self.s.debug('debug_y'),0)
    def test_backpressure_retries_for_one_second_then_stops_until_new_request(self):
        self.net.send_result=0;self.net.incoming.append(encode_request(1,1,10));self.frame();self.frame(dt=500);self.frame(dt=501)
        n=self.net.calls.count(1);self.frame(dt=500);self.assertEqual(self.net.calls.count(1),n)
        self.net.send_result=1;self.assertEqual(self.command(1,1,10)['remaining_ms'],8499)
    def test_both_vms_match_without_a_network_backend(self):
        from labos.native import build_probe,run_probe
        s=Session(self.blob,self.manifest);self.addCleanup(s.close);now=0
        frames=[(0,0),(16,0),(0,1000),(16,0),(0,10),(32,0),(0,1),(64,0)]
        for row,(key,dt) in zip(run_probe(build_probe(),[self.blob],frames,capabilities=9),frames,strict=True):
            now+=dt;done=s.frame(key,now);self.assertEqual(row['status'],'exit' if done else 'running')
            if not done:self.assertEqual(row['rects'],[list(x) for x in s.commands]);self.assertEqual(row['value'],s.debug('debug_value'))
