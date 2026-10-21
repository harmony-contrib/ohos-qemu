"""Exact real SDK/HAP/signature/permission replay inside the admitted actor."""
from pathlib import Path
from types import FunctionType
import json
import os
import re
import subprocess
import time
import zipfile

import batch_apps_contact_picker_coordinator as original
from capability578_callers import compiled_fields_match
from batch_system_calendar_runtime_binding import sdk_commands
from photos579_raw import need, checked, document, ref


def actor_command(actor, output):
    need(subprocess.Popen is actor.ProxyPopen and actor.STATE is not None,
        'signature/CMS replay requires original authenticated final actor')
    commands=[]
    def execute(argv,label):
        need(subprocess.Popen is actor.ProxyPopen and actor.STATE is not None,'actual actor proxy only')
        argv=list(map(str,argv))
        if argv[0]=='java': argv[0]=str(Path(os.environ['JAVA_HOME'])/'bin/java')
        completed=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
        prefix=output/('%04d_%s'%(len(commands),label))
        out,err=Path(str(prefix)+'.stdout'),Path(str(prefix)+'.stderr')
        out.write_text(completed.stdout);err.write_text(completed.stderr)
        commands.append(dict(argv=argv,exit_code=completed.returncode,stdout=ref(out),stderr=ref(err)))
        need(completed.returncode==0,'actual signature command failed: '+label)
        return completed.stdout+completed.stderr
    return execute,commands


def exact_profile(profile,bundle,permissions,udid,*,apl='normal',system_app=False):
    need(apl in ('normal','system_core') and system_app==(apl=='system_core'),'exact existing Photos role APL')
    info=profile['bundle-info'];validity=profile['validity'];now=int(time.time())
    need(profile['type']=='debug' and info['bundle-name']==bundle and info['apl']==apl and
        info['app-feature']==('hos_system_app' if system_app else 'hos_normal_app') and
        profile['debug-info']['device-ids']==[udid] and
        profile['acls']['allowed-acls']==permissions and
        profile['permissions']['restricted-permissions']==permissions and
        type(validity['not-before']) is int and type(validity['not-after']) is int and
        validity['not-before']<=now<validity['not-after'],'actual profile identity/ACL/UDID/validity')


def signed(caller,role,case,project,udid,output,command):
    namespace=dict(original.verify_signed_hap_artifacts.__globals__)
    namespace['verify_profile']=exact_profile
    # Original Java verify-app, leaf fingerprint, extracted CMS and verify-
    # profile checks are retained verbatim. Only the narrow profile contract
    # is the already-existing Photos system_core/declared ACL contract.
    verify=FunctionType(original.verify_signed_hap_artifacts.__code__,namespace,
        original.verify_signed_hap_artifacts.__name__,original.verify_signed_hap_artifacts.__defaults__,
        original.verify_signed_hap_artifacts.__closure__)
    verify.__kwdefaults__=original.verify_signed_hap_artifacts.__kwdefaults__
    sign_app=[row for row in caller['sign_commands'] if 'sign-app' in row['argv']]
    need(len(sign_app)==1,'actual original sign-app command')
    argv=sign_app[0]['argv'];dist=Path(argv[argv.index('-appCertFile')+1]).parent;jar=Path(argv[argv.index('-jar')+1])
    system=role in ('janitor','grant','denied')
    result=verify(checked(caller['signed']),project.bundle(case,role),project.original.permissions(case,role)
        if hasattr(project,'original') else project.permissions(case,role),udid,dist,jar,output,command,
        apl='system_core' if system else 'normal',system_app=system)
    need(result['verified_profile']==document(caller['verified_profile'])==document(caller['signing'])['verified_profile'],
        'actual embedded CMS/profile differs from retained producer')
    original.verify_signed_payload(checked(caller['unsigned']),checked(caller['signed']))
    need(caller['identity']['fingerprint']==original.APP_LEAF,'actual application release leaf')
    return result


def verify_callers(prepared, *, raw, case, project, sdk, udid, actor, output):
    need(set(prepared['callers'])==set(project.ROLES[case]),'exact actual caller roles')
    output.mkdir(exist_ok=False)
    command,commands=actor_command(actor,output)
    metadata=document(sdk['metadata']);device=document(sdk['device_2in1'])
    need(metadata['version']=='26.0.0.105' and 'SystemCapability.Ability.Form' in device['SysCaps'] and
        checked(sdk['device_2in1']).as_posix().endswith('/ets/api/device-define/2in1.json'),
        'actual SDK105 true2in1 profile')
    for artifact in sdk.values(): checked(artifact)
    results={}
    for role,caller in prepared['callers'].items():
        root=Path(caller['project']);manifest=document(ref(root/'capability578-source-inputs.json'))
        expected=project.source_files(case,prepared['run_id'],role,{'profile':'2in1','udid':udid})
        need(all(name in manifest and checked(manifest[name]).read_text()==text for name,text in expected.items()),
            'actual compiled role source differs')
        for name,artifact in manifest.items():
            need(checked(artifact)==root/name,'complete original source inventory')
        for prefix in ('AppScope','entry/src/main','hvigor'):
            for path in (root/prefix).rglob('*'):
                if path.is_file(): need(str(path.relative_to(root)) in manifest,'unlisted build input')
        properties=checked(manifest['local.properties']).read_text().splitlines()
        dirs=[line[8:] for line in properties if line.startswith('sdk.dir=')]
        need(len(dirs)==1 and Path(dirs[0]).resolve()==checked(sdk['metadata']).parents[2],
            'actual compile SDK directory differs from exact SDK105 source')
        with zipfile.ZipFile(checked(caller['signed'])) as hap:
            module=json.loads(hap.read('module.json'));need(hap.read('ets/modules.abc'),'actual compiled ABC')
        fields=project.module_fields(case,role,{'profile':'2in1','udid':udid})
        need(module['app']['bundleName']==project.bundle(case,role) and compiled_fields_match(module['module'],fields) and
            module['module']['deviceTypes']==['2in1'],'compiled actual role module/profile differs')
        build=caller['build_commands'];need(len(build)==2,'exact original SDK dependency/compile pair')
        args=build[0]['argv'];need(args[:3]==['/usr/bin/nice','-n','10'],'original bounded SDK launcher')
        tools={name:ref(path) for name,path in zip(('node','cpu_cap','ohpm'),(args[3],args[6],args[7]))}
        tools['hvigor']=ref(build[1]['argv'][7])
        expected_commands=sdk_commands(tools)
        for actual,(_,expected_argv) in zip(build,expected_commands):
            need(actual in raw.normal and actual['argv']==['/usr/bin/nice','-n','10',*expected_argv] and
                actual['exit_code']==0 and not actual['timed_out'],'actual original SDK recipe/receipt')
        need('BUILD SUCCESSFUL' in checked(build[1]['stdout']).read_text()+checked(build[1]['stderr']).read_text(),
            'actual successful compile output missing')
        for receipt in caller['sign_commands']+caller['verify_commands']:
            need(receipt in raw.normal and receipt['exit_code']==0 and not receipt['timed_out'],
                'actual original signer command absent/failed')
        results[role]=signed(caller,role,case,project,udid,output/role,command)
    return dict(roles=results,actual_crypto_commands=commands,sdk=sdk)
