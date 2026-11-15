"""専用UDP peer向けtimer protocol。経路はOSが管理、アプリ認証は未実装。"""
import ipaddress
import socket
import struct
import time


def encode_request(sequence,operation,seconds=0):
    if (any(type(v) is not int for v in (sequence,operation,seconds)) or
        not 1<=sequence<=0xffffffff or operation not in (1,2,3,4) or
        (not 10<=seconds<=300 if operation==1 else seconds!=0)):
        raise ValueError('timer request bounds')
    return b'LRT1'+struct.pack('<III',sequence,operation,seconds)


def decode_reply(data):
    if not isinstance(data,(bytes,bytearray)) or len(data)!=24 or data[:4]!=b'LRA1':
        raise ValueError('timer reply framing')
    seq,phase,remaining,seconds,elapsed=struct.unpack('<5I',data[4:])
    if (not seq or phase>3 or not 10<=seconds<=300 or remaining>seconds*1000 or
        elapsed+remaining!=seconds*1000 or (phase==0 and elapsed!=0) or
        (phase==3 and remaining!=0) or (phase in (1,2) and not remaining)):
        raise ValueError('timer reply bounds')
    return dict(sequence=seq,phase=phase,remaining_ms=remaining,seconds=seconds,elapsed_ms=elapsed)


def exchange(peer,endpoint,sequence,operation,seconds=0,*,timeout=.3,keepalive=lambda:None,clock=time.monotonic):
    packet=encode_request(sequence,operation,seconds)
    if (type(endpoint) is not tuple or len(endpoint)!=2 or type(endpoint[1]) is not int or
        not 1<=endpoint[1]<=65535 or type(timeout) not in (int,float) or not .05<=timeout<=2):
        raise ValueError('timer peer/timeout bounds')
    try:address=str(ipaddress.IPv4Address(endpoint[0]))
    except (ValueError,TypeError):raise ValueError('timer IPv4 peer') from None
    endpoint=(address,endpoint[1])
    # Same sequence/payload for every retry. A duplicate START must not reset
    # the timer. At most 3 sends and 96 reads, plus bounded native socket waits.
    for _ in range(3):
        keepalive();peer.sendto(packet,endpoint);deadline=clock()+timeout
        for _ in range(32):
            remaining=deadline-clock()
            if remaining<=0:break
            keepalive();peer.settimeout(min(.05,remaining))
            try:data,source=peer.recvfrom(65)
            except (socket.timeout,TimeoutError):continue
            if source!=endpoint:continue
            try:result=decode_reply(data)
            except ValueError:continue
            if result['sequence']==sequence:return result
    raise TimeoutError('timer peer did not acknowledge')
