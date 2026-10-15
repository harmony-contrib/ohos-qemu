#!/usr/bin/env python3
"""Run exact typed selection callers on the enclosing package-owned guest."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time
from build_arkui_selection_probe import BUNDLE, SCOPE, ROLES, CONTRACTS, verify_inputs
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node
from insight_contract_common import file_record
from run_root_probe import digest
from selection_contract_common import identity
from selection_menu_runtime import click_menu
from selection_permission_runtime import grant_once
from selection_runtime import capture
from verify_selection_results import rows, verify, verify_presentations

ROOT = Path(__file__).resolve().parents[2]


def run(args):
    output = args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    report = dict(status='fail',scope=SCOPE,first_artifact_behavior_gate_passed=False,
        archive=str(args.archive.resolve()),archive_sha256=digest(args.archive),boot_id=args.boot_id,
        arch=args.arch,device=args.device,target=args.target,udid=args.udid,
        callers={},commands=[],failures=[],caller_cleanup_verified=False,hdc=file_record(args.hdc))
    def save(): (output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    def command(argv,label,timeout=90,allow_failure=False):
        argv = list(map(str,argv)); log = output/(str(len(report['commands'])).zfill(4)+'-'+label+'.log')
        row = dict(argv=argv,log=str(log),exit_code=None,started_monotonic=time.monotonic())
        report['commands'].append(row); save()
        with log.open('xb') as stream:
            process = subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            try: code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
                row.update(timed_out=True,sha256=digest(log)); save(); raise ValueError('selection command timed out: '+label)
        row.update(exit_code=code,sha256=digest(log),finished_monotonic=time.monotonic()); save()
        text = log.read_text().replace('\r','')
        if not allow_failure and (code or re.search(r'\[Fail\]|Device not found or connected',text)):
            raise ValueError('selection command failed: '+label)
        return text
    hdc = str(args.hdc)
    def shell(script,label,allow_failure=False):
        marker = '__SELECTION_SHELL_EXIT_'+secrets.token_hex(16)+'__='
        reply = command([hdc,'-t',args.target,'shell',script+'; task_selection_rc=$?; printf "\\n'+marker+'%s\\n" "$task_selection_rc"'],label,allow_failure=allow_failure)
        match = re.search(r'(?:^|\n)'+re.escape(marker)+r'(\d+)\s*$',reply)
        if not match or (not allow_failure and match.group(1)!='0'): raise ValueError('actual selection guest exit status lost: '+label)
        return reply[:match.start()]
    def same_boot(label):
        if shell('cat /proc/sys/kernel/random/boot_id',label).strip()!=args.boot_id:
            raise ValueError('selection caller escaped the enclosing boot')
    ui = GuestUi(command,hdc,args.target,output/'ui')
    def click(identifier,label):
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            try: return dict(ui.click(BUNDLE,identifier=identifier,label=label),kind='control',label=label,identifier=identifier)
            except (LayoutNotReady,NodeNotReady): time.sleep(.25)
        raise ValueError('actual selection control never attached: '+identifier)
    save()
    try:
        if shell('id -u; param get const.product.devicetype; uname -m','guest-identity').split()!=[
                '0',args.device,{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[args.arch]]:
            raise ValueError('selection guest ABI or device profile differs')
        same_boot('boot-before')
        for role in ROLES:
            root = output/role; root.mkdir(); nonce = secrets.token_hex(16); pid = None; remote = None
            caller = dict(run_id=nonce,role=role,phases={},actions=[],caller_cleanup_verified=False)
            report['callers'][role] = caller; save()
            try:
                project = root/'project'
                command([sys.executable,ROOT/'ci/capability-audit/build_arkui_selection_probe.py',
                    '--sdk',args.sdk,'--output',project,'--arch',args.arch,'--run-id',nonce,
                    '--hvigor-home',args.hvigor_home,'--node-home',args.node_home,'--role',role],
                    role+'-build-real-selection-caller',1800)
                inputs = project/'arkui-selection-probe-inputs.json'; verify_inputs(json.loads(inputs.read_text()))
                unsigned = project/'entry/build/default/outputs/default/entry-default-unsigned.hap'
                signed = root/'selection-signed.hap'
                command(['docker','run','--rm','--platform','linux/amd64',
                    '--mount','type=volume,src='+args.source_volume+',dst=/ohos,readonly',
                    '--mount','type=bind,src='+str(ROOT)+',dst=/work,readonly',
                    '--mount','type=bind,src='+str(output)+',dst=/probe',args.docker_image,
                    'python3','/work/ci/capability-audit/sign_arkui_selection_probe.py',
                    '--signer-dist','/ohos/developtools/hapsigner/dist',
                    '--jar','/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                    '--unsigned','/probe/'+unsigned.relative_to(output).as_posix(),
                    '--output','/probe/'+signed.relative_to(output).as_posix(),'--role',role,'--udid',args.udid],
                    role+'-sign-real-selection-caller',300)
                command([hdc,'-t',args.target,'uninstall',BUNDLE],role+'-remove-own-old-app',allow_failure=True)
                command([hdc,'-t',args.target,'install',signed],role+'-install-real-selection-caller')
                text = shell('bm dump -n '+BUNDLE,role+'-actual-selection-BMS')
                identity_path = root/'application-identity.json'; identity_path.write_text(text); uid = identity(text,role)
                caller['application'] = dict(project=str(project),inputs=file_record(inputs),
                    unsigned_hap=file_record(unsigned),signed_hap=file_record(signed),
                    signing_receipt=file_record(signed.with_suffix('.signing.json')),
                    application_identity=file_record(identity_path),actual_uid=uid)
                shell('aa start -a EntryAbility -b '+BUNDLE,role+'-start-real-selection-caller')
                deadline = time.monotonic()+60
                while time.monotonic()<deadline:
                    actual = shell('pidof '+BUNDLE+' || true',role+'-running-pid-'+str(len(report['commands']))).strip()
                    if re.fullmatch('[1-9][0-9]*',actual): pid=int(actual); break
                    time.sleep(.25)
                if pid is None: raise ValueError('actual selection caller process never started')
                if role=='reader':
                    caller['permission_request'] = click('selection-grant','reader-permission-request')
                    caller['permission_consent'] = dict(grant_once(ui,'reader-permission-consent'),
                                                       kind='consent',label='reader-permission-consent')
                remote = '/data/app/el2/100/base/'+BUNDLE+'/files/arkui-selection-'+nonce+'-results.log'
                def journal(label): return shell('cat '+remote,label)
                def snapshot(cycle,phase,actions):
                    label = role+'-'+str(cycle)+'-'+phase; record = dict(actions=actions)
                    caller['phases'][str(cycle)+':'+phase] = record
                    record['presentation'] = capture(ui,root/('presentation-'+str(cycle)+'-'+phase+'.json'),nonce,role,cycle,phase)
                    raw = journal(label+'-actual-native-journal'); path = root/('journal-'+str(cycle)+'-'+phase+'.log'); path.write_text(raw)
                    parsed = rows(raw,nonce,uid)
                    actual_pid = next(r['values'][2] for r in parsed if r['name']=='identity')
                    if actual_pid != pid: raise ValueError('selection native journal PID differs from the actual started process')
                    record['journal'] = file_record(path); save(); return raw,actual_pid,record
                for cycle in (0,1):
                    raw,pid,record = snapshot(cycle,'initial',[click('selection-start',role+'-'+str(cycle)+'-create')])
                    for phase,control in (('veto',None),('allowed','selection-allow'),('direct','selection-join')):
                        label = role+'-'+str(cycle)+'-'+phase; actions = []
                        if control: actions.append(click(control,label+'-prepare'))
                        layout,path = ui.layout(bundle=BUNDLE,label=label+'-longpress')
                        node = select_node(layout,BUNDLE,identifier='selection-alpha'); x,y,w,h = node['rect']
                        ui.shell('uitest uiInput longClick '+str(x+w//2)+' '+str(y+h//2),label+'-longpress-actual-text-center')
                        actions.append(dict(layout=str(path),selected_node=node,kind='longpress',label=label+'-longpress'))
                        actions.append(dict(click_menu(ui,BUNDLE,('全选','Select all','Select All'),label+'-select-all'),
                                            kind='menu',label=label+'-select-all',menu_labels=['全选','Select all','Select All']))
                        raw,pid,record = snapshot(cycle,phase+'-selected',actions)
                        action = dict(click_menu(ui,BUNDLE,('复制','Copy'),label+'-copy'),kind='menu',label=label+'-copy',menu_labels=['复制','Copy'])
                        raw,pid,record = snapshot(cycle,phase+'-copied',[action])
                        raw,pid,record = snapshot(cycle,phase+'-deferred',[click('selection-read',label+'-deferred-read')])
                        raw,pid,record = snapshot(cycle,phase+'-cleared',[click('selection-clear',label+'-clear')])
                    raw,pid,record = snapshot(cycle,'removed',[click('selection-remove',role+'-'+str(cycle)+'-remove')])
                    quiet_start = time.monotonic(); time.sleep(2)
                    quiet = journal(role+'-'+str(cycle)+'-removed-quiet')
                    if quiet!=raw: raise ValueError('removed selection emitted a late callback')
                    record.update(quiet_seconds=time.monotonic()-quiet_start,quiet_journal_sha256=digest(Path(record['journal']['path']))); save()
                caller['contracts'] = verify(raw,nonce,uid,role); verify_presentations(caller['phases'],nonce,role)
                caller['status'] = 'pass'; save()
            except Exception as error:
                caller.update(status='fail',error=str(error)); save()
                from probe_failure_snapshot import capture as failure_snapshot
                caller['failure_snapshot']=failure_snapshot(shell,BUNDLE,'actual-selection-'+role+'-failure')
                if remote is not None:
                    try:
                        failed_raw=shell('cat '+remote,'actual-selection-'+role+'-failure-native-journal',True)
                        failed_path=root/'failure-native-journal.log';failed_path.write_text(failed_raw)
                        caller['failure_native_journal']=file_record(failed_path)
                    except Exception as capture_error:
                        caller['failure_snapshot']['journal_capture_error']=str(capture_error)
                save(); raise
            finally:
                try:
                    shell('aa force-stop '+BUNDLE,role+'-stop-owned-selection-caller')
                    if shell('pidof '+BUNDLE+' || true',role+'-cleanup-name-absence').strip(): raise ValueError('selection caller remains running')
                    if pid is None: raise ValueError('actual selection caller PID was never obtained')
                    shell('test ! -e /proc/'+str(pid),role+'-cleanup-actual-pid-absence')
                    caller.update(caller_cleanup_verified=True,cleanup=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True))
                except Exception as cleanup_error:
                    caller.update(status='fail',cleanup_error=str(cleanup_error))
                    report['failures'].append(role+' cleanup: '+str(cleanup_error))
                    if 'error' not in caller: raise
                save()
        same_boot('boot-final'); report.update(status='pass',contracts=list(CONTRACTS),caller_cleanup_verified=True); save()
        from verify_selection_evidence import verify_evidence
        report['verified_contracts'] = verify_evidence(report,report['archive_sha256'],args.boot_id,args.arch,args.device,args.target)
    except Exception as error:
        report['status']='fail'; report['failures'].append(str(error))
        try: shell('hilog -x','actual-selection-failure-hilog')
        except Exception as capture_error: report['failures'].append('hilog: '+str(capture_error))
    save()
    print(json.dumps(dict(status=report['status'],failures=report['failures'],evidence=str(output/'evidence.json'))))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive','sdk','output','hdc','hvigor-home','node-home'): parser.add_argument('--'+name,type=Path,required=True)
    for name in ('arch','device','target','udid','boot-id'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--source-volume',default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image',default='ohos-qemu-m144-build-env:7.0-release')
    raise SystemExit(run(parser.parse_args()))
