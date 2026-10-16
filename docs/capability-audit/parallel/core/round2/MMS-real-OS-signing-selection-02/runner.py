from pathlib import Path
import hashlib,json,shutil,subprocess,sys,time
out=Path(__file__).resolve().parent;source=out/'source';repo=out/'frozen';staging=out/'image-root';policies=source/'vendor/ohemu/virt/preinstall-config'
shutil.copy2('/ohos/vendor/ohemu/virt/preinstall-config/uninstall_list.json',policies/'uninstall_list.json')
target=staging/'app/com.ohos.mms/Mms.hap';target.parent.mkdir(parents=True);shutil.copy2(out/'Mms-signed.hap',target)
staged=staging/'etc/app';staged.mkdir(parents=True)
rows=[]
for label in ('positive','uninstall-veto','numeric-uninstall','ambiguous-uninstall'):
 for p in policies.glob('*.json'):shutil.copy2(p,staged/p.name)
 p=staged/'uninstall_list.json';value=json.loads(p.read_bytes())
 if label=='uninstall-veto':value['uninstall_list'].append('/system/app/com.ohos.mms');p.write_text(json.dumps(value))
 if label=='numeric-uninstall':value['uninstall_list'].append(0);p.write_text(json.dumps(value))
 if label=='ambiguous-uninstall':
  d=staging/'system/etc/app';d.mkdir(parents=True);shutil.copy2(p,d/p.name)
 image=out/(label+'.ext4')
 with image.open('xb') as stream:stream.truncate(64*1024*1024)
 commands=[['/usr/sbin/mkfs.ext4','-q','-F','-d',str(staging),str(image)],[sys.executable,str(repo/'scripts/verify_mms_provider_image.py'),'--system-image',str(image),'--source-root',str(source),'--output',str(out/(label+'-contract.json'))]]
 for index,command in enumerate(commands):
  log=out/(label+'-'+str(index)+'.log');start=time.time()
  with log.open('xb') as stream:r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
  rows.append(dict(label=label,index=index,argv=command,exit_code=r.returncode,seconds=time.time()-start,log=str(log),sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
  (out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
  expected=0 if index==0 or label=='positive' else 1
  assert (r.returncode==0)==(expected==0),rows[-1]
print(json.dumps(dict(status='pass',scope='actual signed MMS new combined selection guard 1 positive 3 uninstall counterexamples ONLY NOT guest',cases=4,first_artifact_behavior_gate_passed=False)),flush=True)
