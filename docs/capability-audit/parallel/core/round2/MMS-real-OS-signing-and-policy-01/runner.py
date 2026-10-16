from pathlib import Path
import copy, hashlib, importlib.util, json, shutil, subprocess, sys, time, zipfile

out=Path(__file__).resolve().parent
repo=out/'frozen'
source=out/'source'
sys.path.insert(0,str(repo/'patches/lib'))
import mms_provider as provider
rows=[]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(label,argv,expected=0):
    start=time.time();log=out/(label+'.log')
    with log.open('xb') as stream:
        result=subprocess.run([str(x) for x in argv],stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    row=dict(label=label,argv=[str(x) for x in argv],exit_code=result.returncode,
             expected_success=expected==0,seconds=time.time()-start,log=str(log),sha256=sha(log))
    rows.append(row);(out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    if (result.returncode==0)!=(expected==0):raise RuntimeError('unexpected result: '+label)

project=source/provider.PROJECT
project.parent.mkdir(parents=True)
run('clone-real-MMS',['git','clone','--shared','--no-checkout','/ohos/'+provider.PROJECT,project])
run('checkout-real-MMS',['git','-C',project,'checkout','--detach',provider.REVISION])
dist=source/'developtools/hapsigner/dist';dist.mkdir(parents=True)
for name in provider.SIGNING_INPUTS:
    shutil.copy2(Path('/ohos/developtools/hapsigner/dist')/name,dist/name)
policy_dir=source/'vendor/ohemu/virt/preinstall-config';policy_dir.mkdir(parents=True)
for name in ('install_list.json','install_list_capability.json','install_list_permissions.json'):
    shutil.copy2(Path('/ohos/vendor/ohemu/virt/preinstall-config')/name,policy_dir/name)
hap_build=source/'applications/standard/hap/BUILD.gn';hap_build.parent.mkdir(parents=True)
shutil.copy2('/ohos/applications/standard/hap/BUILD.gn',hap_build)
for component in ('mms/source_provider','mms/send_data_text','hap/admin_provider','hap/mms_provider'):
    run('apply-'+component.replace('/','-'),['bash',repo/'patches/common/applications/standard'/component/'apply.sh','--source-root',source])
result=provider.prepare(source);provider.verify(source)
profile=project/'signature/mms.p7b'
before={str(p.relative_to(source)):sha(p) for p in (profile,*policy_dir.glob('*.json'))}
provider.prepare(source);provider.verify(source)
after={str(p.relative_to(source)):sha(p) for p in (profile,*policy_dir.glob('*.json'))}
assert before==after
(out/'profile-and-policy.json').write_text(json.dumps(dict(result=result,idempotent=True,files=after,
    profile=provider.verify(source)),indent=2)+'\n')
unsigned=Path('/input-MMS.hap');signed=out/'Mms-signed.hap'
run('sign-real-MMS',['java','-jar',dist/'hap-sign-tool.jar','sign-app','-mode','localSign',
    '-signAlg','SHA256withECDSA','-keyAlias','openharmony application release','-inFile',unsigned,
    '-outFile',signed,'-profileFile',profile,'-keystoreFile',dist/'OpenHarmony.p12',
    '-keyPwd','123456','-keystorePwd','123456','-appCertFile',dist/'OpenHarmonyApplication.pem',
    '-profileSigned','1','-inForm','zip'])
checker=repo/'scripts/verify_mms_provider_image.py'
run('verify-signed-HAP',[sys.executable,checker,'--hap',signed,'--source-root',source,'--output',out/'signed-HAP-contract.json'])

staging=out/'image-root'
target=staging/'app/com.ohos.mms/Mms.hap';target.parent.mkdir(parents=True);shutil.copy2(signed,target)
staged_policies=staging/'etc/app';staged_policies.mkdir(parents=True)
for p in policy_dir.glob('*.json'):shutil.copy2(p,staged_policies/p.name)
image_rows=[]
def image_case(label,mutate=None):
    # Every counterexample starts from the same signed HAP and original policies.
    for p in policy_dir.glob('*.json'):shutil.copy2(p,staged_policies/p.name)
    shutil.copy2(signed,target)
    shutil.rmtree(staging/'system',ignore_errors=True)
    if mutate:mutate()
    image=out/(label+'.ext4')
    with image.open('xb') as stream:stream.truncate(64*1024*1024)
    run(label+'-mkfs',['/usr/sbin/mkfs.ext4','-q','-F','-d',staging,image])
    result_path=out/(label+'-contract.json')
    run(label+'-verify',[sys.executable,checker,'--system-image',image,'--source-root',source,'--output',result_path],expected=1 if mutate else 0)
    result=json.loads(result_path.read_text())
    image_rows.append(dict(case=label,image_sha256=sha(image),result=result))
    (out/'image-cases.json').write_text(json.dumps(image_rows,indent=2)+'\n')

def edit_install(change):
    path=staged_policies/'install_list.json';data=json.loads(path.read_bytes());change(data['install_list'])
    path.write_text(json.dumps(data)+'\n')
def row(rows):return next(r for r in rows if r.get('app_dir')=='/system/app/com.ohos.mms')
def alter_policy(name,change):
    path=staged_policies/name;data=json.loads(path.read_bytes());items=data.get('install_list') if isinstance(data,dict) else data
    change(next(r for r in items if r.get('bundleName')=='com.ohos.mms'));path.write_text(json.dumps(data)+'\n')
def tamper_abc():
    with zipfile.ZipFile(signed) as archive,zipfile.ZipFile(target,'w') as changed:
        for info in archive.infolist():
            data=archive.read(info.filename)
            if info.filename=='ets/modules.abc':data=data[:-1]+bytes([data[-1]^1])
            changed.writestr(info,data)
def duplicate_hap():
    p=staging/'system/app/com.ohos.mms/Mms.hap';p.parent.mkdir(parents=True);shutil.copy2(signed,p)
image_case('positive')
image_case('missing-MMS-install',lambda:edit_install(lambda rows:rows.remove(row(rows))))
image_case('duplicate-MMS-install',lambda:edit_install(lambda rows:rows.append(copy.deepcopy(row(rows)))))
image_case('removable-MMS-install',lambda:edit_install(lambda rows:row(rows).update(removable=True)))
image_case('numeric-removable-MMS-install',lambda:edit_install(lambda rows:row(rows).update(removable=0)))
image_case('wildcard-MMS-grants',lambda:alter_policy('install_list_permissions.json',lambda r:r.update(app_signature=['*'])))
image_case('numeric-MMS-capability',lambda:alter_policy('install_list_capability.json',lambda r:r.update(singleton=1)))
image_case('ambiguous-MMS-HAP',duplicate_hap)
image_case('tampered-MMS-ABC',tamper_abc)
(out/'result.json').write_text(json.dumps(dict(status='pass',unsigned_hap_sha256=sha(unsigned),
    signed_hap_sha256=sha(signed),profile_sha256=sha(profile),image_case_count=len(image_rows),
    first_artifact_behavior_gate_passed=False,provider_runtime_validated=False,
    scope='real public OS signing exact source grants and private ext4 positive/negative checks ONLY NOT product image or guest'),indent=2)+'\n')
