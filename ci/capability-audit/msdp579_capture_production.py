"""Automatic unsigned MSDP fixture production inside ORIGINAL Capture actor.

The original SDK39 caller/nonce and original two input generations are retained.
Extra HAPs use the actual selected API26 ETS SDK, whose own metadata is retained.
No Owner/Guest/Runner, container, socket, signing state or executable selector.
"""
from pathlib import Path
import json,os,shutil,time
from msdp579_contract import need,ref,raw,doc,checked,save

INPUT_ENV='QEMU_TEST_MSDP579_PRODUCTION'
INPUT_SHA_ENV=INPUT_ENV+'_SHA256'
OUTPUT_ENV='QEMU_TEST_MSDP579_SENSOR_ARTIFACTS'
SDK_ENV_KEYS=('QEMU_TEST_HVIGOR_HOME','QEMU_TEST_NODE_HOME','HVIGOR_USER_HOME','JAVA_HOME')
EXEC_ENV_KEYS=SDK_ENV_KEYS+('NODE_HOME','OHOS_SDK_HOME','DEVECO_SDK_HOME','OHPM_HOME')

def native_data(export_ref,archive):
 from msdp579_native import prepared_input
 from msdp579_image import verify
 from production579_target import archive_manifest
 value=doc(export_ref);owner=doc(value['supplemental_owner'])
 need(value['archive']['sha256']==archive['sha256'] and owner['exit_code']==0 and owner['cleanup_verified'] is True and
  owner['owned_container_absent'] is True and set(value['supplemental_builds'])=={'networking579','owning_services579','usb579','msdp579'},'actual closed normal original Owner four singleton receipts required')
 target=archive_manifest(checked(archive))['context']
 native=prepared_input(value['supplemental_builds']['msdp579'],archive=archive,product=target['product'])
 profile=owner['msdp579_actual_path_profile']['source'];image=ref(checked(profile).parent/'msdp579-installed-dsos.json')
 need(doc(image)['expanded_profile']==profile,'actual normal same-image sidecar association');verify(image,archive)
 return native,image

def install_on_original_owner(owner,native_export,request_ref):
 """Fixed pre-suite callable, no resources. Called on the ORIGINAL instance."""
 archive=ref(owner.archive);native,image=native_data(native_export,archive)
 sdk=Path(owner.config['sdk']);metadata=ref(sdk/'ets/oh-uni-package.json');value=doc(metadata)
 need(str(value['apiVersion'])=='26' and value['platformVersion']=='26.0.0' and value['version'] in ('26.0.0.39','26.0.0.105'),'actual selected API26 ETS SDK required')
 node=Path(owner.env['QEMU_TEST_NODE_HOME'])/'bin/node';hvigor=Path(owner.env['QEMU_TEST_HVIGOR_HOME'])
 cli=hvigor.parent.parent;cpu=Path(__file__).with_name('fixtures')/'batch_system/calendar_runtime/cpu-cap.cjs'
 data={'schema':'msdp579-original-Capture-normal-production-inputs/v1','archive':archive,'request':request_ref,'native_export':native_export,
  'native':native,'image':image,'sdk_root':str(sdk),'sdk_metadata':metadata,'sdk_metadata_value':value,
  'tools':{'node':ref(node),'ohpm':ref(cli/'ohpm/bin/pm-cli.js'),'hvigor':ref(hvigor/'bin/hvigorw.js'),'cpu_cap':ref(cpu)},
  'sdk_environment':{k:owner.env[k] for k in SDK_ENV_KEYS},'signer_dist':owner.config['select']['signer_dist']}
 path=Path(owner.output)/'msdp579-normal-production-inputs.json';actual=save(path,data)
 need(INPUT_ENV not in owner.env and INPUT_SHA_ENV not in owner.env and OUTPUT_ENV not in owner.env,'one fresh original Owner input binding')
 # The ordinary main and its original paired callbacks run in this same
 # source-admitted process; Capture receives only its separate DATA file.
 from msdp579_hooks import install_native,install_image
 install_native(native);install_image(image)
 owner.env=dict(owner.env,**{INPUT_ENV:actual['path'],INPUT_SHA_ENV:actual['sha256']})
 return actual

def install_main(children,request_ref):
 """Last fixed Main installer; wrap the already installed original full suite.

 The actual main external-inputs actor calls ordinary Capture.run(). The
 dedicated GNSS16 trace uses partial Capture primitives and is left unchanged.
 """
 value=doc(request_ref)
 need(value['schema']=='actual-root-capability579-deferred-request/v1','actual fixed Main deferred DATA request required')
 native_export=value['native_export'];doc(native_export)
 need(not getattr(children,'_msdp579_production_installed',False),'one fixed original main production installer')
 children._msdp579_production_installed=True;original=children.suite_function
 for name in ('msdp579_capture_production.py','batch_system_run_live_inputs.py','msdp579_sensor.py','msdp579_sdk.py'):
  file=Path(__file__).with_name(name)
  need(children.policy.sources.get(str(file))==ref(file)['sha256'],'current source-kit admission required: '+name)
 def suite_function(canonical_run):
  run=original(canonical_run)
  def actual(args,**callbacks):
   factory=callbacks['owned_guest_factory'];owner=factory.__self__
   need(owner.children is children and children.suite_function is suite_function and
    all(getattr(callbacks[k],'__self__',None) is owner for k in ('owned_command','owned_select_hook','owned_graphics3d_hook')),
    'fixed installed original main Owner callbacks only')
   install_on_original_owner(owner,native_export,request_ref)
   return run(args,**callbacks)
  return actual
 children.suite_function=suite_function

def inventory(root):
 # Match the original CallerBuilder copytree(symlinks=False). Retain each
 # original link and its actual target; do not reject a legitimate wrapper
 # link or silently treat it as an unobserved physical source.
 root=Path(root);files={};links=[];total=0;entries=0
 need(root.is_dir(),'original actual Hvigor wrapper cache required')
 def visit(path,relative,ancestors):
  nonlocal total,entries
  entries+=1;need(entries<=32768 and len(relative.parts)<=64,'fixed SDK wrapper entry/depth bound exceeded')
  if path.is_symlink():links.append(dict(relative=str(relative),target=os.readlink(path),resolved=str(path.resolve(strict=True))))
  actual=path.resolve(strict=True);st=actual.stat();identity=(st.st_dev,st.st_ino)
  if actual.is_dir():
   need(identity not in ancestors,'actual wrapper source has a directory-link cycle')
   for child in sorted(path.iterdir()):visit(child,relative/child.name,ancestors+(identity,))
  else:
   need(actual.is_file(),'actual wrapper source has a nonregular input')
   total+=st.st_size;need(total<=512*1024*1024,'fixed SDK wrapper source byte bound exceeded')
   files[str(relative)]=ref(actual)
 visit(root,Path('.'),())
 return dict(files=files,links=links)

def validate_execution(capture,argv,cwd,environment):
 """Called at the ORIGINAL single subprocess site before its real invocation."""
 context=getattr(capture,'_msdp579_sdk_context',None)
 need(context is not None and cwd is not None and type(environment)is dict and Path(cwd) in context['projects'] and environment==context['environment'] and
  list(map(str,argv)) in context['argv'],'only fixed selected SDK dependency/compile commands')
 return {'cwd':str(cwd),'sdk_environment':{k:environment[k] for k in EXEC_ENV_KEYS},'msdp579_production_input':context['input']}

def _command(capture,argv,label,timeout,cwd,env):
 capture.command(argv,label,timeout=timeout,cwd=cwd,env=env)
 row=capture.report['commands'][-1]
 return {'argv':row['argv'],'exit_code':row['exit_code'],'timed_out':row.get('timed_out',False),
  'stdout':raw(row['stdout_record']).decode(),'stderr':raw(row['stderr_record']).decode(),
  'stdout_ref':row['stdout_record'],'stderr_ref':row['stderr_record'],
  'log':{'path':row['log'],'sha256':row['sha256']},'cwd':row['cwd'],
  'sdk_environment':row['sdk_environment'],'msdp579_production_input':row['msdp579_production_input']}

def prepare_on_capture(capture):
 """Runs automatically after original generations, immediately before new flow."""
 need(INPUT_ENV in os.environ and INPUT_SHA_ENV in os.environ and OUTPUT_ENV not in os.environ,'fixed source-installed DATA required; prebuilt unsigned bypass forbidden')
 input_ref={'path':os.environ[INPUT_ENV],'sha256':os.environ[INPUT_SHA_ENV]};data=doc(input_ref)
 need(set(data)=={'schema','archive','request','native_export','native','image','sdk_root','sdk_metadata','sdk_metadata_value','tools','sdk_environment','signer_dist'} and
  data['schema']=='msdp579-original-Capture-normal-production-inputs/v1' and data['archive']==ref(capture.a.archive),'actual original package production inputs')
 for k in SDK_ENV_KEYS:need(os.environ.get(k)==data['sdk_environment'][k],'inherited original SDK environment differs: '+k)
 native,image=native_data(data['native_export'],data['archive']);need((native,image)==(data['native'],data['image']),'actual normal addon/image projection changed')
 sdk=Path(data['sdk_root']);need(ref(sdk/'ets/oh-uni-package.json')==data['sdk_metadata'] and doc(data['sdk_metadata'])==data['sdk_metadata_value'],'actual selected SDK metadata changed')
 # This is the ORIGINAL real SDK39 caller contract. No regenerated nonce/argv.
 contract=ref(capture.a.project/'live-inputs-contract.json');original=doc(contract)
 need(original['run_id']==capture.a.run_id==capture.report['run_id'] and original['arch']==capture.a.arch and
  original['sdk']['native_metadata']['value']['version']=='26.0.0.39' and capture.report['contract_sha256']==contract['sha256'],'same real SDK39/Capture nonce and source contract required')
 base=capture.output/'msdp579-normal-production';base.mkdir(exist_ok=False);cache=base/'sdk-cache';cache.mkdir()
 wrapper=Path(data['sdk_environment']['HVIGOR_USER_HOME'])/'wrapper';before=inventory(wrapper)
 shutil.copytree(wrapper,cache/'hvigor-home/wrapper',symlinks=False);after=inventory(wrapper);copied=inventory(cache/'hvigor-home/wrapper')
 need(before==after and {k:r['sha256'] for k,r in before['files'].items()}=={k:r['sha256'] for k,r in copied['files'].items()} and not copied['links'],'actual readonly wrapper/cache copy changed')
 cpu=cache/'cpu-cap.cjs';shutil.copyfile(checked(data['tools']['cpu_cap']),cpu)
 tools=dict(data['tools'],cpu_cap=ref(cpu))
 environment=dict(os.environ,NODE_HOME=str(checked(tools['node']).parent.parent),OHOS_SDK_HOME=str(sdk),DEVECO_SDK_HOME=str(sdk.parent),
  HVIGOR_USER_HOME=str(cache/'hvigor-home'),OHPM_HOME=str(cache/'ohpm-home'))
 from batch_system_calendar_runtime_binding import sdk_commands
 from msdp579_project import ROLES
 projects=[base/'unsigned'/role for role in ROLES];commands=[['/usr/bin/nice','-n','10',*argv] for label,argv in sdk_commands(tools)]
 capture._msdp579_sdk_context={'input':input_ref,'projects':projects,'environment':environment,'argv':commands}
 report={'schema':'msdp579-original-Capture-normal-production/v1','input':input_ref,'archive':data['archive'],'boot_id':capture.report['boot_id'],
  'run_id':capture.a.run_id,'original_sdk39_contract':contract,'selected_api26_metadata':data['sdk_metadata'],'selected_api26_metadata_value':data['sdk_metadata_value'],
  'wrapper_before':before,'wrapper_after':after,'wrapper_copied':copied,'tools':tools,'commands':[],
  'runtime_pass':False,'first_artifact_behavior_gate_passed':False};start=len(capture.report['commands']);failure=None
 try:
  from msdp579_sdk import produce
  unsigned=produce(lambda *a,**k:_command(capture,*a,**k),archive=data['archive'],run_id=capture.a.run_id,sdk=sdk,tools=tools,
   environment=environment,output=base/'unsigned',native=native,image=image)
  spec=save(base/'sensor-artifacts.json',{'schema':'msdp579-original-Capture-supplement-inputs/v1','unsigned':unsigned,'signer_dist':data['signer_dist']})
  os.environ[OUTPUT_ENV]=spec['path'];report.update(unsigned=unsigned,sensor_artifacts=spec)
 except BaseException as error:failure=error;report['error']=repr(error)
 finally:
  report['commands']=capture.report['commands'][start:];report['finished_monotonic_ns']=time.monotonic_ns()
  try:
   record=save(base/'production.json',report);capture.report['msdp579_sdk_production']=record
  except BaseException as receipt_error:
   capture.report['msdp579_sdk_receipt_error']=repr(receipt_error)
   if failure is None:failure=receipt_error
  finally:del capture._msdp579_sdk_context
 if failure is not None:raise failure
 return spec['path']

def replay(capture,evidence,*,registry,actor_id):
 """Inside the authenticated original raw actor; all six real SDK commands."""
 report=doc(capture['msdp579_sdk_production']);data=doc(report['input']);contract=doc(report['original_sdk39_contract'])
 need('error' not in report and report['run_id']==evidence.run==capture['run_id']==contract['run_id'] and
  report['boot_id']==evidence.env['boot_id'] and report['archive']==evidence.archive and contract['sdk']['native_metadata']['value']['version']=='26.0.0.39','actual SDK production/nonce/owning boot failed')
 native,image=native_data(data['native_export'],evidence.archive);need((native,image)==(data['native'],data['image']),'same actual normal native/image required')
 need(report['selected_api26_metadata']==data['sdk_metadata'] and doc(data['sdk_metadata'])==report['selected_api26_metadata_value']==data['sdk_metadata_value'],'actual selected API26 identity changed')
 need(report['wrapper_before']==report['wrapper_after'] and {k:r['sha256'] for k,r in report['wrapper_before']['files'].items()}==
  {k:r['sha256'] for k,r in report['wrapper_copied']['files'].items()} and not report['wrapper_copied']['links'],'actual SDK wrapper source/cache copy differs')
 for collection in ('wrapper_before','wrapper_after','wrapper_copied'):
  for r in report[collection]['files'].values():raw(r)
 for link in report['wrapper_before']['links']:
  path=Path(data['sdk_environment']['HVIGOR_USER_HOME'])/'wrapper'/link['relative']
  need(path.is_symlink() and os.readlink(path)==link['target'] and str(path.resolve(strict=True))==link['resolved'],'actual SDK wrapper source link changed')
 from msdp579_sdk import verify
 from msdp579_project import ROLES
 from batch_system_calendar_runtime_binding import sdk_commands
 unsigned=verify(report['unsigned'],evidence.archive,evidence.run,evidence.env['device_type'])
 need(report['unsigned']==evidence.flow['normal_supplement'] and doc(report['sensor_artifacts'])['unsigned']==report['unsigned'] and len(report['commands'])==6,'complete three-role normal SDK fixture supplement required')
 from collections import Counter
 actual_handles=[h for h in registry['handles'].values() if h['parent']==actor_id and h['original_argv'] in [r['argv'] for r in report['commands']]]
 need(len(actual_handles)==6 and Counter(tuple(h['original_argv']) for h in actual_handles)==Counter(tuple(r['argv']) for r in report['commands']) and
  all(h['returncode']==0 and h['settled'] is True for h in actual_handles),'six actual SDK children must belong to the original external-inputs Runner actor')
 for role in ROLES:
  c=unsigned['callers'][role];project=Path(c['project'])
  for actual,(label,argv) in zip(c['build_commands'],sdk_commands(report['tools'])):
   rows=[r for r in report['commands'] if r['argv']==actual['argv'] and r['cwd']==str(project)]
   need(len(rows)==1 and actual['argv']==['/usr/bin/nice','-n','10',*argv] and rows[0]['exit_code']==actual['exit_code']==0 and
    rows[0]['stdout_record']==actual['stdout_ref'] and rows[0]['stderr_record']==actual['stderr_ref'] and
    rows[0]['msdp579_production_input']==report['input'],'original actual command/cwd/raw/input differs')
   row=rows[0];matching=[r for r in evidence.commands if r['argv']==row['argv'] and r['stdout_ref']==row['stdout_record'] and r['stderr_ref']==row['stderr_record']]
   need(len(matching)==1,'normal fixture SDK command is not from original Capture closed IO')
   evidence.command(evidence.norm[evidence.commands.index(matching[0])])
   need(actual['sdk_environment']==row['sdk_environment'] and actual['sdk_environment']['OHOS_SDK_HOME']==data['sdk_root'],'actual SDK command environment changed')
 return {'actual_production':capture['msdp579_sdk_production'],'unsigned':report['unsigned'],'original_sdk39_contract':report['original_sdk39_contract'],
  'selected_api26_metadata':data['sdk_metadata'],'commands':report['commands'],'runtime_pass':False}
