from pathlib import Path
import copy,hashlib,json,shutil,subprocess,sys,time,zipfile

out=Path(__file__).resolve().parent
repo=out/'frozen';source=out/'source'
sys.path.insert(0,str(repo/'patches/lib'))
import contacts_theme_providers as provider
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=[];failures=[]
def run(label,argv,expected=0):
    argv=[str(x) for x in argv];log=out/(label+'.log');start=time.time()
    with log.open('xb') as stream:
        result=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    row=dict(label=label,argv=argv,exit_code=result.returncode,expected_success=expected==0,
             seconds=time.time()-start,log=str(log),sha256=sha(log))
    rows.append(row);(out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    if (result.returncode==0)!=(expected==0):failures.append(label)
    return result.returncode

for name,config in provider.PROFILES.items():
    project=source/config['project'];project.parent.mkdir(parents=True,exist_ok=True)
    assert run('clone-'+name,['git','clone','--shared','--no-checkout','/ohos/'+config['project'],project])==0
    assert run('checkout-'+name,['git','-C',project,'checkout','--detach',config['revision']])==0
dist=source/'developtools/hapsigner/dist';dist.mkdir(parents=True)
for name in provider.SIGNING_INPUTS:shutil.copy2(Path('/ohos/developtools/hapsigner/dist')/name,dist/name)
policies=source/'vendor/ohemu/virt/preinstall-config';policies.mkdir(parents=True)
for name in ('install_list.json','uninstall_list.json','install_list_capability.json','install_list_permissions.json'):
    shutil.copy2(Path('/ohos/vendor/ohemu/virt/preinstall-config')/name,policies/name)
graph=source/'applications/standard/hap/BUILD.gn';graph.parent.mkdir(parents=True)
shutil.copy2('/input-HAP-BUILD.gn',graph)
for name in ('contacts/source_provider','contacts/production_manifest','contacts/picker_session_lifecycle',
             'theme/source_provider','theme/sdk_schema','theme/module_names','theme/api26_compat',
             'theme/renderer_lifecycle','hap/contacts_theme_provider'):
    assert run('apply-'+name.replace('/','-'),['bash',repo/'patches/common/applications/standard'/name/'apply.sh','--source-root',source])==0
prepared=provider.prepare(source);verified=provider.verify(source)
files=[source/c['project']/c['profile'] for c in provider.PROFILES.values()]+list(policies.glob('*.json'))
before={str(p.relative_to(source)):sha(p) for p in files}
provider.prepare(source);provider.verify(source)
assert before=={str(p.relative_to(source)):sha(p) for p in files}
(out/'profiles-and-policy.json').write_text(json.dumps(dict(prepared=prepared,profiles=verified,files=before,idempotent=True),indent=2)+'\n')
signed={}
for name,kind in (('contacts','contacts'),('theme-phone','theme'),('theme-pad','theme')):
    config=provider.PROFILES[kind];path=out/(name+'-signed.hap');signed[name]=path
    assert run('sign-'+name,['java','-jar',dist/'hap-sign-tool.jar','sign-app','-mode','localSign',
        '-signAlg','SHA256withECDSA','-keyAlias','openharmony application release','-inFile','/input-'+name+'.hap',
        '-outFile',path,'-profileFile',source/config['project']/config['profile'],
        '-keystoreFile',dist/'OpenHarmony.p12','-keyPwd','123456','-keystorePwd','123456',
        '-appCertFile',dist/'OpenHarmonyApplication.pem','-profileSigned','1','-inForm','zip'])==0

staging=out/'image-root';targets={}
for name,filename in (('contacts','Contacts.hap'),('theme','Wallpaper.hap')):
    target=staging/'app'/provider.PROFILES[name]['bundle']/filename;target.parent.mkdir(parents=True);targets[name]=target
staged=staging/'etc/app';staged.mkdir(parents=True)
image_rows=[]
def edit_install(name,change):
    path=staged/'install_list.json';data=json.loads(path.read_bytes());rows=data['install_list']
    row=next(r for r in rows if r.get('app_dir')=='/system/app/'+provider.PROFILES[name]['bundle'])
    change(rows,row);path.write_text(json.dumps(data)+'\n')
def alter_policy(filename,change):
    path=staged/filename;data=json.loads(path.read_bytes());items=data.get('install_list') if isinstance(data,dict) else data
    change(next(r for r in items if r.get('bundleName')=='com.ohos.contacts'));path.write_text(json.dumps(data)+'\n')
def duplicate(name):
    target=staging/'system/app'/provider.PROFILES[name]['bundle']/targets[name].name
    target.parent.mkdir(parents=True);shutil.copy2(targets[name],target)
def tamper(name):
    original=out/(name+'-tamper-input.hap');shutil.copy2(targets[name],original)
    with zipfile.ZipFile(original) as archive,zipfile.ZipFile(targets[name],'w') as changed:
        for info in archive.infolist():
            raw=archive.read(info.filename)
            if info.filename=='ets/modules.abc':raw=raw[:-1]+bytes([raw[-1]^1])
            changed.writestr(info,raw)
def veto():
    path=staged/'uninstall_list.json';data=json.loads(path.read_bytes());data['uninstall_list'].append('/system/app/com.ohos.wallpaper')
    data['recover_list']=[r for r in data['recover_list'] if r!='/system/app/com.ohos.wallpaper'];path.write_text(json.dumps(data)+'\n')
def image_case(label,device='phone',mutate=None):
    for path in policies.glob('*.json'):shutil.copy2(path,staged/path.name)
    shutil.rmtree(staging/'system',ignore_errors=True)
    shutil.copy2(signed['contacts'],targets['contacts']);shutil.copy2(signed['theme-pad' if device=='2in1' else 'theme-phone'],targets['theme'])
    if mutate:mutate()
    image=out/(label+'.ext4')
    with image.open('xb') as stream:stream.truncate(64*1024*1024)
    assert run(label+'-mkfs',['/usr/sbin/mkfs.ext4','-q','-F','-d',staging,image])==0
    result_path=out/(label+'-contract.json')
    run(label+'-verify',[sys.executable,repo/'scripts/verify_contacts_theme_provider_image.py','--system-image',image,
        '--source-root',source,'--device',device,'--output',result_path],1 if mutate else 0)
    image_rows.append(dict(case=label,image_sha256=sha(image),expected_accept=mutate is None,result=json.loads(result_path.read_text())))
    (out/'image-cases.json').write_text(json.dumps(image_rows,indent=2)+'\n')

image_case('phone-positive')
image_case('pad-positive','2in1')
image_case('wrong-device',mutate=lambda:shutil.copy2(signed['theme-pad'],targets['theme']))
image_case('contacts-missing-install',mutate=lambda:edit_install('contacts',lambda rows,row:rows.remove(row)))
image_case('wallpaper-wrong-removability',mutate=lambda:edit_install('theme',lambda rows,row:row.update(removable=False)))
image_case('wallpaper-numeric-removability',mutate=lambda:edit_install('theme',lambda rows,row:row.update(removable=1)))
image_case('wallpaper-uninstall-veto',mutate=veto)
image_case('contacts-wildcard-grants',mutate=lambda:alter_policy('install_list_permissions.json',lambda row:row.update(app_signature=['*'])))
image_case('contacts-numeric-capability',mutate=lambda:alter_policy('install_list_capability.json',lambda row:row.update(singleton=1)))
image_case('contacts-ambiguous-inode',mutate=lambda:duplicate('contacts'))
image_case('wallpaper-ambiguous-inode',mutate=lambda:duplicate('theme'))
image_case('contacts-tampered-ABC',mutate=lambda:tamper('contacts'))
image_case('wallpaper-tampered-ABC',mutate=lambda:tamper('theme'))
result=dict(status='fail' if failures else 'pass',failures=failures,signed_haps={name:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for name,p in signed.items()},
            image_case_count=len(image_rows),first_artifact_behavior_gate_passed=False,provider_runtime_validated=False,
            scope='real Contacts/Wallpaper OS signing private ext4 positive/negative ONLY NOT new product image/BMS/guest')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
raise SystemExit(bool(failures))
