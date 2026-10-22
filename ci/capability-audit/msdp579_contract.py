"""Exact original S08, nine source-declared modalities; no closure by flags."""
from pathlib import Path
import hashlib,json,re
ID='behavior:msdp-device-status-mock-or-missing-clients'
LEDGER_SHA='54cac89929c14de4b3e384b1ab0316b9cc9d3aef19668ff4591f73fdadfff28c'
MODALITIES=('Cooperate','Drag','Stationary','DeviceStatus','DistanceMeasurement','MetadataBinding','Motion','OnScreenAwareness','UserStatus')
CAPS=tuple('SystemCapability.Msdp.DeviceStatus.'+n for n in MODALITIES[:3])+tuple('SystemCapability.MultimodalAwareness.'+n for n in MODALITIES[3:])
# Positive provider scopes are NEVER inferred from an API error/getter/has().
POSITIVE_SCOPES=('cooperate-remote-input','drag-udmf-roundtrip','stationary-still-input','stationary-relative-input',
 'device-steady-standing','device-rotation','distance-measurement','metadata-event-roundtrip','metadata-pixel-roundtrip',
 'motion-inference','onscreen-content-control','user-status-inference')
def need(v,m):
 if not v:raise ValueError(m)
def ref(p):
 p=Path(p).absolute();need(p.resolve()==p and p.is_file() and not p.is_symlink(),'actual absolute regular source/raw file required');b=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest())
def checked(r):
 need(type(r)is dict and set(r) in ({'path','sha256'},{'path','sha256','bytes'}),'exact physical Ref2/3')
 p=Path(r['path']);need(p.is_absolute() and not p.is_symlink() and p.is_file() and ref(p)=={k:r[k] for k in ('path','sha256')} and ('bytes'not in r or r['bytes']==p.stat().st_size),'physical source/raw changed');return p
def raw(r):return checked(r).read_bytes()
def doc(r):return json.loads(raw(r))
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
 return ref(p)
def request(run,n,action,payload=None):return dict(run_id=run,request_id='msdp_'+str(n),action=action,payload={} if payload is None else payload)
