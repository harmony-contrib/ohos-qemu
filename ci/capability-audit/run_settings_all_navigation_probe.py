#!/usr/bin/env python3
"""Exercise the real typed Settings caller on the enclosing packaged guest."""
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
from build_settings_all_navigation_probe import BUNDLE, SCOPE, CONTRACTS, verify_inputs
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady
from insight_contract_common import file_record, identity
from settings_all_navigation_runtime import capture
from run_root_probe import digest
from verify_settings_all_navigation_results import verify_rows, supported_routes, ROUTES

ROOT=Path(__file__).resolve().parents[2]


def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    report=dict(status='fail',scope=SCOPE,first_artifact_behavior_gate_passed=False,
        archive=str(args.archive.resolve()),archive_sha256=digest(args.archive),boot_id=args.boot_id,
        arch=args.arch,device=args.device,target=args.target,udid=args.udid,run_id=secrets.token_hex(16),
        phases={},commands=[],failures=[],caller_cleanup_verified=False,hdc=file_record(args.hdc))
    hdc=str(args.hdc);pid=None;remote=None
    def save():(output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    def command(argv,label,timeout=90,allow_failure=False):
        argv=list(map(str,argv));log=output/(str(len(report['commands'])).zfill(3)+'-'+label+'.log')
        row=dict(argv=argv,log=str(log),exit_code=None,started_monotonic=time.monotonic());report['commands'].append(row);save()
        with log.open('xb') as stream:
            child=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            try:code=child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                row.update(timed_out=True,sha256=digest(log));save();raise ValueError('settings_all command timed out: '+label)
        row.update(exit_code=code,sha256=digest(log),finished_monotonic=time.monotonic());save();text=log.read_text().replace('\r','')
        if not allow_failure and (code or re.search(r'\[Fail\]|Device not found or connected',text)):
            raise ValueError('settings_all command failed: '+label)
        return text
    def shell(script,label,allow_failure=False):
        marker='__SETTINGS_ALL_SHELL_EXIT_'+secrets.token_hex(16)+'__='
        reply=command([hdc,'-t',args.target,'shell',script+'; task_settings_all_rc=$?; printf "\\n'+marker+'%s\\n" "$task_settings_all_rc"'],label,allow_failure=allow_failure)
        match=re.search(r'(?:^|\n)'+re.escape(marker)+r'(\d+)\s*$',reply)
        if not match or (not allow_failure and match.group(1)!='0'):raise ValueError('actual settings_all guest exit status lost: '+label)
        return reply[:match.start()]
    def same_boot(label):
        if shell('cat /proc/sys/kernel/random/boot_id',label).strip()!=args.boot_id:raise ValueError('settings_all caller escaped enclosing boot')
    ui=GuestUi(command,hdc,args.target,output/'ui')
    def click(identifier,label):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:return ui.click(BUNDLE,identifier=identifier,label=label)
            except (LayoutNotReady,NodeNotReady):time.sleep(.25)
        raise ValueError('actual settings_all control never attached: '+identifier)
    save()
    try:
        if shell('id -u; param get const.product.devicetype; uname -m','guest-identity').split()!=[
            '0',args.device,{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[args.arch]]:
            raise ValueError('settings_all guest ABI/profile differs')
        same_boot('boot-before')
        project=output/'project';nonce=report['run_id']
        command([sys.executable,ROOT/'ci/capability-audit/build_settings_all_navigation_probe.py',
            '--sdk',args.sdk,'--output',project,'--arch',args.arch,'--run-id',nonce,
            '--hvigor-home',args.hvigor_home,'--node-home',args.node_home],'build-real-settings_all-caller',1800)
        inputs=project/'settings-all-navigation-probe-inputs.json';verify_inputs(json.loads(inputs.read_text()))
        unsigned=project/'entry/build/default/outputs/default/entry-default-unsigned.hap';signed=output/'settings-all-signed.hap'
        command(['docker','run','--rm','--platform','linux/amd64',
            '--mount','type=volume,src='+args.source_volume+',dst=/ohos,readonly',
            '--mount','type=bind,src='+str(ROOT)+',dst=/work,readonly',
            '--mount','type=bind,src='+str(output)+',dst=/probe',args.docker_image,
            'python3','/work/ci/capability-audit/sign_ethernet_control_probe.py',
            '--signer-dist','/ohos/developtools/hapsigner/dist',
            '--jar','/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
            '--unsigned','/probe/'+unsigned.relative_to(output).as_posix(),'--output','/probe/'+signed.name,
            '--role','normal','--udid',args.udid],'sign-real-settings_all-caller',300)
        from run_normal_hap_probe import stop_previous_probe
        report['previous_caller_cleanup']=stop_previous_probe(lambda value,label,accepted_failure=False:shell(value,label,accepted_failure))
        command([hdc,'-t',args.target,'uninstall',BUNDLE],'remove-own-old-app',allow_failure=True)
        command([hdc,'-t',args.target,'install',signed],'install-real-settings_all-caller')
        text=shell('bm dump -n '+BUNDLE,'actual-settings_all-BMS');identity_path=output/'application-identity.json';identity_path.write_text(text)
        uid=identity(text,BUNDLE,'normal')
        report['application']=dict(inputs=file_record(inputs),project=str(project),unsigned_hap=file_record(unsigned),
            signed_hap=file_record(signed),signing_receipt=file_record(signed.with_suffix('.signing.json')),
            application_identity=file_record(identity_path),actual_uid=uid)
        remote='/data/app/el2/100/base/'+BUNDLE+'/files/settings-navigation-'+nonce+'-results.log'
        shell('test ! -e '+remote,'fresh-journal-absence')
        shell('aa start -a EntryAbility -b '+BUNDLE,'start-real-settings_all-caller')
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            actual=shell('pidof '+BUNDLE+' || true','running-pid-'+str(len(report['commands']))).strip()
            if re.fullmatch('[1-9][0-9]*',actual):pid=int(actual);break
            time.sleep(.25)
        if pid is None:raise ValueError('actual Settings process never started')
        remote='/data/app/el2/100/base/'+BUNDLE+'/files/settings-navigation-'+nonce+'-results.log'
        def journal(label):return shell('cat '+remote,label,True)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            raw=journal('startup-journal-'+str(len(report['commands'])))
            if '"name":"ready"' in raw:break
            time.sleep(.25)
        else:raise ValueError('actual Settings startup journal never completed')
        raw=journal('startup-final-journal')
        startup=verify_rows(raw,nonce,uid,pid,startup=True)
        startup_path=output/'startup-results.log';startup_path.write_text(raw)
        report['startup']=file_record(startup_path);methods=startup['methods']
        text=shell('bm dump -n com.ohos.settings','actual-settings-provider-BMS')
        settings_path=output/'settings-identity.json';settings_path.write_text(text)
        from verify_settings_navigation_results import settings_identity
        settings_uid=settings_identity(text);report['settings_identity']=file_record(settings_path)
        report['settings_uid']=settings_uid
        from verify_settings_all_navigation_results import PARAMETERS
        parameters={name:shell('param get '+name,'actual-parameter-'+name,True).strip() for name in PARAMETERS}
        support=supported_routes(args.device,parameters);report['parameters']=parameters;report['supported_routes']=support
        strings=json.loads((project/'AppScope/resources/base/element/string.json').read_text())['string']
        label=next(item['value'] for item in strings if item['name']=='app_name');report['app_label']=label
        report['phases']={};count=7
        for cycle in (1,2):
            for route in ROUTES:
                key=str(cycle)+':'+route;prefix='settings-all-'+str(cycle)+'-'+route
                action=dict(click('settings-probe-'+route,prefix),identifier='settings-probe-'+route,label=prefix)
                action['layout_sha256']=digest(Path(action['layout']))
                record={'action':action,'supported':support[route]};report['phases'][key]=record;save()
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    observed=journal(prefix+'-poll-'+str(len(report['commands'])))
                    parsed=[json.loads(line) for line in observed.splitlines() if line]
                    if len(parsed)>count:break
                    time.sleep(.25)
                else:raise ValueError('Settings public route never returned: '+route)
                expected='network.result' if route=='network' else route+'.request-returned'
                if len(parsed)!=count+1 or parsed[-1]['name']!=expected or parsed[-1]['pass'] is not True:
                    raise ValueError('Settings route failed/foreign/reordered: '+route)
                if not observed.startswith(raw):raise ValueError('Settings journal lost native append-only history')
                count+=1;raw=observed
                raw_path=output/('journal-'+key.replace(':','-')+'.log');raw_path.write_text(raw)
                record['journal']=file_record(raw_path);save()
                record['presentation']=capture(ui,shell,output/('presentation-'+key.replace(':','-')+'.json'),
                    prefix,route,support[route],nonce,methods,label,settings_uid,uid,pid)
                if support[route]:shell('uitest uiInput keyEvent Back',prefix+'-back')
                # UITest's existing public syntax is keyEvent Back through uiInput.
                record['returned']=capture(ui,shell,output/('returned-'+key.replace(':','-')+'.json'),
                    prefix+'-returned',route,False,nonce,methods,label,settings_uid,uid,pid)
                same_boot(prefix+'-same-boot');save()
        report['native_results']=verify_rows(raw,nonce,uid,pid)
        final_path=output/'actual-results.log';final_path.write_text(raw);report['actual_results']=file_record(final_path)
        quiet_start=time.monotonic();time.sleep(2)
        if journal('final-journal-quiet')!=raw:raise ValueError('Settings emitted late native callbacks')
        report['quiet_seconds']=time.monotonic()-quiet_start
        report['contracts']=CONTRACTS
        same_boot('boot-final');report['status']='pass';save()
    except Exception as error:
        report['failures'].append(str(error));save()
        from probe_failure_snapshot import capture as failure_snapshot
        report['failure_snapshot']=failure_snapshot(shell,BUNDLE,'actual-settings_all-failure');save()
        if remote is not None:
            try:
                failed_raw=shell('cat '+remote,'actual-settings_all-failure-native-journal',True)
                failed_path=output/'failure-native-journal.log';failed_path.write_text(failed_raw)
                report['failure_native_journal']=file_record(failed_path);save()
            except Exception as capture_error:
                report['failure_snapshot']['journal_capture_error']=str(capture_error);save()
        try:shell('hilog -x','actual-settings_all-failure-hilog')
        except Exception as capture_error:report['failures'].append('hilog: '+str(capture_error))
    finally:
        try:
            shell('aa force-stop '+BUNDLE,'stop-owned-settings_all-caller')
            script='pidof '+BUNDLE+' || true'
            if shell(script,'cleanup-name-absence').strip():raise ValueError('settings_all caller process remains')
            if pid is not None:
                shell('test ! -e /proc/'+str(pid),'cleanup-actual-pid-absence')
                report['cleanup']=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True)
                report['caller_cleanup_verified']=True
            else:raise ValueError('actual running settings_all caller PID was never obtained')
        except Exception as error:report['status']='fail';report['failures'].append('cleanup: '+str(error))
        if report['status']=='pass':
            try:
                from verify_settings_all_navigation_evidence import verify_evidence
                report['verified_contracts']=verify_evidence(report,report['archive_sha256'],args.boot_id,args.arch,args.device,args.target)
            except Exception as error:report['status']='fail';report['failures'].append('provenance: '+str(error))
        save()
    print(json.dumps(dict(status=report['status'],failures=report['failures'],evidence=str(output/'evidence.json'))))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','sdk','output','hdc','hvigor-home','node-home'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('arch','device','target','udid','boot-id'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--source-volume',default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image',default='ohos-qemu-m144-build-env:7.0-release')
    raise SystemExit(run(parser.parse_args()))
