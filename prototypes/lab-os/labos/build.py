"""ABI 2アプリをプロジェクト内の固定C compilerで生成する。"""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
from .sdk import Session,make_manifest
ROOT=Path(__file__).resolve().parents[3]
COMPILER=ROOT/'.cache/os-sdk-toolchain/zig-aarch64-macos-0.15.2/zig'
SDK=Path(__file__).resolve().parents[1]/'sdk'

def build(name,output):
    if name not in ('game','counter','speaker','microphone','network'):raise ValueError('app')
    version=subprocess.run([str(COMPILER),'version'],capture_output=True,text=True,check=True).stdout.strip()
    if version!='0.15.2':raise ValueError('compiler version')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        target=Path(tmp)/'app.wasm'
        exports=('sdk_abi','init','tick','shutdown','debug_value','debug_x','debug_y','debug_elapsed')
        cmd=[str(COMPILER),'cc','-target','wasm32-freestanding','-std=c99','-Oz','-fno-builtin','-nostdlib',
             '-Wl,--no-entry','-Wl,--strip-all','-Wl,--initial-memory=131072','-Wl,--max-memory=131072',
             '-Wl,-z,stack-size=16384',*[f'-Wl,--export={x}' for x in exports],str(SDK/(name+'.c')),'-o',str(target)]
        env={**os.environ,'ZIG_GLOBAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig'),'ZIG_LOCAL_CACHE_DIR':str(ROOT/'.cache/os-sdk-zig-local')}
        subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=60,env=env)
        blob=target.read_bytes()
        caps={'speaker':['draw','speaker'],'microphone':['draw','speaker','microphone'],'network':['draw','network']}.get(name,['draw'])
        title={'speaker':'Speaker','microphone':'Microphone','network':'Network'}.get(name)
        manifest=make_manifest(name,blob,title=title,capabilities=caps)
        s=Session(blob,manifest);s.frame(0,0);s.close()
        path=output/name;path.mkdir(exist_ok=True)
        (path/'app.wasm').write_bytes(blob);(path/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True)+'\n')
        return manifest,blob
