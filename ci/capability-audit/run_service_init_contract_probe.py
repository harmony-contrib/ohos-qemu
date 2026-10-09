#!/usr/bin/env python3
"""Package image + owned guest init proof, not complete Fusion hardware support."""
import argparse
import json
import os
from pathlib import Path
import signal
import secrets
import subprocess
import time

from boot_package import FATAL
from run_root_probe import digest,validate_identity
from verify_service_init_contracts import FUSION,FUSION_CFG,I18N_CFG,I18N_DIRECTORIES,verify,verify_load_results,verify_fusion_execution

ROOT=Path(__file__).resolve().parents[2]

def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    report={'status':'fail','persona':'service-init-contracts','scope':'Fusion_init_accounts_and_I18n_init_paths_only',
        'first_artifact_behavior_gate_passed':False,'commands':[],'failures':[],
        'not_claimed':['Fusion ranging or peer transport','OEM customization update delivery',
                       'ordinary app permission grants']}
    def command(argv,label,timeout=60):
        argv=list(map(str,argv))
        path=args.output/(str(len(report['commands'])).zfill(3)+'-'+label+'.log')
        record={'argv':argv,'log':str(path),'exit_code':None}
        report['commands'].append(record)
        with path.open('x') as stream:
            process=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
                record['timed_out']=True
        record.update(exit_code=process.returncode,sha256=digest(path))
        value=path.read_text(errors='replace').replace('\r','')
        if process.returncode or record.get('timed_out') or '[Fail]' in value:
            raise ValueError('owned init probe command failed: '+label)
        return value
    try:
        boot=json.loads(args.boot.read_text())
        env=boot['test_environment']
        image=args.boot.parent/'extract'/args.archive.name.removesuffix('.tar.gz')/'images/system.img'
        serial=args.boot.parent/'qemu.log'
        archive_sha=digest(args.archive)
        image_sha=digest(image)
        if (boot.get('status')!='pass' or boot.get('purpose')!='acceptance' or
            boot.get('archive_sha256')!=archive_sha or env.get('external_keepalive') is not False or
            image.is_symlink() or image_sha!=boot.get('initial_package_file_sha256',{}).get('images/system.img') or
            not serial.is_file() or serial.is_symlink()):
            raise ValueError('requires unchanged new package image and actual acceptance boot')
        report.update(archive_sha256=archive_sha,system_image=str(image),system_image_sha256=image_sha,
            boot_id=env['boot_id'],verifier_sha256=digest(Path(__file__).with_name('verify_service_init_contracts.py')))
        def shell(script,label):
            return command([args.hdc,'-t',env['target'],'shell',script],label)
        def same_boot(label):
            current=command(['ps','-p',env['qemu_pid'],'-o','command='],label+'-process').strip()
            if current!=env['qemu_command'] or env['qmp_socket'] not in current:
                raise ValueError('init probe no longer owns this exact VM')
            validate_identity(shell('id -u; param get const.product.devicetype; uname -m',label+'-identity'),
                              env['guest_arch'],env['device_type'])
            if shell('cat /proc/sys/kernel/random/boot_id',label+'-boot-id').strip()!=env['boot_id']:
                raise ValueError('init probe kernel boot changed')
            if FATAL.search(serial.read_text(errors='replace')):
                raise ValueError('owned guest has a fatal service/kernel failure')
        def packaged(path):
            # stdout is the exact file; debugfs diagnostics go to stderr. Do
            # not mix its banner into account/JSON contents or ignore errors.
            result=subprocess.run(['docker','run','--rm','--platform','linux/amd64',
                '--mount','type=bind,src='+str(image.parent)+',dst=/pkg,readonly',
                '--entrypoint','debugfs',args.docker_image,'-R','cat '+path,'/pkg/system.img'],
                capture_output=True,text=True,timeout=120)
            if result.returncode or result.stderr.strip()!='debugfs 1.46.5 (30-Dec-2021)':
                raise ValueError('could not read exact packaged init contract: '+path)
            target=args.output/('image'+path.replace('/','-')+'.txt')
            target.write_text(result.stdout)
            report.setdefault('image_contract_files',{})[path]={'sha256':digest(target),'file':str(target)}
            return result.stdout
        same_boot('before')
        configs={path:packaged(path) for path in (*FUSION_CFG.values(),I18N_CFG)}
        passwd,group=packaged('/etc/passwd'),packaged('/etc/group')
        # Use the actual SAMGR API. Setting an Android-style "ctl.start"
        # parameter merely stores an inert value on this Release. A direct
        # sa_main invocation would bypass the init identity being verified.
        source_path='/Volumes/PSSD/qemu/openharmony'
        command(['docker','run','--rm','--platform','linux/amd64',
            '--mount','type=volume,src='+args.source_volume+',dst='+source_path+',readonly',
            '--mount','type=volume,src='+args.out_volume+',dst='+source_path+'/out,readonly',
            '--mount','type=bind,src='+str(ROOT)+',dst=/work,readonly',
            '--mount','type=bind,src='+str(args.output.resolve())+',dst=/probe',
            args.docker_image,'python3','/work/ci/capability-audit/build_service_load_probe.py',
            '--source-root',source_path,'--arch',env['guest_arch'],'--output','/probe/loader'],
            'build-actual-product-SAMGR-caller',timeout=300)
        binary=args.output/'loader/service-load'
        build_path=args.output/'loader/build.json'
        build=json.loads(build_path.read_text())
        if build.get('status')!='pass' or build.get('probe_sha256')!=digest(binary):
            raise ValueError('actual SAMGR caller build was not verified')
        remote='/data/local/tmp/qemu-fusion-service-load-'+secrets.token_hex(16)
        if shell('if test -e '+remote+'; then echo STALE; else echo ABSENT; fi','fresh-loader-path').strip()!='ABSENT':
            raise ValueError('stale guest loader path')
        command([args.hdc,'-t',env['target'],'file','send',binary,remote],'send-SAMGR-caller')
        shell('chmod 700 '+remote,'caller-mode')
        result=shell(remote+'; task_loader_rc=$?; printf "\\nLOAD_EXIT=%s\\n" "$task_loader_rc"',
                     'request-real-SAMGR-load')
        if not result.strip().endswith('LOAD_EXIT=0'):
            raise ValueError('actual SAMGR load failed; init/permission/service errors must be repaired')
        rows=verify_load_results(result)
        observation=report['commands'][-1]
        report['samgr_load']={'build':str(build_path),'build_sha256':digest(build_path),
            'binary':str(binary),'binary_sha256':digest(binary),'results':rows,
            'file':observation['log'],'sha256':observation['sha256']}
        deadline=time.monotonic()+30
        while True:
            publication_hilog=shell('hilog -x','actual-Fusion-publication-hilog')
            try:
                verify_fusion_execution(serial.read_text(errors='replace'),publication_hilog)
                break
            except ValueError:
                if time.monotonic()>=deadline:
                    raise ValueError('real Fusion init service did not publish from its actual init PID within deadline')
                time.sleep(0.2)
        hilog_path=args.output/'publication-hilog.log'
        hilog_path.write_text(publication_hilog)
        report.update(publication_hilog=str(hilog_path),publication_hilog_sha256=digest(hilog_path))
        paths=['/data/service/el1/public/'+name for name,_,_ in FUSION]+[
               ('/data/service/el1/public/i18n/'+leaf).rstrip('/') for leaf in I18N_DIRECTORIES]
        ownership={}
        report['ownership_files']={}
        for index,path in enumerate(paths):
            ownership[path]=shell("stat -c '%u:%g:%a:%F' "+path,'ownership-'+str(index)).strip()
            observation=report['commands'][-1]
            report['ownership_files'][path]={'file':observation['log'],'sha256':observation['sha256']}
        captured=args.output/'serial.log'
        captured.write_bytes(serial.read_bytes())
        report['result']=verify(passwd,group,configs,ownership,captured.read_text(errors='replace'),publication_hilog)
        report['serial_sha256']=digest(captured)
        report['serial']=str(captured)
        report['ownership']=ownership
        same_boot('after')
        if digest(image)!=image_sha or digest(args.archive)!=archive_sha:
            raise ValueError('archive/image changed while init probe ran')
        report['status']='pass'
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        (args.output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--boot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--hdc',default='hdc')
    parser.add_argument('--docker-image',default='ohos-qemu-m144-build-env:7.0-release')
    parser.add_argument('--source-volume',default=os.environ.get('DOCKER_SOURCE_VOLUME','ohos-qemu-7_0-release-source'))
    parser.add_argument('--out-volume',default=os.environ.get('DOCKER_OUT_VOLUME','ohos-qemu-7_0-release-out'))
    result=run(parser.parse_args())
    print(json.dumps({key:result[key] for key in ('status','scope','failures')}))
    return 0 if result['status']=='pass' else 1

if __name__=='__main__':
    raise SystemExit(main())
