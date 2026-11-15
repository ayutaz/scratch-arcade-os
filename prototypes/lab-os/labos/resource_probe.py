"""保存/転送/LittleFSのpayload確保を計測するhost-only probe。"""
from contextlib import contextmanager,nullcontext
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from .memory_probe import build_profile
from .native import ROOT,SOURCE
from .target import verify_littlefs,LITTLEFS
from .transfer import Client
from .package import encode

BUILD=ROOT/'build/lab-os-resource-probe'
NATIVE=ROOT/'prototypes/lab-os/native'
HASH=C.CFUNCTYPE(C.c_bool,C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p)
KEYS=('live_bytes','peak_bytes','attempts','failures','live_blocks','bad_frees')


@contextmanager
def native():
    for folder in (ROOT/'build',BUILD):
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):raise ValueError('probe workspace')
    verify_littlefs();runtime=build_profile().parent/'liblabos-memory-runtime.a'
    BUILD.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        folder=Path(tmp);profile=NATIVE/'resource-profile';objects=[]
        tracked=[NATIVE/name for name in ('app_store.c','app_lfs.c','app_home.c','app_transfer.c')]
        tracked += [LITTLEFS/'lfs.c',LITTLEFS/'lfs_util.c']
        sources=tracked+[profile/'heap_track.c',profile/'probe.c',NATIVE/'guest_vm.c']
        includes=['-I'+str(p) for p in (NATIVE,LITTLEFS,profile,SOURCE/'core/iwasm/include')]
        for i,source in enumerate(sources):
            out=folder/f'{i}.o';objects.append(str(out))
            flags=['-DLAB_HEAP_TRACK','-include',str(profile/'heap_track.h')] if source in tracked else []
            p=subprocess.run(['/usr/bin/clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fPIC',
                              '-DLFS_NO_DEBUG','-DLFS_NO_WARN','-DLFS_NO_ERROR',*includes,*flags,
                              '-c',str(source),'-o',str(out)],capture_output=True,text=True,timeout=30)
            if p.returncode:raise RuntimeError(p.stderr)
        output=folder/'resource.dylib'
        p=subprocess.run(['/usr/bin/clang','-shared',*objects,str(runtime),'-lpthread','-lm','-o',str(output)],
                         capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        api=C.CDLL(str(output))
        signatures={
            'lab_resource_new':([C.c_void_p,C.c_uint32,HASH,C.c_uint32],C.c_void_p),
            'lab_resource_free':([C.c_void_p],None),
            'lab_resource_feed':([C.c_void_p,C.c_void_p,C.c_uint32,C.c_uint32],C.c_int),
            'lab_resource_poll':([C.c_void_p,C.c_uint32],C.c_int),
            'lab_resource_read':([C.c_void_p,C.c_void_p,C.c_uint32],C.c_uint32),
            'lab_resource_dump':([C.c_void_p,C.c_void_p,C.c_uint32],C.c_int),
            'lab_resource_info':([C.c_void_p,C.c_uint32,C.c_void_p],C.c_int),
            'lab_resource_package':([C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32],C.c_int),
            'lab_resource_count':([C.c_void_p],C.c_uint32),
            'lab_resource_counter':([C.c_void_p],C.c_int),
            'lab_heap_window':([C.c_size_t,C.c_uint64],None),
            'lab_heap_metric':([C.c_uint],C.c_uint64)}
        for name,(args,result) in signatures.items():
            fn=getattr(api,name);fn.argtypes,fn.restype=args,result
        yield api


def metrics(api):return {key:api.lab_heap_metric(i) for i,key in enumerate(KEYS)}


def _budget(limit,fail_at=0):
    if type(limit) is not int or not 0<=limit<=262144 or type(fail_at) is not int or not 0<=fail_at<=1000000:
        raise ValueError('heap budget/failure point')


class Probe:
    def __init__(self,api,image,*,limit=262144):
        _budget(limit)
        if not isinstance(image,bytes) or not 65536<=len(image)<=8388608 or len(image)%4096:raise ValueError('RAM image')
        def digest(context,p,n,out):
            del context
            if n>65792 or not out or (n and not p):return False
            C.memmove(out,hashlib.sha256(C.string_at(p,n)).digest(),32);return True
        self.api=api;self.hash=HASH(digest);self.size=len(image);self.now=0.0
        self.handle=api.lab_resource_new(image,len(image),self.hash,limit)
        if not self.handle:raise ValueError('probe mount/runtime/allocation failed')
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def _live(self):
        if not self.handle:raise ValueError('probe is closed')
    def close(self):
        if self.handle:self.api.lab_resource_free(self.handle);self.handle=None
    def window(self,*,limit=262144,fail_at=0):
        self._live()
        _budget(limit,fail_at);self.api.lab_heap_window(limit,fail_at)
    def metrics(self):self._live();return metrics(self.api)
    def client(self):
        self._live()
        client=Client(self,clock=lambda:self.now,timeout=1.2,session=999);client.connect();return client
    def read(self,n):
        self._live()
        self.now+=.01;self.api.lab_resource_poll(self.handle,int(self.now*1000))
        out=C.create_string_buffer(n);size=self.api.lab_resource_read(self.handle,out,n);return out.raw[:size]
    def write(self,data):
        self._live()
        for i in range(0,len(data),128):
            piece=data[i:i+128]
            if not self.api.lab_resource_feed(self.handle,piece,len(piece),int(self.now*1000)):return 0
        return len(data)
    def snapshot(self):
        self._live()
        out=C.create_string_buffer(self.size)
        if not self.api.lab_resource_dump(self.handle,out,self.size):raise ValueError('RAM image read')
        return out.raw
    def versions(self):
        self._live()
        result={}
        for i in range(self.api.lab_resource_count(self.handle)):
            out=C.create_string_buffer(160)
            if not self.api.lab_resource_info(self.handle,i,out):raise ValueError('catalog read')
            key,version=out.value.decode().split('|');result[key]=version
        return result
    def package(self,name):
        for at,key in enumerate(self.versions()):
            if key==name:
                out=C.create_string_buffer(16384);n=self.api.lab_resource_package(self.handle,at,out,len(out))
                if n<0:raise ValueError('package read')
                return out.raw[:n]
        raise ValueError('unknown app')
    def run_counter(self):self._live();return self.api.lab_resource_counter(self.handle)


def padded_package(manifest,blob,*,version,size):
    if type(size) is not int or not 264<=size<=16384 or not isinstance(blob,bytes):raise ValueError('padded size')
    goal=size-256
    def uleb(n):
        out=bytearray()
        while True:
            b=n&127;n>>=7;out.append(b|(128 if n else 0))
            if not n:return bytes(out)
    gap=goal-len(blob)
    for padding in range(max(0,gap-6),gap):
        section=b'\0'+uleb(1+padding)+bytes(1+padding)
        if len(blob)+len(section)==goal:
            data=blob+section
            return encode(dict(manifest,version=version,sha256=hashlib.sha256(data).hexdigest()),data)
    raise ValueError('no room for canonical custom section')


def _released(api):
    row=metrics(api)
    if any(row[key] for key in ('live_bytes','live_blocks','bad_frees')):raise RuntimeError('tracked heap ownership did not return to baseline')
    return row


def _recover(api,image,game,allowed,rollback=None):
    with Probe(api,image) as p:
        if p.versions().get('counter') not in allowed or p.package('game')!=game:raise RuntimeError('catalog or unrelated app changed')
        if rollback:
            c=p.client();c.rollback('counter');c.close()
            if p.versions()['counter']!=rollback:raise RuntimeError('previous version unavailable')
        if p.run_counter()!=1:raise RuntimeError('counter did not run after reopen')
    _released(api)


def _campaign(api,image,operation,game,allowed,rollback=None):
    from .transfer import TransferError
    with Probe(api,image) as p:
        p.window();operation(p.client());count=p.metrics()['attempts']
    _released(api)
    if not 0<count<=512:raise RuntimeError('allocation campaign work limit')
    for at in range(1,count+1):
        with Probe(api,image) as p:
            p.window(fail_at=at)
            try:operation(p.client())
            except TransferError:pass
            saved=p.snapshot()
        _released(api);_recover(api,saved,game,allowed,rollback)
    return {'cases':count,'recoverable':count,'cleanup_live_bytes':0}


def run_report(*,api=None,cycles=5,allocation_failures=False):
    if type(cycles) is not int or not 1<=cycles<=20 or type(allocation_failures) is not bool:raise ValueError('report limits')
    from .build import build
    from .fs_image import create_image
    from .transfer import TransferError
    with native() if api is None else nullcontext(api) as api:
        with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
            counter,blob=build('counter',tmp);game_manifest,game_blob=build('game',tmp)
        game=encode(game_manifest,game_blob);seed,_=create_image([encode(counter,blob),game])
        maximum=padded_package(counter,blob,version='1.0.1',size=16384)
        with Probe(api,seed) as p:
            startup=p.metrics();p.window(limit=65536)
            for i in range(cycles):
                c=p.client();c.install(padded_package(counter,blob,version=f'1.0.{i+1}',size=16384));c.close()
                if p.run_counter()!=1:raise RuntimeError('counter failed after maximum update')
            transfer_stats=p.metrics()
        cleanup=_released(api);budgets={}
        for cap in (8192,16384,32768,65536):
            with Probe(api,seed) as p:
                p.window(limit=cap);c=p.client();success=True
                try:c.install(maximum)
                except TransferError:success=False
                row=p.metrics();saved=p.snapshot()
            _released(api);_recover(api,saved,game,('1.0.0','1.0.1'))
            budgets[str(cap)]={'succeeded':success,'stats':row,'recoverable':True}
        with Probe(api,seed) as p:
            c=p.client()
            for i in range(1,4):c.install(padded_package(counter,blob,version=f'1.0.{i}',size=16384))
            c.close();gc_seed=p.snapshot()
        _released(api)
        with Probe(api,gc_seed) as p:
            p.window();c=p.client();gc_result=c.collect();c.close();gc_stats=p.metrics();saved=p.snapshot()
        _released(api);_recover(api,saved,game,('1.0.3',),'1.0.2')
        campaigns={}
        if allocation_failures:
            campaigns['maximum_update']=_campaign(api,seed,lambda c:c.install(maximum),game,('1.0.0','1.0.1'))
            campaigns['collection']=_campaign(api,gc_seed,lambda c:c.collect(),game,('1.0.3',),'1.0.2')
        return {'format':'lab-os-system-heap-v1','device_tested':False,'physical_heap_measured':False,
                'cycles':cycles,'vm_pool_bytes':196608,'payload_accounting_only':True,
                'tracked_sources':['app_store.c','app_lfs.c','app_home.c','app_transfer.c','lfs.c','lfs_util.c'],
                'excluded':['allocator metadata/fragmentation','RAM NOR/harness/output buffers','Python/SHA callback',
                            'WAMR runtime pool/platform services','IDF drivers/tasks/native stack'],
                'scenarios':{'startup':startup,'maximum_update':transfer_stats,'collection':gc_stats},
                'collection':gc_result,'budgets':budgets,'failure_campaigns':campaigns,'cleanup':cleanup}


def main(argv=None):
    parser=argparse.ArgumentParser(description='host-only system heap probe; no device/port options')
    parser.add_argument('--cycles',type=int,default=5);parser.add_argument('--allocation-failures',action='store_true')
    args=parser.parse_args(argv)
    if not 1<=args.cycles<=20:parser.error('cycles must be 1..20')
    print(json.dumps(run_report(cycles=args.cycles,allocation_failures=args.allocation_failures),ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
