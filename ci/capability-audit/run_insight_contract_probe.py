#!/usr/bin/env python3
"""Run all seven dynamic intent contracts on an already booted packaged guest.

This tool never boots or substitutes a guest image. An enclosing suite must bind
its archive and boot evidence before any contract may be registered.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node
from insight_contract_common import EVIDENCE_SCOPE, file_record, identity as bms_identity
from prepare_form_component_sdk import prepare, PROJECT_HEAD, SOURCE_PATH
from run_root_probe import digest

ROOT=Path(__file__).resolve().parents[2]
OWNED_BUNDLES=('org.harmonycontrib.insightnavigationaudit','org.harmonycontrib.insightdriveraudit',
    'org.harmonycontrib.insightformhostaudit','org.harmonycontrib.capabilityaudit')


def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    repo=ROOT;hdc=str(args.hdc)
    report=dict(status='fail',scope=EVIDENCE_SCOPE,first_artifact_behavior_gate_passed=False,
        archive=str(args.archive.resolve()),archive_sha256=digest(args.archive),boot_id=args.boot_id,
        arch=args.arch,device=args.device,target=args.target,udid=args.udid,
        applications={},commands=[],failures=[],caller_cleanup_verified=False)
    def save():(output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    def sha(path):return digest(Path(path))
    def command(argv,label,timeout=90,allow_failure=False):
        argv=list(map(str,argv));log=output/(str(len(report['commands'])).zfill(3)+'-'+label+'.log')
        row=dict(argv=argv,log=str(log),exit_code=None);report['commands'].append(row);save()
        child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            stdin=subprocess.DEVNULL,start_new_session=True)
        try:stdout,stderr=child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            try:stdout,stderr=child.communicate(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);stdout,stderr=child.communicate()
            log.write_text(stdout+stderr);row.update(timed_out=True,sha256=digest(log));save()
            raise ValueError('intent command timed out: '+label)
        log.write_text(stdout+stderr);row.update(exit_code=child.returncode,sha256=digest(log));save()
        if not allow_failure and (child.returncode or re.search(r'\[Fail\]|Device not found or connected',stdout)):
            raise ValueError('intent command failed: '+label)
        return stdout.replace('\r','')
    def shell(script,label,allow_failure=False):
        marker='__INTENT_SHELL_EXIT_'+secrets.token_hex(16)+'__='
        reply=command([hdc,'-t',args.target,'shell',script+'; task_intent_rc=$?; printf "\\n'+marker+'%s\\n" "$task_intent_rc"'],label,allow_failure=allow_failure)
        match=re.search(r'(?:^|\n)'+re.escape(marker)+r'(\d+)\s*$',reply)
        if not match or (not allow_failure and match.group(1)!='0'):
            raise ValueError('intent guest command lost its actual exit status: '+label)
        return reply[:match.start()]
    guest=SimpleNamespace(shell=shell,target=args.target,udid=args.udid)
    ui=GuestUi(command,hdc,args.target,output/'ui')
    def same_guest(label):
        if shell('cat /proc/sys/kernel/random/boot_id',label).strip()!=args.boot_id:
            raise ValueError('intent proof escaped the enclosing guest boot')
    save()
    try:
        cpu={'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[args.arch]
        if shell('id -u; param get const.product.devicetype; uname -m','guest-identity').split()!=['0',args.device,cpu]:
            raise ValueError('intent guest architecture/profile differs')
        same_guest('boot-before')
        prepared_sdk=output/'sdk'
        shutil.copytree(args.sdk,prepared_sdk,symlinks=True)
        declaration=output/'pinned-form-component.d.ts'
        source_program="from pathlib import Path; import shutil,subprocess; root=Path('/ohos/interface/sdk-js'); assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()=="+repr(PROJECT_HEAD)+"; shutil.copyfile(Path('/ohos')/"+repr(SOURCE_PATH)+",'/probe/pinned-form-component.d.ts')"
        command(['docker','run','--rm','--platform','linux/amd64',
            '--mount','type=volume,src='+args.source_volume+',dst=/ohos,readonly',
            '--mount','type=bind,src='+str(output)+',dst=/probe',args.docker_image,
            'python3','-c',source_program],'copy-pinned-real-widget-declaration',300)
        report['sdk_preparation']=prepare(prepared_sdk,declaration);save()
        shell('power-shell wakeup','intent-start-wakeup')
        sdk=prepared_sdk
        nonce=secrets.token_hex(16);target=output/'target-project'
        command([sys.executable,repo/'ci/capability-audit/build_insight_decorator_probe.py','--sdk',sdk,'--output',target,'--role','normal','--arch',args.arch,'--run-id',nonce,'--arkdown',args.arkdown],'build-real-decorated-target',1800)
        command([sys.executable,repo/'ci/capability-audit/verify_insight_decorator_build.py','--project',target,'--run-id',nonce,'--output',output/'target-build-verification.json'],'verify-real-target-metadata',90)
        def sign_install(name,project,signer,role,bundle):
            unsigned=project/'entry/build/default/outputs/default/entry-default-unsigned.hap'
            signed=output/(name+'-signed.hap')
            command(['docker','run','--rm','--platform','linux/amd64',
                '--mount','type=volume,src='+args.source_volume+',dst=/ohos,readonly',
                '--mount','type=bind,src='+str(repo)+',dst=/work,readonly',
                '--mount','type=bind,src='+str(output.resolve())+',dst=/probe',args.docker_image,
                'python3','/work/ci/capability-audit/'+signer,
                '--signer-dist','/ohos/developtools/hapsigner/dist',
                '--jar','/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                '--unsigned','/probe/'+unsigned.relative_to(output).as_posix(),
                '--output','/probe/'+signed.relative_to(output).as_posix(),'--role',role,'--udid',args.udid],name+'-sign',300)
            command([hdc,'-t',guest.target,'uninstall',bundle],name+'-remove-own-old',allow_failure=True)
            command([hdc,'-t',guest.target,'install',signed],name+'-install')
            text=guest.shell('bm dump -n '+bundle,name+'-actual-BMS-record')
            identity_path=output/(name+'-application-identity.json');identity_path.write_text(text)
            receipt_name=('insight-decorator' if name=='target' else 'insight-form-host' if name.startswith('caller-') else
                'insight-driver' if name.startswith('function-caller-') else 'insight-navigation')+'-probe-inputs.json'
            report['applications'][name]=dict(role=role,bundle=bundle,project=str(project),
                inputs=file_record(project/receipt_name),application_identity=file_record(identity_path),
                unsigned_hap=file_record(unsigned),signed_hap=file_record(signed),
                signing_receipt=file_record(signed.with_suffix('.signing.json')),actual_uid=bms_identity(text,bundle,role))
            save();return text
        report['target_nonce']=nonce
        sign_install('target',target,'sign_ethernet_control_probe.py','normal','org.harmonycontrib.capabilityaudit')
        guest.shell('aa start -a EntryAbility -b org.harmonycontrib.capabilityaudit','start-target')
        time.sleep(2)
        # This child uses the enclosing guest; every copied observation must be
        # bound to its archive/boot and the actual installed signed application.
        sys.path.insert(0,str(repo/'ci/capability-audit'))
        from verify_insight_driver_results import verify
        from insight_form_runtime import capture_phase
        from verify_insight_form_host_results import verify as verify_form, verify_provider, verify_pixels
        metadata=json.loads((output/'target-build-verification.json').read_text())
        report['roles']={}
        for role in ('normal','system-denied','system'):
            caller_nonce=secrets.token_hex(16);caller=output/('caller-'+role+'-project')
            command([sys.executable,repo/'ci/capability-audit/build_insight_form_host_probe.py','--sdk',sdk,'--output',caller,'--role',role,'--arch',args.arch,'--run-id',caller_nonce,'--arkdown',args.arkdown],role+'-build-real-caller',1800)
            identity=sign_install('caller-'+role,caller,'sign_insight_form_host_probe.py',role,'org.harmonycontrib.insightformhostaudit')
            doc=json.loads(identity[identity.index('{'):]);uid=doc['applicationInfo']['uid']
            guest.shell('aa start -a EntryAbility -b org.harmonycontrib.insightformhostaudit',role+'-start-caller')
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                try:
                    layout,path=ui.layout(bundle='org.harmonycontrib.insightformhostaudit',label=role+'-actual-intent-caller-ready')
                    selected=select_node(layout,'org.harmonycontrib.insightformhostaudit',identifier='insight-form-host-start',clickable=True)
                except (LayoutNotReady,NodeNotReady):time.sleep(.25);continue
                left,top,width,height=selected['rect']
                ui.shell('uitest uiInput click '+str(left+width//2)+' '+str(top+height//2),role+'-actual-intent-caller-ready-node-center');break
            else:raise ValueError('real intent caller never attached its enabled Run control')
            remote='/data/app/el2/100/base/org.harmonycontrib.insightformhostaudit/files/insight-form-host-'+caller_nonce+'-results.log'
            provider_remote='/data/app/el2/100/base/org.harmonycontrib.capabilityaudit/files/insight-form-'+nonce+'-results.log'
            phase_evidence=[]
            def read_rows():
                text=guest.shell('cat '+shlex.quote(remote)+' 2>/dev/null',role+'-host-phase-observation',True)
                return [json.loads(line) for line in text.splitlines() if line]
            def await_phase(predicate,label):
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    rows=read_rows()
                    if any(row.get('name')=='failed' for row in rows):raise ValueError('actual FormComponent failed: '+json.dumps(rows))
                    if predicate(rows):return rows
                    time.sleep(.25)
                raise ValueError('actual form phase timed out: '+label)
            def click_control(identifier,label):
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    try:return ui.click('org.harmonycontrib.insightformhostaudit',identifier=identifier,label=label)
                    except (LayoutNotReady,NodeNotReady):time.sleep(.25)
                raise ValueError('actual form control never ready: '+identifier)
            if role=='system':
                for cycle in range(2):
                    rows=await_phase(lambda rows:any(row['cycle']==cycle and row['name']=='acquired' for row in rows),'acquired')
                    form_id=next(row['data'] for row in rows if row['cycle']==cycle and row['name']=='acquired')
                    if not form_id.isdecimal() or int(form_id)<=0:raise ValueError('invalid actual form ID')
                    phase=dict(cycle=cycle,form_id=form_id,acquired_rows=rows)
                    acquired=capture_phase(ui,output/('form-acquired-'+str(cycle)+'-presentation.json'),nonce,form_id,'added','form-acquired-'+str(cycle))
                    phase.update(acquired_layout=acquired['layout'],acquired_screenshot=acquired['screenshot'],acquired_presentation=acquired)
                    phase['request_click']=click_control('insight-form-host-request','form-request-'+str(cycle))
                    await_phase(lambda rows:any(row['cycle']==cycle and row['name']=='request' for row in rows),'requested')
                    deadline=time.monotonic()+90
                    while time.monotonic()<deadline:
                        text=guest.shell('cat '+shlex.quote(provider_remote)+' 2>/dev/null','provider-update-'+str(cycle),True)
                        provider_rows=[json.loads(line) for line in text.splitlines() if line]
                        if any(row['formId']==form_id and row['name']=='update.success' for row in provider_rows):break
                        time.sleep(.25)
                    else:raise ValueError('actual provider never completed updateForm')
                    phase['updated_provider_rows']=provider_rows
                    updated=capture_phase(ui,output/('form-updated-'+str(cycle)+'-presentation.json'),nonce,form_id,'updated','form-updated-'+str(cycle))
                    phase.update(updated_layout=updated['layout'],updated_screenshot=updated['screenshot'],updated_presentation=updated)
                    phase['delete_click']=click_control('insight-form-host-delete','form-delete-'+str(cycle))
                    phase['deleted_rows']=await_phase(lambda rows:any(row['cycle']==cycle and row['name']=='summary' for row in rows),'deleted')
                    phase_evidence.append(phase)
                    if cycle==0:
                        phase['repeat_click']=click_control('insight-form-host-repeat','form-repeat')
                        phase['start_again_click']=click_control('insight-form-host-start','form-start-again')
            report.setdefault('phases',{})[role]=phase_evidence;save()
            deadline=time.monotonic()+180;raw=''
            while time.monotonic()<deadline:
                raw=guest.shell('cat '+shlex.quote(remote)+' 2>/dev/null',role+'-intent-own-results',True)
                if ('"summary"' in raw or '"failed"' in raw) and raw.endswith('\n'):break
                time.sleep(.5)
            raw_path=output/(role+'-results.log');raw_path.write_text(raw)
            report['roles'][role]=dict(run_id=caller_nonce,uid=uid,raw_results=str(raw_path),raw_results_sha256=sha(raw_path),rows=[json.loads(line) for line in raw.splitlines() if line]);save()
            provider_remote='/data/app/el2/100/base/org.harmonycontrib.capabilityaudit/files/insight-form-'+nonce+'-results.log'
            provider=guest.shell('if test -e '+shlex.quote(provider_remote)+'; then cat '+shlex.quote(provider_remote)+'; fi',role+'-real-form-provider-journal')
            provider_path=output/(role+'-provider-results.log');provider_path.write_text(provider)
            report['roles'][role]['provider_results']=str(provider_path)
            report['roles'][role]['provider_results_sha256']=sha(provider_path)
            identifiers=verify_form(raw,caller_nonce,role,uid)
            if role=='system':
                verify_provider(provider,nonce,identifiers)
                for phase in report['phases']['system']:
                    if phase['form_id']!=identifiers[phase['cycle']]:raise ValueError('form UI phase is foreign')
                    phase['pixel_verification']=verify_pixels(phase['acquired_screenshot'],phase['updated_screenshot'],json.loads(Path(phase['acquired_layout']).read_text()),json.loads(Path(phase['updated_layout']).read_text()),nonce,phase['form_id'])
            elif provider!='':raise ValueError('denied caller caused a real provider callback')
            report['roles'][role]['strict_parser_passed']=True
            guest.shell('aa force-stop org.harmonycontrib.insightformhostaudit',role+'-stop-own-caller')
            if guest.shell('cat /proc/sys/kernel/random/boot_id',role+'-unchanged-boot').strip()!=report['boot_id']:raise ValueError('diagnostic boot changed')
            save()
        from verify_insight_complete_driver_results import verify as verify_complete_driver
        report['complete_driver_roles']={}
        for role in ('normal','system-denied','system'):
            caller_nonce=secrets.token_hex(16);caller=output/('function-caller-'+role+'-project')
            command([sys.executable,repo/'ci/capability-audit/build_insight_driver_probe.py','--sdk',sdk,'--output',caller,'--role',role,'--arch',args.arch,'--run-id',caller_nonce,'--arkdown',args.arkdown],role+'-build-complete-driver',1800)
            identity=sign_install('function-caller-'+role,caller,'sign_insight_driver_probe.py',role,'org.harmonycontrib.insightdriveraudit')
            uid=json.loads(identity[identity.index('{'):])['applicationInfo']['uid']
            guest.shell('aa start -a EntryAbility -b org.harmonycontrib.insightdriveraudit',role+'-start-complete-driver')
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                try:click=ui.click('org.harmonycontrib.insightdriveraudit',identifier='insight-driver-start',label=role+'-complete-driver-start');break
                except (LayoutNotReady,NodeNotReady):time.sleep(.25)
            else:raise ValueError('complete driver actual control never ready')
            remote='/data/app/el2/100/base/org.harmonycontrib.insightdriveraudit/files/insight-driver-'+caller_nonce+'-results.log'
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                raw=guest.shell('cat '+shlex.quote(remote)+' 2>/dev/null',role+'-complete-driver-own-results',True)
                if ('"summary"' in raw or '"failed"' in raw) and raw.endswith('\n'):break
                time.sleep(.5)
            path=output/('complete-driver-'+role+'-results.log');path.write_text(raw)
            record=dict(run_id=caller_nonce,uid=uid,raw_results=str(path),raw_results_sha256=sha(path),click=click,strict_parser_passed=False)
            report['complete_driver_roles'][role]=record;save()
            record['rows']=verify_complete_driver(raw,caller_nonce,role,uid,{'extractInsightIntents':metadata['metadata']},nonce)
            record['strict_parser_passed']=True;save()
            guest.shell('aa force-stop org.harmonycontrib.insightdriveraudit',role+'-stop-complete-driver')
        report['navigation_roles']={}
        for role in ('normal','system-denied','system'):
            caller_nonce=secrets.token_hex(16);caller=output/('navigation-caller-'+role+'-project')
            command([sys.executable,repo/'ci/capability-audit/build_insight_navigation_probe.py','--sdk',sdk,'--output',caller,'--role',role,'--arch',args.arch,'--run-id',caller_nonce,'--target-run-id',nonce,'--arkdown',args.arkdown],role+'-build-navigation-driver',1800)
            identity=sign_install('navigation-caller-'+role,caller,'sign_insight_navigation_probe.py',role,'org.harmonycontrib.insightnavigationaudit')
            uid=json.loads(identity[identity.index('{'):])['applicationInfo']['uid']
            record=dict(run_id=caller_nonce,uid=uid,phases=[],strict_parser_passed=False)
            report['navigation_roles'][role]=record;save()
            remote='/data/app/el2/100/base/org.harmonycontrib.insightnavigationaudit/files/insight-navigation-'+caller_nonce+'-results.log'
            def nav_read():
                text=guest.shell('cat '+shlex.quote(remote)+' 2>/dev/null',role+'-navigation-own-results',True)
                path=output/('navigation-'+role+'-results.log');path.write_text(text)
                record.update(raw_results=str(path),raw_results_sha256=sha(path),rows=[json.loads(line) for line in text.splitlines() if line]);save()
                return record['rows']
            def nav_wait(predicate,label):
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    rows=nav_read()
                    if any(row['name']=='failed' for row in rows):raise ValueError('real navigation failed: '+json.dumps(rows))
                    if predicate(rows):return rows
                    time.sleep(.25)
                raise ValueError('actual navigation timed out: '+label)
            def nav_click(identifier,label):
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    try:return ui.click('org.harmonycontrib.insightnavigationaudit',identifier=identifier,label=label)
                    except (LayoutNotReady,NodeNotReady):time.sleep(.25)
                raise ValueError('actual navigation control never ready: '+identifier)
            guest.shell('aa start -a EntryAbility -b org.harmonycontrib.insightnavigationaudit',role+'-navigation-start-own-caller')
            record['initialize_click']=nav_click('insight-navigation-start',role+'-navigation-initialize')
            if role=='system':
                nav_wait(lambda rows:any(row['name']=='lookup.page' for row in rows),'metadata')
                for kind in ('page','link'):
                    for cycle in range(2):
                        if kind!='page' or cycle!=0:
                            guest.shell('aa start -a EntryAbility -b org.harmonycontrib.insightnavigationaudit','navigation-return-to-owned-caller-'+kind+'-'+str(cycle))
                        if kind=='page' and cycle==0:
                            guest.shell('aa force-stop org.harmonycontrib.capabilityaudit','navigation-page-cold-stop-own-target')
                        phase=dict(kind=kind,cycle=cycle,cold_start=kind=='page' and cycle==0)
                        phase['dispatch_click']=nav_click('insight-navigation-'+kind,'navigation-dispatch-'+kind+'-'+str(cycle))
                        try:nav_wait(lambda rows:any(row['name']=='returned.'+kind+'.'+str(cycle) for row in rows),kind+' returned')
                        except ValueError as error:
                            phase['error']=str(error);record['phases'].append(phase);save();break
                        from insight_navigation_runtime import capture_phase as capture_navigation
                        presentation=capture_navigation(ui,output/('navigation-'+kind+'-'+str(cycle)+'-presentation.json'),kind,cycle,nonce,caller_nonce)
                        phase.update(presentation=presentation,layout=presentation['layout'],
                            layout_sha256=presentation['layout_sha256'],selected_node=presentation['selected_node'],
                            screenshot=presentation['screenshot'],screenshot_sha256=presentation['screenshot_sha256'])
                        record['phases'].append(phase);save()
                if len(record['phases'])==4 and not any(phase.get('error') for phase in record['phases']):
                    nav_wait(lambda rows:any(row['name']=='summary' for row in rows),'all navigation summary')
                else:report['failures'].append('navigation incomplete: '+json.dumps(record['phases']));save()
            else:
                nav_wait(lambda rows:any(row['name']=='summary' for row in rows),'permission summary')
            for name in ('target','page'):
                provider_remote='/data/app/el2/100/base/org.harmonycontrib.capabilityaudit/files/insight-'+name+'-'+nonce+'-results.log'
                raw=guest.shell('cat '+shlex.quote(provider_remote)+' 2>/dev/null','navigation-'+role+'-actual-'+name+'-journal',True)
                path=output/('navigation-'+role+'-'+name+'-results.log');path.write_text(raw)
                record[name+'_results']=str(path);record[name+'_results_sha256']=sha(path)
            guest.shell('aa force-stop org.harmonycontrib.insightnavigationaudit',role+'-stop-navigation-own-caller')
            if guest.shell('cat /proc/sys/kernel/random/boot_id',role+'-navigation-unchanged-boot').strip()!=report['boot_id']:raise ValueError('diagnostic boot changed')
            save()
        same_guest('boot-final')
        if digest(args.archive)!=report['archive_sha256']:raise ValueError('intent archive changed during validation')
        if report['failures']:raise ValueError('incomplete actual intent behavior')
        report['status']='pass'
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as error:
        report['failures'].append(str(error));save()
    finally:
        report['cleanup']={}
        for bundle in OWNED_BUNDLES:
            try:
                shell('aa force-stop '+bundle,'cleanup-stop-'+bundle)
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    reply=shell('pidof '+bundle+' || true','cleanup-process-absence-'+bundle)
                    if not reply.strip():break
                    time.sleep(.25)
                else:raise ValueError('owned intent process did not exit')
                report['cleanup'][bundle]=dict(process_absent=True)
            except Exception as error:
                report['status']='fail';report['failures'].append('intent caller cleanup: '+str(error))
        report['caller_cleanup_verified']=len(report['cleanup'])==len(OWNED_BUNDLES)
        if report['status']=='pass':
            try:
                from verify_insight_contract_evidence import verify_evidence
                report['verified_contracts']=verify_evidence(report,report['archive_sha256'],args.boot_id,
                    args.arch,args.device,args.target)
            except Exception as error:
                report['status']='fail';report['failures'].append('complete intent evidence: '+str(error))
        report['finished_epoch']=time.time();save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','sdk','output'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('udid','target','boot-id'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--arch',choices=('arm64','armv7a','x86_64'),required=True)
    parser.add_argument('--device',choices=('phone','2in1'),required=True)
    parser.add_argument('--hdc',default='hdc')
    parser.add_argument('--source-volume',default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image',default='ohos-qemu-m144-build-env:7.0-release')
    parser.add_argument('--arkdown',default=os.environ.get('ARKDOWN','arkdown'))
    args=parser.parse_args()
    if not re.fullmatch('[a-fA-F0-9]{64}',args.udid) or not re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',args.boot_id):
        parser.error('actual guest UDID and boot ID required')
    result=run(args);print(json.dumps(dict(status=result['status'],failure_count=len(result['failures']))))
    raise SystemExit(result['status']!='pass')
