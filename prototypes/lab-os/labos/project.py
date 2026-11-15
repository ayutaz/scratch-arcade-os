"""自作Cアプリの作成・build・有限試験・Mac実行。実機I/Oは持たない。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .build import COMPILER, ROOT, SDK
from .package import encode
from .sdk import CAPABILITY_BITS, Session, make_manifest

OWNER = 'labos-project-build-v1'
TEMPLATE = '''#include "lab_os.h"
#include "lab_digits.h"
static int32_t value;
uint32_t sdk_abi(void){return LAB_ABI;}
void init(void){value=0;}
void shutdown(uint32_t reason){(void)reason;}
int32_t debug_value(void){return value;}
int32_t debug_x(void){return 0;}
int32_t debug_y(void){return 0;}
int32_t debug_elapsed(void){return 0;}
int32_t tick(uint32_t held,uint32_t pressed,uint32_t released,uint32_t dt){
 (void)held;(void)released;(void)dt;
 if(pressed&BACK)return 1;
 if(pressed&START)value++;
 if(pressed&RESET)value=0;
 rect(0,0,320,240,0);lab_number(value,20,40);return 0;
}
'''


def real_path(path):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise ValueError('project paths must not contain symlinks')
    return path


def configuration(config):
    if not isinstance(config, dict) or set(config) != {'id','title','version','capabilities'}:
        raise ValueError('project schema')
    if not isinstance(config['id'],str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}',config['id']):
        raise ValueError('app id')
    if not isinstance(config['title'],str) or not 1 <= len(config['title']) <= 20 or any(ord(c)<32 or ord(c)==127 for c in config['title']):
        raise ValueError('title')
    if not isinstance(config['version'],str) or not re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}',config['version']):
        raise ValueError('version')
    caps=config['capabilities']
    if type(caps) is not list or caps != [name for _,name in CAPABILITY_BITS if name in caps]:
        raise ValueError('capabilities')
    return config


def create(folder, app_id, *, title=None):
    config=configuration(dict(id=app_id,title=title or app_id,version='1.0.0',capabilities=['draw']))
    folder=real_path(folder)
    if folder.exists():
        raise ValueError('project already exists')
    folder.mkdir(parents=True)
    (folder/'app.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    (folder/'app.c').write_text(TEMPLATE)
    (folder/'.gitignore').write_text('build/\n')
    return config


def build_project(folder):
    folder=real_path(folder)
    for name in ('app.json','app.c'):
        path=real_path(folder/name)
        if not path.is_file() or path.stat().st_size>262144:
            raise ValueError('bounded project file required')
    config=configuration(json.loads((folder/'app.json').read_text()))
    out=real_path(folder/'build'); marker=out/'.lab-build-owner'
    if out.exists():
        if any(p.is_symlink() for p in out.rglob('*')) or not marker.is_file() or marker.read_text()!=OWNER:
            raise ValueError('build output is not owned')
    else:
        out.mkdir();marker.write_text(OWNER)
    version=subprocess.run([str(COMPILER),'version'],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if version!='0.15.2':raise ValueError('compiler version')
    exports=('sdk_abi','init','tick','shutdown','debug_value','debug_x','debug_y','debug_elapsed')
    env={**os.environ,'ZIG_GLOBAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig'),
         'ZIG_LOCAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig-local')}
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        target=Path(tmp)/'app.wasm'
        cmd=[str(COMPILER),'cc','-target','wasm32-freestanding','-std=c99','-Oz','-fno-builtin','-nostdlib',
             '-I'+str(SDK),'-Wl,--no-entry','-Wl,--strip-all','-Wl,--initial-memory=131072',
             '-Wl,--max-memory=131072','-Wl,-z,stack-size=16384',
             *[f'-Wl,--export={x}' for x in exports],str(folder/'app.c'),'-o',str(target)]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=60,env=env)
        if proc.returncode:raise RuntimeError(proc.stderr[-8000:])
        wasm=target.read_bytes()
        manifest=make_manifest(config['id'],wasm,config['version'],config['title'],capabilities=config['capabilities'])
        package=encode(manifest,wasm)
        if len(package)>16384:raise ValueError('device package limit: 16384 bytes')
        session=Session(wasm,manifest)
        try:session.frame(0,0)
        finally:session.close()
        # Last good outputs survive compile/validation errors. Each file is replaced atomically.
        data={'app.wasm':wasm,'app.labapp':package,
              'manifest.json':(json.dumps(manifest,ensure_ascii=False,sort_keys=True)+'\n').encode()}
        for name,blob in data.items():
            temp=Path(tmp)/name;temp.write_bytes(blob);os.replace(temp,out/name)
    return {'id':config['id'],'package':str(out/'app.labapp'),'wasm_bytes':len(wasm),
            'package_bytes':len(package),'package_sha256':hashlib.sha256(package).hexdigest(),
            'device_tested':False}


def check_project(folder):
    result=build_project(folder);out=real_path(folder)/'build'
    manifest=json.loads((out/'manifest.json').read_text())
    session=Session((out/'app.wasm').read_bytes(),manifest)
    try:
        for now,held in ((0,0),(16,16),(32,0),(48,1),(64,0)):
            if session.frame(held,now):raise ValueError('app exited before BACK')
        if not session.frame(64,80):raise ValueError('BACK must exit the sample')
    finally:session.close()
    return {**result,'normal_exit':True,'resources_closed':session.closed}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('new','build','check','run'):
        child=sub.add_parser(name);child.add_argument('folder',type=Path)
        if name=='new':
            child.add_argument('--id',required=True);child.add_argument('--title')
    args=parser.parse_args(argv)
    if args.command=='new':result=create(args.folder,args.id,title=args.title)
    elif args.command=='check':result=check_project(args.folder)
    else:
        result=build_project(args.folder)
        if args.command=='run':
            from .cli import run_window
            from .home import Home
            from .repository import Repository
            out=real_path(args.folder)/'build';home=Home(Repository(out/'host-apps'))
            try:
                home.install(json.loads((out/'manifest.json').read_text()),(out/'app.wasm').read_bytes())
                run_window(home)
            finally:home.close()
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
