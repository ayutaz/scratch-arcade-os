"""S3と同じmapping adapterを使うホスト計測。実機へ接続しない。"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from .native import ROOT, SOURCE, WAMR_COMMIT
from .build import build

BUILD=ROOT/'build/lab-os-memory-profile'
PROJECT=ROOT/'prototypes/lab-os/native/memory-profile'


def build_profile():
    for folder in (ROOT/'build',BUILD):
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise ValueError('profile workspace must be a real directory')
    result=subprocess.run(['git','-C',str(SOURCE),'rev-parse','HEAD'],capture_output=True,text=True,check=True)
    if result.stdout.strip()!=WAMR_COMMIT:raise ValueError('WAMR source commit')
    result=subprocess.run(['git','-C',str(SOURCE),'diff','--quiet','HEAD'],capture_output=True,check=False)
    if result.returncode:raise ValueError('WAMR profile sources modified')
    BUILD.mkdir(parents=True,exist_ok=True)
    cmake=['uvx','--from','cmake==4.1.2','cmake']
    with tempfile.TemporaryFile(mode='w+') as log:
        for args in (['-S',str(PROJECT),'-B',str(BUILD)],['--build',str(BUILD),'-j','4']):
            result=subprocess.run(cmake+args,stdout=log,stderr=log,timeout=180)
            if result.returncode:
                log.seek(0);raise RuntimeError(log.read()[-14000:])
    return BUILD/'labos-memory-probe'


def run_profile(runner,blobs,*,cycles=30,pool_bytes=196608,capabilities=1):
    if type(cycles) is not int or not 1<=cycles<=200 or type(pool_bytes) is not int or not 65536<=pool_bytes<=196608:
        raise ValueError('profile work limits')
    if type(capabilities) is not int or not 0<=capabilities<=31:raise ValueError('profile capability mask')
    if not isinstance(blobs,(list,tuple)) or not 1<=len(blobs)<=16 or any(not isinstance(b,bytes) or not 8<=len(b)<=65536 for b in blobs):
        raise ValueError('profile app limits')
    with tempfile.TemporaryDirectory() as tmp:
        paths=[]
        for i,blob in enumerate(blobs):
            p=Path(tmp)/f'{i}.wasm';p.write_bytes(blob);paths.append(str(p))
        result=subprocess.run([str(runner),*([] if capabilities==1 else ['--caps='+str(capabilities)]),str(cycles),str(pool_bytes),*paths],capture_output=True,text=True,check=True,timeout=30)
    rows=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    if len(rows)!=1 or rows[0].get('format')!='lab-os-memory-profile-v1' or rows[0].get('device_tested') is not False:
        raise ValueError('profile output')
    row=rows[0]
    fields=('pool_capacity','pool_total','baseline_used','after_used','peak_used','opened','closed','rejected',
            'traps','normal_exits','leak_cycles','linear_in_pool','input_buffer_peak')
    if type(row.get('capabilities')) is not int or row['capabilities']!=capabilities:raise ValueError('profile capability mismatch')
    if row.get('software_bounds') is not True or any(type(row.get(k)) is not int or row[k]<0 for k in fields):
        raise ValueError('profile values')
    attempts=cycles*len(blobs)
    if (row['pool_capacity']!=pool_bytes or not 0<row['pool_total']<=pool_bytes or
        max(row['baseline_used'],row['after_used'])>row['peak_used'] or row['peak_used']>row['pool_total'] or
        row['opened']+row['rejected']!=attempts or row['closed']!=row['opened'] or
        row['traps']+row['normal_exits']>row['opened'] or row['leak_cycles']>attempts or
        row['linear_in_pool']>row['opened'] or row['input_buffer_peak']!=max(map(len,blobs))):
        raise ValueError('inconsistent profile measurements')
    return row


def main(argv=None):
    parser=argparse.ArgumentParser(description='host-only fixed-pool profile; never opens a device')
    parser.add_argument('--cycles',type=int,default=30)
    parser.add_argument('--pool-bytes',type=int,default=196608)
    args=parser.parse_args(argv)
    if not 1<=args.cycles<=200 or not 65536<=args.pool_bytes<=196608:parser.error('profile limits')
    runner=build_profile()
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        blobs=[build(name,tmp)[1] for name in ('counter','game')]
        report=run_profile(runner,blobs,cycles=args.cycles,pool_bytes=args.pool_bytes)
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
