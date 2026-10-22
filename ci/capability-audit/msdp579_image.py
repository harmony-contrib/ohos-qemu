"""Separate same-package Cooperate/client DSO proof; original15 unchanged."""
from pathlib import Path
import json,secrets
from msdp579_contract import need,ref,raw,doc,checked
NAME='libintention_cooperate.z.so'
CLIENT='libdevicestatus_client.z.so'
def verify(proof,archive):
 v=doc(proof);need(v['schema']=='actual-package-msdp579-installed-dsos/v1' and v['archive']['sha256']==archive['sha256'] and set(v['entries'])==set(v['proofs'])=={NAME,CLIENT},'one actual same-image MSDP DSO sidecar')
 from production579_target import archive_manifest
 target=archive_manifest(checked(archive))['context']
 from batch_system_build_runtime_helpers import elf_header,elf_soname
 export=doc(v['source_export'])
 for name in (NAME,CLIENT):
  entry=v['entries'][name];p=v['proofs'][name];staged=p['staged'];actual=checked(p['actual_image'])
  need(p['partition']=='system' and type(p['image_inode'])is int and p['image_inode']>0 and entry['soname']==name and entry['image_member']==staged['image_member'] and
   entry['staged']['sha256']==entry['image_file']['sha256']==p['actual_image']['sha256']==staged['sha256'] and
   entry['image_member'].startswith('/'+('lib' if target['arch']=='armv7a' else 'lib64')+'/') and Path(entry['image_member']).name==name and actual.stat().st_size==staged['bytes'],'actual image inode/staged/export/ABI member')
  elf_header(actual,product=target['product']);need(elf_soname(actual,product=target['product'])==name,'actual DSO class/machine/SONAME')
  need(staged in export['files'],'same original readonly export row')
  exported=checked(v['source_export']).parent/staged['export_relative'];need(ref(exported)['sha256']==staged['sha256'],'actual export bytes changed')
 need(doc(v['build_inputs'])['source_git_revision']==v['source_commit'],'actual normal build source identity')
 return v

def observe(io,proof,*,name=NAME,uid=None):
 archive=ref(io.capture.a.archive) if hasattr(io,'capture') else ref(io.owner.archive)
 v=verify(proof,archive);entry=v['entries'][name]
 from msdp579_mappings import snapshot_script,parse_snapshot
 remote='/system'+entry['image_member'];nonce=secrets.token_hex(16)
 scan=io.shell(snapshot_script(nonce,io.boot_id),'msdp579_provider_discovery')
 parsed=parse_snapshot(scan['stdout'],nonce,io.boot_id);need(parsed['complete'],'complete original provider discovery scan')
 candidates=[pid for pid,p in parsed['processes'].items() if p['classification']=='user' and
  p['uids'] and (max(p['uids'])<10000 if uid is None else set(p['uids'])=={uid}) and any(m['path']==remote for m in p['maps']) and
  any(Path(m['path']).name==('libdevicestatus_service.z.so' if uid is None else 'libmsdp579.so') for m in p['maps'])]
 need(len(candidates)==1,'one actual native MSDP process must load both service and Cooperate plugin')
 pid=candidates[0];observations=[]
 for label in ('before','after'):
  nonce=secrets.token_hex(16);script=snapshot_script(nonce,io.boot_id,pid=pid,libraries=(remote,));row=io.shell(script,'msdp579_provider_'+label)
  value=parse_snapshot(row['stdout'],nonce,io.boot_id,pid=pid,libraries=(remote,));need(value['complete'],'actual exact-PID provider cut incomplete')
  observations.append(dict(nonce=nonce,script=script,command=io.ref_receipt(row)))
 return dict(image=proof,name=name,uid=uid,pid=pid,mappings=observations,discovery=dict(nonce=parsed['nonce'],command=io.ref_receipt(scan)),boot_id=io.boot_id)

def replay(observation,e):
 v=verify(observation['image'],e.archive)
 from msdp579_mappings import parse_snapshot,_file_identity,_text
 name=observation['name'];need(name in (NAME,CLIENT),'finite loaded DSO')
 remote='/system'+v['entries'][name]['image_member'];expected=v['entries'][name]['staged']['sha256'];pid=observation['pid'];results=[]
 discovery=parse_snapshot(e.command(observation['discovery']['command']),observation['discovery']['nonce'],e.env['boot_id'])
 need(discovery['complete'] and pid in discovery['processes'],'actual full provider discovery missing')
 for item in observation['mappings']:
  cut=parse_snapshot(e.command(item['command']),item['nonce'],e.env['boot_id'],pid=pid,libraries=(remote,));need(cut['complete'],'same-OFD image/PID cut incomplete')
  p=cut['processes'][pid];need(p['classification']=='user' and len(set(p['uids']))==1 and (p['uids'][0]<10000 if observation['uid'] is None else p['uids'][0]==observation['uid']) and
   any(Path(m['path']).name==('libdevicestatus_service.z.so' if observation['uid'] is None else 'libmsdp579.so') and 'x' in m['permissions'] for m in p['maps']),'actual native service identity')
  first=_file_identity(_text(cut['queries']['file_before_0']['hex']));last=_file_identity(_text(cut['queries']['file_after_0']['hex']));need(first==last,'image DSO inode changed')
  matches=[m for m in p['maps'] if m['path']==remote];need(matches and any('x' in m['permissions'] for m in matches) and all(not m['deleted'] and m['inode']==first['inode'] and m['device']==first['device'] for m in matches),'actual executable mapped same-image inode')
  for phase in ('before','after'):need(_text(cut['queries']['hash_'+phase+'_0']['hex'])==expected+'  '+remote,'actual guest DSO differs from installed source/image')
  results.append(p)
 need(results[0]['before']['start_ticks']==results[1]['after']['start_ticks'] and all(results[0][k]==results[1][k] for k in ('uids','argv','exe','attr')),'provider process generation/UID changed')
 return dict(image=observation['image'],boot_id=e.env['boot_id'],pid=pid,start_ticks=results[0]['before']['start_ticks'],uid=results[0]['uids'][0])
