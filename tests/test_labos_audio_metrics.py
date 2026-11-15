"""小さい統計だけのUSB診断。PCMや実機の音声は扱わない。"""
import ctypes as C
import struct
import unittest
from unittest import mock
import test_labos_board_session as fixture
import test_labos_audio_home as audio
from labos.transfer import Client,TransferError


class MetricsWireTests(unittest.TestCase):
    def packet(self,**changes):
        names=('version','available','frames','minimum','maximum','mean','rms','ac_rms','centered_peak','saturated_frames','first_1320','first_1760','second_1320','second_1760','requested_gain','effective_scale_q15','discarded_input_frames')
        data=dict(zip(names,(1,1,8000,-20,30,0,2,2,30,0,0,0,0,0,4,0,1600)))
        data.update(changes)
        return struct.pack('<3I3i11I',*[data[k] for k in names])+b'\0'*12

    def test_request_is_read_only_and_small_typed_metrics_are_parsed(self):
        c=Client(mock.Mock());c._request=mock.Mock(return_value=self.packet())
        result=c.audio_metrics()
        c._request.assert_called_once_with(15,struct.pack('<I',4))
        self.assertEqual((result['frames'],result['mean'],result['ac_rms']),(8000,0,2))
        self.assertNotIn('pcm',result)

    def test_malformed_inconsistent_and_stale_metrics_fail_closed(self):
        for data in (b'\0'*79,self.packet(version=2),self.packet(available=0),self.packet(frames=32001),self.packet(minimum=100),self.packet(centered_peak=65536),self.packet(saturated_frames=8001),self.packet(requested_gain=9),self.packet(effective_scale_q15=262145),self.packet(discarded_input_frames=1601),self.packet()+b'x',self.packet()[:-1]+b'x'):
            c=Client(mock.Mock());c._request=mock.Mock(return_value=data)
            with self.assertRaises(TransferError):c.audio_metrics()
            self.assertTrue(c.failed)


class MetricsSessionTests(fixture.SessionFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        p=audio.audio_package('a-metrics',['speaker','microphone'],
            'local.get $p i32.const 16 i32.and if i32.const 500 call $rec drop end',
            '(import "os" "audio_record" (func $rec (param i32) (result i32)))')
        self.assertTrue(self.install(self.store,p));self.open();self.step();self.pending=bytearray()
        self.lib.test_audio_auto_io(1);case=self
        class Stream:
            def write(self,data):case.assertTrue(case.lib.test_session_enqueue(data,len(data)));return len(data)
            def read(self,n):
                case.step(5);out=C.create_string_buffer(8192);size=case.lib.test_session_output(out,len(out))
                case.pending.extend(out.raw[:size]);reply=bytes(case.pending[:n]);del case.pending[:n];return reply
        self.client=Client(Stream(),clock=lambda:self.now/1000,timeout=.5,session=781)
        self.client.connect();self.addCleanup(self.client.close)

    def press(self,key):
        self.client.input_pulse(key,duration_ms=20)
        for _ in range(6):self.step(10)

    def test_home_and_busy_recording_never_expose_previous_app_metrics(self):
        self.assertFalse(self.client.audio_metrics()['available'])
        self.press(16);self.lib.test_audio_auto_io(0);self.press(16)
        self.assertEqual(self.client.audio_status()['phase'],2)
        self.assertFalse(self.client.audio_metrics()['available'])

    def test_complete_capture_reports_metrics_without_allocating_or_starting_io(self):
        self.press(16);self.press(16)
        for _ in range(40):self.step(16)
        before=self.lib.test_audio_calls(0)
        value=self.client.audio_metrics()
        self.assertTrue(value['available']);self.assertEqual(value['frames'],8000)
        self.assertEqual((value['minimum'],value['maximum'],value['mean']),(-20,30,0))
        self.assertEqual(value['discarded_input_frames'],1600)
        self.assertEqual(self.lib.test_audio_calls(0),before)
        self.press(192);self.step()
        self.assertFalse(self.client.audio_metrics()['available'])
