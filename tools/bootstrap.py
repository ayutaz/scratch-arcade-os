"""固定された公開依存だけを取得する。実機・Flashには接続しない。"""
import argparse
import hashlib
import os
from pathlib import Path,PurePosixPath
import platform
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 'wamr':dict(url='https://github.com/bytecodealliance/wasm-micro-runtime.git',tag='WAMR-2.4.5',commit='25bd7eb63e828e4bd242cc9b38d260b4b31c6605',path='downloads/os-research/wamr-upstream'),
 'littlefs':dict(url='https://github.com/littlefs-project/littlefs.git',tag='v2.11.3',commit='6cb4e86540eca0d9ba62500a298385c9d863c8be',path='.cache/os-littlefs-v2.11.3'),
 'idf':dict(url='https://github.com/espressif/esp-idf.git',tag='v6.1',commit='fff9895c82d744c7237be8847347bdd1b07c6643',path='.cache/os-idf-v6.1')}
ZIG=dict(url='https://ziglang.org/download/0.15.2/zig-aarch64-macos-0.15.2.tar.xz',sha256='3cc2bab367e185cdfb27501c4b30b1b0653c28d9f73df8dc91488e66ece5fa6b',bytes=50635984,path='.cache/os-sdk-toolchain/zig-aarch64-macos-0.15.2')
CONSTRAINTS=dict(url='https://dl.espressif.com/dl/esp-idf/espidf.constraints.v6.1.txt',sha256='192e8c82a7890164a4e8fe6fafe8423a47f6042c84b5f6a500a003640ae4d32b')
FONT=dict(url='https://raw.githubusercontent.com/google/fonts/29b4ec6df2522a8aee279414b78a07910b065874/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf',sha256='c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f')

def safe_members(members,prefix):
 result=[]
 for m in members:
  p=PurePosixPath(m.name)
  if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!=prefix or not (m.isfile() or m.isdir()):raise ValueError('unsafe archive member')
  result.append(m)
 return result

def checked_path(root,relative):
 root=Path(root).resolve();rel=Path(relative)
 if rel.is_absolute() or '..' in rel.parts:raise ValueError('dependency path')
 p=root/rel
 if not p.is_relative_to(root):raise ValueError('dependency path')
 for q in [p,*p.parents]:
  if q==root:break
  if q.is_symlink():raise ValueError('dependency symlink')
 return p

def ensure_source(spec,root=ROOT):
 p=checked_path(root,spec['path']);p.parent.mkdir(parents=True,exist_ok=True)
 def verify(path):
  actual=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
  if actual!=spec['commit']:raise ValueError('dependency commit mismatch')
  if subprocess.run(['git','-C',str(path),'status','--porcelain','--untracked-files=no'],capture_output=True,text=True,check=True).stdout.strip():raise ValueError('modified dependency')
 if p.exists():verify(p);return p
 with tempfile.TemporaryDirectory(dir=p.parent) as d:
  temp=Path(d)/'source'
  subprocess.run(['git','clone','--depth','1','--branch',spec['tag'],spec['url'],str(temp)],check=True)
  verify(temp);temp.rename(p)
 return p

def download(url,digest,maximum=64*1024*1024):
 with urlopen(url,timeout=60) as response:data=response.read(maximum+1)
 if len(data)>maximum or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('download checksum/size')
 return data

def ensure_zig(root=ROOT):
 if (platform.system(),platform.machine())!=('Darwin','arm64'):raise ValueError('host tools currently require macOS arm64')
 p=checked_path(root,ZIG['path']);exe=p/'zig'
 if p.exists():
  if subprocess.check_output([str(exe),'version'],text=True).strip()!='0.15.2':raise ValueError('compiler version')
  return p
 p.parent.mkdir(parents=True,exist_ok=True);data=download(ZIG['url'],ZIG['sha256'])
 if len(data)!=ZIG['bytes']:raise ValueError('compiler archive size')
 with tempfile.TemporaryDirectory(dir=p.parent) as d:
  archive=Path(d)/'zig.tar.xz';archive.write_bytes(data)
  with tarfile.open(archive,'r:xz') as f:f.extractall(d,members=safe_members(f.getmembers(),p.name),filter='data')
  (Path(d)/p.name).rename(p)
 return p

def ensure_constraints(root=ROOT):
 path=checked_path(root,'.cache/os-idf-tools/espidf.constraints.v6.1.txt')
 if path.exists():
  if hashlib.sha256(path.read_bytes()).hexdigest()!=CONSTRAINTS['sha256']:raise ValueError('IDF constraints checksum')
 else:
  path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(download(CONSTRAINTS['url'],CONSTRAINTS['sha256']))
 return path

def ensure_font(root=ROOT):
 folder=checked_path(root,'downloads/fonts');folder.mkdir(parents=True,exist_ok=True)
 path=checked_path(root,'downloads/fonts/NotoSansJP.ttf')
 if path.exists():
  if hashlib.sha256(path.read_bytes()).hexdigest()!=FONT['sha256']:raise ValueError('font checksum')
 else:path.write_bytes(download(FONT['url'],FONT['sha256']))
 pinned=checked_path(root,'downloads/fonts/NotoSansJP-pinned.ttf')
 if pinned.exists() and pinned.read_bytes()!=path.read_bytes():raise ValueError('pinned font differs')
 if not pinned.exists():shutil.copyfile(path,pinned)

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--idf',action='store_true');parser.add_argument('--font',action='store_true');args=parser.parse_args(argv)
 ensure_zig()
 for name in ('wamr','littlefs'):ensure_source(SOURCES[name])
 if args.font:ensure_font()
 if args.idf:
  ensure_constraints()
  path=ensure_source(SOURCES['idf']);subprocess.run(['git','-C',str(path),'submodule','update','--init','--recursive','--depth','1'],check=True)
  env={**os.environ,'IDF_TOOLS_PATH':str(ROOT/'.cache/os-idf-tools')}
  subprocess.run(['uv','run','--locked','python',str(path/'tools/idf_tools.py'),'--non-interactive','install','--targets','esp32s3','xtensa-esp-elf','esp32ulp-elf','cmake','ninja','esp-rom-elfs'],env=env,check=True)
 print('Pinned dependencies ready. No device accessed.')
 return 0
if __name__=='__main__':raise SystemExit(main())
