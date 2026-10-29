#!/usr/bin/env python3
"""Exact one-file source transaction; no model, injected data or acceptance."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def apply(root):
 root=Path(root).resolve();m=json.loads((HERE/'manifest.json').read_text());p=root/m['path']
 if p.is_symlink() or not p.is_file():raise ValueError('regular actual stationary source required')
 if subprocess.check_output(['git','-C',str(root/m['project']),'rev-parse','HEAD'],text=True).strip()!=m['revision']:raise ValueError('actual project HEAD differs')
 old=p.read_bytes();digest=lambda b:hashlib.sha256(b).hexdigest()
 if digest(old)==m['after']:return {'status':'already_applied','runtime_pass':False}
 if digest(old)!=m['before']:raise ValueError('unknown stationary source; preserving edits')
 data=(HERE/'after.cpp').read_bytes()
 if digest(data)!=m['after'] or digest((HERE/'before.cpp').read_bytes())!=m['before']:raise ValueError('component payload changed')
 state=p.stat();fd,name=tempfile.mkstemp(prefix='.msdp-rotation-',dir=p.parent)
 try:
  with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
  os.chmod(name,state.st_mode&0o777)
  if p.read_bytes()!=old:raise ValueError('source changed after preflight')
  os.replace(name,p)
 finally:Path(name).unlink(missing_ok=True)
 return {'status':'source_applied_NOT_runtime','runtime_pass':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--source-root',type=Path,required=True);print(json.dumps(apply(a.parse_args().source_root)))
