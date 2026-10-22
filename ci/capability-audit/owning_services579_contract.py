"""Finite original A26/S03 data contract. Source is never a runtime verdict."""
from pathlib import Path
import hashlib,json,re
ROOT=Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
HERE=Path(__file__).resolve().parent
IDS={'services':'behavior:phone-published-capabilities-not-declared','ads':'behavior:advertising-service-provider-missing'}
KEYS={'prepare_callers','install','start','input','collect','network','cleanup'}
NAMES=('DistributedFile','HiDumper','DataTransitManager','DeviceAuth','DeviceSecurityLevel','PinAuth')
LEDGER=ROOT/'docs/capability-audit/integration-20261019/remaining-requirements.json'
LEDGER_SHA='54cac89929c14de4b3e384b1ab0316b9cc9d3aef19668ff4591f73fdadfff28c'
ACTIONS=('identity','declarations','permissions','native','account-create','account-restore','account-recover','pin-open','pin-denied','pin-info','pin-enroll','pin-auth','pin-wrong','pin-cancel','pin-cancel-now','pin-delete','pin-close','dfs-connect','dfs-disconnect','dfs-write','dfs-read','dfs-delete','dfs-cleanup','exit')

def need(x,m):
 if not x:raise ValueError(m)
def ref(path):
 p=Path(path);need(p.is_absolute() and p.resolve()==p and p.is_file() and not any(x.is_symlink() for x in (p,*p.parents)),'regular absolute artifact')
 digest=hashlib.sha256()
 with p.open('rb') as stream:
  for block in iter(lambda:stream.read(2*1024*1024),b''):digest.update(block)
 return {'path':str(p),'sha256':digest.hexdigest()}
def check_ref(row):
 need(type(row) is dict and set(row) in ({'path','sha256'},{'path','sha256','bytes'}),'actual Ref2/3')
 need(ref(row['path'])=={k:row[k] for k in ('path','sha256')},'changed artifact')
 p=Path(row['path']);need('bytes' not in row or p.stat().st_size==row['bytes'],'actual artifact size')
 return p
def raw(row):
 p=Path(row['path']);need(p.stat().st_size<=256*1024*1024,'bounded raw metadata/transport artifact')
 return check_ref(row).read_bytes()
def unique(rows):
 out={}
 for k,v in rows:need(k not in out,'duplicate JSON key');out[k]=v
 return out
def loads(body):return json.loads(body,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
def doc(row):return loads(raw(row))
def save(path,value):
 p=Path(path);need(p.parent.is_dir() and p.parent.resolve()==p.parent,'owned existing output')
 with p.open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 return ref(p)
def original():
 need(ref(LEDGER)['sha256']==LEDGER_SHA,'immutable original ledger')
 value=loads(LEDGER.read_bytes());need(value['schema']=='post-consolidation-source-assessment/v1','original ledger schema')
 rows=[x for x in value['requirements'] if x['id'] in IDS.values()]
 need({x['id'] for x in rows}==set(IDS.values()) and len(rows)==2,'two exact original top-level IDs')
 return rows
