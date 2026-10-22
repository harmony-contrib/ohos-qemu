"""Original complete /proc UID scan + same-generation mapped-library cuts."""
from pathlib import Path
import secrets,time
from owning_services579_contract import need
from batch_network_openvpn_runtime_collect import snapshot_script,parse_snapshot,SnapshotRace


def observe(io,uid,bundle,label,*,maps=False):
 deadline=time.monotonic()+30
 while True:
  nonce=secrets.token_hex(16);script=snapshot_script(nonce,io.boot_id,mode='uid',uid=uid,bundle=bundle)
  before=io.shell(script,label+'_scan_before',timeout=60)
  try:first=parse_snapshot(before['stdout'],nonce,io.boot_id,mode='uid',uid=uid,bundle=bundle)
  except SnapshotRace:
   need(time.monotonic()<deadline,'actual UID scan did not stabilize');continue
  mapped={}
  if maps:
   for pid in first['processes']:
    row=io.shell('cat /proc/'+str(pid)+'/maps',label+'_maps_'+str(pid),timeout=60)
    mapped[str(pid)]=io.ref_receipt(row)
  after_nonce=secrets.token_hex(16)
  after=io.shell(snapshot_script(after_nonce,io.boot_id,mode='uid',uid=uid,bundle=bundle),label+'_scan_after',timeout=60)
  try:last=parse_snapshot(after['stdout'],after_nonce,io.boot_id,mode='uid',uid=uid,bundle=bundle)
  except SnapshotRace:
   need(time.monotonic()<deadline,'actual UID scan did not stabilize');continue
  identities=lambda value:{int(pid):(v['start'],v['uid'],tuple(v['argv'])) for pid,v in value['processes'].items()}
  if identities(first)!=identities(last):
   need(time.monotonic()<deadline,'actual caller generation changed during maps observation');continue
  return {'uid':uid,'bundle':bundle,'boot_id':io.boot_id,'before_nonce':nonce,'after_nonce':after_nonce,
   'before':io.ref_receipt(before),'after':io.ref_receipt(after),'maps':mapped}


def replay(value,command):
 before=parse_snapshot(command(value['before']),value['before_nonce'],value['boot_id'],mode='uid',uid=value['uid'],bundle=value['bundle'])
 after=parse_snapshot(command(value['after']),value['after_nonce'],value['boot_id'],mode='uid',uid=value['uid'],bundle=value['bundle'])
 identities=lambda data:{int(pid):(row['start'],row['uid'],tuple(row['argv'])) for pid,row in data['processes'].items()}
 need(identities(before)==identities(after),'actual UID/map generation changed')
 need(not value['maps'] or set(value['maps'])=={str(k) for k in before['processes']},'actual complete selected maps')
 return {'processes':after['processes'],'maps':{int(pid):command(row) for pid,row in value['maps'].items()}}
