import io
import json
import struct
import unittest
import sys
from pathlib import Path
from contextlib import nullcontext,redirect_stdout
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototypes/lab-os'))
from labos import transfer


class CollectionClientTests(unittest.TestCase):
    def test_progress_to_done_returns_stats_and_uses_only_collect_requests(self):
        client=transfer.Client(object());client.connected=True
        with mock.patch.object(client,'_request',side_effect=[struct.pack('<5I',0,0,9000,0,0),
                struct.pack('<5I',1,400,9000,0,0),struct.pack('<5I',2,800,9000,8200,1)]) as send:
            result=client.collect()
        self.assertEqual(result,{'removed_files':2,'removed_bytes':800,'logical_before':9000,'logical_after':8200})
        self.assertEqual(send.call_args_list,[mock.call(12)]*3);self.assertIsNone(client.deadline)

    def test_malformed_or_regressing_progress_marks_session_uncertain(self):
        for replies in ([b'bad'],[struct.pack('<5I',0,0,0,0,2)],
                        [struct.pack('<5I',2,40,100,0,0),struct.pack('<5I',1,20,100,80,1)]):
            client=transfer.Client(object());client.connected=True
            with self.subTest(replies=replies),mock.patch.object(client,'_request',side_effect=replies),self.assertRaises(transfer.TransferError):
                client.collect()
            self.assertTrue(client.failed);self.assertIsNone(client.deadline)

    def test_progress_has_absolute_deadline_and_finite_command_limit(self):
        for times in ([0,31],None):
            client=transfer.Client(object(),clock=mock.Mock(side_effect=times) if times else lambda:0);client.connected=True
            with mock.patch.object(client,'_request',return_value=struct.pack('<5I',0,0,0,0,0)),self.assertRaises(transfer.TransferError): client.collect()
            self.assertTrue(client.failed);self.assertIsNone(client.deadline)

    def test_cli_collect_prints_stats_and_closes_client_using_fake_connection_only(self):
        result={'removed_files':1,'removed_bytes':100,'logical_before':5000,'logical_after':4900}
        output=io.StringIO()
        with mock.patch.object(transfer,'serial_connection',return_value=nullcontext(object())) as connection, \
             mock.patch.object(transfer,'Client') as factory,redirect_stdout(output):
            factory.return_value.collect.return_value=result
            self.assertEqual(transfer.main(['--port','fixture-only','collect']),0)
        connection.assert_called_once_with('fixture-only');factory.return_value.collect.assert_called_once_with()
        factory.return_value.close.assert_called_once_with();self.assertEqual(json.loads(output.getvalue()),result)
