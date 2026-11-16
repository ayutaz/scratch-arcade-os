"""ABI 2の入力・実時間・描画・生存期間。"""
import hashlib
import re
import wasmtime

ABI=2
MAX_DT=60000
CAPABILITY_BITS=((1,'draw'),(2,'speaker'),(4,'microphone'),(8,'network'),(16,'storage'))


def portable_code_policy(blob):
    """WAMRのmeter設定前に走るstart/constructorを、共通packageから除く。"""
    if blob[:8] != b'\x00asm\x01\x00\x00\x00':
        raise ValueError('WASM bytecode required')
    pos = 8

    def leb(end):
        nonlocal pos
        value = 0
        for shift in range(0, 35, 7):
            if pos >= end:
                raise ValueError('truncated LEB')
            byte = blob[pos]
            pos += 1
            if shift == 28 and byte & 0xf0:
                raise ValueError('oversized LEB')
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError('invalid LEB')

    names = {b'sdk_abi', b'init', b'tick', b'shutdown', b'memory',
             b'debug_value', b'debug_x', b'debug_y', b'debug_elapsed'}
    while pos < len(blob):
        kind = blob[pos]
        pos += 1
        size = leb(len(blob))
        end = pos + size
        if end > len(blob) or kind == 8:
            raise ValueError('start/invalid section')
        if kind == 7:
            count = leb(end)
            if count > 128:
                raise ValueError('export quota')
            for _ in range(count):
                length = leb(end)
                if pos + length >= end or bytes(blob[pos:pos + length]) not in names:
                    raise ValueError('unsupported export')
                pos += length + 1  # export kindはVMの検証に委ねる。
                leb(end)
            if pos != end:
                raise ValueError('export section length')
        pos = end

class FrameInput:
    def __init__(self,initial=0):
        self.previous=0;self.sample(initial)
    def sample(self,held):
        if type(held) is not int or not 0<=held<=255:raise ValueError('input mask')
        result=(held,held&~self.previous,self.previous&~held)
        self.previous=held
        return result

class Clock:
    def __init__(self,now=0):
        if type(now) is not int or now<0:raise ValueError('clock')
        self.previous=now
    def step(self,now):
        if type(now) is not int or not self.previous<=now<=self.previous+MAX_DT:raise ValueError('non-monotonic/oversized time step')
        dt=now-self.previous;self.previous=now;return dt


def make_manifest(name,blob,version='1.0.0',title=None,*,capabilities=None):
    m={'id':name,'version':version,'abi':ABI,'runtime':'wasm','sha256':hashlib.sha256(blob).hexdigest(),
       'title':title or {'game':'ゲーム','counter':'カウンター'}.get(name,name),
       'capabilities':['draw'] if capabilities is None else capabilities,'memory_pages':2,'fuel':50000}
    validate(m,blob);return m


def validate(m,blob):
    keys={'id','version','abi','runtime','sha256','title','capabilities','memory_pages','fuel'}
    if not isinstance(m,dict) or set(m)!=keys:raise ValueError('manifest schema')
    if not isinstance(m['id'],str) or not re.fullmatch('[a-z][a-z0-9-]{0,31}',m['id']):raise ValueError('app id')
    if not isinstance(m['version'],str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}',m['version']):raise ValueError('version')
    if type(m['abi']) is not int or m['abi']!=ABI or m['runtime']!='wasm':raise ValueError('ABI/runtime')
    if not isinstance(blob,(bytes,bytearray)) or len(blob)>262144 or m['sha256']!=hashlib.sha256(blob).hexdigest():raise ValueError('binary/hash')
    portable_code_policy(blob)
    if not isinstance(m['title'],str) or not 1<=len(m['title'])<=20 or any(ord(c)<32 for c in m['title']):raise ValueError('title')
    caps=m['capabilities']
    if (type(caps) is not list or any(type(c) is not str for c in caps) or
        caps!=[c for _,c in CAPABILITY_BITS if c in caps]):raise ValueError('capabilities')
    for key,lo,hi in [('memory_pages',1,16),('fuel',100,1000000)]:
        if type(m[key]) is not int or not lo<=m[key]<=hi:raise ValueError(key)


def signature(fn,store,params,results):
    if not isinstance(fn,wasmtime.Func):raise RuntimeError('function required')
    t=fn.type(store)
    if [str(x) for x in t.params]!=params or [str(x) for x in t.results]!=results:raise RuntimeError('ABI signature')

class Session:
    def __init__(self,blob,manifest,initial_held=0,now_ms=0,*,audio=None,network=None,state=None):
        validate(manifest,blob)
        if audio is not None and not callable(getattr(audio,'call',None)):raise ValueError('audio backend')
        if network is not None and not callable(getattr(network,'call',None)):raise ValueError('network backend')
        if state is not None and not callable(getattr(state,'call',None)):raise ValueError('storage backend')
        self.state=state;self.state_allowed='storage' in manifest['capabilities']
        self.state_queries=self.state_mutations=0;self.state_result=-1 if state is None else 0
        # Borrowed OS lease, just like the native VM; close VM before its owner
        # retries/relinquishes hardware. Session does not conceal cleanup failure.
        self.audio=audio;self.audio_caps=(2 if 'speaker' in manifest['capabilities'] else 0)|(4 if 'microphone' in manifest['capabilities'] else 0)
        self.audio_mutations=self.audio_queries=0
        self.network=network;self.network_allowed='network' in manifest['capabilities']
        self.network_mutations=self.network_queries=0
        self.closed=False;self.commands=[];self.shutdown_reason=None
        self.input=FrameInput(initial_held);self.clock=Clock(now_ms)
        config=wasmtime.Config();config.consume_fuel=True
        self.engine=wasmtime.Engine(config);self.store=wasmtime.Store(self.engine)
        self.store.set_limits(memory_size=manifest['memory_pages']*65536,memories=1,instances=1,tables=1,table_elements=256)
        self.fuel=manifest['fuel'];self.allowed='draw' in manifest['capabilities']
        self.store.set_fuel(self.fuel)
        linker=wasmtime.Linker(self.engine)
        linker.define_func('os','rect',wasmtime.FuncType([wasmtime.ValType.i32()]*5,[]),self._rect)
        i32=wasmtime.ValType.i32()
        for name,op,n in [('audio_tone',1,2),('audio_record',2,1),('audio_play',3,0),
                          ('audio_state',4,0),('audio_level',5,0),('audio_stop',6,0),('audio_position',7,0),
                          ('audio_set_gain',8,1),('audio_classify',9,0),('audio_reply',10,1)]:
            linker.define_func('os',name,wasmtime.FuncType([i32]*n,[i32]),
                               lambda *args,op=op:self._audio(op,*(list(args)+[0]*(2-len(args)))))
        for name,op,n in [('network_send',1,2),('network_receive',2,2),('network_state',3,0)]:
            linker.define_func('os',name,wasmtime.FuncType([i32]*n,[i32]),
                lambda caller,*args,op=op:self._network(caller,op,*(list(args)+[0]*(2-len(args)))),access_caller=True)
        for name,op,n in [('state_read',1,2),('state_write',2,2),('state_status',0,0)]:
            linker.define_func('os',name,wasmtime.FuncType([i32]*n,[i32]),
                lambda *args,op=op:self._state(op,*(list(args)+[0]*(2-len(args)))))
        try:
            self.instance=linker.instantiate(self.store,wasmtime.Module(self.engine,blob))
            exports=self.instance.exports(self.store)
            signature(exports['sdk_abi'],self.store,[],['i32'])
            if exports['sdk_abi'](self.store)!=ABI:raise RuntimeError('guest ABI')
            signature(exports['init'],self.store,[],[])
            signature(exports['tick'],self.store,['i32']*4,['i32'])
            self.tick_fn=exports['tick'];exports['init'](self.store)
        except Exception as error:
            self.close(2);raise RuntimeError(str(error)) from error
    def _state(self,op,slot,value):
        if not self.state_allowed:raise wasmtime.Trap('storage permission')
        if op!=2:
            self.state_queries+=1
            if self.state_queries>8:raise wasmtime.Trap('storage per-frame quota')
        else:
            self.state_mutations+=1
            if self.state_mutations>1:raise wasmtime.Trap('storage per-frame quota')
        if not op:return self.state_result
        fallback=value;status=-1
        if 0<=slot<8 and self.state is not None:
            reply=self.state.call(op,slot,value)
            if (type(reply) is not tuple or len(reply)!=2 or
                type(reply[0]) is not int or not -1<=reply[0]<=1 or
                type(reply[1]) is not int or not -2147483648<=reply[1]<=2147483647):
                raise wasmtime.Trap('storage service contract')
            status,value=reply
        self.state_result=status
        return (value if status==1 else fallback) if op==1 else status
    def _audio(self,op,a,b):
        required=2 if op in (1,3,8,10) else 4 if op in (2,5,9) else 6
        if not self.audio_caps&required:raise wasmtime.Trap('audio permission')
        if op in (4,5,7):
            self.audio_queries+=1
            if self.audio_queries>8:raise wasmtime.Trap('audio per-frame quota')
        else:
            self.audio_mutations+=1
            if self.audio_mutations>2:raise wasmtime.Trap('audio per-frame quota')
        if (op==1 and not (200<=a<=4000 and 20<=b<=1000)) or (op==2 and not 1<=a<=2000) or (op==8 and not 0<=a<=8) or (op==10 and not 0<=a<=4):return -1
        if self.audio is None:return -1
        value=self.audio.call(op,a,b)
        maximum=6 if op==9 else 4 if op==4 else 32768 if op==5 else 32000 if op==7 else 1
        if type(value) is not int or not -1<=value<=maximum:raise wasmtime.Trap('audio service contract')
        return value
    def _network(self,caller,op,address,length):
        if not self.network_allowed:raise wasmtime.Trap('network permission')
        query=op==3
        if query:
            self.network_queries+=1
            if self.network_queries>8:raise wasmtime.Trap('network per-frame quota')
        else:
            self.network_mutations+=1
            if self.network_mutations>2:raise wasmtime.Trap('network per-frame quota')
            if not 1<=length<=64:return -1
            address &= 0xffffffff
            memory=caller.get('memory')
            if not isinstance(memory,wasmtime.Memory) or address+length>memory.data_len(caller):
                raise wasmtime.Trap('network memory bounds/export')
        if self.network is None:return -1
        data=None if query else bytearray(length)
        if op==1:data[:]=memory.read(caller,address,address+length)
        try:
            value=self.network.call(op,data,0 if query else length)
            maximum=3 if query else 1 if op==1 else length
            if (type(value) is not int or not -1<=value<=maximum or
                (data is not None and len(data)!=length)):raise wasmtime.Trap('network service contract')
            if op==2 and value>0:memory.write(caller,data[:value],address)
            return value
        finally:
            if data is not None:data[:]=bytes(len(data))
    def _rect(self,x,y,w,h,c):
        if not self.allowed or len(self.commands)>=128:raise wasmtime.Trap('draw permission/quota')
        if not (0<=x<320 and 0<=y<240 and 1<=w<=320-x and 1<=h<=240-y and 0<=c<=65535):raise wasmtime.Trap('draw bounds')
        self.commands.append((x,y,w,h,c))
    def frame(self,held,now_ms):
        if self.closed:raise RuntimeError('closed session')
        self.commands=[]
        self.audio_mutations=self.audio_queries=0
        self.network_mutations=self.network_queries=0
        self.state_mutations=self.state_queries=0
        try:
            dt=self.clock.step(now_ms);h,p,r=self.input.sample(held)
            self.store.set_fuel(self.fuel)
            result=self.tick_fn(self.store,h,p,r,dt)
            if result not in (0,1):raise RuntimeError('invalid tick result')
            if result:self.close(0)
            return bool(result)
        except Exception as error:
            self.close(2);raise RuntimeError(str(error)) from error
    def debug(self,name):
        if self.closed:raise RuntimeError('closed session')
        fn=self.instance.exports(self.store)[name];signature(fn,self.store,[],['i32'])
        self.store.set_fuel(self.fuel);return fn(self.store)
    def close(self,reason=1):
        if self.closed:return
        self.closed=True;self.shutdown_reason=reason
        try:
            if reason!=2 and hasattr(self,'instance'):
                fn=self.instance.exports(self.store).get('shutdown')
                if fn:
                    signature(fn,self.store,['i32'],[]);self.store.set_fuel(1000);fn(self.store,reason)
        except Exception:pass
        finally:
            self.commands=[];self.tick_fn=None;self.instance=None
            self.store.close()
            self.engine.close()
