"""同じSession/USB/実WAMRへ期限付き入力を渡す。実GPIOはfixture。"""
from pathlib import Path
import socket
import struct
import tempfile
import time
import unittest

import test_labos_c_store as contract
from test_labos_board_session import SessionFixture
from labos.build import build
from labos.package import encode


class RemoteInputTests(SessionFixture,unittest.TestCase):
    def test_repeated_home_direction_pulses_release_edges_while_management_gate_remains(self):
        self.assertTrue(self.install(self.store,contract.package('game')))
        self.assertTrue(self.install(self.store,contract.package('network')))
        self.start_remote();self.pulse(4);self.release();self.assertEqual(self.status()['selected'],1)
        self.pulse(4);self.release();self.assertEqual(self.status()['selected'],2)
        self.input(2);self.step();self.step(20)
        self.assertEqual(self.metric(1),0)  # Physical A stays gated by USB management.
    def audio_status(self):
        reply=self.rpc(struct.pack('<I',3));self.assertEqual(reply.status,0)
        self.assertEqual(len(reply.payload),80);self.assertEqual(reply.payload[48:],bytes(32))
        return dict(zip(('version','phase','claimed','driver_owned','capacity','recorded','total','position','kind','replaying','peak','result'),struct.unpack('<11Ii32x',reply.payload)))
    def test_audio_status_does_not_allocate_or_start_hardware_and_clears_after_exit(self):
        with tempfile.TemporaryDirectory() as tmp:m,b=build('speaker',Path(tmp))
        self.assertTrue(self.install(self.store,encode(m,b)));self.start_remote()
        row=self.audio_status();self.assertEqual((row['capacity'],row['claimed']),(0,0))
        self.assertEqual(self.lib.test_audio_calls(0),0);self.assertEqual(self.lib.test_audio_memory(0),0)
        self.pulse(4);self.release();self.launch_remote()
        row=self.audio_status();self.assertEqual((row['capacity'],row['claimed'],row['driver_owned']),(16000,1,0))
        self.assertEqual(self.lib.test_audio_calls(0),0)
        self.lib.test_audio_auto_io(1);self.pulse(16)
        for _ in range(30):self.step(10)
        self.lib.test_audio_sent(5);self.step()
        row=self.audio_status();self.assertEqual((row['total'],row['position'],row['result']),(3200,3200,1))
        self.assertEqual((row['phase'],row['driver_owned']),(0,0))
        self.release();self.pulse(192);self.release();row=self.audio_status()
        self.assertEqual((row['capacity'],row['claimed'],row['position']),(0,0,0))
    def test_microphone_diagnostics_expose_only_frame_counts_and_peak(self):
        with tempfile.TemporaryDirectory() as tmp:m,b=build('microphone',Path(tmp))
        self.assertTrue(self.install(self.store,encode(m,b)));self.start_remote()
        self.lib.test_audio_auto_io(1);self.pulse(4);self.release();self.launch_remote();self.pulse(16)
        for _ in range(40):self.step(10)
        row=self.audio_status();self.assertEqual((row['recorded'],row['total'],row['result']),(8000,8000,1))
        self.assertEqual(row['kind'],2);self.assertGreater(row['peak'],0)
        self.release();self.pulse(32)
        for _ in range(40):self.step(10)
        self.lib.test_audio_sent(5);self.step()
        row=self.audio_status();self.assertEqual((row['replaying'],row['position'],row['result']),(1,8000,1))
        self.release();self.pulse(192);self.release()
        self.assertEqual(self.audio_status()['capacity'],0)
    def start_remote(self,*,counter=False):
        if counter:
            with tempfile.TemporaryDirectory() as tmp:m,b=build('counter',Path(tmp))
            self.assertTrue(self.install(self.store,encode(m,b)))
        self.open();self.step()
        self.assertEqual(self.raw(2,1,struct.pack('<I',123)).status,0);self.request=2
    def rpc(self,payload):
        reply=self.raw(15,self.request,payload);self.request+=1;return reply
    def status(self):
        reply=self.rpc(struct.pack('<I',1));self.assertEqual(reply.status,0)
        fields=struct.unpack('<11I33s3x',reply.payload)
        return dict(zip(('version','mode','notice','selected','count','held','remaining_ms','generation','applied','draw_count','draw_crc32','active_id'),(*fields[:11],fields[11].split(b'\0')[0].decode())))
    def pulse(self,held,ms=100):
        reply=self.rpc(struct.pack('<3I',2,held,ms));self.assertEqual(reply.status,0);return reply
    def release(self):self.step(251)
    def launch_remote(self):
        self.pulse(0);self.release();self.pulse(16);self.assertEqual(self.metric(1),1);self.release()
    def test_remote_counter_launch_operation_exit_and_readonly_draw_snapshot(self):
        self.start_remote(counter=True);self.assertEqual(self.status()['active_id'],'')
        self.launch_remote();before=self.status();self.assertEqual(before['active_id'],'counter')
        self.assertGreater(before['draw_count'],0);self.pulse(1);self.release()
        after=self.status();self.assertNotEqual(after['draw_crc32'],before['draw_crc32'])
        self.assertEqual(self.lib.test_session_value(self.session),1)
        self.pulse(192);self.assertEqual(self.metric(1),2);self.release()
        self.assertEqual((self.metric(1),self.metric(3)),(0,0));self.assertEqual(self.status()['active_id'],'')
        self.assertGreater(after['applied'],before['applied']);self.assert_hardware_ok()
    def test_measured_idle_axis_drift_allows_remote_launch_but_real_direction_interrupts(self):
        self.input(x=1950,y=1895)
        self.start_remote(counter=True);self.launch_remote()
        self.assertEqual(self.status()['active_id'],'counter')
        self.pulse(1);self.release()
        self.assertEqual(self.lib.test_session_value(self.session),1)
        self.pulse(1);self.input(x=1147,y=1895);self.step(result=1)
        self.assertEqual((self.metric(1),self.metric(3)),(0,0))
        self.assertEqual(self.rpc(struct.pack('<3I',2,16,100)).status,8)
        self.input(x=1955,y=1897);self.step()
        self.launch_remote();self.pulse(192);self.release()
        self.assertEqual((self.metric(1),self.metric(3)),(0,0))

    def test_duplicate_ack_never_extends_deadline_or_repeats_pulse(self):
        self.start_remote();self.pulse(0);self.release()
        request=self.request;original=self.pulse(16,100);self.step(30)
        reply=self.raw(15,request,struct.pack('<3I',2,16,100))
        self.assertEqual((reply.status,reply.payload),(0,original.payload));first=self.status()
        self.assertEqual(first['generation'],2);self.assertLess(first['remaining_ms'],100)
        reply=self.raw(15,request,struct.pack('<3I',2,16,100))
        # Replay only works for the most recent request. A later STATUS consumes
        # the sequence, so this stale request must be rejected rather than rerun.
        self.assertEqual(reply.status,3)
        self.release();last=self.status();self.assertEqual(last['generation'],first['generation'])
        self.assertEqual((last['held'],last['remaining_ms']),(0,0))
    def test_close_and_reopen_same_session_id_in_one_read_cancel_old_pulse(self):
        self.start_remote();self.launch_remote();self.pulse(1)
        from labos.transfer import Frame,encode as frame
        packet=frame(Frame(10,999,self.request,b''))+frame(Frame(2,999,1,struct.pack('<I',123)))
        self.write(packet);self.output();self.request=2
        self.assertEqual(self.status()['remaining_ms'],0)
    def test_close_or_usb_failure_releases_remote_input_without_restarting_app(self):
        for failure in ('close','read'):
            with self.subTest(failure=failure):
                self.start_remote();self.launch_remote();self.pulse(1)
                if failure=='close':self.assertEqual(self.raw(10,self.request).status,0)
                else:self.lib.test_session_usb_read_fault(-1);self.step()
                self.assertEqual(self.metric(1),1)
                self.assertEqual(self.lib.test_session_value(self.session),8)
                self.assertEqual(self.lib.test_session_remote_metric(self.session,0),0)
                self.assertEqual(self.lib.test_session_remote_metric(self.session,1),0)
                self.key(5);self.key();self.assertEqual(self.metric(1),0)
                self.assertTrue(self.lib.test_session_close(self.session))
                self.lib.test_session_usb_reset()
    def test_physical_input_interrupts_remote_control_and_requires_neutral(self):
        self.start_remote();self.launch_remote();self.pulse(1)
        self.input(2);self.step(result=1)
        self.assertEqual((self.metric(1),self.metric(3)),(0,0))
        reply=self.rpc(struct.pack('<3I',2,16,100));self.assertEqual(reply.status,8)
        self.input();self.step();status=self.status();self.assertEqual(status['remaining_ms'],0)
        self.pulse(0);self.release();self.pulse(16);self.assertEqual(self.metric(1),1)
    def test_upload_cancels_queued_pulse_and_status_never_advances_upload(self):
        self.start_remote();self.pulse(0);self.release()
        from labos.transfer import Frame,encode as frame
        packet=frame(Frame(15,999,self.request,struct.pack('<3I',2,16,100)))
        packet+=frame(Frame(3,999,self.request+1,struct.pack('<I',264)+bytes(32)))
        self.request+=2;self.write(packet);self.output()
        self.assertEqual((self.metric(1),self.metric(5)),(0,1))
        self.assertEqual(self.status()['remaining_ms'],0)
        self.assertEqual(self.rpc(struct.pack('<3I',2,16,100)).status,2)
        self.assertEqual(self.metric(5),1);self.assertEqual(self.raw(6,self.request).status,0)
    def test_pulse_expires_across_uint32_clock_wrap(self):
        self.now=0xfffffff0;self.start_remote();self.pulse(0,100)
        self.step(50);self.assertGreater(self.status()['remaining_ms'],0)
        self.step(100);self.assertEqual(self.status()['remaining_ms'],0)
    def test_status_crc_matches_rectangles_and_never_calls_guest_debug_export(self):
        # Supplemental read-only coverage after implementation: a debug export
        # with an audio side effect must never be called by STATUS.
        import wasmtime,zlib
        blob=bytes(wasmtime.wat2wasm('''(module
          (import "os" "rect" (func $rect (param i32 i32 i32 i32 i32)))
          (import "os" "audio_tone" (func $tone (param i32 i32) (result i32)))
          (func (export "sdk_abi") (result i32) i32.const 2)
          (func (export "init"))
          (func (export "debug_value") (result i32) i32.const 1000 i32.const 20 call $tone)
          (func (export "tick") (param i32 i32 i32 i32) (result i32)
            i32.const 10 i32.const 20 i32.const 30 i32.const 40 i32.const 65535 call $rect i32.const 0))'''))
        manifest=contract.make_manifest('counter',blob,capabilities=['draw','speaker'])
        self.assertTrue(self.install(self.store,encode(manifest,blob)));self.start_remote();self.launch_remote()
        before=self.lib.test_audio_calls(0);status=self.status()
        self.assertEqual((status['draw_count'],status['draw_crc32']),(1,zlib.crc32(struct.pack('<5I',10,20,30,40,65535))))
        self.assertEqual(self.lib.test_audio_calls(0),before);self.assertEqual(before,0)
    def test_input_read_failure_cancels_remote_lease_before_recovery(self):
        # Supplemental failure-path coverage; the implementation already clears it.
        self.start_remote();self.launch_remote();self.pulse(1)
        self.lib.test_fault(6);self.step(result=1);self.lib.test_fault(0);self.step()
        self.assertEqual(self.status()['remaining_ms'],0)
        self.assertEqual((self.metric(1),self.metric(3)),(0,0))
    def test_actual_c_network_app_uses_remote_input_and_real_socket_without_physical_keys(self):
        with tempfile.TemporaryDirectory() as tmp:m,b=build('network',Path(tmp))
        self.assertTrue(self.install(self.store,encode(m,b)))
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.addCleanup(peer.close)
        peer.bind(('127.0.0.1',0));peer.settimeout(1)
        self.start_remote()
        payload=struct.pack('<3I32s64s',1,8,13,b'lab-test',b'test-only-key')
        self.assertEqual(self.raw(14,self.request,payload).status,0);self.request+=1
        self.lib.test_wifi_notify(1);self.step();self.lib.test_wifi_notify(2);self.step()
        payload=struct.pack('<I4s2I',4,b'\x7f\0\0\x01',0,peer.getsockname()[1])
        self.assertEqual(self.raw(14,self.request,payload).status,0);self.request+=1
        self.pulse(0);self.release();self.pulse(4);self.release();self.launch_remote()
        self.assertEqual(self.status()['active_id'],'network')
        reply=self.raw(14,self.request,struct.pack('<I',5));self.request+=1
        state,port=struct.unpack('<2I',reply.payload);self.assertEqual(state,1)
        packet=b'LBN1'+struct.pack('<I',12)+b'\x00\xffAB';peer.sendto(packet,('127.0.0.1',port))
        deadline=time.monotonic()+1
        while self.lib.test_session_value(self.session)!=1 and time.monotonic()<deadline:self.step();time.sleep(.001)
        self.assertEqual(self.lib.test_session_value(self.session),1);self.pulse(16);self.step()
        data,source=peer.recvfrom(128);self.assertEqual(data,b'LBA1'+packet[4:]);self.assertEqual(source[1],port)
        self.release();self.pulse(192);self.release()
        self.assertEqual((self.metric(1),self.metric(3)),(0,0))

    def test_slow_full_frame_render_does_not_starve_16khz_microphone_dma(self):
        with tempfile.TemporaryDirectory() as tmp:m,b=build('microphone',Path(tmp))
        self.assertTrue(self.install(self.store,encode(m,b)));self.start_remote()
        self.lib.test_audio_auto_io(1);self.pulse(4);self.release();self.launch_remote()
        # Each LCD row costs 333us: one frame is ~80ms. The real four 128-frame
        # descriptors hold only 32ms. Arrival is time-paced, not unlimited I/O.
        self.lib.test_audio_paced(1);self.pulse(16,20)
        result=None
        for _ in range(18):
            self.step(90);result=self.audio_status()
            if result['result']:break
        self.assertEqual((result['recorded'],result['position'],result['result']),(8000,8000,1))
        self.assertEqual(self.lib.test_audio_dropped(),0)
        self.release();self.pulse(192);self.release()
        self.assertEqual(self.audio_status()['capacity'],0)
