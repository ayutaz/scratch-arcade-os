import ctypes as C
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'firmware/esp-idf/lab-os-core/main'
NATIVE=ROOT/'prototypes/lab-os/native'

class BoardUdpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe=Path(cls.tmp.name)/'udp'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'tests/native/udp_fixture'),'-I'+str(MAIN),'-I'+str(NATIVE),
            str(ROOT/'tests/native/lab_board_udp_contract.c'),'-o',str(cls.exe)],
            capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
    def check(self,name):
        p=subprocess.run([str(self.exe),name],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
    def test_invalid_or_closed_requests_touch_no_socket(self):self.check('invalid')
    def test_nonblocking_connected_route_reports_local_port_and_rejects_reopen(self):self.check('open')
    def test_each_partial_initialization_failure_closes_only_the_owned_descriptor(self):self.check('partial')
    def test_receive_drops_oversized_packet_and_clears_unused_or_error_output(self):self.check('receive')
    def test_backpressure_is_transient_but_partial_udp_send_stops_more_io(self):self.check('backpressure')
    def test_fatal_receive_stops_more_io_until_explicit_close(self):self.check('fatal')
    def test_ambiguous_close_failure_never_retries_a_potentially_reused_descriptor(self):self.check('close')

class UdpLoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        output=Path(cls.tmp.name)/'udp.dylib'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I'+str(ROOT/'tests/native/udp_fixture'),'-I'+str(MAIN),'-I'+str(NATIVE),
            str(MAIN/'board_udp.c'),str(NATIVE/'udp_service.c'),str(ROOT/'tests/native/lab_udp_loopback_bridge.c'),
            '-o',str(output)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(output));cls.lib.test_udp_new.restype=C.c_void_p
        for name,args,result in (
            ('test_udp_open',[C.c_void_p,C.c_void_p,C.c_uint16],C.c_int),
            ('test_udp_port',[C.c_void_p],C.c_uint16),
            ('test_udp_send',[C.c_void_p,C.c_void_p,C.c_uint32,C.c_uint32],C.c_int),
            ('test_udp_receive',[C.c_void_p,C.c_void_p,C.c_uint32],C.c_int),
            ('test_udp_poll',[C.c_void_p,C.c_uint32],C.c_int),('test_udp_free',[C.c_void_p],C.c_int)):
            fn=getattr(cls.lib,name);fn.argtypes=args;fn.restype=result
    def test_real_mac_socket_binary_roundtrip_peer_filter_and_oversized_drop(self):
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(peer.close)
        peer.bind(('127.0.0.1',0));peer.settimeout(1)
        handle=self.lib.test_udp_new();self.assertTrue(handle)
        self.addCleanup(lambda:self.assertTrue(self.lib.test_udp_free(handle)))
        self.assertTrue(self.lib.test_udp_open(handle,b'\x7f\0\0\x01',peer.getsockname()[1]))
        local=('127.0.0.1',self.lib.test_udp_port(handle));self.assertNotEqual(local[1],0)
        payload=bytes(range(64));self.assertEqual(self.lib.test_udp_send(handle,payload,64,0),1)
        self.assertTrue(self.lib.test_udp_poll(handle,1));packet,source=peer.recvfrom(128)
        self.assertEqual(packet,payload);self.assertEqual(source,local)
        out=C.create_string_buffer(64)
        def receive(expected):
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                self.assertTrue(self.lib.test_udp_poll(handle,2))
                n=self.lib.test_udp_receive(handle,out,64)
                if n:
                    self.assertEqual(n,len(expected));self.assertEqual(out.raw[:n],expected);return
                time.sleep(.001)
            self.fail('loopback receive deadline')
        reply=bytes(v^0xa5 for v in payload);peer.sendto(reply,local);receive(reply)
        outsider=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(outsider.close)
        outsider.bind(('127.0.0.1',0));outsider.sendto(b'wrong-peer',local)
        peer.sendto(b'x'*100,local);peer.sendto(b'valid',local);receive(b'valid')
