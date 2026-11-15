"""所有領域だけのimmutable package/参照切替。電源断耐性の保証ではない。"""
from pathlib import Path
import copy,hashlib,json,os,re,shutil,tempfile
from .sdk import validate,Session

def encoded(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def package_id(m,b):return hashlib.sha256(encoded(m)+bytes(b)).hexdigest()
def safe_read(path):
    if path.is_symlink() or not path.is_file():raise ValueError('not a regular package file')
    return path.read_bytes()

class Repository:
    def __init__(self,root,quota=4*1024*1024):
        self.root=Path(root);self.quota=quota;self.recovered=False
        if self.root.is_symlink():raise ValueError('symlink root')
        self.root.mkdir(parents=True,exist_ok=True);marker=self.root/'.labos-owner'
        if not marker.exists():
            if any(self.root.iterdir()):raise ValueError('unowned nonempty repository')
            marker.write_text('lab-os-repository-v1\n')
        if safe_read(marker)!=b'lab-os-repository-v1\n':raise ValueError('owner mismatch')
        (self.root/'packages').mkdir(exist_ok=True)
        if (self.root/'packages').is_symlink():raise ValueError('symlink packages')
        self.index={}
        if (self.root/'index.json').exists():
            try:self.index=self._read_index(self.root/'index.json')
            except (ValueError,OSError,KeyError,TypeError):
                self.index=self._read_index(self.root/'index.previous');self.recovered=True
    def _read_index(self,path):
        d=json.loads(safe_read(path))
        if not isinstance(d,dict) or set(d)!={'v','apps'} or type(d['v']) is not int or d['v']!=1 or not isinstance(d['apps'],dict):raise ValueError('index schema')
        for name,row in d['apps'].items():
            self._name(name)
            if not isinstance(row,dict) or set(row)!={'current','previous','quarantined'}:raise ValueError('index row')
            if not isinstance(row['quarantined'],list) or len(row['quarantined'])>8 or any(x is None for x in row['quarantined']):raise ValueError('quarantine schema')
            for digest in [row['current'],row['previous'],*row['quarantined']]:
                if digest is not None and (not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)):raise ValueError('package reference')
        return d['apps']
    def _name(self,name):
        if not isinstance(name,str) or not re.fullmatch('[a-z][a-z0-9-]{0,31}',name):raise ValueError('app name')
    def _dir(self,name,digest=None):
        self._name(name);path=self.root/'packages'/name
        if path.is_symlink():raise ValueError('symlink app directory')
        if digest:
            if not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('digest')
            path=path/digest
            if path.is_symlink():raise ValueError('symlink version directory')
        return path
    def _atomic(self,path,data):
        tmp=path.with_name(path.name+'.new')
        if tmp.is_symlink() or path.is_symlink():raise ValueError('symlink index')
        with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        tmp.replace(path)
        fd=os.open(self.root,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def _write_index(self,index):
        self._atomic(self.root/'index.previous',encoded({'v':1,'apps':self.index}))
        self._atomic(self.root/'index.json',encoded({'v':1,'apps':index}))
    def _commit(self,index):self._write_index(index);self.index=index
    def _load(self,name,digest):
        p=self._dir(name,digest);m=json.loads(safe_read(p/'manifest.json'));b=safe_read(p/'app.wasm')
        validate(m,b)
        if m['id']!=name or package_id(m,b)!=digest:raise ValueError('package identity')
        return m,b
    def current(self,name):
        self._name(name);digest=self.index.get(name,{}).get('current')
        return copy.deepcopy(self._load(name,digest)[0]) if digest else None
    def list_apps(self):return [self.current(n) for n in sorted(self.index) if self.index[n]['current']]
    def load(self,name):
        m=self.current(name)
        if not m:raise KeyError(name)
        return self._load(name,self.index[name]['current'])
    def install(self,m,b):
        validate(m,b);session=Session(b,m)
        try:session.frame(0,0)
        finally:session.close()
        name=m['id'];digest=package_id(m,b);target=self._dir(name,digest)
        used=sum(p.stat().st_size for p in (self.root/'packages').rglob('*') if p.is_file() and not p.is_symlink())
        additional=0 if target.exists() else len(b)+len(encoded(m))
        if used+additional>self.quota:raise ValueError('repository quota')
        parent=self._dir(name);parent.mkdir(exist_ok=True)
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix='.candidate-',dir=parent) as tmp:
                p=Path(tmp);(p/'app.wasm').write_bytes(b);(p/'manifest.json').write_bytes(encoded(m))
                for f in p.iterdir():
                    with f.open('rb') as stream:os.fsync(stream.fileno())
                p.rename(target)
        self._load(name,digest)
        index=copy.deepcopy(self.index);old=index.get(name,{'current':None,'previous':None,'quarantined':[]})
        index[name]={'current':digest,'previous':old['current'] if old['current']!=digest else old['previous'],
                     'quarantined':[x for x in old['quarantined'] if x!=digest][-8:]}
        self._commit(index)
    def rollback(self,name):
        self._name(name);index=copy.deepcopy(self.index);row=index[name]
        if not row['previous']:raise ValueError('no previous version')
        self._load(name,row['previous']);row['current'],row['previous']=row['previous'],row['current'];self._commit(index)
    def quarantine(self,name):
        self._name(name);index=copy.deepcopy(self.index);row=index[name]
        row['quarantined']=(row['quarantined']+[row['current']])[-8:]
        previous=row['previous'] if row['previous'] not in row['quarantined'] else None
        if previous:self._load(name,previous)
        row['current']=previous;row['previous']=None;self._commit(index)
    def uninstall(self,name):
        self._name(name);path=self._dir(name);index=copy.deepcopy(self.index);index.pop(name,None);self._commit(index)
        if path.exists():shutil.rmtree(path)
    def gc(self):
        for name in self.index:
            path=self._dir(name)
            if not path.exists():continue
            keep={self.index[name]['current'],self.index[name]['previous']}
            for child in path.iterdir():
                if child.is_symlink():raise ValueError('symlink GC')
                if child.is_dir() and re.fullmatch('[0-9a-f]{64}',child.name) and child.name not in keep:shutil.rmtree(child)
