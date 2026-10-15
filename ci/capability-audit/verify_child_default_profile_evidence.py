"""Bind exact disabled-profile C/ArkTS compilation, installation, native results and exit."""
import copy
import hashlib
import json
from pathlib import Path
import re
import zipfile
from child_native_payload import processed_payload, parameter_matches
from build_child_default_profile_probe import BUNDLE, SCOPE, CONTRACTS, verify_inputs, ABI
import math
from insight_contract_common import checked_file, identity
from run_root_probe import digest
from sign_ethernet_control_probe import configure_profile
from verify_child_default_profile_results import verify, PARAMETERS


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status')!='pass' or document.get('scope')!=SCOPE or document.get('failures')!=[] or
        document.get('archive_sha256')!=archive_sha or document.get('boot_id')!=boot_id or
        document.get('arch')!=arch or document.get('device')!=device or document.get('target')!=target or
        document.get('caller_cleanup_verified') is not True or document.get('contracts')!=CONTRACTS or
        re.fullmatch('[0-9a-fA-F]{64}',document.get('udid','')) is None):
        raise ValueError('complete typed Child profile proof on the exact packaged guest required')
    app=document['application'];paths={key:checked_file(app[key]) for key in
        ('inputs','signed_hap','unsigned_hap','signing_receipt','application_identity')}
    inputs=json.loads(paths['inputs'].read_text());verify_inputs(inputs)
    nonce=document['run_id']
    if inputs['run_id']!=nonce or inputs['arch']!=arch or inputs['project']!=app['project']:
        raise ValueError('child_default caller nonce/ABI/project differs')
    uid=identity(paths['application_identity'].read_text(),BUNDLE,'normal')
    if app['actual_uid']!=uid:raise ValueError('actual child_default BMS UID differs')
    signing=json.loads(paths['signing_receipt'].read_text())
    with zipfile.ZipFile(paths['unsigned_hap']) as unsigned,zipfile.ZipFile(paths['signed_hap']) as signed:
        if len(signed.namelist())!=len(set(signed.namelist())):raise ValueError('duplicate signed child_default HAP entries')
        # The pinned PageInfoGenerator adds the executable-page bitmap for code signing.
        if (set(signed.namelist())!=set(unsigned.namelist())|{'.pages.info'} or
            not signed.read('.pages.info') or len(signed.read('.pages.info'))%8!=0):
            raise ValueError('signed child_default HAP file set changed')
        for name in unsigned.namelist():
            if unsigned.read(name)!=signed.read(name):raise ValueError('signing changed the compiled child_default caller')
        compiled=json.loads(signed.read('module.json'));abc=signed.read('ets/modules.abc')
        if len(abc)<1000:raise ValueError('actual child_default compiled ABC missing')
        for library,key in (('libprofile.so','native_elf_sha256'),('libc++_shared.so','runtime_elf_sha256')):
            member='libs/'+ABI[arch][0]+'/'+library
            strip=Path(inputs['sdk'])/'native/llvm/bin/llvm-strip'
            source=Path(inputs['project'])/'entry/libs'/ABI[arch][0]/library
            actual=processed_payload(source,strip,inputs[key],inputs['compiler_sha256'][str(strip)])
            processed_key='processed_native_elf_sha256' if library=='libprofile.so' else 'processed_runtime_elf_sha256'
            if (hashlib.sha256(actual).hexdigest()!=inputs[processed_key] or signed.read(member)!=actual):
                raise ValueError('actual official SDK stripped child native payload differs: '+library)

    profile=signing.get('verified_profile',{})
    if (signing.get('status')!='pass' or signing.get('role')!='normal' or
        signing.get('scope')!='actual_signature_profile_and_codesign_NOT_guest' or
        signing.get('signed_sha256')!=digest(paths['signed_hap']) or
        signing.get('unsigned_sha256')!=digest(paths['unsigned_hap']) or
        compiled['module'].get('deviceTypes')!=['default'] or
        compiled['module'].get('requestPermissions')!=[] or
        inputs['runtime_elf_sha256']!=inputs['SDK_runtime_elf_sha256'] or
        configure_profile(copy.deepcopy(profile),'normal',document['udid'],compiled)!=profile):
        raise ValueError('exact ordinary device-bound child_default signature required')
    hdc=str(checked_file(document['hdc']));commands=[];previous_command_end=-math.inf
    for row in document.get('commands',[]):
        path=Path(row['log'])
        if (path.is_symlink() or digest(path)!=row['sha256'] or type(row['exit_code']) is not int or
            row.get('timed_out') or not isinstance(row.get('argv'),list) or
            any(type(arg) is not str for arg in row['argv']) or
            type(row.get('started_monotonic')) not in (int,float) or
            type(row.get('finished_monotonic')) not in (int,float) or
            not math.isfinite(row['started_monotonic']) or not math.isfinite(row['finished_monotonic']) or
            row.get('finished_monotonic',0)<row['started_monotonic'] or
            row['started_monotonic']<previous_command_end):
            raise ValueError('actual child_default command journal changed or malformed')
        commands.append((path.name.split('-',1)[1][:-4],row,path.read_text().replace('\r','')))
        previous_command_end=row['finished_monotonic']
    def one(label):
        matches=[(i,row,reply) for i,(name,row,reply) in enumerate(commands) if name==label]
        if len(matches)!=1 or matches[0][1]['exit_code']!=0:raise ValueError('one successful child_default command required: '+label)
        return matches[0]
    def shell(label,script,expected=None):
        index,row,reply=one(label);argv=row['argv']
        if (len(argv)!=5 or argv[:4]!=[hdc,'-t',target,'shell'] or
            not argv[4].startswith(script+'; task_child_default_rc=$?; printf "\\n__CHILD_DEFAULT_SHELL_EXIT_')):
            raise ValueError('actual child_default script/transport differs: '+label)
        match=re.search(r'(?:^|\n)__CHILD_DEFAULT_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
        actual=reply[:match.start()] if match else None
        if label.startswith('actual-parameter-'):
            correct=parameter_matches(actual,expected)
        else:
            correct=(actual is not None and actual.split()==expected.split()) if label=='guest-identity' else (actual is not None and (expected is None or actual==expected))
        if not match or not correct:raise ValueError('child_default observation lacks actual successful guest origin: '+label)
        return index,row
    _,build,build_log=one('build-real-child_default-caller')
    expected_args=['--sdk',inputs['sdk'],'--output',inputs['project'],'--arch',arch,'--run-id',nonce,
        '--hvigor-home',inputs['hvigor_home'],'--node-home',inputs['node_home']]
    if (build['argv'][1:]!=[str(Path(__file__).with_name('build_child_default_profile_probe.py')),*expected_args] or
        'CompileArkTS' not in build_log or 'BUILD SUCCESSFUL' not in build_log or '0 up-to-date' not in build_log):
        raise ValueError('fresh official checked child_default compilation required')
    sign_index,sign,sign_log=one('sign-real-child_default-caller');install_index,install,reply=one('install-real-child_default-caller')
    if (sign_index>=install_index or sign['argv'][:3]!=['docker','run','--rm'] or
        sign['argv'][-4:]!=['--role','normal','--udid',document['udid']] or
        install['argv'][1:]!=['-t',target,'install',str(paths['signed_hap'])] or
        not re.search('success',reply,re.I) or re.search('failed to install',reply,re.I)):
        raise ValueError('actual signed child_default installation required')
    if not all(marker in sign_log for marker in ('verify codesign success','Digest verify result: true',
        'verify-app success','verify permission sign success')):
        raise ValueError('actual child_default code signature, digest and permissions not verified')
    identity_index,_=shell('actual-child_default-BMS','bm dump -n '+BUNDLE,paths['application_identity'].read_text())
    if identity_index<=install_index:raise ValueError('child_default identity preceded installation')
    shell('guest-identity','id -u; param get const.product.devicetype; uname -m',
        '0\n'+device+'\n'+{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[arch]+'\n')
    boot_before,_=shell('boot-before','cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    boot_final,_=shell('boot-final','cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    pid=document['cleanup']['actual_pid']
    if type(pid) is not int or pid<=0:raise ValueError('actual Child profile PID required')
    remote='/data/app/el2/100/base/'+BUNDLE+'/files/child-profile-'+nonce+'-results.log'
    raw=checked_file(document['actual_results']).read_text()
    parameters=document['parameters']
    for parameter in PARAMETERS:
        shell('actual-parameter-'+parameter,'param get '+parameter,parameters[parameter]+'\n')
    actual=verify(raw,nonce,uid,pid,parameters,device)
    if actual!=document.get('native_results'):
        raise ValueError('actual C/ArkTS boundary summary differs from its guest journal')
    startup_index,_=shell('startup-final-journal','cat '+remote,raw)
    fresh_index,_=shell('fresh-journal-absence','test ! -e '+remote,'')
    start_index,_=shell('start-real-child_default-caller','aa start -a EntryAbility -b '+BUNDLE)
    if not boot_before<install_index<identity_index<fresh_index<start_index<startup_index:
        raise ValueError('actual child installation/freshness/startup order differs')
    running=[]
    for label,row,reply in commands:
        if label.startswith('running-pid-'):
            match=re.search(r'(?:^|\n)__CHILD_DEFAULT_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
            if match and reply[:match.start()].strip()==str(pid):
                index,_=shell(label,'pidof '+BUNDLE+' || true',reply[:match.start()]);running.append(index)
    if len(running)!=1 or not start_index<running[0]<startup_index:
        raise ValueError('actual child caller PID lacks started-process origin')
    previous=startup_index
    for kind in ('native-peer','worker'):
        peer=remote.removesuffix('-results.log')+'-'+kind+'.log'
        if document['peer_journals'].get(kind)!=dict(remote=peer,absent=True):
            raise ValueError('actual disabled-profile peer absence summary differs')
        index,_=shell('peer-absence-'+kind,'test ! -e '+peer,'')
        if index<=previous:raise ValueError('actual child journal absence was observed too early')
        previous=index
    quiet_index,quiet=shell('final-journal-quiet','cat '+remote,raw)
    if (type(document.get('quiet_seconds')) not in (int,float) or
        not math.isfinite(document['quiet_seconds']) or document['quiet_seconds']<2 or
        quiet['started_monotonic']-commands[previous][1]['finished_monotonic']<2):
        raise ValueError('actual child final quiet interval missing')
    if document['cleanup']!=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True):
        raise ValueError('actual child caller cleanup differs')
    stop_index,_=shell('stop-owned-child_default-caller','aa force-stop '+BUNDLE,'force stop process successfully.\n')
    name_index,_=shell('cleanup-name-absence','pidof '+BUNDLE+' || true','')
    absence_index,_=shell('cleanup-actual-pid-absence','test ! -e /proc/'+str(pid),'')
    if not quiet_index<boot_final<stop_index<name_index<absence_index:
        raise ValueError('actual child stop/exit provenance unordered')
    return actual
