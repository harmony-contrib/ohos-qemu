#!/usr/bin/env python3
"""Exercise the real typed lazy waterflow/dynamic callers on the enclosing packaged guest."""
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
from build_arkui_lazy_layouts_probe import BUNDLE, SCOPE, verify_inputs
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady
from insight_contract_common import file_record, identity
from lazy_layouts_runtime import capture
from run_root_probe import digest
from verify_lazy_layouts_results import rows, verify, verify_presentations

ROOT=Path(__file__).resolve().parents[2]


def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    report=dict(status='fail',scope=SCOPE,first_artifact_behavior_gate_passed=False,
        archive=str(args.archive.resolve()),archive_sha256=digest(args.archive),boot_id=args.boot_id,
        arch=args.arch,device=args.device,target=args.target,udid=args.udid,run_id=secrets.token_hex(16),
        phases={},commands=[],failures=[],caller_cleanup_verified=False)
    hdc=str(args.hdc);pid=None
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
                row.update(timed_out=True,sha256=digest(log));save();raise ValueError('lazy command timed out: '+label)
        row.update(exit_code=code,sha256=digest(log),finished_monotonic=time.monotonic());save();text=log.read_text().replace('\r','')
        if not allow_failure and (code or re.search(r'\[Fail\]|Device not found or connected',text)):
            raise ValueError('lazy command failed: '+label)
        return text
    def shell(script,label,allow_failure=False):
        marker='__LAZY_SHELL_EXIT_'+secrets.token_hex(16)+'__='
        reply=command([hdc,'-t',args.target,'shell',script+'; task_lazy_rc=$?; printf "\\n'+marker+'%s\\n" "$task_lazy_rc"'],label,allow_failure=allow_failure)
        match=re.search(r'(?:^|\n)'+re.escape(marker)+r'(\d+)\s*$',reply)
        if not match or (not allow_failure and match.group(1)!='0'):raise ValueError('actual lazy guest exit status lost: '+label)
        return reply[:match.start()]
    def same_boot(label):
        if shell('cat /proc/sys/kernel/random/boot_id',label).strip()!=args.boot_id:raise ValueError('lazy caller escaped enclosing boot')
    ui=GuestUi(command,hdc,args.target,output/'ui')
    def click(identifier,label):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:return ui.click(BUNDLE,identifier=identifier,label=label)
            except (LayoutNotReady,NodeNotReady):time.sleep(.25)
        raise ValueError('actual lazy control never attached: '+identifier)
    save()
    try:
        if shell('id -u; param get const.product.devicetype; uname -m','guest-identity').split()!=[
            '0',args.device,{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[args.arch]]:
            raise ValueError('lazy guest ABI/profile differs')
        same_boot('boot-before')
        project=output/'project';nonce=report['run_id']
        command([sys.executable,ROOT/'ci/capability-audit/build_arkui_lazy_layouts_probe.py',
            '--sdk',args.sdk,'--output',project,'--arch',args.arch,'--run-id',nonce,
            '--hvigor-home',args.hvigor_home,'--node-home',args.node_home],'build-real-lazy-caller',1800)
        inputs=project/'arkui-lazy-layouts-probe-inputs.json';verify_inputs(json.loads(inputs.read_text()))
        unsigned=project/'entry/build/default/outputs/default/entry-default-unsigned.hap';signed=output/'lazy-layouts-signed.hap'
        command(['docker','run','--rm','--platform','linux/amd64',
            '--mount','type=volume,src='+args.source_volume+',dst=/ohos,readonly',
            '--mount','type=bind,src='+str(ROOT)+',dst=/work,readonly',
            '--mount','type=bind,src='+str(output)+',dst=/probe',args.docker_image,
            'python3','/work/ci/capability-audit/sign_ethernet_control_probe.py',
            '--signer-dist','/ohos/developtools/hapsigner/dist',
            '--jar','/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
            '--unsigned','/probe/'+unsigned.relative_to(output).as_posix(),'--output','/probe/'+signed.name,
            '--role','normal','--udid',args.udid],'sign-real-lazy-caller',300)
        command([hdc,'-t',args.target,'uninstall',BUNDLE],'remove-own-old-app',allow_failure=True)
        command([hdc,'-t',args.target,'install',signed],'install-real-lazy-caller')
        text=shell('bm dump -n '+BUNDLE,'actual-lazy-BMS');identity_path=output/'application-identity.json';identity_path.write_text(text)
        uid=identity(text,BUNDLE,'normal')
        report['application']=dict(inputs=file_record(inputs),project=str(project),unsigned_hap=file_record(unsigned),
            signed_hap=file_record(signed),signing_receipt=file_record(signed.with_suffix('.signing.json')),
            application_identity=file_record(identity_path),actual_uid=uid)
        shell('aa start -a EntryAbility -b '+BUNDLE,'start-real-lazy-caller')
        remote='/data/app/el2/100/base/'+BUNDLE+'/files/arkui-lazy-layouts-'+nonce+'-results.log'
        def journal(label):return shell('cat '+remote,label)
        for kind in ('water','dynamic'):
          for cycle in (0,1):
            report['phases'][kind+':'+str(cycle)+':initial']=dict(click=click('lazy-layouts-'+kind,'lazy-create-'+kind+'-'+str(cycle)))
            for phase,control in (('initial',None),('changed','lazy-layouts-change'),('bottom','lazy-layouts-last'),('top','lazy-layouts-first'),('removed','lazy-layouts-remove')):
                key=kind+':'+str(cycle)+':'+phase;record=report['phases'].setdefault(key,{})
                if control:record['click']=click(control,'lazy-'+key.replace(':','-'))
                record['presentation']=capture(ui,output/('presentation-'+key.replace(':','-')+'.json'),nonce,kind,cycle,phase)
                raw=journal('lazy-journal-'+key.replace(':','-'));path=output/('journal-'+key.replace(':','-')+'.log');path.write_text(raw)
                observed=rows(raw,nonce,uid);pid=observed[0]['values'][2]
                record['journal']=file_record(path);save()
                if phase=='removed':
                    quiet_start=time.monotonic();time.sleep(2)
                    quiet=journal('lazy-quiet-'+kind+'-'+str(cycle))
                    if quiet!=raw:raise ValueError('removed lazy layout emitted a late callback')
                    record['quiet_seconds']=time.monotonic()-quiet_start;record['quiet_journal_sha256']=digest(path);save()
        report['contracts']=verify(raw,nonce,uid);verify_presentations(report['phases'],nonce)
        same_boot('boot-final');report['status']='pass';save()
    except Exception as error:
        report['failures'].append(str(error));save()
        try:shell('hilog -x','actual-lazy-failure-hilog')
        except Exception as capture_error:report['failures'].append('hilog: '+str(capture_error))
    finally:
        try:
            shell('aa force-stop '+BUNDLE,'stop-owned-lazy-caller')
            script='pidof '+BUNDLE+' || true'
            if shell(script,'cleanup-name-absence').strip():raise ValueError('lazy caller process remains')
            if pid is not None:
                shell('test ! -e /proc/'+str(pid),'cleanup-actual-pid-absence')
                report['cleanup']=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True)
                report['caller_cleanup_verified']=True
            else:raise ValueError('actual running lazy caller PID was never obtained')
        except Exception as error:report['status']='fail';report['failures'].append('cleanup: '+str(error))
        if report['status']=='pass':
            try:
                from verify_lazy_layouts_evidence import verify_evidence
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
