#!/usr/bin/env python3
"""Exercise exact disabled-profile C/ArkTS boundaries on the enclosing packaged guest."""
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
from build_child_default_profile_probe import BUNDLE, SCOPE, CONTRACTS, verify_inputs
from insight_contract_common import file_record, identity
from run_root_probe import digest
from verify_child_default_profile_results import verify, PARAMETERS

ROOT=Path(__file__).resolve().parents[2]


def run(args):
    import sys
    fixed_additional_root = '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-identity-generated/source-whole579-next01/candidate/additional579'
    if fixed_additional_root not in sys.path: sys.path.insert(0, fixed_additional_root)
    from additional579_raw import module as admitted_additional_source
    enabled = admitted_additional_source('identity579_mandatory').run_enabled_if_available(args)
    if enabled is not None: return enabled
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
                row.update(timed_out=True,sha256=digest(log));save();raise ValueError('child_default command timed out: '+label)
        row.update(exit_code=code,sha256=digest(log),finished_monotonic=time.monotonic());save();text=log.read_text(errors='replace').replace('\r','')
        if not allow_failure and (code or re.search(r'\[Fail\]|Device not found or connected',text)):
            raise ValueError('child_default command failed: '+label)
        return text
    def shell(script,label,allow_failure=False):
        marker='__CHILD_DEFAULT_SHELL_EXIT_'+secrets.token_hex(16)+'__='
        reply=command([hdc,'-t',args.target,'shell',script+'; task_child_default_rc=$?; printf "\\n'+marker+'%s\\n" "$task_child_default_rc"'],label,allow_failure=allow_failure)
        match=re.search(r'(?:^|\n)'+re.escape(marker)+r'(\d+)\s*$',reply)
        if not match or (not allow_failure and match.group(1)!='0'):raise ValueError('actual child_default guest exit status lost: '+label)
        return reply[:match.start()]
    def same_boot(label):
        if shell('cat /proc/sys/kernel/random/boot_id',label).strip()!=args.boot_id:raise ValueError('child_default caller escaped enclosing boot')
    save()
    try:
        if shell('id -u; param get const.product.devicetype; uname -m','guest-identity').split()!=[
            '0',args.device,{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[args.arch]]:
            raise ValueError('child_default guest ABI/profile differs')
        same_boot('boot-before')
        project=output/'project';nonce=report['run_id']
        command([sys.executable,ROOT/'ci/capability-audit/build_child_default_profile_probe.py',
            '--sdk',args.sdk,'--output',project,'--arch',args.arch,'--run-id',nonce,
            '--hvigor-home',args.hvigor_home,'--node-home',args.node_home],'build-real-child_default-caller',1800)
        inputs=project/'child-default-profile-probe-inputs.json';verify_inputs(json.loads(inputs.read_text()))
        unsigned=project/'entry/build/default/outputs/default/entry-default-unsigned.hap';signed=output/'child-default-signed.hap'
        command(['docker','run','--rm','--platform','linux/amd64',
            '--mount','type=volume,src='+args.source_volume+',dst=/ohos,readonly',
            '--mount','type=bind,src='+str(ROOT)+',dst=/work,readonly',
            '--mount','type=bind,src='+str(output)+',dst=/probe',args.docker_image,
            'python3','/work/ci/capability-audit/sign_ethernet_control_probe.py',
            '--signer-dist','/ohos/developtools/hapsigner/dist',
            '--jar','/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
            '--unsigned','/probe/'+unsigned.relative_to(output).as_posix(),'--output','/probe/'+signed.name,
            '--role','normal','--udid',args.udid],'sign-real-child_default-caller',300)
        from run_normal_hap_probe import stop_previous_probe
        report['previous_caller_cleanup']=stop_previous_probe(lambda value,label,accepted_failure=False:shell(value,label,accepted_failure))
        command([hdc,'-t',args.target,'uninstall',BUNDLE],'remove-own-old-app',allow_failure=True)
        command([hdc,'-t',args.target,'install',signed],'install-real-child_default-caller')
        text=shell('bm dump -n '+BUNDLE,'actual-child_default-BMS');identity_path=output/'application-identity.json';identity_path.write_text(text)
        uid=identity(text,BUNDLE,'normal')
        report['application']=dict(inputs=file_record(inputs),project=str(project),unsigned_hap=file_record(unsigned),
            signed_hap=file_record(signed),signing_receipt=file_record(signed.with_suffix('.signing.json')),
            application_identity=file_record(identity_path),actual_uid=uid)
        remote='/data/app/el2/100/base/'+BUNDLE+'/files/child-profile-'+nonce+'-results.log'
        shell('test ! -e '+remote,'fresh-journal-absence')
        shell('aa start -a EntryAbility -b '+BUNDLE,'start-real-child_default-caller')
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            actual=shell('pidof '+BUNDLE+' || true','running-pid-'+str(len(report['commands']))).strip()
            if re.fullmatch('[1-9][0-9]*',actual):pid=int(actual);break
            time.sleep(.25)
        if pid is None:raise ValueError('actual Child profile process never started')
        remote='/data/app/el2/100/base/'+BUNDLE+'/files/child-profile-'+nonce+'-results.log'
        def journal(label):return shell('cat '+remote,label,True)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            raw=journal('startup-journal-'+str(len(report['commands'])))
            if '"name":"summary"' in raw:break
            time.sleep(.25)
        else:raise ValueError('actual Child profile startup journal never completed')
        raw=journal('startup-final-journal')
        actual_path=output/'actual-results.jsonl';actual_path.write_text(raw)
        report['actual_results']=file_record(actual_path)
        parameters={name:shell('param get '+name,'actual-parameter-'+name).strip() for name in PARAMETERS}
        report['parameters']=parameters
        report['peer_journals']={}
        for kind in ('native-peer','worker'):
            peer=remote.removesuffix('-results.log')+'-'+kind+'.log'
            text=shell('test ! -e '+peer,'peer-absence-'+kind)
            if text!='':raise ValueError('disabled profile produced an unexpected child journal')
            report['peer_journals'][kind]=dict(remote=peer,absent=True)
        quiet_start=time.monotonic();time.sleep(2)
        if journal('final-journal-quiet')!=raw:raise ValueError('child profile emitted late native callbacks')
        report['quiet_seconds']=time.monotonic()-quiet_start
        report['native_results']=verify(raw,nonce,uid,pid,parameters,args.device)
        report['contracts']=CONTRACTS
        same_boot('boot-final');report['status']='pass';save()
    except Exception as error:
        report['failures'].append(str(error));save()
        from probe_failure_snapshot import capture as failure_snapshot
        report['failure_snapshot']=failure_snapshot(shell,BUNDLE,'actual-child_default-failure');save()
        if remote is not None:
            try:
                failed_raw=shell('cat '+remote,'actual-child_default-failure-native-journal',True)
                failed_path=output/'failure-native-journal.log';failed_path.write_text(failed_raw)
                report['failure_native_journal']=file_record(failed_path);save()
            except Exception as capture_error:
                report['failure_snapshot']['journal_capture_error']=str(capture_error);save()
        try:shell('hilog -x','actual-child_default-failure-hilog')
        except Exception as capture_error:report['failures'].append('hilog: '+str(capture_error))
    finally:
        try:
            shell('aa force-stop '+BUNDLE,'stop-owned-child_default-caller')
            script='pidof '+BUNDLE+' || true'
            if shell(script,'cleanup-name-absence').strip():raise ValueError('child_default caller process remains')
            if pid is not None:
                shell('test ! -e /proc/'+str(pid),'cleanup-actual-pid-absence')
                report['cleanup']=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True)
                report['caller_cleanup_verified']=True
            else:raise ValueError('actual running child_default caller PID was never obtained')
        except Exception as error:report['status']='fail';report['failures'].append('cleanup: '+str(error))
        if report['status']=='pass':
            try:
                from verify_child_default_profile_evidence import verify_evidence
                report['verified_boundary']=verify_evidence(report,report['archive_sha256'],args.boot_id,args.arch,args.device,args.target)
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
