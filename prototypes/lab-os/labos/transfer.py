"""独自OS専用の有限転送。識別beaconを受信するまで送信しない。"""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
import stat
import struct
import time
import zlib

from .package import decode

MAGIC = b'LABXFR1\0'
SIGNATURE = b'LABOS_TRANSFER_1'
MAX_PAYLOAD = 516


@dataclass(frozen=True)
class Frame:
    op: int
    session: int
    request: int
    payload: bytes
    status: int = 0
    response: bool = False


def encode(frame):
    for value, maximum in ((frame.op, 255), (frame.status, 255),
                           (frame.session, 0xffffffff), (frame.request, 0xffffffff)):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError('frame field')
    if type(frame.response) is not bool or not isinstance(frame.payload, bytes) or len(frame.payload) > MAX_PAYLOAD:
        raise ValueError('frame payload/flags')
    header = MAGIC + struct.pack('<4B3I', frame.op, 128 if frame.response else 0,
                                 frame.status, 0, frame.session, frame.request, len(frame.payload))
    return header + struct.pack('<I', zlib.crc32(header + frame.payload)) + frame.payload


class Parser:
    def __init__(self): self.buffer = bytearray()

    def feed(self, data):
        frames = []
        for byte in data:
            self.buffer.append(byte)
            while len(self.buffer) >= 8 and self.buffer[:8] != MAGIC:
                del self.buffer[0]
            if len(self.buffer) < 28:
                continue
            op, flags, status, reserved, session, request, n = struct.unpack_from('<4B3I', self.buffer, 8)
            if flags not in (0, 128) or reserved or n > MAX_PAYLOAD:
                del self.buffer[0]
                continue
            if len(self.buffer) < 28 + n:
                continue
            packet = bytes(self.buffer[:28 + n])
            del self.buffer[:28 + n]
            if zlib.crc32(packet[:24] + packet[28:]) != struct.unpack_from('<I', packet, 24)[0]:
                continue  # 破損payload中のmagicを別命令として解釈しない。
            frames.append(Frame(op, session, request, packet[28:], status, flags == 128))
        return frames


class TransferError(RuntimeError):
    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


class Client:
    """stream.readは有限時間で返る。timeout時は同じrequestだけを再送する。"""
    def __init__(self, stream, *, clock=time.monotonic, timeout=1.0, attempts=3, session=None):
        if timeout <= 0 or type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError('transfer deadline')
        self.stream, self.clock, self.timeout, self.attempts = stream, clock, timeout, attempts
        self.session = (secrets.randbits(32) or 1) if session is None else session
        if type(self.session) is not int or not 1 <= self.session <= 0xffffffff:
            raise ValueError('session')
        self.parser = Parser()
        self.request = 1
        self.connected = self.failed = False
        self.max_package, self.chunk = 0, 0
        self.deadline = None
        self.boot_nonce = None

    def _within_budget(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            self.failed = True
            raise TransferError('転送全体の30秒期限を超えました。保存結果は再接続後に照合してください')

    def _receive(self, deadline, predicate):
        while self.clock() < deadline:
            for frame in self.parser.feed(self.stream.read(544)):
                if predicate(frame): return frame
        return None

    def connect(self):
        if self.connected or self.failed: raise TransferError('client state')
        def supported(frame):
            if (frame.op, frame.session, frame.request, frame.response, frame.status) != (1, 0, 0, True, 0): return False
            if len(frame.payload) != 32 or frame.payload[:16] != SIGNATURE: return False
            nonce, maximum, chunk, abi = struct.unpack_from('<4I', frame.payload, 16)
            return nonce != 0 and 264 <= maximum <= 65792 and 1 <= chunk <= 512 and abi == 2
        seen = set()
        self.deadline = self.clock() + self.timeout * self.attempts
        try:
            for _ in range(self.attempts):
                self._within_budget()
                beacon = self._receive(min(self.clock() + self.timeout, self.deadline),
                    lambda f: supported(f) and struct.unpack_from('<I', f.payload, 16)[0] not in seen)
                if beacon is None:
                    raise TransferError('対応するLab OSの新しいbeaconを受信できません')
                nonce, self.max_package, self.chunk, _ = struct.unpack_from('<4I', beacon.payload, 16)
                seen.add(nonce)
                self.connected = True
                try:
                    self._request(2, struct.pack('<I', nonce))
                    self.boot_nonce = nonce
                    return
                except TransferError as error:
                    self.connected = False
                    # Only an explicit BAD OPEN establishes rejection. A lost
                    # ACK, busy/session/sequence error never starts a new OPEN.
                    if error.status != 1 or self.failed: raise
                    self.request = 1
                except Exception:
                    self.connected = False
                    raise
            raise TransferError('新しいboot challengeでも接続が拒否されました')
        finally:
            self.deadline = None

    def _request(self, op, payload=b''):
        if not self.connected or self.failed or self.request > 0xffffffff:
            raise TransferError('closed/uncertain session')
        packet = encode(Frame(op, self.session, self.request, payload))
        for _ in range(self.attempts):
            self._within_budget()
            try:
                if self.stream.write(packet) != len(packet): raise TransferError('partial write')
                deadline = self.clock() + self.timeout
                if self.deadline is not None: deadline = min(deadline, self.deadline)
                frame = self._receive(deadline,
                                      lambda f: f.response and f.op == op and f.session == self.session and f.request == self.request)
            except Exception:
                self.failed = True
                raise
            if frame is None: continue
            self.request += 1
            if frame.status:
                if frame.status in (3, 6): self.failed = True
                raise TransferError(f'OS応答 status={frame.status}。変更が保存されたかは一覧で照合してください', status=frame.status)
            return frame.payload
        self.failed = True
        raise TransferError('ACKを確認できません。結果を推測して別requestで再実行しないでください')

    def install(self, package):
        self.deadline = self.clock() + 30
        try: return self._install(package)
        finally: self.deadline = None

    def _install(self, package):
        package = bytes(package)
        manifest, _ = decode(package)
        if len(package) > self.max_package: raise TransferError('転送profileの最大サイズを超えています')
        digest = hashlib.sha256(package).digest()
        if self._request(3, struct.pack('<I', len(package)) + digest) != bytes(4):
            self.failed = True
            raise TransferError('BEGIN offset')
        for offset in range(0, len(package), self.chunk):
            self._within_budget()
            chunk = package[offset:offset + self.chunk]
            ack = self._request(4, struct.pack('<I', offset) + chunk)
            if ack != struct.pack('<I', offset + len(chunk)):
                self.failed = True
                raise TransferError('DATA offset')
        self._within_budget()
        if len(self._request(5)) != 4:
            self.failed = True
            raise TransferError('COMMIT sequence')
        row = next((r for r in self.list_apps() if r['id'] == manifest['id']), None)
        if row is None or row['sha256'] != digest.hex() or row['version'] != manifest['version']:
            self.failed = True
            raise TransferError('installed package identity mismatch')
        return row

    def list_apps(self):
        rows, total = [], None
        for index in range(16):
            payload = self._request(7, struct.pack('<I', index))
            if len(payload) == 4 and index == 0 and payload == bytes(4): return []
            if len(payload) != 179: raise TransferError('catalog row length')
            count, ordinal = struct.unpack_from('<2I', payload)
            if not 1 <= count <= 16 or ordinal != index or (total is not None and total != count):
                raise TransferError('catalog changed or invalid')
            total = count
            row = {}
            for start, width, name in ((8, 33, 'id'), (41, 81, 'title'), (122, 25, 'version')):
                raw = payload[start:start+width]
                try:
                    end = raw.index(0)
                    if not end or any(raw[end:]): raise ValueError('padding')
                    row[name] = raw[:end].decode('utf-8')
                except (ValueError, UnicodeError) as error: raise TransferError('catalog string') from error
            if row['id'] in [r['id'] for r in rows]: raise TransferError('duplicate app')
            row['sha256'] = payload[147:].hex()
            rows.append(row)
            if len(rows) == total: return rows
        raise TransferError('catalog quota')

    def remove(self, name):
        self._request(8, name.encode('ascii'))

    def rollback(self, name):
        self._request(9, name.encode('ascii'))

    def _network_control(self, payload):
        reply = self._request(14, payload)
        try:
            if len(reply) != 8: raise ValueError('length')
            state, ipv4 = struct.unpack('<2I', reply)
            if state > 4 or (state == 2) != bool(ipv4): raise ValueError('state/ip')
        except (ValueError, TypeError, struct.error):
            self.failed = True
            raise TransferError('invalid network status') from None
        return dict(state=state, ipv4=ipv4)

    def network_start(self, ssid, password):
        """RAM-only Wi-Fi要求。Python/OS/serial内部の全コピー消去は保証しない。"""
        if type(ssid) is not str or type(password) is not str:
            raise ValueError('Wi-Fi設定の形式が不正です')
        try:
            ssid_bytes, password_bytes = ssid.encode('utf-8'), password.encode('ascii')
        except UnicodeError:
            raise ValueError('Wi-Fi設定の文字形式が不正です') from None
        if (not 1 <= len(ssid_bytes) <= 32 or not 8 <= len(password_bytes) <= 63 or
            any(c < 32 or c == 127 for c in ssid_bytes) or
            any(c < 32 or c > 126 for c in password_bytes)):
            raise ValueError('Wi-Fi設定の長さまたは文字形式が不正です')
        return self._network_control(struct.pack('<3I32s64s',1,len(ssid_bytes),len(password_bytes),
                                                 ssid_bytes,password_bytes))

    def network_status(self):
        return self._network_control(struct.pack('<I',2))

    def network_stop(self):
        return self._network_control(struct.pack('<I',3))

    def network_route(self, peer, peer_port, *, local_port=0):
        if (type(peer) is not str or type(peer_port) is not int or not 1<=peer_port<=65535 or
            type(local_port) is not int or (local_port!=0 and not 1024<=local_port<=65535)):
            raise ValueError('invalid UDP route')
        try:
            address=ipaddress.IPv4Address(peer).packed
        except ValueError:
            raise ValueError('invalid UDP route') from None
        if not 1<=address[0]<224:raise ValueError('invalid UDP route')
        return self._network_control(struct.pack('<I4s2I',4,address,local_port,peer_port))

    def network_channel_status(self):
        reply=self._request(14,struct.pack('<I',5))
        try:
            if len(reply)!=8:raise ValueError('length')
            state,port=struct.unpack('<2I',reply)
            if state>3 or port>65535 or (state==1)!=bool(port):raise ValueError('state/port')
        except (TypeError,ValueError,struct.error):
            self.failed=True
            raise TransferError('invalid network channel status') from None
        return dict(state=state,port=port)

    def _control(self,payload):
        reply=self._request(15,payload)
        try:
            if len(reply)!=80 or any(reply[77:]):raise ValueError('length/padding')
            values=struct.unpack_from('<11I',reply)
            schema,mode,notice,selected,count,held,ms,generation,applied,draws,crc=values
            if (schema!=1 or mode>3 or notice>6 or count>16 or selected>=(count or 1) or
                held>255 or ms>250 or (not ms and held) or (ms and not generation) or draws>128 or
                (not draws and crc) or (mode==1 and not count)):raise ValueError('fields')
            raw=reply[44:77];end=raw.index(0)
            if any(raw[end:]):raise ValueError('id padding')
            active=raw[:end].decode('ascii')
            if active and not re.fullmatch('[a-z][a-z0-9-]{0,31}',active):raise ValueError('id')
            if (mode==1 and not active) or (mode in (0,2) and active):raise ValueError('mode/id')
        except (ValueError,TypeError,struct.error):
            self.failed=True
            raise TransferError('invalid control snapshot') from None
        return dict(zip(('version','mode','notice','selected','count','held','remaining_ms',
                         'generation','applied','draw_count','draw_crc32','active_id'),(*values,active)))

    def control_status(self):return self._control(struct.pack('<I',1))

    def audio_status(self):
        reply=self._request(15,struct.pack('<I',3))
        try:
            if len(reply)!=80 or any(reply[48:]):raise ValueError('length/padding')
            values=struct.unpack_from('<11Ii',reply)
            schema,phase,claimed,owned,capacity,recorded,total,position,kind,replaying,peak,result=values
            if (schema!=1 or phase>4 or claimed>1 or owned>1 or capacity>32000 or recorded>capacity or
                total>capacity or position>total or kind>2 or replaying>1 or peak>32768 or
                not -1<=result<=1 or (not capacity and any(values[1:]))):raise ValueError('fields')
        except (ValueError,TypeError,struct.error):
            self.failed=True
            raise TransferError('invalid audio snapshot') from None
        return dict(zip(('version','phase','claimed','driver_owned','capacity','recorded','total',
                         'position','kind','replaying','peak','result'),values))

    def audio_metrics(self):
        """完了した現在の録音の集計だけを読む。PCM・録音履歴は取得しない。"""
        reply=self._request(15,struct.pack('<I',4))
        names=('version','available','frames','minimum','maximum','mean','rms','ac_rms',
               'centered_peak','saturated_frames','first_1320','first_1760','second_1320',
               'second_1760','requested_gain','effective_scale_q15','discarded_input_frames')
        try:
            if len(reply)!=80 or any(reply[68:]):raise ValueError('length/padding')
            values=struct.unpack_from('<3I3i11I',reply)
            v=dict(zip(names,values))
            if v['version']!=1 or v['available']>1:raise ValueError('schema/available')
            if not v['available']:
                if any(values[2:]):raise ValueError('stale metrics')
            elif (not 1<=v['frames']<=32000 or
                  not -32768<=v['minimum']<=v['mean']<=v['maximum']<=32767 or
                  not abs(v['mean'])<=v['rms']<=32768 or not v['ac_rms']<=v['rms'] or
                  v['centered_peak']!=max(v['maximum']-v['mean'],v['mean']-v['minimum']) or
                  v['saturated_frames']>v['frames'] or any(x>65535 for x in values[10:14]) or
                  v['requested_gain']>8 or v['effective_scale_q15']>262144 or
                  v['discarded_input_frames']>1600):raise ValueError('metrics bounds')
        except (ValueError,TypeError,struct.error):
            self.failed=True
            raise TransferError('invalid audio metrics') from None
        return v

    def input_pulse(self,held,*,duration_ms=100):
        if type(held) is not int or not 0<=held<=255 or type(duration_ms) is not int or not 20<=duration_ms<=250:
            raise ValueError('invalid input pulse')
        return self._control(struct.pack('<3I',2,held,duration_ms))

    def telemetry(self):
        """連番で同じ窓を読む。上書き時だけ最大3回、全体30秒以内で再取得。"""
        self.deadline = self.clock() + 30
        try:
            for _ in range(3):
                try:
                    self._within_budget()
                    header = self._request(13, bytes(8))
                    if len(header) != 12: raise ValueError('telemetry header size')
                    schema, count, newest = struct.unpack('<3I', header)
                    if schema != 1 or count > 32 or (count == 0 and newest != 0):
                        raise ValueError('telemetry header')
                    rows = []
                    for index in range(count):
                        self._within_budget()
                        sequence = (newest - count + 1 + index) & 0xffffffff
                        payload = self._request(13, struct.pack('<2I', 1, sequence))
                        rows.append(_telemetry_row(payload, sequence))
                    return dict(schema=schema, newest_sequence=newest, samples=rows)
                except TransferError as error:
                    if error.status == 9 and not self.failed: continue
                    raise
                except (ValueError, struct.error) as error:
                    self.failed = True
                    raise TransferError('invalid telemetry response') from error
            raise TransferError('計測記録が上書きされ、3回の再取得でも同じ窓を取得できませんでした')
        finally:
            self.deadline = None

    def collect(self):
        """専用app領域だけの段階回収。再送は同じrequestを再利用する。"""
        self.deadline = self.clock() + 30
        previous = (0, 0)
        try:
            for _ in range(4096):
                self._within_budget()
                payload = self._request(12)
                if len(payload) != 20: raise TransferError('collection progress size')
                removed, size, before, after, done = struct.unpack('<5I', payload)
                if done not in (0, 1) or removed < previous[0] or size < previous[1]:
                    raise TransferError('collection progress')
                previous = removed, size
                if done:
                    return dict(removed_files=removed, removed_bytes=size,
                                logical_before=before, logical_after=after)
            raise TransferError('collection command limit')
        except Exception:
            self.failed = True
            raise
        finally:
            self.deadline = None

    def close(self):
        if not self.connected or self.failed: return
        try: self._request(10)
        finally: self.connected = False


def _telemetry_row(payload, expected):
    if len(payload) != 72: raise ValueError('telemetry row size')
    words = struct.unpack('<18I', payload)
    sequence, time_ms, stage, flags = words[:4]
    total, used, peak, valid = words[14:]
    if sequence != expected or not 1 <= stage <= 6 or flags > 31 or valid not in (0, 1):
        raise ValueError('telemetry row fields')
    if valid:
        if not flags & 1 or not used <= peak <= total: raise ValueError('telemetry VM stats')
    elif any((total, used, peak)):
        raise ValueError('telemetry invalid VM padding')
    heaps = {}
    for i, name in enumerate(('internal_8bit', 'dma_8bit', 'spiram_8bit')):
        free, largest, minimum = words[4+3*i:7+3*i]
        if largest > free or minimum > free: raise ValueError('telemetry heap stats')
        heaps[name] = dict(free_bytes=free, largest_free_bytes=largest, minimum_free_bytes=minimum)
    return dict(sequence=sequence, time_ms=time_ms, stage=stage, flags=flags, heap=heaps,
                stack_free_bytes=words[13], vm=dict(valid=bool(valid), total=total, used=used, peak=peak))


@contextmanager
def serial_connection(port):
    import serial
    stream = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=.5, exclusive=True)
    try:
        stream.dtr = stream.rts = False
        stream.port = port
        stream.open()
        yield stream
    finally:
        stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='独自OSのbeacon確認後だけappを転送。純正REPL/Flash操作は行わない')
    parser.add_argument('--port', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    sub.add_parser('collect')
    sub.add_parser('telemetry')
    sub.add_parser('install').add_argument('package', type=Path)
    for action in ('remove', 'rollback'): sub.add_parser(action).add_argument('id')
    args = parser.parse_args(argv)
    package = None
    if args.action == 'install':
        info = args.package.stat()
        if not stat.S_ISREG(info.st_mode) or not 264 <= info.st_size <= 16384:
            raise TransferError('通常fileの264〜16,384 bytesのpackageだけを転送できます')
        with args.package.open('rb') as stream: package = stream.read(16385)
        if len(package) != info.st_size:
            raise TransferError('packageが読取り中に変化しました')
    if package is not None: decode(package)  # ポートを開く前に形式検査する。
    with serial_connection(args.port) as stream:
        client = Client(stream)
        try:
            client.connect()
            if package is not None: client.install(package)
            elif args.action == 'remove': client.remove(args.id)
            elif args.action == 'rollback': client.rollback(args.id)
            if args.action == 'collect': result = client.collect()
            elif args.action == 'telemetry': result = client.telemetry()
            else: result = client.list_apps()
            print(json.dumps(result, ensure_ascii=False))
        finally:
            client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
