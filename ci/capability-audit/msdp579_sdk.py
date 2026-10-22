"""Separate normal unsigned supplement; caller supplies original Owner command."""
from pathlib import Path
import json,shutil,zipfile
from msdp579_contract import need,ref,doc,raw,save
from msdp579_project import ROLES,bundle,source_files,module_fields
from batch_apps_contact_picker_runtime import prepare_project
from batch_system_calendar_runtime_binding import sdk_commands
from capability578_callers import compiled_fields_match
from production579_target import archive_manifest

def produce(command,*,archive,run_id,sdk,tools,environment,output,native,image):
 # command is an explicitly bound original Owner producer method; JSON cannot
 # choose it, an executable, module or source file. No Owner/resource here.
 from msdp579_contract import checked
 target=archive_manifest(checked(archive))['context'];output=Path(output);output.mkdir(exist_ok=False)
 from msdp579_admission import admit
 admit(native,archive_sha256=archive['sha256'],arch=target['arch'])
 from msdp579_image import verify as verify_image
 verify_image(image,archive)
 report=dict(native=native,image=image,schema='msdp579-normal-unsigned-sensor-supplement/v1',archive=archive,run_id=run_id,target=target,
  sdk=ref(Path(sdk)/'ets/oh-uni-package.json'),tools=tools,callers={},commands=[],runtime_pass=False,first_artifact_behavior_gate_passed=False)
 for role in ROLES:
  root=output/role;prepare_project(root);shutil.rmtree(root/'entry/src/main/ets/model');(root/'caller-source-manifest.json').unlink()
  app=root/'AppScope/app.json5';a=json.loads(app.read_text());a['app']['bundleName']=bundle('sensor',role);app.write_text(json.dumps(a)+'\n')
  manifest=root/'entry/src/main/module.json5';m=json.loads(manifest.read_text());m['module'].update(module_fields('sensor',role));manifest.write_text(json.dumps(m)+'\n')
  for name,text in source_files('sensor',run_id,role,{'profile':target['device']}).items():
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
  from msdp579_project import native_artifact_destination
  dest=root/native_artifact_destination(target['arch']);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(native['binary']['path'],dest)
  bp=root/'entry/build-profile.json5';bv=json.loads(bp.read_text());bv.setdefault('buildOption',{})['nativeLib']={'debugSymbol':{'strip':False}};bp.write_text(json.dumps(bv)+'\n')
  (root/'local.properties').write_text('sdk.dir='+str(Path(sdk).parent)+'\n')
  sources={str(p.relative_to(root)):ref(p) for p in root.rglob('*') if p.is_file()}
  save(root/'capability578-source-inputs.json',sources)
  rows=[]
  for label,argv in sdk_commands(tools):
   row=command(['/usr/bin/nice','-n','10',*argv],'msdp579_sensor_'+role+'_'+label,timeout=1800,cwd=root,env=environment)
   need(row['exit_code']==0 and not row.get('timed_out',False),'actual normal SDK operation failed')
   if label=='compile':need('BUILD SUCCESSFUL' in row['stdout']+row['stderr'],'real SDK compile incomplete')
   rows.append(row);report['commands'].append(row)
  haps=list(root.glob('entry/build/default/outputs/default/*-unsigned.hap'));need(len(haps)==1,'one real unsigned HAP')
  with zipfile.ZipFile(haps[0]) as z:
   compiled=json.loads(z.read('module.json'));need(z.read('libs/'+native['abi']+'/libmsdp579.so')==raw(native['binary']),'actual SDK native bytes changed');need(z.read('ets/modules.abc') and len(z.namelist())==len(set(z.namelist())) and compiled['app']['bundleName']==bundle('sensor',role) and compiled_fields_match(compiled['module'],module_fields('sensor',role)),'actual compiled sensor role')
  report['callers'][role]=dict(bundle=bundle('sensor',role),project=str(root),unsigned=ref(haps[0]),source_index=ref(root/'capability578-source-inputs.json'),build_commands=rows)
 return save(output/'msdp579-sensor-unsigned.json',report)

def verify(row,archive,run,profile):
 report=doc(row);need(report['schema']=='msdp579-normal-unsigned-sensor-supplement/v1' and report['archive']==archive and report['run_id']==run and report['target']['device']==profile and set(report['callers'])==set(ROLES),'actual package/nonce/three role SDK supplement')
 raw(report['sdk'])
 from msdp579_admission import admit
 admit(report['native'],archive_sha256=archive['sha256'],arch=report['target']['arch'])
 for role,c in report['callers'].items():
  sources=doc(c['source_index'])
  for name,text in source_files('sensor',run,role,{'profile':profile}).items():need(raw(sources[name])==text.encode(),'actual compiled fixture differs')
  for s in sources.values():raw(s)
  need(len(c['build_commands'])==2,'actual dependency+compile commands')
  for command in c['build_commands']:
   need(command['exit_code']==0 and not command.get('timed_out',False),'actual SDK command failed')
   need(raw(command['stdout_ref']).decode()==command['stdout'] and raw(command['stderr_ref']).decode()==command['stderr'],'actual SDK streams changed')
  need('BUILD SUCCESSFUL' in c['build_commands'][1]['stdout']+c['build_commands'][1]['stderr'],'real Hvigor success absent');raw(c['unsigned'])
 return report
