import ctypes as C
import hashlib
import struct
import unittest

import test_labos_lfs as fs
import test_labos_c_store as contract
from labos.transfer import Frame, Parser, encode, Client, TransferError

READ = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32))
SEND = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p, C.c_uint32)
NETWORK = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p)
CONTROL = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p)
ROOT = contract.ROOT


class TransferTests(fs.LittleFsFixture, unittest.TestCase):
    extra_sources = (ROOT / 'prototypes/lab-os/native/app_transfer.c',
                     ROOT / 'tests/native/lab_transfer_bridge.c',
                     ROOT / 'firmware/esp-idf/lab-os-core/main/resource_monitor.c',
                     ROOT / 'tests/native/lab_telemetry_fixture.c',
                     ROOT / 'tests/native/lab_transfer_private_bridge.c')
    extra_flags = tuple('-I'+str(ROOT/p) for p in ('firmware/esp-idf/lab-os-core/main','tests/native/resource_fixture'))
    extra_signatures = {
        'lab_transfer_set_control': ([C.c_void_p, CONTROL, C.c_void_p], C.c_bool),
        'lab_transfer_set_network': ([C.c_void_p, NETWORK, C.c_void_p], C.c_bool),
        'test_transfer_memory_size': ([], C.c_uint32),
        'test_transfer_rx_zero': ([C.c_void_p], C.c_int),
        'test_transfer_hash_failure': ([C.c_void_p, C.c_int], None),
        'lab_transfer_close': ([C.c_void_p], None),
        'test_telemetry_init': ([], C.c_void_p),
        'test_telemetry_advance': ([C.c_uint], None),
        'test_telemetry_sequence': ([C.c_uint32], None),
        'lab_transfer_set_telemetry': ([C.c_void_p, READ, C.c_void_p], C.c_bool),
        'lab_resource_readout': ([C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32)], C.c_int),
        'test_transfer_new': ([C.c_void_p, SEND, C.c_void_p, C.c_uint32], C.c_void_p),
        'test_transfer_free': ([C.c_void_p], None),
        'test_transfer_feed': ([C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32], C.c_int),
        'test_transfer_poll': ([C.c_void_p, C.c_uint32], C.c_int),
        'test_transfer_busy': ([C.c_void_p], C.c_int),
        'test_home_count': ([C.c_void_p], C.c_int),
        'test_home_refresh': ([C.c_void_p], C.c_int),
    }

    def setUp(self):
        self.transfers = []
        super().setUp()
        self.assertTrue(self.connect())
        self.store = self.open_store()
        self.assertTrue(self.lib.test_home_start(self.store))
        self.now = 0.0
        self.responses = bytearray()
        self.sent = []
        self.replies = []
        self.drop = []
        self.corrupt_offset = False
        self.sender = SEND(self.emit)
        self.receiver = self.lib.test_transfer_new(self.store, self.sender, None, 123)
        self.assertTrue(self.receiver)
        self.transfers.append(self.receiver)

    def close_all(self):
        for transfer in self.transfers:
            self.lib.test_transfer_free(transfer)
        self.transfers.clear()
        super().close_all()

    def emit(self, ctx, data, n):
        packet = C.string_at(data, n)
        frame = Parser().feed(packet)[0]
        self.replies.append(frame)
        if frame.op in self.drop:
            self.drop.remove(frame.op)
            return True  # Simulate an ACK lost after the OS completed work.
        if self.corrupt_offset and frame.op == 4:
            packet = encode(Frame(frame.op, frame.session, frame.request,
                                  struct.pack('<I', 0xffffffff), frame.status, True))
        self.responses.extend(packet)
        return True

    def clock(self): return self.now

    def read(self, n):
        self.now += .01
        self.lib.test_transfer_poll(self.receiver, int(self.now * 1000) & 0xffffffff)
        out = bytes(self.responses[:min(n, 17)])
        del self.responses[:len(out)]
        return out

    def write(self, data):
        self.sent.append(bytes(data))
        for i in range(0, len(data), 13):
            self.assertTrue(self.lib.test_transfer_feed(self.receiver, data[i:i+13],
                                                        len(data[i:i+13]), int(self.now * 1000)))
        return len(data)

    def client(self):
        c = Client(self, clock=self.clock, timeout=.2, attempts=3, session=999)
        c.connect()
        return c

    def test_stale_boot_challenge_reacquires_fresh_beacon_only_after_explicit_rejection(self):
        payload=b'LABOS_TRANSFER_1'+struct.pack('<4I',987,16384,512,2)
        self.responses.extend(encode(Frame(1,0,0,payload,response=True)))
        c=Client(self,clock=self.clock,timeout=1.2,attempts=3,session=777)
        c.connect()
        opens=[Parser().feed(packet)[0] for packet in self.sent]
        self.assertTrue(c.connected)
        self.assertEqual(c.boot_nonce,123)
        self.assertEqual([struct.unpack('<I',f.payload)[0] for f in opens],[987,123])
        self.assertTrue(all(f.op==2 and f.request==1 for f in opens))
        self.assertEqual(c.list_apps(),[]);c.close()

    def test_busy_open_never_restarts_handshake_with_another_session_or_challenge(self):
        first=self.client();self.responses.clear();self.sent.clear()
        payload=b'LABOS_TRANSFER_1'+struct.pack('<4I',123,16384,512,2)
        self.responses.extend(encode(Frame(1,0,0,payload,response=True)))
        c=Client(self,clock=self.clock,timeout=.2,attempts=3,session=777)
        with self.assertRaises(TransferError) as error:c.connect()
        self.assertEqual(error.exception.status,2);self.assertEqual(len(self.sent),1)
        self.assertIsNone(c.boot_nonce)
        first.close()

    def raw(self, op, request, payload=b'', session=999):
        self.responses.clear()
        self.write(encode(Frame(op, session, request, payload)))
        frames = Parser().feed(bytes(self.responses))
        self.responses.clear()
        self.assertEqual(len(frames), 1)
        return frames[0]

    def begin(self, pack, request=2):
        return self.raw(3, request, struct.pack('<I', len(pack)) + hashlib.sha256(pack).digest())

    def bind_telemetry(self, callback=None):
        self.monitor=self.lib.test_telemetry_init();self.read_calls=0
        def read(context,kind,sequence,out,length):
            self.read_calls+=1
            return self.lib.lab_resource_readout(context,kind,sequence,out,length)
        self.reader=READ(callback or read)
        self.assertTrue(self.lib.lab_transfer_set_telemetry(self.receiver,self.reader,self.monitor))

    def bind_control(self):
        self.control_calls=[]
        def control(ctx,data,size,now,out):
            payload=C.string_at(data,size);self.control_calls.append((payload,now))
            C.memmove(out,struct.pack('<11I33s3x',1,0,0,0,0,0,0,0,0,0,0,b''),80);return 1
        self.controller=CONTROL(control)
        self.assertTrue(self.lib.lab_transfer_set_control(self.receiver,self.controller,None))

    def test_control_requires_an_explicit_provider_and_canonical_input(self):
        client=self.client()
        self.assertEqual(self.raw(15,client.request,struct.pack('<I',1)).status,8);client.request+=1
        for payload in (b'',struct.pack('<I',5),struct.pack('<3I',2,256,100),
                        struct.pack('<3I',2,16,19),struct.pack('<3I',2,16,251),struct.pack('<4I',2,16,100,0)):
            self.assertEqual(self.raw(15,client.request,payload).status,1);client.request+=1
        client.close()

    def test_audio_status_is_readonly_during_upload_without_cancelling_it(self):
        self.bind_control();client=self.client()
        client._request(3,struct.pack('<I',264)+bytes(32))
        self.assertEqual(client.audio_status()['capacity'],0)
        self.assertTrue(self.lib.test_transfer_busy(self.receiver));self.assertEqual(len(self.control_calls),1)
        self.assertEqual(self.control_calls[0][0],struct.pack('<I',3));client._request(6);client.close()

    def test_control_ack_retry_does_not_repeat_pulse_and_setter_is_pre_session_only(self):
        self.bind_control();client=self.client();self.drop=[15]
        client.input_pulse(16,duration_ms=100)
        self.assertEqual(len(self.control_calls),1)
        self.assertEqual(self.control_calls[0][0],struct.pack('<3I',2,16,100))
        self.assertFalse(self.lib.lab_transfer_set_control(self.receiver,self.controller,None));client.close()

    def test_control_status_during_upload_preserves_transaction_and_blocks_pulse(self):
        self.bind_control();client=self.client();pack=contract.package()
        client._request(3,struct.pack('<I',len(pack))+bytes(32));self.assertTrue(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(client.control_status()['mode'],0)
        with self.assertRaises(TransferError) as error:client.input_pulse(16,duration_ms=100)
        self.assertEqual(error.exception.status,2);self.assertTrue(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(len(self.control_calls),1);client._request(6);client.close()

    def test_control_pulse_and_status_are_available_while_app_runs(self):
        self.bind_control();client=self.client();client.install(contract.package(value=7))
        self.lib.test_home_frame(self.store,16,0);self.lib.test_home_frame(self.store,0,0)
        client.input_pulse(192,duration_ms=100);client.control_status()
        self.assertEqual(len(self.control_calls),2);self.assertEqual(self.lib.test_home_value(self.store),7)
        client.close()

    def bind_network(self, callback=None):
        self.network_calls = []
        def network(context, data, size, now, out):
            payload = C.string_at(data, size)
            self.network_calls.append((payload, now))
            C.memmove(out, struct.pack('<2I', 1, 0), 8)
            return 1
        self.network_callback = NETWORK(callback or network)
        self.assertTrue(self.lib.lab_transfer_set_network(self.receiver, self.network_callback, None))

    def network_packet(self):
        return struct.pack('<3I32s64s', 1, 8, 13, b'lab-test', b'test-only-key')

    def assert_no_network_secret(self):
        memory = C.string_at(self.receiver, self.lib.test_transfer_memory_size())
        self.assertNotIn(b'lab-test', memory)
        self.assertNotIn(b'test-only-key', memory)
        self.assertTrue(self.lib.test_transfer_rx_zero(self.receiver))

    def test_network_start_replays_lost_ack_once_without_retaining_raw_credentials(self):
        self.bind_network();c=self.client();self.drop=[14]
        self.assertEqual(c.network_start('lab-test','test-only-key'),dict(state=1,ipv4=0))
        self.assertEqual(len(self.network_calls),1)
        self.assertEqual(self.network_calls[0][0],self.network_packet())
        packets=[p for p in self.sent if Parser().feed(p)[0].op==14]
        self.assertEqual(len(packets),2);self.assertEqual(packets[0],packets[1])
        self.assert_no_network_secret();c.close()
    def bind_channel(self):
        self.channel_calls=[]
        def control(ctx,data,size,now,out):
            payload=C.string_at(data,size);self.channel_calls.append(payload)
            reply=(1,50001) if struct.unpack_from('<I',payload)[0]==5 else (0,0)
            C.memmove(out,struct.pack('<2I',*reply),8);return 1
        self.bind_network(control)
    def test_network_route_replays_ack_and_channel_status_is_readable_during_app(self):
        self.bind_channel();c=self.client();self.drop=[14]
        self.assertEqual(c.network_route('127.0.0.1',50000),dict(state=0,ipv4=0))
        self.assertEqual(len(self.channel_calls),1)
        c.install(contract.package(value=7));self.lib.test_home_frame(self.store,16,0);self.lib.test_home_frame(self.store,0,0)
        self.assertEqual(c.network_channel_status(),dict(state=1,port=50001))
        with self.assertRaises(TransferError) as error:c.network_route('127.0.0.1',50002)
        self.assertEqual(error.exception.status,2);self.assertEqual(len(self.channel_calls),2)
        self.assertEqual(self.lib.test_home_value(self.store),7);c.close()
    def test_network_route_malformed_values_are_rejected_before_callback(self):
        self.bind_channel();c=self.client()
        for peer,local,remote in ((b'\xe0\0\0\x01',0,50000),(bytes(4),0,50000),
                                  (b'\x7f\0\0\x01',80,50000),(b'\x7f\0\0\x01',65536,50000),
                                  (b'\x7f\0\0\x01',0,0),(b'\x7f\0\0\x01',0,65536)):
            reply=self.raw(14,c.request,struct.pack('<I4s2I',4,peer,local,remote));c.request+=1
            self.assertEqual((reply.status,reply.payload),(1,b''))
        self.assertEqual(self.channel_calls,[]);c.close()
    def test_network_channel_status_does_not_advance_or_cancel_upload(self):
        self.bind_channel();c=self.client();pack=contract.package()
        c._request(3,struct.pack('<I',len(pack))+bytes(32));self.assertTrue(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(c.network_channel_status(),dict(state=1,port=50001))
        with self.assertRaises(TransferError) as error:c.network_route('127.0.0.1',50000)
        self.assertEqual(error.exception.status,2);self.assertTrue(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(len(self.channel_calls),1);c._request(6);c.close()

    def test_network_control_rejects_noncanonical_payloads_before_provider(self):
        self.bind_network();c=self.client()
        malformed=[b'',bytes(4),struct.pack('<I',4),struct.pack('<I',1),
                   self.network_packet()+b'x',
                   struct.pack('<3I32s64s',1,33,13,b'lab-test',b'test-only-key'),
                   struct.pack('<3I32s64s',1,8,7,b'lab-test',b'test-only-key'),
                   struct.pack('<3I32s64s',1,8,13,b'lab-testX',b'test-only-key'),
                   struct.pack('<3I32s64s',1,8,13,b'lab-test',b'test-only-keyX'),
                   struct.pack('<3I32s64s',1,8,13,b'lab\0test',b'test-only-key')]
        for payload in malformed:
            with self.subTest(size=len(payload)):
                frame=self.raw(14,c.request,payload);c.request+=1
                self.assertEqual(frame.status,1);self.assertEqual(frame.payload,b'')
                self.assert_no_network_secret()
        self.assertEqual(self.network_calls,[]);c.close()

    def test_network_requires_a_session_and_provider_and_cannot_rebind_during_session(self):
        self.assertEqual(self.raw(14,1,self.network_packet()).status,6)
        self.assert_no_network_secret();self.now+=1.1;c=self.client()
        with self.assertRaises(TransferError) as error:c.network_status()
        self.assertEqual(error.exception.status,8);c.close();self.bind_network();self.now+=1.1;c=self.client()
        self.assertFalse(self.lib.lab_transfer_set_network(self.receiver,self.network_callback,None))
        self.assertEqual(c.network_stop(),dict(state=1,ipv4=0));c.close()

    def test_network_status_during_app_or_upload_is_read_only_but_mutations_are_busy(self):
        self.bind_network();c=self.client();c.install(contract.package(value=7))
        self.lib.test_home_frame(self.store,16,0);self.lib.test_home_frame(self.store,0,0)
        self.assertEqual(c.network_status(),dict(state=1,ipv4=0))
        for method in (lambda:c.network_start('lab-test','test-only-key'),c.network_stop):
            with self.assertRaises(TransferError) as error:method()
            self.assertEqual(error.exception.status,2)
        self.assertEqual(len(self.network_calls),1);self.assertEqual(self.lib.test_home_value(self.store),7)
        self.lib.test_home_frame(self.store,192,0);self.lib.test_home_frame(self.store,0,0)
        c._request(3,struct.pack('<I',len(contract.package()))+bytes(32))
        self.assertTrue(self.lib.test_transfer_busy(self.receiver));c.network_status()
        with self.assertRaises(TransferError) as error:c.network_stop()
        self.assertEqual(error.exception.status,2);self.assertTrue(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(len(self.network_calls),2);c._request(6);c.close()

    def test_network_same_request_with_different_secret_is_rejected_without_repeating_start(self):
        self.bind_network();c=self.client();c.network_start('lab-test','test-only-key')
        other=struct.pack('<3I32s64s',1,8,13,b'lab-test',b'changed-value')
        self.assertEqual(self.raw(14,2,other).status,3)
        self.assertEqual(len(self.network_calls),1);self.assert_no_network_secret();c.close()

    def test_network_partial_frame_timeout_and_close_wipe_service_owned_receive_memory(self):
        packet=encode(Frame(14,999,1,self.network_packet()))
        self.assertTrue(self.lib.test_transfer_feed(self.receiver,packet[:-6],len(packet)-6,0))
        self.assertIn(b'test-only-key',C.string_at(self.receiver,self.lib.test_transfer_memory_size()))
        self.lib.test_transfer_poll(self.receiver,2001);self.assert_no_network_secret()
        self.assertTrue(self.lib.test_transfer_feed(self.receiver,packet[:-6],len(packet)-6,2010))
        self.lib.lab_transfer_close(self.receiver);self.assert_no_network_secret()

    def test_network_digest_failure_stops_before_provider_and_does_not_retain_credentials(self):
        self.bind_network();c=self.client();self.lib.test_transfer_hash_failure(self.receiver,1)
        try:
            with self.assertRaises(TransferError) as error:c.network_start('lab-test','test-only-key')
            self.assertEqual(error.exception.status,5);self.assertEqual(self.network_calls,[])
            self.assert_no_network_secret()
        finally:self.lib.test_transfer_hash_failure(self.receiver,0)

    def test_network_callback_errors_have_no_payload_or_secret_and_are_not_reexecuted_on_retry(self):
        for result,status in ((0,8),(-1,5),(2,5)):
            calls=[]
            def reject(context,data,size,now,out):
                calls.append(size);C.memmove(out,b'secret!?',8);return result
            self.bind_network(reject);self.now+=1.1;c=self.client();self.drop=[14]
            first_reply=len(self.replies)
            with self.assertRaises(TransferError) as error:c.network_start('lab-test','test-only-key')
            self.assertEqual(error.exception.status,status);self.assertEqual(calls,[108])
            replies=[f for f in self.replies[first_reply:] if f.op==14 and f.request==2]
            self.assertTrue(replies)
            self.assertTrue(all(f.status==status and f.payload==b'' for f in replies))
            self.assert_no_network_secret();c.close()

    def test_telemetry_reads_real_ring_and_replays_lost_ack_without_repeating_callback(self):
        self.bind_telemetry();self.lib.test_telemetry_advance(3);c=self.client();self.drop=[13]
        result=c.telemetry()
        self.assertEqual(result['newest_sequence'],3)
        self.assertEqual([r['sequence'] for r in result['samples']],[1,2,3])
        self.assertEqual([r['time_ms'] for r in result['samples']],[1000,2000,3000])
        self.assertEqual(result['samples'][0]['stack_free_bytes'],1234)
        self.assertEqual(self.read_calls,4)
        self.assertEqual(self.lib.test_count(self.store),0)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver));c.close()

    def test_telemetry_is_readable_during_app_upload_and_collection_without_mutation(self):
        self.bind_telemetry();self.lib.test_telemetry_advance(1);c=self.client()
        c.install(contract.package(value=7));self.lib.test_home_frame(self.store,16,0);self.lib.test_home_frame(self.store,0,0)
        self.assertEqual(c.telemetry()['samples'][0]['sequence'],1)
        self.assertEqual(self.lib.test_home_value(self.store),7)
        self.lib.test_home_frame(self.store,192,0);self.lib.test_home_frame(self.store,0,0)
        pack=contract.package(version='1.0.1')
        c._request(3,struct.pack('<I',len(pack))+hashlib.sha256(pack).digest())
        self.assertTrue(self.lib.test_transfer_busy(self.receiver));self.assertEqual(len(c.telemetry()['samples']),1)
        self.assertTrue(self.lib.test_transfer_busy(self.receiver));c._request(6)
        self.assertEqual(self.lib.test_count(self.store),1);c.close()
        # Collector attachment is permitted only outside a protocol session.
        collect_type=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(C.c_uint32));cancel_type=C.CFUNCTYPE(None,C.c_void_p)
        self.collect_calls=0
        def collect(context,stats):
            self.collect_calls+=1
            return 0
        self.collector=collect_type(collect);self.cancel=cancel_type(lambda context:None)
        fn=self.lib.lab_transfer_set_collector;fn.argtypes=[C.c_void_p,collect_type,cancel_type,C.c_void_p];fn.restype=C.c_bool
        self.assertTrue(fn(self.receiver,self.collector,self.cancel,None))
        self.now+=1.1;c=self.client();c._request(12)
        self.assertTrue(self.lib.test_transfer_busy(self.receiver));c.telemetry()
        self.assertEqual(self.collect_calls,1);self.assertTrue(self.lib.test_transfer_busy(self.receiver));c.close()

    def test_telemetry_keeps_snapshot_sequences_when_new_rows_arrive_and_retries_overwrite(self):
        self.bind_telemetry();self.lib.test_telemetry_advance(32)
        self.overwrite=True
        def read(context,kind,sequence,out,length):
            if kind==1 and self.overwrite:self.overwrite=False;self.lib.test_telemetry_advance(1)
            return self.lib.lab_resource_readout(context,kind,sequence,out,length)
        self.reader=READ(read);self.assertTrue(self.lib.lab_transfer_set_telemetry(self.receiver,self.reader,self.monitor))
        c=self.client();result=c.telemetry()
        self.assertEqual([r['sequence'] for r in result['samples']],list(range(2,34)))
        self.assertFalse(c.failed);c.close()

    def test_telemetry_empty_and_sequence_wrap_have_unambiguous_rows(self):
        self.bind_telemetry();c=self.client();self.assertEqual(c.telemetry()['samples'],[])
        self.lib.test_telemetry_sequence(0xfffffffe);self.lib.test_telemetry_advance(2)
        result=c.telemetry();self.assertEqual(result['newest_sequence'],0)
        self.assertEqual([r['sequence'] for r in result['samples']],[0xffffffff,0]);c.close()

    def test_telemetry_requires_session_reader_and_valid_request_and_checks_callback_result(self):
        self.assertEqual(self.raw(13,1,bytes(8)).status,6);self.now+=1.1;c=self.client()
        self.assertEqual(self.raw(13,2,bytes(8)).status,8)
        c.request=3;c.close();self.bind_telemetry();self.now+=1.1;c=self.client()
        for payload in (b'',bytes(4),struct.pack('<2I',2,0),struct.pack('<2I',0,1)):
            self.assertEqual(self.raw(13,c.request,payload).status,1);c.request+=1
        self.assertEqual(self.read_calls,0)
        self.assertFalse(self.lib.lab_transfer_set_telemetry(self.receiver,self.reader,self.monitor))
        self.assertEqual(self.raw(13,c.request,struct.pack('<2I',1,99)).status,9);c.request+=1
        c.close();self.now+=1.1
        for result,size in ((-1,0),(2,0),(1,81)):
            def bad(context,kind,sequence,out,length):length[0]=size;return result
            self.reader=READ(bad);self.assertTrue(self.lib.lab_transfer_set_telemetry(self.receiver,self.reader,self.monitor))
            c=self.client();self.assertEqual(self.raw(13,2,bytes(8)).status,5);c.request=3;c.close();self.now+=1.1

    def test_client_to_real_c_store_home_and_littlefs_individual_updates(self):
        c = self.client()
        self.assertEqual(c.list_apps(), [])
        c.install(contract.package(value=7))
        game = contract.package('game')
        c.install(game)
        before = self.raw_get('/lab-apps/' + hashlib.sha256(game).hexdigest() + '.lab')
        c.install(contract.package(value=9, version='1.0.1'))
        rows = c.list_apps()
        self.assertEqual([(r['id'], r['version']) for r in rows], [('counter', '1.0.1'), ('game', '1.0.0')])
        self.assertEqual(self.lib.test_home_count(self.store), 2)
        self.assertEqual(self.raw_get('/lab-apps/' + hashlib.sha256(game).hexdigest() + '.lab'), before)
        c.rollback('counter')
        self.assertEqual(c.list_apps()[0]['version'], '1.0.0')
        c.remove('game')
        self.assertEqual([r['id'] for r in c.list_apps()], ['counter'])
        c.close()
        for held in (16, 0): self.lib.test_home_frame(self.store, held, 10)
        self.assertEqual(self.lib.test_home_value(self.store), 7)

    def test_lost_data_and_commit_acks_are_replayed_without_repeating_mutations(self):
        c = self.client()
        self.drop = [4, 5]
        c.install(contract.package())
        self.assertEqual(self.lib.test_status(self.store, 2), 1)
        packets = [Parser().feed(p)[0] for p in self.sent]
        for op in (4, 5):
            repeated = [p for p in packets if p.op == op]
            self.assertEqual(len(repeated), 2)
            self.assertEqual(repeated[0], repeated[1])

    def test_session_offsets_complete_size_and_duplicate_identity_are_checked(self):
        self.assertEqual(self.raw(3, 1, b'x').status, 6)
        self.assertEqual(self.raw(2, 1, struct.pack('<I', 321)).status, 1)
        self.assertEqual(self.raw(2, 1, struct.pack('<I', 123)).status, 0)
        pack = contract.package()
        self.assertEqual(self.begin(pack).status, 0)
        self.assertEqual(self.raw(4, 3, struct.pack('<I', 1) + pack[:10]).status, 3)
        self.assertEqual(self.raw(4, 4, struct.pack('<I', 0) + pack[:10]).status, 0)
        self.assertEqual(self.raw(4, 4, struct.pack('<I', 0) + b'wrong').status, 3)
        self.assertEqual(self.raw(4, 4, struct.pack('<I', 0) + pack[:10]).status, 0)
        self.assertEqual(self.raw(5, 5).status, 3)
        self.assertEqual(self.raw(4, 6, struct.pack('<I', 10) + pack[10:], session=888).status, 6)
        self.assertEqual(self.lib.test_count(self.store), 0)
        self.assertEqual(self.raw(6, 6).status, 0)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))

    def test_hash_or_vm_failure_does_not_publish_and_frees_upload(self):
        self.raw(2, 1, struct.pack('<I', 123))
        pack = contract.package()
        self.assertEqual(self.raw(3, 2, struct.pack('<I', len(pack)) + bytes(32)).status, 0)
        self.assertEqual(self.raw(4, 3, struct.pack('<I', 0) + pack).status, 0)
        self.assertEqual(self.raw(5, 4).status, 4)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))
        c = self.client_after_close(5)
        with self.assertRaises(TransferError): c.install(contract.package(body='unreachable'))
        self.assertEqual(self.lib.test_count(self.store), 0)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))

    def client_after_close(self, request):
        self.assertEqual(self.raw(10, request).status, 0)
        self.now += 1.1
        return self.client()

    def test_idle_and_absolute_deadlines_free_ram_and_ignore_late_commit(self):
        self.raw(2, 1, struct.pack('<I', 123))
        self.begin(contract.package())
        self.now = 6.0
        self.lib.test_transfer_poll(self.receiver, 6000)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(self.raw(5, 3).status, 6)
        self.raw(2, 1, struct.pack('<I', 123))
        self.begin(contract.package())
        for i in range(1, 30):
            self.now = 6.0 + i
            self.assertEqual(self.raw(11, i + 2).status, 0)
        self.now = 36.001
        self.lib.test_transfer_poll(self.receiver, 36001)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(self.raw(5, 32).status, 6)
        self.assertEqual(self.lib.test_count(self.store), 0)

    def test_partial_packet_timeout_resynchronizes_and_clock_wrap_is_safe(self):
        partial = encode(Frame(2, 999, 1, struct.pack('<I', 123)))[:20]
        self.assertTrue(self.lib.test_transfer_feed(self.receiver, partial, len(partial), 0))
        self.lib.test_transfer_poll(self.receiver, 2001)
        self.now = (2**32 - 100) / 1000
        self.assertEqual(self.raw(2, 1, struct.pack('<I', 123)).status, 0)
        self.now = .02
        self.assertEqual(self.begin(contract.package()).status, 0)
        self.assertTrue(self.lib.test_transfer_busy(self.receiver))

    def test_running_app_rejects_begin_and_starting_app_cancels_pending_upload(self):
        self.assertTrue(self.install(self.store, contract.package()))
        self.assertTrue(self.lib.test_home_refresh(self.store))
        self.raw(2, 1, struct.pack('<I', 123))
        self.begin(contract.package(version='1.0.1'))
        self.lib.test_home_frame(self.store, 16, 0)
        self.assertEqual(self.raw(4, 3, struct.pack('<I', 0) + b'x').status, 2)
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))
        self.assertEqual(self.begin(contract.package(), 4).status, 2)
        self.assertEqual(self.version(self.store), '1.0.0')

    def test_read_only_storage_error_leaves_existing_app_list_and_code_intact(self):
        self.assertTrue(self.connect(quota=3800))
        # This fixture's store points to the same driver; quota is applied below it.
        c = self.client()
        c.install(contract.package(value=7))
        with self.assertRaises(TransferError): c.install(contract.package('game'))
        self.assertFalse(self.lib.test_status(self.store, 0))
        self.assertEqual([r['id'] for r in c.list_apps()], ['counter'])
        c.close()
        for held in (16, 0): self.lib.test_home_frame(self.store, held, 10)
        self.assertEqual(self.lib.test_home_value(self.store), 7)

    def test_malformed_control_and_oversized_begin_cannot_modify_store(self):
        self.raw(2, 1, struct.pack('<I', 123))
        self.assertEqual(self.raw(3, 2, struct.pack('<I', 0xffffffff) + bytes(32)).status, 1)
        self.assertEqual(self.raw(8, 3, b'counter\0other').status, 1)
        self.assertEqual(self.raw(8, 4, b'../outside').status, 1)
        self.assertEqual(self.raw(99, 5).status, 1)
        self.assertEqual(self.lib.test_count(self.store), 0)

    def test_native_stream_discards_crc_corruption_embedded_commands_and_echoes(self):
        self.lib.test_transfer_poll(self.receiver, 0)
        echo = bytes(self.responses)
        self.responses.clear()
        self.write(echo)
        self.assertEqual(self.responses, b'')
        opening = encode(Frame(2, 999, 1, struct.pack('<I', 123)))
        bad = bytearray(encode(Frame(4, 999, 2, opening)))
        bad[24] ^= 1
        oversized = bytearray(opening[:28])
        struct.pack_into('<I', oversized, 20, 0xffffffff)
        self.write(b'x' * 8192 + oversized + bad)
        self.assertEqual(self.responses, b'')
        self.assertEqual(self.raw(3, 2, b'x').status, 6)
        self.assertEqual(self.raw(2, 1, struct.pack('<I', 123)).status, 0)
        self.assertEqual(self.lib.test_count(self.store), 0)

    def test_client_rejects_wrong_ack_offset_before_sending_commit(self):
        c = self.client()
        self.corrupt_offset = True
        with self.assertRaises(TransferError): c.install(contract.package())
        self.assertNotIn(5, [Parser().feed(p)[0].op for p in self.sent])
        self.assertEqual(self.lib.test_count(self.store), 0)

    @unittest.skipUnless(contract.COMPILER.exists(), '固定C compilerが必要')
    def test_actual_c_samples_transfer_then_run_in_same_supervisor(self):
        c = self.client()
        for name in ('counter', 'game'):
            m, b = contract.build(name, self.services.root / 'packages')
            c.install(contract.encode(m, b))
        c.close()
        for held in (16, 0, 1): self.lib.test_home_frame(self.store, held, 10)
        self.assertEqual(self.lib.test_home_value(self.store), 1)
