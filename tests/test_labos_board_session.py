import ctypes as C
import hashlib
import struct
import socket
import time
import tempfile
import unittest
import wasmtime
from pathlib import Path

import test_labos_c_store as contract
import test_labos_lfs as fs
from labos.transfer import Frame, Parser, encode
from labos.ui_assets import generate
from test_labos_network_home import package as network_package

ROOT = contract.ROOT
MAIN = ROOT / 'firmware/esp-idf/lab-os-core/main'
NATIVE = ROOT / 'prototypes/lab-os/native'


class SessionFixture(fs.LittleFsFixture):
    extra_sources = tuple(MAIN / name for name in ('board_session.c', 'board_input.c', 'board_display.c', 'usb_transfer.c','board_audio.c','board_sound.c','board_wifi.c','board_network.c','board_udp.c')) + tuple(
        NATIVE / name for name in ('run_loop.c', 'input.c', 'ui.c', 'app_transfer.c','audio_service.c','audio_binding.c','udp_service.c','network_binding.c')) + tuple(
        ROOT / 'tests/native' / name for name in ('lab_session_bridge.c', 'lab_session_display_fixture.c', 'lab_session_input_fixture.c','lab_session_audio_fixture.c','lab_session_wifi_fixture.c'))
    extra_signatures = {
        'test_session_remote_metric': ([C.c_void_p,C.c_uint],C.c_uint),
        'test_session_network_metric': ([C.c_void_p,C.c_uint],C.c_uint),
        'test_session_udp_fault': ([C.c_void_p,C.c_int],None),
        'test_wifi_fault': ([C.c_int],None),
        'test_wifi_calls': ([C.c_uint],C.c_int),
        'test_wifi_notify': ([C.c_int],None),
        'test_session_network_state': ([C.c_void_p],C.c_uint),
        'test_session_new': ([], C.c_void_p),
        'test_session_free': ([C.c_void_p], None),
        'test_session_open': ([C.c_void_p, C.c_void_p, C.c_int, C.c_uint32, C.c_uint32], C.c_int),
        'test_session_step': ([C.c_void_p, C.c_uint32], C.c_int),
        'test_session_close': ([C.c_void_p], C.c_int),
        'test_session_audio_hooks': ([C.c_void_p], C.c_int),
        'test_session_audio_fault': ([C.c_int], None),
        'test_session_sound_metric': ([C.c_void_p,C.c_uint],C.c_uint),
        'test_audio_memory': ([C.c_uint],C.c_uint),
        'test_audio_memory_fault': ([C.c_int,C.c_int],None),
        'test_audio_fault': ([C.c_int],None),
        'test_audio_auto_io': ([C.c_int],None),
        'test_audio_calls': ([C.c_int],C.c_int),
        'test_audio_bad': ([],C.c_int),
        'test_audio_sent': ([C.c_uint],None),
        'test_session_metric': ([C.c_void_p, C.c_int], C.c_int),
        'test_session_value': ([C.c_void_p], C.c_int),
        'test_session_enqueue': ([C.c_void_p, C.c_uint32], C.c_int),
        'test_session_output': ([C.c_void_p, C.c_uint32], C.c_uint32),
        'test_session_usb_installed': ([C.c_int], None),
        'test_session_usb_read_fault': ([C.c_int], None),
        'test_display_fault': ([C.c_int, C.c_int], None),
        'test_display_metric': ([C.c_int], C.c_int),
        'test_display_calls': ([C.c_int], C.c_int),
        'test_fault': ([C.c_int], None),
        'test_values': ([C.c_int, C.c_int, C.c_int], None),
        'test_calls': ([C.c_int], C.c_int),
        'test_bad': ([], C.c_int),
    }
    console_flags = ()

    @classmethod
    def setUpClass(cls):
        cls.fonts = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fonts.cleanup)
        generate(Path(cls.fonts.name))
        cls.extra_flags = tuple('-I' + str(ROOT / 'tests/native' / name) for name in
                                ('wifi_fixture','udp_fixture','session_fixture', 'display_fixture', 'input_fixture', 'usb_fixture','audio_fixture')) + (
            '-I' + str(MAIN), '-I' + cls.fonts.name, '-I' + str(ROOT / 'assets/fonts'), *cls.console_flags)
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.sessions = []
        self.lib.test_display_reset()
        self.lib.test_reset()
        self.lib.test_session_usb_reset()
        self.assertTrue(self.connect())
        self.store = self.open_store()
        self.assertTrue(self.install(self.store, contract.package(value=7)))
        self.session = self.new_session()
        self.now = 0

    def close_all(self):
        for session in self.sessions: self.lib.test_session_free(session)
        self.sessions.clear()
        super().close_all()

    def new_session(self):
        session = self.lib.test_session_new()
        self.assertTrue(session)
        self.sessions.append(session)
        return session

    def open(self): self.assertTrue(self.lib.test_session_open(self.session, self.store, 1, 123, self.now))
    def metric(self, i): return self.lib.test_session_metric(self.session, i)
    def step(self, dt=1, result=0):
        self.now += dt
        self.assertEqual(self.lib.test_session_step(self.session, self.now), result)

    def input(self, keys=0, x=2048, y=2048): self.lib.test_values(keys, x, y)
    def key(self, keys=0):
        self.input(keys)
        self.step();self.step(20)

    def output(self):
        out = C.create_string_buffer(8192)
        n = self.lib.test_session_output(out, len(out))
        return Parser().feed(out.raw[:n])

    def write(self, data):
        self.assertTrue(self.lib.test_session_enqueue(data, len(data)))
        while self.metric(11): self.step()

    def raw(self, op, request, payload=b'', session=999):
        self.output()
        self.write(encode(Frame(op, session, request, payload)))
        replies = [f for f in self.output() if (f.op, f.session, f.request) == (op, session, request)]
        self.assertEqual(len(replies), 1)
        return replies[0]

    def begin(self, pack):
        self.assertEqual(self.raw(2, 1, struct.pack('<I', 123)).status, 0)
        self.assertEqual(self.raw(3, 2, struct.pack('<I', len(pack)) + hashlib.sha256(pack).digest()).status, 0)

    def finish(self, pack):
        request = 3
        for at in range(0, len(pack), 512):
            self.assertEqual(self.raw(4, request, struct.pack('<I', at) + pack[at:at + 512]).status, 0)
            request += 1
        self.assertEqual(self.raw(5, request).status, 0)
        return request

    def launch(self):
        self.input();self.step()
        self.key(2)
        self.assertEqual(self.metric(1), 1)

    def assert_hardware_ok(self):
        self.assertEqual((self.lib.test_bad(), self.lib.test_display_metric(0), self.metric(10)), (0, 0, 0))


class BoardSessionTests(SessionFixture, unittest.TestCase):
    def net(self,n):return self.lib.test_session_network_metric(self.session,n)
    def network_app(self):self.assertTrue(self.install(self.store,network_package()))
    def wifi_route(self,port):
        self.start_network();self.lib.test_wifi_notify(1);self.step();self.lib.test_wifi_notify(2);self.step()
        reply=self.raw(14,3,struct.pack('<I4s2I',4,b'\x7f\0\0\x01',0,port))
        self.assertEqual(reply.status,0);self.assertEqual(struct.unpack('<I',reply.payload[:4])[0],2)
        self.assertEqual(self.raw(10,4).status,0)
    def test_network_hook_is_offline_by_default_without_radio_or_socket(self):
        self.network_app();self.open();self.assertEqual(self.net(4),1)
        self.key();self.key(2);self.assertEqual(self.metric(1),2)
        self.assertEqual(self.net(7),self.net(8))
        self.assertEqual((self.net(0),self.net(1)),(0,0))
        self.assertTrue(all(self.lib.test_wifi_calls(i)==0 for i in range(24)))
        self.key();self.assertEqual(self.metric(2),2)
    def test_usb_route_native_input_wasm_and_real_host_socket_share_one_session(self):
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(peer.close)
        peer.bind(('127.0.0.1',0));peer.settimeout(1)
        self.network_app();self.open();self.wifi_route(peer.getsockname()[1]);self.launch();self.key()
        self.input(x=0);self.step();self.step(20);self.input();self.step()
        packet,source=peer.recvfrom(128);self.assertEqual(packet,b'\0\xffABC');self.assertEqual(source[1],self.net(2))
        peer.sendto(b'\x01\x02\x03',source);deadline=time.monotonic()+1
        while self.net(5)!=3 and time.monotonic()<deadline:self.step();time.sleep(.001)
        self.assertEqual(self.net(5),3);self.key(2);self.assertEqual(self.lib.test_session_value(self.session),3)
        self.assertEqual(self.raw(2,1,struct.pack('<I',123),session=777).status,0)
        reply=self.raw(14,2,struct.pack('<I',5),session=777)
        self.assertEqual((reply.status,struct.unpack('<2I',reply.payload)),(0,(1,self.net(2))))
        self.assertEqual(self.raw(14,3,struct.pack('<I4s2I',4,b'\x7f\0\0\x01',0,50001),session=777).status,2)
        self.assertEqual(self.raw(10,4,session=777).status,0);self.key(5);self.key()
        self.assertEqual((self.metric(1),self.net(0),self.net(1)),(0,0,0));self.assert_hardware_ok()
    def test_udp_cleanup_failure_keeps_parent_hardware_and_wifi_until_home_close_succeeds(self):
        self.network_app();self.open();self.wifi_route(50000);self.launch();self.key()
        self.lib.test_session_udp_fault(self.session,1);self.key(5);self.key()
        self.assertEqual((self.metric(1),self.metric(3),self.net(1)),(3,1,1))
        self.assertFalse(self.lib.test_session_close(self.session));self.assertEqual(self.lib.test_display_metric(1),1)
        self.assertEqual(self.lib.test_wifi_calls(18),0);self.lib.test_session_udp_fault(self.session,0)
        self.assertTrue(self.lib.test_session_close(self.session));self.assertEqual(self.lib.test_wifi_calls(18),1)
        self.assertEqual(self.lib.test_display_metric(1),0)
    def start_network(self):
        self.assertEqual(self.raw(2,1,struct.pack('<I',123)).status,0)
        payload=struct.pack('<3I32s64s',1,8,13,b'lab-test',b'test-only-key')
        reply=self.raw(14,2,payload);self.assertEqual(reply.status,0)
        self.assertEqual(struct.unpack('<2I',reply.payload),(1,0))
    def test_network_is_lazy_at_boot_and_usb_control_polls_driver_then_stops(self):
        self.open();self.step()
        self.assertTrue(all(self.lib.test_wifi_calls(i)==0 for i in range(24)))
        self.start_network();self.lib.test_wifi_notify(1);self.step();self.assertEqual(self.lib.test_wifi_calls(14),1)
        self.lib.test_wifi_notify(2);self.step()
        reply=self.raw(14,3,struct.pack('<I',2));self.assertEqual(struct.unpack('<2I',reply.payload),(2,0x0a0200c0))
        reply=self.raw(14,4,struct.pack('<I',3));self.assertEqual(struct.unpack('<2I',reply.payload),(0,0))
        self.assertEqual(self.lib.test_wifi_calls(18),1)
    def test_network_cleanup_failure_retains_session_hardware_until_explicit_retry(self):
        self.open();self.start_network();self.lib.test_wifi_fault(15)
        self.assertFalse(self.lib.test_session_close(self.session))
        self.assertEqual((self.lib.test_display_metric(1),self.metric(12)),(1,1))
        self.lib.test_wifi_fault(0);self.assertTrue(self.lib.test_session_close(self.session))
        self.assertEqual((self.lib.test_display_metric(1),self.metric(12)),(0,0))
    def test_network_timeout_continues_cleanup_when_usb_is_removed(self):
        self.open();self.start_network();self.lib.test_wifi_notify(1);self.step()
        self.lib.test_session_usb_installed(0);self.step();self.step(30001)
        self.assertEqual(self.lib.test_wifi_calls(18),1);self.assertEqual(self.metric(0),1)
        self.assertEqual(self.lib.test_session_network_state(self.session),0)

    def install_sound(self,microphone=False):
        name='audio_record' if microphone else 'audio_tone'
        args='i32.const 32' if microphone else 'i32.const 1000 i32.const 20'
        signature='(param i32)' if microphone else '(param i32 i32)'
        blob=bytes(wasmtime.wat2wasm(f'(module\n          (import "os" "{name}" (func $sound {signature} (result i32)))\n          (global $v (mut i32) (i32.const 0))\n          (func (export "sdk_abi") (result i32) i32.const 2)\n          (func (export "init"))\n          (func (export "debug_value") (result i32) global.get $v)\n          (func (export "tick") (param i32 i32 i32 i32) (result i32)\n            local.get 1 i32.const 16 i32.and if {args} call $sound global.set $v end i32.const 0))'))
        caps=['draw','speaker','microphone'] if microphone else ['draw','speaker']
        pack=contract.encode(contract.make_manifest('counter',blob,capabilities=caps),blob)
        self.assertTrue(self.install(self.store,pack));self.lib.test_audio_auto_io(1)
    def sound(self,i):return self.lib.test_session_sound_metric(self.session,i)
    def test_bsp_sound_is_lazy_for_draw_app_and_allocates_output_only_on_audio_launch(self):
        self.open();self.launch();self.assertEqual(self.lib.test_audio_memory(0),0)
        self.key(5);self.key();self.assertTrue(self.lib.test_session_close(self.session))
        self.install_sound();self.open();self.launch()
        self.assertEqual((self.sound(0),self.lib.test_audio_memory(2),self.lib.test_audio_calls(0)),(16000,32000,0))
        self.key();self.key(2);self.assertEqual(self.lib.test_session_value(self.session),1)
        self.assertEqual(self.lib.test_audio_calls(0),1);self.key(5);self.key()
        self.assertEqual((self.lib.test_audio_memory(2),self.lib.test_audio_memory(4)),(0,1))
        self.assertEqual(self.lib.test_audio_bad(),0)
    def test_bsp_audio_oom_keeps_ui_available_and_launch_can_retry(self):
        self.install_sound();self.open();self.lib.test_audio_memory_fault(1,0)
        self.key();self.key(2);self.assertEqual(self.metric(1),2)
        self.assertEqual(self.sound(4),self.sound(5));self.assertEqual(self.lib.test_audio_calls(0),0)
        self.assertEqual(self.lib.test_audio_memory(2),0);self.lib.test_audio_memory_fault(0,0)
        self.key();self.launch();self.assertEqual(self.lib.test_audio_memory(2),32000)
    def test_bsp_driver_cleanup_failure_keeps_pcm_image_and_display_until_retry(self):
        self.install_sound();self.open();self.launch();self.key();self.key(2)
        self.lib.test_audio_fault(7);self.key(5);self.assertEqual(self.metric(1),3)
        self.assertEqual((self.metric(3),self.lib.test_audio_memory(2)),(1,32000))
        self.assertFalse(self.lib.test_session_close(self.session));self.assertEqual(self.lib.test_display_metric(1),1)
        self.lib.test_audio_fault(0);self.assertTrue(self.lib.test_session_close(self.session))
        self.assertEqual((self.lib.test_audio_memory(2),self.lib.test_display_metric(1)),(0,0))
    def test_bsp_microphone_uses_input_driver_and_erases_64kb_on_exit(self):
        self.install_sound(True);self.open();self.launch();self.assertEqual(self.lib.test_audio_memory(2),64000)
        self.key();self.key(2)
        for _ in range(5):self.step(10)
        self.assertEqual(self.lib.test_session_value(self.session),1);self.assertEqual(self.lib.test_audio_calls(2),1)
        self.key(5);self.key();self.assertEqual((self.lib.test_audio_memory(2),self.lib.test_audio_memory(4)),(0,1))
        self.assertEqual(self.lib.test_audio_bad(),0)

    def test_audio_cleanup_failure_retains_home_loop_and_hardware_until_retry(self):
        blob=contract.wasm()
        pack=contract.encode(contract.make_manifest('counter',blob,capabilities=['speaker']),blob)
        self.assertTrue(self.install(self.store,pack));self.open()
        self.assertTrue(self.lib.test_session_audio_hooks(self.session));self.launch()
        self.lib.test_session_audio_fault(1)
        self.assertFalse(self.lib.test_session_close(self.session))
        self.assertEqual((self.metric(3),self.metric(12)),(1,1))
        self.assertEqual((self.lib.test_display_metric(1),self.lib.test_calls(5)),(1,0))
        self.lib.test_session_audio_fault(0);self.assertTrue(self.lib.test_session_close(self.session))
        self.assertEqual((self.lib.test_display_metric(1),self.lib.test_calls(5),self.metric(12)),(0,1,0))

    def test_empty_catalog_boot_accepts_first_usb_app_without_restarting_session(self):
        # Supplemental integration coverage after initial implementation.
        self.lib.test_action.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
        self.assertTrue(self.lib.test_action(self.store, b'counter', 1))
        self.open();self.step()
        self.assertEqual((self.metric(0), self.metric(2)), (1, 0))
        pack = contract.package(value=3)
        self.begin(pack);request = self.finish(pack)
        self.assertEqual(self.raw(10, request + 1).status, 0)
        self.assertEqual(self.metric(2), 1)
        self.launch()
        self.assertEqual(self.lib.test_session_value(self.session), 3)
        self.assert_hardware_ok()

    def test_invalid_configuration_and_existing_image_lease_do_no_hardware_io(self):
        for store, profile, nonce in ((self.store, 0, 123), (self.store, 2, 123), (self.store, 1, 0), (None, 1, 123)):
            self.assertFalse(self.lib.test_session_open(self.session, store, profile, nonce, 0))
        self.lib.test_open.argtypes = [C.c_void_p, C.c_char_p]
        self.lib.test_release.argtypes = [C.c_void_p]
        self.assertTrue(self.lib.test_open(self.store, b'counter'))
        self.assertFalse(self.lib.test_session_open(self.session, self.store, 1, 123, 0))
        self.lib.test_release(self.store)
        self.assertEqual([self.lib.test_display_calls(i) for i in range(20)], [0] * 20)
        self.assertEqual([self.lib.test_calls(i) for i in range(8)], [0] * 8)

    def test_real_input_renderer_vm_and_reserved_exit_share_one_session(self):
        self.open();self.launch()
        self.assertEqual(self.lib.test_session_value(self.session), 7)
        self.assertEqual(self.metric(3), 1)
        self.key(5)  # FN+B
        self.assertEqual(self.metric(1), 2)
        self.key()
        self.assertEqual((self.metric(1), self.metric(3)), (0, 0))
        self.assertTrue(self.lib.test_session_close(self.session))
        self.assertEqual((self.lib.test_display_metric(1), self.lib.test_calls(5), self.metric(12)), (0, 1, 0))
        self.assertTrue(self.install(self.store, contract.package(value=8, version='1.0.1')))
        self.assert_hardware_ok()

    def test_usb_install_update_and_second_app_start_use_same_store_and_runtime(self):
        self.open();self.step()
        self.assertTrue(any(f.op == 1 and f.response for f in self.output()))
        pack = contract.package(value=9, version='1.0.1')
        self.begin(pack);request = self.finish(pack)
        self.assertEqual(self.raw(10, request + 1).status, 0)
        self.assertEqual(self.version(self.store), '1.0.1')
        self.launch()
        self.assertEqual(self.lib.test_session_value(self.session), 9)
        self.key(5);self.key()
        game = contract.package('game', value=4)
        self.begin(game);request = self.finish(game)
        self.assertEqual(self.raw(10, request + 1).status, 0)
        self.assertEqual(self.metric(2), 2)
        self.input();self.step()
        self.input(y=0);self.step()  # down, un-debounced ADC direction.
        self.input();self.step()
        self.key(2)
        self.assertEqual((self.metric(1), self.lib.test_session_value(self.session)), (1, 4))
        self.assertEqual(self.version(self.store, 0), '1.0.1')
        self.assert_hardware_ok()

    def test_short_management_session_and_partial_frame_gate_home_until_release(self):
        self.open();self.step()
        self.input(2)
        packet = encode(Frame(2, 999, 1, struct.pack('<I', 123))) + encode(Frame(10, 999, 2, b''))
        self.write(packet)
        self.step(20)
        self.assertEqual((self.metric(1), self.metric(6)), (0, 0))
        self.key();self.key(2)
        self.assertEqual(self.metric(1), 1)
        self.key(5);self.key()
        self.input(2)
        frame = encode(Frame(2, 999, 1, struct.pack('<I', 123)))
        self.write(frame[:15]);self.step(20)
        self.assertEqual(self.metric(1), 0)
        self.write(frame[15:])
        self.assertEqual(self.metric(6), 999)
        self.raw(10, 2);self.step(20)
        self.assertEqual(self.metric(1), 0)
        self.key();self.key(2)
        self.assertEqual(self.metric(1), 1)

    def test_reused_session_ids_in_one_read_still_require_release(self):
        self.open();self.step()
        packet = encode(Frame(2, 999, 1, struct.pack('<I', 123))) + encode(Frame(10, 999, 2, b''))
        self.write(packet)
        self.assertEqual((self.metric(1), self.metric(6)), (0, 0))
        self.input(2)
        self.write(packet)  # end-state counters equal the previous OPEN/CLOSE pair.
        self.step(20)
        self.assertEqual(self.metric(1), 0)
        self.key();self.key(2)
        self.assertEqual(self.metric(1), 1)

    def test_running_guest_and_fn_b_continue_during_management_session(self):
        self.open();self.launch()
        self.assertEqual(self.raw(2, 1, struct.pack('<I', 123)).status, 0)
        self.assertEqual(self.raw(3, 2, struct.pack('<I', 264) + bytes(32)).status, 2)
        self.assertEqual(self.metric(1), 1)
        self.key(5);self.key()
        self.key(2)
        self.assertEqual(self.metric(1), 0)
        self.raw(10, 3)
        self.key();self.key(2)
        self.assertEqual(self.metric(1), 1)

    def test_tx_backpressure_keeps_upload_and_exact_commit_replay(self):
        self.open();self.step()
        pack = contract.package(value=12, version='1.0.1')
        self.begin(pack)
        self.assertEqual(self.raw(4, 3, struct.pack('<I', 0) + pack).status, 0)
        self.output();self.lib.test_session_usb_reject_tx()
        packet = encode(Frame(5, 999, 4, b''))
        self.write(packet)
        sequence = self.lib.test_status(self.store, 2)
        self.assertEqual((self.metric(0), self.metric(4), self.metric(5)), (1, 1, 0))
        self.write(packet)
        self.assertTrue(any(f.op == 5 and f.status == 0 for f in self.output()))
        self.assertEqual(self.lib.test_status(self.store, 2), sequence)
        self.assertEqual(self.version(self.store), '1.0.1')

    def test_missing_usb_or_read_fault_keeps_local_home_but_frees_upload(self):
        self.lib.test_session_usb_installed(0)
        self.open();self.launch()
        self.assertEqual(self.metric(4), 0)
        self.assertTrue(self.lib.test_session_close(self.session))
        self.lib.test_session_usb_installed(1)
        self.open();self.step()
        self.begin(contract.package())
        self.assertEqual(self.metric(5), 1)
        self.lib.test_session_usb_read_fault(-1);self.step()
        self.assertEqual((self.metric(0), self.metric(4), self.metric(5)), (1, 0, 0))
        self.key();self.key(2)
        self.assertEqual(self.metric(1), 1)
        self.assert_hardware_ok()

    def test_input_failure_releases_guest_and_services_keep_polling_until_neutral(self):
        self.open();self.launch()
        self.lib.test_fault(6);self.step(result=1)
        self.assertEqual((self.metric(0), self.metric(1), self.metric(3)), (1, 0, 0))
        reads = self.metric(8)
        self.lib.test_fault(0)
        self.input(2);self.step()
        self.assertGreater(self.metric(8), reads)
        self.assertEqual(self.metric(1), 0)
        self.key();self.key(2)
        self.assertEqual(self.metric(1), 1)

    def test_display_failure_closes_upload_input_and_display_and_stops(self):
        self.open();self.step()
        self.begin(contract.package())
        self.lib.test_display_fault(7, self.lib.test_display_calls(7) + 1)
        # Static HOME no longer paints on a timer. An input fault changes the
        # visible notice and makes the next actual paint hit the SPI failure.
        self.lib.test_fault(6)
        self.step(40, result=2)
        self.assertEqual([self.metric(i) for i in (0, 3, 4, 5, 12)], [0] * 5)
        self.assertEqual((self.lib.test_display_metric(1), self.lib.test_calls(5)), (0, 1))
        reads = self.metric(8);self.step(result=2)
        self.assertEqual(self.metric(8), reads)
        self.assertTrue(self.install(self.store, contract.package(version='1.0.1')))

    def test_partial_boot_failure_unwinds_and_retains_borrowed_store(self):
        for input_stage, display_stage in ((0, 4), (3, -1)):
            with self.subTest(input_stage=input_stage, display_stage=display_stage):
                self.lib.test_fault(input_stage);self.lib.test_display_fault(display_stage, 1)
                self.assertFalse(self.lib.test_session_open(self.session, self.store, 1, 123, 0))
                self.lib.test_fault(0);self.lib.test_display_fault(-1, 1)
                self.assertTrue(self.lib.test_session_close(self.session))
                self.assertEqual([self.metric(i) for i in (0, 3, 4, 5, 12)], [0] * 5)
                self.assertEqual([self.lib.test_display_metric(i) for i in range(1, 6)], [0] * 5)
                self.assertEqual(self.version(self.store), '1.0.0')

    def test_cleanup_failure_attempts_both_drivers_and_retains_global_owner_for_retry(self):
        self.open();self.launch()
        other = self.new_session()
        self.lib.test_fault(7)
        self.assertFalse(self.lib.test_session_close(self.session))
        self.assertEqual((self.metric(3), self.metric(4), self.lib.test_display_metric(1)), (0, 0, 0))
        before = self.lib.test_calls(1)
        self.assertFalse(self.lib.test_session_open(other, self.store, 1, 123, 0))
        self.assertEqual(self.lib.test_calls(1), before)
        self.lib.test_fault(0)
        self.assertTrue(self.lib.test_session_close(self.session))
        self.assertTrue(self.lib.test_session_open(other, self.store, 1, 123, 0))


    def test_voice_query_at_home_is_unavailable_and_never_opens_microphone(self):
        self.open();self.assertEqual(self.raw(2,1,struct.pack('<I',123)).status,0)
        result=self.raw(15,2,struct.pack('<I',5))
        self.assertEqual(result.status,0);self.assertEqual(result.payload,struct.pack('<I',1)+bytes(76))
        self.assertEqual(self.lib.test_audio_calls(0),0)

    def test_voice_query_serializes_provider_scalars_and_hides_them_after_exit(self):
        self.install_sound(True);self.open()
        provider=self.lib.test_session_voice_fixture;provider.argtypes=[C.c_void_p]
        self.assertEqual(provider(self.session),1);self.launch();self.key()
        self.assertEqual(self.raw(2,1,struct.pack('<I',123)).status,0)
        result=self.raw(15,2,struct.pack('<I',5));self.assertEqual(result.status,0)
        self.assertEqual(struct.unpack('<3Ii2I3i4I2i4I',result.payload[:76]),
                         (1,1,7,6,0,32000,1600,1600,1600,1600,0,0,0,1600,1600,1,3,1234,1))
        self.assertEqual(result.payload[76:],bytes(4));self.assertEqual(self.lib.test_audio_calls(0),0)
        self.assertEqual(self.raw(10,3).status,0);self.key(5);self.key()
        self.assertEqual(self.raw(2,1,struct.pack('<I',123),session=777).status,0)
        result=self.raw(15,2,struct.pack('<I',5),session=777)
        self.assertEqual(result.status,0);self.assertEqual(result.payload,struct.pack('<I',1)+bytes(76))


class SessionConsoleGuardTests(SessionFixture, unittest.TestCase):
    console_flags = ('-DCONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=1',)

    def test_shared_console_leaves_transfer_off_without_changing_driver_or_local_ui(self):
        self.open();self.launch()
        self.assertEqual((self.metric(4), self.metric(8), self.metric(9)), (0, 0, 0))
        self.assertEqual(self.metric(1), 1)
        self.assert_hardware_ok()
