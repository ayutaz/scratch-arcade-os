"""公開対象の追跡ファイルだけを検査する。Git履歴の書換えやネット送信なし。"""
from pathlib import Path
import re
import subprocess
ROOT=Path(__file__).resolve().parents[1]
TOKEN=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
FORBIDDEN={'backups','secrets','reports','logs','downloads','build','dist','__pycache__','.cache','.venv','.git'}
def check_paths(root,paths):
 root=Path(root).resolve();count=0
 for name in paths:
  rel=Path(name)
  if rel.is_absolute() or '..' in rel.parts or any(x in FORBIDDEN for x in rel.parts) or rel.name=='frozen.py' or rel.suffix in {'.bin','.elf','.map','.mpy','.wav','.pcm','.mp3','.key','.pem'}:raise ValueError('private/generated path: '+name)
  p=root/rel
  if p.is_symlink() or not p.is_file():raise ValueError('non-regular publication file: '+name)
  raw=p.read_bytes()
  if p.suffix!='.png':
   raw.decode('utf-8')
   if TOKEN.search(raw):raise ValueError('credential-like content: '+name)
   if re.search(rb'/Users/[A-Za-z0-9_.-]+/',raw):raise ValueError('private local path: '+name)
  count+=1
 return count

def main():
 paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');paths=[p for p in paths if p]
 if not paths:raise ValueError('stage the source distribution before checking')
 count=check_paths(ROOT,paths);print('Public source boundary check:',count,'files');return 0
if __name__=='__main__':raise SystemExit(main())
