"""4本のC appを再build/両VM比較/PNG化。接続・実機転送・公開を含めない。"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from .display import render
from .native import build_probe,run_probe
from .package import decode
from .project import build_project,real_path
from .sdk import CAPABILITY_BITS,Session

ROOT=Path(__file__).resolve().parents[3]
FRAMES={
 'lane-catcher':[(0,0),(16,0),(0,1000),(1,1000),(0,3000),(32,0),(0,1),(64,0)],
 'focus-timer':[(0,0),(8,0),(0,0),(16,0),(0,1000),(16,0),(0,1000),(16,0),(0,60000),(32,0),(0,1),(64,0)],
 'voice-recorder':[(0,0),(16,0),(0,1000),(32,0),(0,1000),(4,0),(0,1),(64,0)],
 'remote-timer':[(0,0),(16,0),(0,1000),(16,0),(0,1000),(16,0),(0,60000),(32,0),(0,1),(64,0)]}


def verify(manifest,blob,frames,runner):
    caps=sum(bit for bit,name in CAPABILITY_BITS if name in manifest['capabilities'])
    rows=run_probe(runner,[blob],frames,capabilities=caps)
    if len(rows)!=len(frames):raise ValueError('native frame count mismatch')
    s=Session(blob,manifest);now=0;cover=None
    try:
        for index,(row,(held,dt)) in enumerate(zip(rows,frames,strict=True)):
            now+=dt;done=s.frame(held,now)
            if row['status']!=('exit' if done else 'running'):raise ValueError('VM exit mismatch')
            if not done:
                if row['rects']!=[list(x) for x in s.commands]:raise ValueError('VM drawing mismatch')
                for field,export in (('value','debug_value'),('x','debug_x'),('y','debug_y'),('elapsed','debug_elapsed')):
                    if row[field]!=s.debug(export):raise ValueError('VM state mismatch')
                if index==0:cover=list(s.commands)
            elif index!=len(frames)-1:raise ValueError('premature exit')
        if not s.closed or cover is None:raise ValueError('normal exit/cover required')
        return cover
    finally:s.close()


def run(output):
    output=real_path(output)
    if output.exists():raise ValueError('fresh output directory required')
    checked={};screens={};runner=build_probe()
    for name,frames in FRAMES.items():
        first=build_project(ROOT/'apps'/name);a=Path(first['package']).read_bytes()
        second=build_project(ROOT/'apps'/name);b=Path(second['package']).read_bytes()
        if a!=b:raise ValueError('nondeterministic app package')
        m,blob=decode(a);screens[name]=verify(m,blob,frames,runner)
        checked[name]=dict(version=m['version'],capabilities=m['capabilities'],package_bytes=len(a),
            package_sha256=hashlib.sha256(a).hexdigest(),frames=len(frames),both_vms_match=True,
            normal_exit=True,deterministic_build=True,screen=name+'.png',device_tested=False)
    # Only publish a ready report after all builds/VM checks succeed. A fresh
    # directory preserves older evidence; no prior files are overwritten.
    output.mkdir(parents=True,exist_ok=False)
    for name,commands in screens.items():render(SimpleNamespace(mode='running',commands=commands)).save(output/(name+'.png'))
    result=dict(apps=checked,device_tested=False,deployed=False,published=False,
        service_backends='absent: tests fallback behavior; physical I/O covered separately')
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    print(json.dumps(run(args.output),ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
