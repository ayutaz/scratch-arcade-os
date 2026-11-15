import ctypes as C
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import wasmtime

import test_labos_c_store as contract
from labos.native import build_probe,SOURCE
from labos.sdk import make_manifest
from labos.build import build
from labos.package import encode
from labos.ui_assets import generate

ROOT=contract.ROOT
def package(name='a-network',*,broken=False,audio=False):
    sound='(import "os" "audio_tone" (func $tone (param i32 i32) (result i32)))' if audio else ''
    tone='i32.const 1000 i32.const 32 call $tone drop' if audio else ''
    blob=bytes(wasmtime.wat2wasm(f'''(module {sound}
     (import "os" "network_send" (func $send (param i32 i32) (result i32)))
     (import "os" "network_receive" (func $receive (param i32 i32) (result i32)))
     (import "os" "network_state" (func $state (result i32)))
     (memory (export "memory") 1 2)
     (data (i32.const 16) "\\00\\ffABC") (data (i32.const 64) "ZZZZ")
     (global $v (mut i32) (i32.const 0))
     (func (export "sdk_abi") (result i32) i32.const 2) (func (export "init"))
     (func (export "debug_value") (result i32) global.get $v)
     (func (export "debug_x") (result i32) i32.const 64 i32.load)
     (func (export "tick") (param i32) (param $p i32) (param i32 i32) (result i32)
      local.get $p i32.const 1 i32.and if {tone} i32.const 16 i32.const 5 call $send global.set $v {'unreachable' if broken else ''} end
      local.get $p i32.const 16 i32.and if i32.const 64 i32.const 64 call $receive global.set $v end
      local.get $p i32.const 32 i32.and if call $state global.set $v end i32.const 0))'''))
    caps=['speaker','network'] if audio else ['network']
    return encode(make_manifest(name,blob,capabilities=caps),blob)

class NetworkHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_probe();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);folder=Path(cls.tmp.name)
        generate(folder);native=ROOT/'prototypes/lab-os/native';main=ROOT/'firmware/esp-idf/lab-os-core/main';out=folder/'home.dylib'
        sources=[native/(name+'.c') for name in ('guest_vm','app_home','app_store','run_loop','ui','udp_service','network_binding','audio_service','audio_binding')]
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I'+str(native),'-I'+str(main),'-I'+str(ROOT/'tests/native/udp_fixture'),
            '-I'+str(SOURCE/'core/iwasm/include'),'-I'+str(folder),'-I'+str(ROOT/'assets/fonts'),
            *map(str,sources),str(main/'board_udp.c'),str(ROOT/'tests/native/lab_network_home_bridge.c'),
            str(ROOT/'build/lab-os-native/wamr/libiwasm.a'),'-lpthread','-lm','-o',str(out)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        cls.lib=C.CDLL(str(out));cls.lib.test_new.argtypes=[C.POINTER(contract.Storage)];cls.lib.test_new.restype=C.c_void_p
        for name in ('test_free','test_start','test_mode','test_loop_close','test_clean','test_port'):getattr(cls.lib,name).argtypes=[C.c_void_p]
        cls.lib.test_install.argtypes=[C.c_void_p,C.c_void_p,C.c_uint]
        cls.lib.test_step.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        cls.lib.test_debug.argtypes=[C.c_void_p,C.c_char_p]
        cls.lib.test_metric.argtypes=[C.c_void_p,C.c_uint]
        cls.lib.test_fault.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
        cls.lib.test_available.argtypes=cls.lib.test_configure.argtypes=[C.c_void_p,C.c_int]
        cls.lib.test_route.argtypes=[C.c_void_p,C.c_uint,C.c_int]
        cls.lib.test_inject.argtypes=[C.c_void_p,C.c_void_p,C.c_uint]
        cls.lib.test_verify.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
        assert cls.lib.test_runtime_start();cls.addClassCleanup(cls.lib.test_runtime_stop)
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.disk=contract.DiskFixture(tmp.name,self.lib);(Path(tmp.name)/'owner').write_bytes(b'lab-os-c-store-v1\n')
        self.rig=self.lib.test_new(C.byref(self.disk.io));self.assertTrue(self.rig);self.addCleanup(self.lib.test_free,self.rig)
    def step(self,held=0,dt=16):self.assertEqual(self.lib.test_step(self.rig,held,dt),0)
    def metric(self,n):return self.lib.test_metric(self.rig,n)
    def value(self,name='debug_value'):return self.lib.test_debug(self.rig,name.encode())
    def install(self,p):self.assertTrue(self.lib.test_install(self.rig,p,len(p)))
    def start(self):self.assertTrue(self.lib.test_start(self.rig));self.step()
    def launch(self):self.step(16);self.assertEqual(self.lib.test_mode(self.rig),1);self.step()
    def exit(self):self.step(192);self.step();self.assertEqual(self.lib.test_mode(self.rig),0)
    def test_two_apps_use_distinct_leases_and_do_not_inherit_unread_packet(self):
        self.install(package());self.install(package('b-network'));self.start();self.launch();first=self.metric(4)
        self.step(1);self.assertEqual(self.value(),1);self.step();self.assertEqual(self.metric(5),1)
        self.lib.test_inject(self.rig,b'\x01\x02\x03',3);self.step(16);self.assertEqual(self.value(),3)
        self.assertEqual(self.value('debug_x'),0x5a030201)
        self.lib.test_inject(self.rig,b'old',3);self.step();self.exit();self.assertTrue(self.lib.test_clean(self.rig))
        self.step(4);self.step();self.launch();self.assertNotEqual(self.metric(4),first)
        self.step(16);self.assertEqual(self.value(),0);self.exit();self.assertEqual(self.metric(0),2)
        self.assertEqual(self.metric(8),0)
    def test_failed_network_cleanup_also_attempts_audio_and_keeps_image_and_owner(self):
        p=package(audio=True);self.install(p);self.start();self.launch();self.step(1)
        self.lib.test_fault(self.rig,1,0,1);self.step(192)
        self.assertEqual((self.lib.test_mode(self.rig),self.metric(2),self.metric(3)),(3,1,0))
        self.assertTrue(self.lib.test_clean(self.rig));self.assertGreater(self.metric(11),0)
        self.assertFalse(self.lib.test_install(self.rig,p,len(p)))
        opens=self.metric(0)
        for held in (0,16,4,16):self.step(held);self.assertEqual(self.lib.test_mode(self.rig),3)
        self.assertEqual(self.metric(0),opens);self.lib.test_fault(self.rig,0,0,0);self.step();self.step()
        self.assertEqual((self.metric(2),self.metric(4),self.metric(12),self.metric(8)),(0,0,0,0))
    def test_trapped_guest_discards_unsent_packet_and_delays_quarantine_until_cleanup(self):
        self.install(package(broken=True));self.install(package('b-network'));self.start();self.launch()
        self.lib.test_fault(self.rig,1,0,0);self.step(1)
        self.assertEqual((self.lib.test_mode(self.rig),self.metric(6),self.metric(5)),(3,2,0))
        self.assertTrue(self.lib.test_clean(self.rig));self.lib.test_fault(self.rig,0,0,0);self.step();self.step()
        self.assertEqual((self.metric(6),self.metric(2),self.metric(5)),(1,0,0));self.launch()
    def test_unavailable_network_is_retriable_and_does_not_quarantine_app(self):
        self.install(package());self.start();self.lib.test_available(self.rig,0);self.step(16)
        self.assertEqual((self.lib.test_mode(self.rig),self.metric(9),self.metric(6)),(2,self.lib.test_notice_network(),1))
        self.assertEqual((self.metric(2),self.metric(0)),(0,0));self.step();self.lib.test_available(self.rig,1);self.launch()
    def test_service_and_route_configuration_reject_live_or_partial_hooks(self):
        self.install(package());self.start();self.assertFalse(self.lib.test_configure(self.rig,1))
        self.launch();self.assertFalse(self.lib.test_configure(self.rig,0));self.assertFalse(self.lib.test_route(self.rig,50001,0))
        self.exit();self.assertTrue(self.lib.test_configure(self.rig,0));self.assertTrue(self.lib.test_route(self.rig,50001,0))
    def test_legacy_draw_app_never_claims_network(self):
        self.install(contract.package());self.start();self.launch();self.step(1)
        self.assertEqual((self.metric(0),self.metric(4),self.metric(10)),(0,0,0));self.exit()
    def test_link_loss_closes_socket_but_keeps_borrow_guard_until_vm_exit(self):
        self.install(package());self.start();self.launch();self.lib.test_available(self.rig,0);self.step(32)
        self.assertEqual(self.value(),-1);self.assertEqual(self.metric(4),0)
        self.assertFalse(self.lib.test_route(self.rig,50001,0));self.assertEqual(self.metric(10),1)
        self.exit();self.assertTrue(self.lib.test_route(self.rig,50001,0))
    def test_partial_start_with_failed_close_keeps_resources_and_retries_without_disabling_app(self):
        self.install(package());self.start();self.lib.test_fault(self.rig,1,1,0);self.step(16)
        self.assertEqual((self.lib.test_mode(self.rig),self.metric(2),self.metric(6)),(3,1,1))
        self.assertGreater(self.metric(4),0);self.lib.test_fault(self.rig,0,0,0);self.step();self.step();self.launch()
    def test_loop_close_propagates_network_cleanup_failure(self):
        self.install(package());self.start();self.launch();self.lib.test_fault(self.rig,1,0,0)
        self.assertFalse(self.lib.test_loop_close(self.rig));self.assertEqual((self.metric(2),self.metric(7)),(1,0))
        self.lib.test_fault(self.rig,0,0,0);self.assertTrue(self.lib.test_loop_close(self.rig));self.assertEqual(self.metric(2),0)
    def test_wasm_home_manager_and_real_mac_udp_roundtrip(self):
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(peer.close)
        peer.bind(('127.0.0.1',0));peer.settimeout(1)
        self.assertTrue(self.lib.test_route(self.rig,peer.getsockname()[1],1))
        self.install(package());self.start();self.launch();self.step(1);self.step()
        data,source=peer.recvfrom(128);self.assertEqual(data,b'\0\xffABC');self.assertEqual(source[1],self.lib.test_port(self.rig))
        peer.sendto(b'\x01\x02\x03',source)
        deadline=time.monotonic()+1
        while self.metric(13)!=3 and time.monotonic()<deadline:self.step();time.sleep(.001)
        self.assertEqual(self.metric(13),3);self.step(16)
        self.assertEqual((self.value(),self.value('debug_x')),(3,0x5a030201))
        self.exit();self.assertEqual((self.lib.test_port(self.rig),self.metric(2)),(0,0))
    def test_actual_c_network_app_receives_replies_and_exits_over_real_mac_socket(self):
        import struct
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(peer.close)
        peer.bind(('127.0.0.1',0));peer.settimeout(.05)
        self.assertTrue(self.lib.test_route(self.rig,peer.getsockname()[1],1))
        with tempfile.TemporaryDirectory() as tmp:
            manifest,blob=build('network',Path(tmp))
        self.install(encode(manifest,blob));self.start();self.launch()
        port=self.lib.test_port(self.rig);self.assertGreater(port,0)
        packet=b'LBN1'+struct.pack('<I',7)+b'\x00\xffAB'
        peer.sendto(packet,('127.0.0.1',port));deadline=time.monotonic()+1
        while self.value()!=1 and time.monotonic()<deadline:self.step();time.sleep(.001)
        self.assertEqual((self.value(),self.value('debug_y')),(1,7))
        self.assertEqual(self.metric(5),0);self.step(16);self.step()
        data,source=peer.recvfrom(128);self.assertEqual(data,b'LBA1'+packet[4:]);self.assertEqual(source[1],port)
        self.assertEqual(self.value('debug_x'),1);self.step(16);self.step(16)
        with self.assertRaises(socket.timeout):peer.recvfrom(128)
        self.exit();self.assertEqual((self.lib.test_port(self.rig),self.metric(2)),(0,0))
        self.assertTrue(self.lib.test_clean(self.rig));self.launch()
        self.assertEqual((self.value(),self.value('debug_x'),self.value('debug_y')),(0,0,0))
        self.exit()

    def test_remote_timer_commands_roundtrip_through_real_mac_udp_and_c_home(self):
        from labos.project import build_project
        from labos.remote_timer import exchange
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(peer.close)
        peer.bind(('127.0.0.1',0));self.assertTrue(self.lib.test_route(self.rig,peer.getsockname()[1],1))
        self.install(Path(build_project(ROOT/'apps/remote-timer')['package']).read_bytes());self.start();self.launch()
        endpoint=('127.0.0.1',self.lib.test_port(self.rig))
        keep=lambda:self.step(0,10)
        r=exchange(peer,endpoint,1,1,10,keepalive=keep);self.assertEqual(r['phase'],1)
        self.step(0,1000);r=exchange(peer,endpoint,1,1,10,keepalive=keep);self.assertLess(r['remaining_ms'],9000)
        r=exchange(peer,endpoint,2,2,keepalive=keep);self.assertEqual(r['phase'],2);stopped=r['remaining_ms']
        self.step(0,1000);r=exchange(peer,endpoint,3,3,keepalive=keep);self.assertEqual(r['remaining_ms'],stopped)
        r=exchange(peer,endpoint,4,4,keepalive=keep);self.assertEqual((r['phase'],r['remaining_ms']),(0,10000))
        self.exit();self.assertEqual((self.lib.test_port(self.rig),self.metric(2)),(0,0))
