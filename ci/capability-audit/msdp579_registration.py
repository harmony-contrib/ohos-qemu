"""Original S08 only, fixed complete raw join in Root's final actor."""
from pathlib import Path
import subprocess
from msdp579_contract import ID,LEDGER_SHA,POSITIVE_SCOPES,need,ref,raw,doc,save
from msdp579_replay import Evidence,local,sensor,cooperate
from msdp579_image import replay as image_replay

def collect(packet,output,actor,*,replayed):
 need(subprocess.Popen is actor.ProxyPopen and actor.STATE is not None,'original authenticated final raw actor only')
 from final579_contract import ORIGINAL,own_sources
 from final579_seal import settlement
 need(ref(ORIGINAL)['sha256']==LEDGER_SHA,'immutable original requirements changed')
 original=[r for r in doc(ref(ORIGINAL))['requirements'] if r['id']==ID];need(len(original)==1,'one exact original S08 row')
 approved={r['path']:r['sha256'] for r in doc(own_sources())['files']}
 names=('contract','project','process','io','runtime','sdk','capture_bridge','capture_production','sensor','mappings','image','hooks','replay','registration','policy','rotation','native','admission')
 for name in names:
  file=Path(__file__).with_name('msdp579_'+name+'.py')
  need(approved.get(str(file.resolve()))==ref(file)['sha256'],'Root must explicitly admit every fixed MSDP source')
 archive=packet['archive'];main=doc(packet['main_boot']);parts={};failures=[];unresolved=[];scopes={}
 def check(name,f):
  try:parts[name]=f();scopes.update(parts[name])
  except (ValueError,KeyError,TypeError,IndexError,OSError) as error:failures.append(dict(scope=name,error=type(error).__name__+': '+str(error)))
 closure=settlement(packet['main_settlement']['held'],packet['main_settlement']['constructors'])
 suite=doc(packet['main_suite']);stage=doc(suite['capability578']);root=Path(closure['root'])
 def main_part():
  matches=[c for c in stage['cases'] if c['group']=='msdp-nine' and c['case']=='local'];need(len(matches)==1,'fixed S08 local main stage missing')
  case=matches[0];base=Path(case['result']['path']).parent;need(base.is_relative_to(root),'actual stage must belong to original main Owner')
  e=Evidence(flow=ref(base/'msdp579/flow.json'),io=ref(base/'io.json'),boot=packet['main_boot'],archive=archive)
  need(e.env['boot_id']==main['test_environment']['boot_id'],'actual main boot differs');return local(e)
 check('main',main_part)
 def sensor_part():
  # Only main's ordinary external-inputs actor calls the complete Capture.run.
  # Dedicated GNSS16 directly uses selected Capture primitives, not this flow.
  from msdp579_contract import checked
  from parallel_runtime_suite import load_plan,argv as family_argv,verify_family
  work=Path(suite['work']);base=work/'external-inputs';family_ref=ref(base/'evidence.json');family=doc(family_ref)
  need(work.is_relative_to(root) and packet['runtime_root']==str(work),'actual main work/Owner root differs')
  check_row=suite['checks']['external-inputs']
  need(check_row['evidence']==family_ref['path'] and check_row['sha256']==family_ref['sha256'],'original main family check/raw differs')
  boot=ref(work/'boot/external-inputs-boot.json')
  need(family['boot']==boot and family['archive']==archive and family['capture']==ref(base/'capture/capture.json'),'actual complete external-inputs receipt/capture/stable boot path differs')
  plan=load_plan(checked({k:suite['capability_inputs'][k] for k in ('path','sha256')}),main['test_environment'])
  expected=family_argv('external-inputs',plan,checked(boot),checked(archive),family['hdc'],base,checked(packet['main_suite']))
  commands=check_row['commands']
  need(len(commands)==1 and commands[0] in suite['commands'] and commands[0]['argv']==expected and commands[0]['exit_code']==0 and
   not commands[0].get('timed_out',False) and Path(commands[0]['log']).is_relative_to(work) and
   ref(commands[0]['log'])['sha256']==commands[0]['sha256'],'original full external-inputs actual command/exit/log differs')
  registry=doc(packet['main_settlement']['constructors'])
  actors=[(key,a) for key,a in registry['actors'].items() if a['entry']==str(Path(__file__).with_name('batch_system_live_inputs_suite.py')) and a['argv']==expected and a['parent']=='root-suite']
  need(len(actors)==1,'one actual original main external-inputs Runner actor required')
  actor_id,owner_actor=actors[0];handles=[h for h in registry['handles'].values() if h['actor']==actor_id]
  need(owner_actor['started'] is True and owner_actor['done'] is True and len(handles)==1 and
   handles[0]['returncode']==0 and handles[0]['settled'] is True,'actual complete family actor did not finish successfully')
  original_result=verify_family('external-inputs',checked(family_ref),checked(archive),main['test_environment'])
  capture=doc(family['capture']);data=capture['msdp579']
  e=Evidence(flow=data['flow'],io=data['io'],boot=boot,archive=archive)
  need(e.env['boot_id']==main['test_environment']['boot_id'] and family['run_id']==capture['run_id']==e.run,'actual main owning boot/SDK39 nonce differs')
  from msdp579_capture_production import replay as replay_production
  production=replay_production(capture,e,registry=registry,actor_id=actor_id)
  need(doc(doc(capture['msdp579_sdk_production'])['input'])['request']==doc(packet['main_attempt'])['capability_request'],'SDK DATA was not derived from the actual fixed Main request')
  from msdp579_rotation import replay as rotation_replay
  return dict(sensor(e,capture),**rotation_replay(e,capture),sdk_production=production,original_external_inputs=original_result)
 check('sensor',sensor_part)
 def pair_part():
  outer=doc(packet['paired']['report']);live=doc(packet['paired']['live_proof']);endpoints={}
  for name in ('source','sink'):
   io=live['endpoint_io'][name];base=Path(io['path']).parent
   need(base==Path(outer['endpoints'][name]['output'])/'business-io','actual original paired IO location')
   endpoints[name]=Evidence(flow=ref(base/'msdp579/flow.json'),io=io,boot=outer['endpoints'][name]['boot'],archive=archive)
  proof=doc(replayed['paired']['proof'])['raw_replay'];need(not replayed['paired']['failures'],'original complete paired raw failure')
  runtime=doc(outer['runtime']);operations=runtime['operations']
  selected=[(i,o) for i,o in enumerate(operations) if o['kind']=='network_msdp579-held'];need(len(selected)==1,'one fixed early trusted MSDP callback required')
  position,operation=selected[0];record=operation['record'];meta=doc(record['semantic_callback'])
  need(meta['error'] is None and meta['arguments']==['msdp579-held',doc(record['trusted'])] and
   record['flows']=={n:ref(Path(live['endpoint_io'][n]['path']).parent/'msdp579/flow.json') for n in endpoints},'fixed callback raw arguments/flow references differ')
  need(any(o['kind']=='network_owning-services579-held' for o in operations[:position]),'actual common trusted seam predecessor missing')
  later=[]
  for o in operations[position+1:]:
   if o['kind']=='request':continue
   m=doc(o['record']['semantic_callback'])
   if m['kind']=='start':later.append(m['arguments'][1] if len(m['arguments'])>1 else None)
  need('camera-devices' in later and 'dm-unbind' in later,'cooperation must precede actual media and final unbind')
  for name,e in endpoints.items():
   need(e.flow['paired_business']['trusted_window']==record['trusted'],'raw trust envelope changed')
   need(all(meta['started_ns']<=a['started_ns']<=a['finished_ns']<=meta['finished_ns'] for a in e.flow['actions']),'actual public actions escape the retained early trusted window')
  result=cooperate(endpoints['source'],endpoints['sink'],proof)
  for e in endpoints.values():
   need(len(e.flow['cooperate_provider'])==2,'actual provider must be observed in both activated generations')
   for observation in e.flow['cooperate_provider']:image_replay(observation,e)
  return result
 check('cooperate',pair_part)
 # Exact Root-adopted source policy is distinct from actual supported raw.
 # A missing policy/fact or failed boundary never becomes a pass/exclusion.
 from msdp579_policy import approved
 policy={}
 try:policy=approved()
 except (ValueError,KeyError,TypeError,OSError) as error:failures.append(dict(scope='exact seven provider source disposition',error=str(error)))
 supported={k:v for k,v in scopes.items() if k in POSITIVE_SCOPES and v.get('complete') is True}
 need(not (set(supported)&set(policy)),'a source-unsupported model cannot be relabeled supported')
 missing=sorted(set(POSITIVE_SCOPES)-set(supported)-set(policy));registrations={}
 for name in missing:unresolved.append(dict(id=ID,scope=name,reason='complete actual positive raw or exact Root-adopted public provider disposition absent'))
 framework_complete=scopes.get('framework-boundaries',{}).get('complete') is True
 if not framework_complete:unresolved.append(dict(id=ID,scope='framework-boundaries',reason='complete actual nine-modality framework boundaries were not reconstructed'))
 if failures:unresolved.append(dict(id=ID,scope='actual supported obligations',details=failures))
 complete=not unresolved and not failures
 result=save(Path(output)/'msdp579-nine-modalities.json',dict(schema='msdp579-nine-modalities-original-S08-raw-join/v1',archive=archive,
  original_requirement=original[0],parts=parts,supported_portions=supported,unsupported_positive_portions=policy,unresolved=unresolved,failures=failures,
  required_obligations_complete=complete,formally_closed=[],runtime_pass=False,first_artifact_behavior_gate_passed=False))
 if complete:registrations[ID]=dict(archive_sha256=archive['sha256'],boot_id=main['test_environment']['boot_id'],evidence=result,original_requirement=original[0],resolution='actual_supported_nine_modality_obligations_with_exact_disclosed_nonpass_provider_scopes',unsupported_positive_portions=policy,runtime_pass=False)
 return dict(registrations=registrations,failures=failures,unresolved=unresolved,supported_portions=supported,proof=result,required_obligations_complete=complete,original_owner_finish_still_required=True)
