"""Fresh owned package proof of actual HUKS compatibility permissions."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import uuid

from boot_package import FATAL
from run_root_probe import digest, validate_identity
from verify_huks_compatibility_results import BINARY, CFG, SCOPE, image_and_boot, remote_output, verify


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    report={'status':'fail','persona':'huks-compatibility','scope':SCOPE,
        'first_artifact_behavior_gate_passed':False,'commands':[],'failures':[],
        'observations':{},'not_claimed':['legacy encrypted key conversion','TEE or OEM attestation']}
    created=False
    env=None
    run_id=uuid.uuid4().hex
    remote='/data/data/huks_service/.qemu-compatibility-'+run_id
    serial=None

    def command(argv,label,timeout=60):
        argv=list(map(str,argv))
        path=args.output/(str(len(report['commands'])).zfill(3)+'-'+label+'.log')
        row={'argv':argv,'log':str(path),'exit_code':None}
        report['commands'].append(row)
        with path.open('x') as stream:
            process=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,start_new_session=True)
            try: process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                row['timed_out']=True
        row.update(exit_code=process.returncode,sha256=digest(path))
        text=path.read_text(errors='replace').replace('\r','')
        if process.returncode or row.get('timed_out') or '[Fail]' in text or 'Device not found or connected' in text:
            raise ValueError('owned HUKS probe operation failed: '+label)
        return text

    def shell(script,label):
        nonce=run_id+'_'+str(len(report['commands']))
        wrapped='( '+script+' ); result=$?; printf "\\n__HUKS_EXIT_'+nonce+'=%s\\n" "$result"'
        text=command([args.hdc,'-t',env['target'],'shell',wrapped],label)
        report['commands'][-1]['remote_exit_nonce']=nonce
        return remote_output(text,nonce)

    def same_boot(label):
        value=command(['ps','-p',env['qemu_pid'],'-o','command='],label+'-process').strip()
        if value!=env['qemu_command'] or env['qmp_socket'] not in value:
            raise ValueError('HUKS probe no longer owns this exact VM')
        validate_identity(shell('id -u; param get const.product.devicetype; uname -m',label+'-identity'),
                          env['guest_arch'],env['device_type'])
        if shell('cat /proc/sys/kernel/random/boot_id',label+'-boot-id').strip()!=env['boot_id']:
            raise ValueError('HUKS probe kernel boot changed')
        if FATAL.search(serial.read_text(errors='replace')):
            raise ValueError('owned guest has a fatal service/kernel failure')

    def observation(name,script):
        report['observations'][name]=shell(script,name).strip()
        entry=report['commands'][-1]
        report.setdefault('observation_files',{})[name]={'file':entry['log'],'sha256':entry['sha256'],
            'remote_exit_nonce':entry['remote_exit_nonce']}

    def cleanup():
        nonlocal created
        same_boot('cleanup')
        # Remove only our fresh exclusive nonce fixture, not a keystore root
        # or any unknown legacy key. Unexpected data or links stop cleanup.
        shell('set -eu; test -d '+remote+'; test ! -L '+remote+
            '; test ! -L '+remote+'/legacy-key; if test -e '+remote+'/legacy-key; then '
            'test "$(cat '+remote+'/legacy-key)" = '+run_id+'; rm '+remote+'/legacy-key; fi; '
            'rmdir '+remote,'remove-only-owned-nonce-fixture')
        created=False
        observation('fixture_cleaned','test ! -e '+remote+' && printf absent')

    try:
        boot=json.loads(args.boot.read_text())
        env=boot['test_environment']
        image=args.boot.parent/'extract'/args.archive.name.removesuffix('.tar.gz')/'images/system.img'
        serial=args.boot.parent/'qemu.log'
        archive_sha=digest(args.archive)
        image_sha=digest(image)
        if (boot.get('status')!='pass' or boot.get('purpose')!='acceptance' or
            boot.get('archive_sha256')!=archive_sha or env.get('external_keepalive') is not False or
            env.get('freshly_extracted_directory')!=str(image.parent.parent) or
            image.is_symlink() or image_sha!=boot.get('initial_package_file_sha256',{}).get('images/system.img') or
            not serial.is_file() or serial.is_symlink() or type(env.get('qemu_pid')) is not int or
            env['qemu_pid']<=1 or not env.get('qemu_command') or
            not Path(env.get('qmp_socket','')).is_absolute()):
            raise ValueError('requires unchanged new package image and actual acceptance boot')
        report.update(archive_sha256=archive_sha,system_image=str(image),system_image_sha256=image_sha,
            boot_id=env['boot_id'],run_id=run_id,owned_fixture=remote,
            verifier_sha256=digest(Path(__file__).with_name('verify_huks_compatibility_results.py')))
        same_boot('before')
        files={}
        for name,operation in ((BINARY,'stat'),(CFG,'cat'),('/etc/passwd','cat'),('/etc/group','cat')):
            result=subprocess.run(['docker','run','--rm','--platform','linux/amd64',
                '--mount','type=bind,src='+str(image.parent)+',dst=/pkg,readonly',
                '--entrypoint','debugfs',args.docker_image,'-R',operation+' '+name,'/pkg/system.img'],
                capture_output=True,text=True,timeout=120)
            if result.returncode or result.stderr.strip()!='debugfs 1.46.5 (30-Dec-2021)':
                raise ValueError('could not read exact packaged HUKS contract: '+name)
            path=args.output/('image'+name.replace('/','-')+'.txt')
            path.write_text(result.stdout)
            report.setdefault('image_contract_files',{})[name]={'file':str(path),'sha256':digest(path)}
            files[name]=result.stdout
        captured=args.output/'serial.log';captured.write_bytes(serial.read_bytes())
        report.update(serial=str(captured),serial_sha256=digest(captured))
        image_and_boot(files[BINARY],files[CFG],files['/etc/passwd'],files['/etc/group'],
                       captured.read_text(errors='replace'))
        stat="stat -c '%u:%g:%a:%F' "
        observation('base_before',stat+'/data/data/huks_service')
        shell('set -eu; umask 077; test ! -e '+remote+'; test ! -L '+remote+'; mkdir '+remote,
              'create-exclusive-owned-directory')
        created=True
        shell('set -eu; printf %s '+run_id+' > '+remote+'/legacy-key; chmod 755 '+remote+
              '; chmod 644 '+remote+'/legacy-key','populate-owned-legacy-fixture')
        for name,path in (('before_directory',remote),('before_file',remote+'/legacy-key')):
            observation(name,stat+path)
        observation('payload_before','cat '+remote+'/legacy-key')
        observation('helper',BINARY)
        for name,path in (('after_directory',remote),('after_file',remote+'/legacy-key'),
                          ('base_after','/data/data/huks_service')):
            observation(name,stat+path)
        observation('payload_after','cat '+remote+'/legacy-key')
        cleanup()
        report['result']=verify(files[BINARY],files[CFG],files['/etc/passwd'],files['/etc/group'],
            captured.read_text(errors='replace'),report['observations'],run_id)
        same_boot('after')
        if digest(image)!=image_sha or digest(args.archive)!=archive_sha:
            raise ValueError('archive or image changed during HUKS migration probe')
        report['status']='pass'
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        if created and env is not None:
            try: cleanup()
            except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
                report['status']='fail';report['failures'].append('owned fixture cleanup failed: '+str(error))
        (args.output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--boot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--hdc',default='hdc')
    parser.add_argument('--docker-image',default='ohos-qemu-m144-build-env:7.0-release')
    report=run(parser.parse_args())
    print(json.dumps({key:report[key] for key in ('status','scope','failures')}))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
