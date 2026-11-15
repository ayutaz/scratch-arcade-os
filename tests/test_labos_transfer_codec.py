import struct
import sys
import unittest
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototypes/lab-os'))
from labos.transfer import Frame, Parser, encode, Client, TransferError, serial_connection, main
from labos.package import encode as package_encode
from labos.sdk import make_manifest
import wasmtime


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


class TransferCodecTests(unittest.TestCase):
    def test_audio_status_is_a_bounded_readonly_snapshot_without_pcm(self):
        payload=struct.pack('<11Ii32x',1,2,1,1,32000,0,8000,256,2,0,32768,0)
        client=Client(None,session=9);client._request=mock.Mock(return_value=payload)
        row=client.audio_status();client._request.assert_called_once_with(15,struct.pack('<I',3))
        self.assertEqual((row['phase'],row['position'],row['peak'],row['result']),(2,256,32768,0))
        self.assertNotIn('pcm',row)
    def test_audio_status_rejects_impossible_bounds_and_reserved_data(self):
        good=struct.pack('<11Ii32x',1,2,1,1,32000,0,8000,256,2,0,32768,0)
        bad=[good[:-1],good[:-1]+b'x']
        for index,value in ((0,2),(1,5),(2,2),(3,2),(4,32001),(5,32001),(6,32001),(7,8001),(8,3),(9,2),(10,32769),(11,2)):
            p=bytearray(good);struct.pack_into('<I',p,index*4,value);bad.append(bytes(p))
        for p in bad:
            client=Client(None,session=9);client._request=mock.Mock(return_value=p)
            with self.assertRaises(TransferError):client.audio_status()
            self.assertTrue(client.failed)
    def test_control_helpers_encode_pulse_and_decode_canonical_snapshot(self):
        payload=struct.pack('<11I33s3x',1,1,0,0,2,16,100,7,9,3,123,b'counter')
        client=Client(None,session=9);client._request=mock.Mock(return_value=payload)
        status=client.input_pulse(16,duration_ms=100)
        self.assertEqual((status['active_id'],status['held'],status['remaining_ms'],status['generation']),('counter',16,100,7))
        client._request.assert_called_with(15,struct.pack('<3I',2,16,100))
        self.assertEqual(client.control_status()['draw_crc32'],123)
        client._request.assert_called_with(15,struct.pack('<I',1))
    def test_control_rejects_unbounded_or_non_integer_pulse_before_sending(self):
        client=Client(None,session=9);client._request=mock.Mock()
        for held,ms in ((True,100),(-1,100),(256,100),(16,True),(16,19),(16,251)):
            with self.subTest(held=held,ms=ms),self.assertRaises(ValueError):client.input_pulse(held,duration_ms=ms)
        client._request.assert_not_called()
    def test_control_rejects_noncanonical_snapshots_without_echoing_them(self):
        good=struct.pack('<11I33s3x',1,1,0,0,2,16,100,7,9,3,123,b'counter')
        bad=[b'private-status',good[:-1],good[:-1]+b'x',good[:44]+b'../bad'+bytes(30)]
        for index,value in ((0,2),(1,4),(2,7),(3,2),(4,17),(5,256),(6,251),(9,129)):
            payload=bytearray(good);struct.pack_into('<I',payload,index*4,value);bad.append(bytes(payload))
        for payload in bad:
            client=Client(None,session=9);client._request=mock.Mock(return_value=payload)
            with self.assertRaises(TransferError) as error:client.control_status()
            self.assertTrue(client.failed);self.assertNotIn('private-status',str(error.exception))
    def test_control_rejects_impossible_empty_drawing_and_unowned_active_lease(self):
        good=struct.pack('<11I33s3x',1,1,0,0,2,16,100,7,9,3,123,b'counter')
        for index,value in ((4,0),(7,0),(9,0)):
            payload=bytearray(good);struct.pack_into('<I',payload,index*4,value)
            client=Client(None,session=9);client._request=mock.Mock(return_value=bytes(payload))
            with self.subTest(index=index),self.assertRaises(TransferError):client.control_status()
    def test_network_route_and_channel_status_have_separate_canonical_payloads(self):
        client=Client(None,session=9);client._request=mock.Mock(return_value=struct.pack('<2I',0,0))
        self.assertEqual(client.network_route('127.0.0.1',50000),dict(state=0,ipv4=0))
        client._request.assert_called_with(14,struct.pack('<I4s2I',4,b'\x7f\0\0\x01',0,50000))
        client._request.return_value=struct.pack('<2I',1,50001)
        self.assertEqual(client.network_channel_status(),dict(state=1,port=50001))
        client._request.assert_called_with(14,struct.pack('<I',5))
    def test_network_route_rejects_hostname_multicast_and_invalid_port_without_sending(self):
        client=Client(None,session=9);client._request=mock.Mock()
        for peer,port,local in (('localhost',50000,0),('224.0.0.1',50000,0),('0.0.0.0',50000,0),
                                ('127.0.0.1',0,0),('127.0.0.1',65536,0),('127.0.0.1',True,0),
                                ('127.0.0.1',50000,80),('127.0.0.1',50000,65536)):
            with self.subTest(peer=peer,port=port,local=local),self.assertRaises(ValueError):
                client.network_route(peer,port,local_port=local)
        client._request.assert_not_called()
    def test_channel_status_rejects_invalid_state_port_pair_and_never_echoes_payload(self):
        for reply in (b'bad-private',struct.pack('<2I',4,0),struct.pack('<2I',1,0),
                      struct.pack('<2I',0,5),struct.pack('<2I',1,65536)):
            client=Client(None,session=9);client._request=mock.Mock(return_value=reply)
            with self.assertRaises(TransferError) as error:client.network_channel_status()
            self.assertTrue(client.failed);self.assertNotIn('bad-private',str(error.exception))
    def test_network_helpers_validate_credentials_before_sending_without_echoing_them(self):
        client=Client(None,session=9);client._request=mock.Mock()
        for ssid,password in (('', 'test-only-key'),('s'*33,'test-only-key'),
                              ('lab-test','short'),('lab-test','p'*64),
                              ('lab\0test','test-only-key'),('lab-test','password\n'),
                              ('lab-test','日本語のパスワード'),(None,'test-only-key')):
            with self.subTest(ssid_bytes=len(ssid or '')):
                with self.assertRaises(ValueError) as error:client.network_start(ssid,password)
                self.assertNotIn('test-only-key',str(error.exception))
                self.assertNotIn('password\n',str(error.exception))
        client._request.assert_not_called()

    def test_network_helpers_encode_canonical_maximum_fields_and_small_status_stop(self):
        client=Client(None,session=9);client._request=mock.Mock(return_value=struct.pack('<2I',2,0x01020304))
        self.assertEqual(client.network_start('s'*32,'p'*63),dict(state=2,ipv4=0x01020304))
        client._request.assert_called_with(14,struct.pack('<3I32s64s',1,32,63,b's'*32,b'p'*63))
        client.network_status();client._request.assert_called_with(14,struct.pack('<I',2))
        client.network_stop();client._request.assert_called_with(14,struct.pack('<I',3))

    def test_invalid_network_status_is_not_accepted_or_included_in_error_text(self):
        for payload in (b'secret-response',struct.pack('<2I',5,0),struct.pack('<2I',2,0),
                        struct.pack('<2I',1,123)):
            client=Client(None,session=9);client._request=mock.Mock(return_value=payload)
            with self.assertRaises(TransferError) as error:client.network_status()
            self.assertTrue(client.failed);self.assertNotIn('secret-response',str(error.exception))

    def test_little_endian_crc_frame_survives_every_split(self):
        frame = Frame(4, 123, 9, b'\0\0\0\0\x00asm')
        packet = encode(frame)
        self.assertEqual(packet[:8], b'LABXFR1\0')
        self.assertEqual(struct.unpack_from('<3I', packet, 12), (123, 9, 8))
        for split in range(len(packet) + 1):
            parser = Parser()
            self.assertEqual(parser.feed(packet[:split]) + parser.feed(packet[split:]), [frame])

    def test_junk_corrupt_crc_oversized_header_and_embedded_frame_do_not_execute(self):
        good = encode(Frame(2, 9, 1, struct.pack('<I', 123)))
        bad = bytearray(encode(Frame(4, 9, 2, good)))
        bad[-1] ^= 1
        oversized = bytearray(good[:28])
        struct.pack_into('<I', oversized, 20, 0xffffffff)
        parser = Parser()
        result = parser.feed(b'x' * 8192 + bytes(oversized) + bytes(bad) + good)
        self.assertEqual(result, [Frame(2, 9, 1, struct.pack('<I', 123))])
        self.assertLessEqual(len(parser.buffer), 544)

    def test_outbound_frames_reject_unbounded_fields_and_unknown_flags(self):
        for frame in (Frame(4, 1, 1, b'x' * 517), Frame(4, -1, 1, b''),
                      Frame(True, 1, 1, b''), Frame(4, 1, 2**32, b'')):
            with self.assertRaises(ValueError): encode(frame)
        packet = bytearray(encode(Frame(2, 9, 1, b'')))
        packet[9] = 1
        self.assertEqual(Parser().feed(packet), [])

    def test_client_does_not_transmit_before_a_matching_passive_beacon(self):
        clock = Clock()
        class StockStream:
            writes = []
            def read(self, n): clock.now += .1; return b'MicroPython v1.25.0\r\n>>> '
            def write(self, data): self.writes.append(data); return len(data)
        stream = StockStream()
        client = Client(stream, clock=clock, timeout=.2, attempts=2, session=9)
        with self.assertRaises(TransferError): client.connect()
        client.close()
        self.assertEqual(stream.writes, [])

    def test_matching_crc_with_wrong_beacon_profile_is_still_passive(self):
        clock = Clock()
        wrong = encode(Frame(1, 0, 0, b'LABOS_TRANSFER_1' + struct.pack('<4I', 123, 16384, 512, 1), response=True))
        class WrongStream:
            writes = []
            def read(self, n): clock.now += .1; return wrong
            def write(self, data): self.writes.append(data); return len(data)
        stream = WrongStream()
        with self.assertRaises(TransferError):
            Client(stream, clock=clock, timeout=.2, session=9).connect()
        self.assertEqual(stream.writes, [])

    def test_serial_port_opens_with_control_lines_disabled_and_no_repl_commands(self):
        observed = []
        port = mock.Mock()
        port.open.side_effect = lambda: observed.append((port.dtr, port.rts, port.port))
        with mock.patch('serial.Serial', return_value=port) as factory:
            with serial_connection('/dev/cu.lab-test') as stream:
                self.assertIs(stream, port)
        self.assertEqual(observed, [(False, False, '/dev/cu.lab-test')])
        port.write.assert_not_called()
        port.close.assert_called_once()
        self.assertEqual(factory.call_args.kwargs['port'], None)

    def test_upload_has_whole_operation_deadline_even_when_every_ack_arrives(self):
        clock = Clock()
        client = Client(None, clock=clock, session=9)
        client.connected, client.max_package, client.chunk = True, 16384, 1
        operations = []
        def acknowledge(op, payload=b''):
            operations.append(op)
            clock.now += 1
            if op == 3: return bytes(4)
            if op == 4: return struct.pack('<I', struct.unpack_from('<I', payload)[0] + len(payload) - 4)
            return bytes(4)
        client._request = acknowledge
        wasm = bytes(wasmtime.wat2wasm('(module)'))
        with self.assertRaises(TransferError):
            client.install(package_encode(make_manifest('timer', wasm), wasm))
        self.assertNotIn(5, operations)
        self.assertLessEqual(len(operations), 31)
        self.assertTrue(client.failed)

    def test_cli_rejects_oversized_package_before_reading_or_opening_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / 'oversized.labapp'
            with package.open('wb') as stream: stream.truncate(16385)
            with mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded file read')), \
                 mock.patch('labos.transfer.serial_connection') as connection, self.assertRaises(TransferError):
                main(['--port', '/dev/cu.lab-test', 'install', str(package)])
            connection.assert_not_called()
