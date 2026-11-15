import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from unittest import mock

import test_labos_c_store as contract
from labos.transfer import Client,TransferError,main


def row(sequence=7):
    return struct.pack('<18I',sequence,100,2,1,*((50000,20000,10000)*3),1234,196192,40,1000,1)


class TelemetryClientTests(unittest.TestCase):
    def client(self):
        c=Client(None,clock=lambda:0,session=9);c.connected=True;return c

    def test_decoder_rejects_malformed_or_inconsistent_snapshots(self):
        valid=list(struct.unpack('<18I',row()))
        cases=[(struct.pack('<3I',2,1,7),row()),(struct.pack('<3I',1,33,7),row()),
               (bytes(4),row()),(struct.pack('<3I',1,1,7),bytes(4))]
        for at,value in ((0,8),(2,0),(3,32),(5,50001),(6,50001),(17,2),(16,196193),(15,1001),(17,0),(3,0)):
            words=valid.copy();words[at]=value
            cases.append((struct.pack('<3I',1,1,7),struct.pack('<18I',*words)))
        for header,payload in cases:
            c=self.client()
            with self.subTest(header=header,payload=payload),mock.patch.object(c,'_request',side_effect=[header,payload]),self.assertRaises(TransferError):c.telemetry()
            self.assertTrue(c.failed);self.assertIsNone(c.deadline)

    def test_stale_snapshots_retry_only_three_times_and_leave_read_only_session_usable(self):
        c=self.client()
        def reply(op,payload):
            self.assertEqual(op,13)
            if struct.unpack('<2I',payload)[0]==0:return struct.pack('<3I',1,1,7)
            raise TransferError('overwritten',status=9)
        with mock.patch.object(c,'_request',side_effect=reply) as request,self.assertRaises(TransferError):c.telemetry()
        self.assertEqual(request.call_count,6);self.assertFalse(c.failed);self.assertIsNone(c.deadline)

    def test_readout_obeys_overall_deadline_before_request(self):
        c=self.client();c.clock=mock.Mock(side_effect=[0,31])
        with mock.patch.object(c,'_request') as request,self.assertRaises(TransferError):c.telemetry()
        request.assert_not_called();self.assertTrue(c.failed);self.assertIsNone(c.deadline)

    def test_cli_telemetry_does_not_fall_back_to_catalog_or_mutating_commands(self):
        result={'schema':1,'newest_sequence':0,'samples':[]};client=mock.Mock();client.telemetry.return_value=result
        output=io.StringIO()
        with mock.patch('labos.transfer.serial_connection') as connection,\
             mock.patch('labos.transfer.Client',return_value=client),redirect_stdout(output):
            self.assertEqual(main(['--port','/dev/cu.fixture','telemetry']),0)
        connection.assert_called_once_with('/dev/cu.fixture');client.connect.assert_called_once_with()
        client.telemetry.assert_called_once_with();client.close.assert_called_once_with()
        client.list_apps.assert_not_called();client.collect.assert_not_called();client.install.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()),result)
