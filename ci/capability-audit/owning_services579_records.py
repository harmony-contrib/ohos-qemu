"""Pure raw reconstruction; it has no shell, callback or resource methods."""
from pathlib import Path
import json,re,zipfile
from owning_services579_contract import need,ref,raw,doc,loads,check_ref
from owning_services579_project import ROLES,bundle,source_files,module_fields,configure_profile


def normalized(row):
 result={k:row[k] for k in ('argv','exit_code','boot_id','timed_out')}
 result.update(stdout=row['stdout_ref'],stderr=row['stderr_ref'])
 if 'shell_exit_code' in row:result.update(shell_exit_code=row['shell_exit_code'],shell_stdout=row['shell_stdout_ref'])
 return result

def body(row):
 # Exact original frozen43 provider579_records.shell_body transport contract.
 # This fixed local definition avoids depending on whether API action loaded
 # a private module before an unrelated service replay. No wrapper is forged.
 need(type(row['argv']) is list and row['argv'] and type(row['exit_code']) is int and row['timed_out'] is False,'actual settled command')
 out=raw(row['stdout_ref']).decode();err=raw(row['stderr_ref']).decode()
 need(out==row['stdout'] and err==row['stderr'] and raw(row['log'])==(out+err).encode(),'complete original command streams/log changed')
 if len(row['argv'])>=5 and row['argv'][3]=='shell':
  from guest_ui import command_exit
  marker=re.findall(r'__CAP578_EXIT_[a-f0-9]{32}__=',row['argv'][4])
  ui=re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=',row['argv'][4])
  need((len(marker),len(ui)) in ((1,0),(0,1)),'one original private shell or GuestUi nonce footer')
  result,code=command_exit(out,(marker or ui)[0])
  if marker:need(row['shell_stdout']==result and row['shell_exit_code']==code and raw(row['shell_stdout_ref']).decode()==result,'actual inner shell status/body mismatch')
  else:need('shell_stdout' not in row and 'shell_exit_code' not in row,'GuestUi transport must remain original raw')
  return result,code
 return out,row['exit_code']


class Evidence:
 def __init__(self,retained,archive,*,kind):
  self.retained=doc(retained);self.archive=archive;check_ref(archive);v=self.retained
  need(v['schema']=='six-owning-services579-closed-IO/v1' and v['kind']==kind and v['archive_sha256']==archive['sha256'],'same-artifact retained service flow')
  self.boot=doc(v['boot']);self.env=self.boot['test_environment'];self.io=doc(v['io'])
  need(self.boot['archive_sha256']==archive['sha256'] and self.boot['purpose']=='acceptance' and
   self.env['external_keepalive'] is False and self.env['device_type']=='phone' and
   self.env['boot_id']==v['boot_id']==self.io['boot_id'] and self.io['archive_sha256']==archive['sha256'] and self.io['closed'] is True and
   not any(self.boot.get(k) for k in ('candidate_kernel','kernel_command_line_diagnostic','diagnostic_assistance','diagnostic_power_button')),'real unassisted new package/closed IO')
  build=doc(v['build_inputs']);manifest=doc(v['package_manifest']);initial=self.boot['initial_package_file_sha256']
  need(initial['build-inputs.json']==v['build_inputs']['sha256'] and initial['manifest.json']==v['package_manifest']['sha256'],'actual archive initial metadata')
  need(initial['device-profile.json']==v['device_profile']['sha256'],'actual package device-contract metadata')
  self.device_profile=doc(v['device_profile'])
  from production579_target import context
  target=context(manifest);need(target['device']=='phone' and target['arch']==self.env['guest_arch'] and target['product']==self.env['product'],'actual phone target')
  need(all(x['reaped'] is True and type(x['exit_code']) is int for x in self.io['held_transports'].values()),'IO transports not reaped')
  self.rows=self.io['commands'];self.commands=[normalized(r) for r in self.rows];self.bodies=[body(r) for r in self.rows]
  need(all(r['boot_id']==self.env['boot_id'] for r in self.rows),'foreign command boot')
  a=v['attempt'];capture=a['capture'] if kind=='local' else a['capture']['source' if kind=='dfs-source' else 'sink']
  self.capture=doc(capture);self.result=doc(a['result']);self.run=self.capture['run_id'];self.case=self.capture['case']
  need(re.fullmatch('[a-f0-9]{32}',self.run) and self.capture['boot_id']==self.env['boot_id'] and self.capture['archive_sha256']==archive['sha256'] and
   self.capture['result']==a['result'] and not self.result['failures'],'actual producer failure retained')
  self.cuts=[doc(r) for r in self.capture['cuts']];last=0
  for cut in self.cuts:
   need(cut['schema']=='owning-services579-actual-callback/v1' and cut['error'] is None and cut['boot_id']==self.env['boot_id'] and cut['run_id']==self.run and cut['archive_sha256']==archive['sha256'] and
    last<=cut['started_ns']<=cut['finished_ns'],'actual callback identity/error/time')
   last=cut['finished_ns']
   for row in cut['commands']:self.command(row)
   for qmp in cut['qmp_records']:
    need(qmp in self.io['qmp'],'foreign QMP')
    from apps_ui578_contract import qmp_wire
    qmp_wire(qmp)
  self.identities={};self.events={};self.prepare()
  starts=[c for c in self.cuts if c['callback']=='start']
  for start in starts:
   role,action,request=start['arguments'];need(request['run_id']==self.run and request['action']==action,'source-dispatched request')
   collected=[c for c in self.cuts if c['callback']=='collect' and c['arguments']==[role,request['request_id']]]
   need(collected,'actual collected request missing')
   for collected_cut in collected:
    actual=collected_cut['result'];rows=[]
    for descriptor in actual['journal_files']:
     for line in raw(descriptor).splitlines():rows.append(loads(line))
    need(rows==actual['journal'],'parsed journal/raw differs')
    for row in rows:
     need(row['run_id']==self.run and row['kind']==self.case and row['role']==role and row['bundle']==bundle(self.case,role) and
      row['uid']==self.identities[role]['uid'] and type(row['pid']) is int and row['pid']>0,'actual app UID/role/nonce')
     key=(role,row['pid'],row['seq']);need(key not in self.events or self.events[key]==row,'journal identity was replaced');self.events[key]=row
    actual_requests=[r for r in rows if r['request_id']==request['request_id'] and r['event']=='request']
    need(len(actual_requests)==1,'actual request journal missing/duplicate')
    payload=loads(actual_requests[0]['value']);need(payload['run_id']==self.run and payload['request_id']==request['request_id'] and payload['action']==action and loads(payload['payload'])==request['payload'],'actual Want payload differs')
  for role in ROLES:
   for pid in {key[1] for key in self.events if key[0]==role}:
    numbers=sorted(key[2] for key in self.events if key[:2]==(role,pid));need(numbers==list(range(len(numbers))),'truncated actual lifecycle journal')
   identities=[loads(r['value']) for key,r in self.events.items() if key[0]==role and r['event']=='self-identity']
   need(identities and all(i['bundle']==bundle(self.case,role) and i['fingerprint'].replace(':','').upper()==self.identities[role]['fingerprint'] for i in identities),'actual self/BMS/signer mismatch')
  self.cleanup()

 def command(self,row):
  need(row in self.commands,'receipt not in original closed IO')
  text,code=self.bodies[self.commands.index(row)];need(code==0 and not row['timed_out'],'actual operation failed')
  return text

 def prepare(self):
  from capability578_callers import compiled_fields_match
  prepared=self.capture['prepared'];native=self.retained['native']
  need(prepared['case']==self.case and prepared['run_id']==self.run and prepared['boot_id']==self.env['boot_id'] and set(prepared['callers'])==set(ROLES),'actual source callers')
  from owning_services579_admission import admit
  admit(native,archive_sha256=self.archive['sha256'],arch=self.env['guest_arch'])
  build=doc(native['build']);row=build['helpers']['owning_services579_napi'];self.native_row=row
  observations=[c['result'] for c in self.cuts if c['callback']=='network' and c['arguments']==['observe',{}]]
  if self.case=='local':
   need(len(observations)==1,'actual service/DSO observation')
   for name,receipt in observations[0]['dsos'].items():
    entry=row['installed_runtime_profile']['profile']['dsos'][name]
    need(self.command(receipt).split()[0]==entry['staged']['sha256'],'actual guest DSO differs from linked installed image '+name)
  from apps_providers579_bindings import bms_json
  for role,caller in prepared['callers'].items():
   need(caller['bundle']==bundle(self.case,role),'compiled exact bundle')
   source_index=doc(ref(Path(caller['project'])/'capability578-source-inputs.json'))
   for path,text in source_files(self.case,self.run,role,{'profile':'phone'}).items():need(raw(source_index[path])==text.encode(),'compiled source changed '+path)
   for k in ('build_commands','sign_commands','verify_commands'):
    need(caller[k],'missing actual SDK/sign transcript')
    for command in caller[k]:self.command(command)
   need('BUILD SUCCESSFUL' in ''.join((raw(r['stdout'])+raw(r['stderr'])).decode() for r in caller['build_commands']),'actual Hvigor build did not succeed')
   with zipfile.ZipFile(caller['signed']['path']) as signed,zipfile.ZipFile(caller['unsigned']['path']) as unsigned:
    raw(caller['signed']);raw(caller['unsigned']);need(len(signed.namelist())==len(set(signed.namelist())) and signed.read('ets/modules.abc'),'actual ABC')
    need(all(unsigned.read(n)==signed.read(n) for n in unsigned.namelist()),'signer changed compiled payload')
    compiled=loads(signed.read('module.json'));need(compiled['app']['bundleName']==caller['bundle'] and compiled_fields_match(compiled['module'],module_fields(self.case,role,{'profile':'phone'})),'actual role permissions/device')
    need(signed.read('libs/'+native['abi']+'/libowning_services579.so')==raw(native['binary']),'actual NAPI addon not in signed HAP')
   profile=doc(caller['verified_profile']);signing=doc(caller['signing'])
   need(configure_profile(self.case)(loads(json.dumps(profile)),role,self.capture['udid'],compiled)==profile and signing['verified_profile']==profile and signing['signed_sha256']==caller['signed']['sha256'],'real signer profile/UDID')
   verify=[c for c in caller['verify_commands'] if 'verify-app' in c['argv']];need(len(verify)==1,'actual verify-app')
   text=(raw(verify[0]['stdout'])+raw(verify[0]['stderr'])).decode();leaf=re.split(r'certificate #1\b',re.split(r'certificate #0\b',text,maxsplit=1)[1],maxsplit=1)[0]
   fingerprints=re.findall(r'SHA256:\s*([0-9A-Fa-f:]+)',leaf);need(len(fingerprints)==1,'actual leaf')
   fingerprint=fingerprints[0].replace(':','').upper();actual=self.capture['installed'][role]
   bms=bms_json(self.command(actual['bms']));need(bms['applicationInfo']['uid']==actual['uid'],'actual BMS UID')
   need(self.command(actual['hap']).split()[0]==caller['signed']['sha256'],'installed signed HAP hash')
   self.identities[role]=dict(uid=actual['uid'],fingerprint=fingerprint)

 def actions(self,role,action):
  output=[]
  for cut in self.cuts:
   if cut['callback']=='start' and cut['arguments'][0:2]==[role,action]:
    request=cut['arguments'][2];rows=[r for k,r in self.events.items() if k[0]==role and r['request_id']==request['request_id']]
    output.append((request,rows))
  return output
 def one(self,role,action,event,index=0):
  requests=self.actions(role,action);need(len(requests)>index,'missing action '+action)
  req,rows=requests[index];found=[r for r in rows if r['event']==event];need(len(found)==1,'missing/duplicate '+event+' '+action)
  return found[0]
 def native(self,role,operation):
  output=[]
  for request,rows in self.actions(role,'native'):
   if request['payload']['operation']!=operation:continue
   results=[r for r in rows if r['event']=='native-result'];need(len(results)==1,'actual native result missing')
   r=results[0];v=loads(r['value']);need(v['action']==operation and v['argument']==request['payload']['argument'] and v['account']==request['payload']['account'] and
    v['uid']==r['uid'] and v['pid']==r['pid'] and int(v['token'])>0 and 0<int(v['begin_ns'])<=int(v['end_ns']) and v['napi_status']==0,'native actual argument/token/clock/UID')
   matches=[c for c in self.cuts if c['callback']=='collect' and c['arguments']==[role,request['request_id']]]
   need(matches,'actual native observation')
   from owning_services579_process import replay
   observed=replay(matches[-1]['result']['process_after'],self.command)
   need(v['pid'] in observed['processes'] and observed['processes'][v['pid']]['uid']==v['uid'] and 'libowning_services579.so' in observed['maps'][v['pid']],'actual native addon process mapping')
   mappings=observed['maps'][v['pid']]
   for name in ('libdata_transit_mgr.z.so','libdslm_sdk.z.so','libhidumper_client.z.so','libdeviceauth_sdk.z.so'):
    entry=self.native_row['installed_runtime_profile']['profile']['dsos'][name];wanted='/system'+entry['image_member']
    actual=[line.split(maxsplit=5) for line in mappings.splitlines()]
    need(any(len(fields)==6 and fields[5]==wanted and int(fields[4])>0 and 'x' in fields[1] for fields in actual),
     'actual HAP process lacks executable mapping of installed source-bound SDK DSO '+name)
   for callback in v['callbacks']:need(int(v['begin_ns'])<=int(callback['ns'])<=int(v['end_ns']),'callback outside actual native interval')
   output.append(v)
  need(output,'native operation not dispatched '+operation);return output
 def cleanup(self):
  clean=[c for c in self.cuts if c['callback']=='cleanup'];need(len(clean)==1 and not clean[0]['result']['failures'],'complete original cleanup')
  bms=self.command(clean[0]['result']['bms_after']);ams=self.command(clean[0]['result']['ams_after'])
  need(all(bundle(self.case,r) not in bms and bundle(self.case,r) not in ams for r in ROLES),'BMS/AMS fixture survived')
  from owning_services579_process import replay
  need(set(clean[0]['result']['uids_after'])==set(ROLES),'every caller UID cleanup')
  for role,cut in clean[0]['result']['uids_after'].items():need(cut['uid']==self.identities[role]['uid'] and not replay(cut,self.command)['processes'],'caller UID survived cleanup')
  if self.case=='dfs':
   actual=clean[0]['result']['dfs_cleanup'];need(actual is not None,'actual owned DFS cleanup raw')
   journal=[]
   for descriptor in actual['journal_files']:
    journal += [loads(line) for line in raw(descriptor).splitlines()]
   matched=[r for r in journal if r['request_id']=='cleanup_dfs' and r['event']=='dfs-cleanup-owned']
   need(len(matched)==1 and matched[0]['uid']==self.identities['grant']['uid'],'actual owner cleanup journal')
   value=loads(matched[0]['value']);need(value['exists'] is False and value['missing'] in (0,13900002) and value['disconnectStatus'] in (0,13600004) and value['path'].endswith('/services579-'+self.run+'.bin'),'owned nonce file not removed')
  for role in ROLES:
   stops=[c for c in self.cuts if c['callback']=='input' and c['arguments']==['force-stop',{'role':role}]]
   for stop in stops:
    from owning_services579_process import replay
    need(not replay(stop['result']['after'],self.command)['processes'],'actual stopped UID remains')
