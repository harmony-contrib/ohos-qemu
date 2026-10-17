#!/usr/bin/env python3
"""One command for real wallpaper callers/actions on the suite's existing guest.

Consumes precompiled SDK projects and product helper receipts. Never compiles,
boots a VM, grants permissions, writes media SQL or declares a package gate.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import tempfile
import tarfile
from types import SimpleNamespace
import zipfile

from batch_media_wallpaper_runtime import HERE, Runtime, record, sha, write_json, SEED, SETTINGS, PHOTOS
from batch_media_wallpaper_coordinator import Coordinator, QUERY, READ, validate_hap, adapt_sdk_build, ordered_actions, request_file, actual_query
from batch_media_wallpaper_artifacts import caller_sources, adapt_helpers, verify_helper_receipt, verify_runtime_guest_observation
import batch_media_wallpaper_native as native_binding
from batch_media_verify_wallpaper_runtime import (checked, check_challenge, verify, verify_token_observation,
    bms_identity, replay_observation)
from enclosing_acceptance_guest import EnclosingAcceptanceGuest, validate_binding
from guest_ui import GuestUi

sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from power_test_policy import power_timeout, verify_policy_states

SCOPE='real_Settings_wallpaper_wrapper_same_packaged_guest_NOT_full_package_gate'


def query_profile(profile,role,udid,module):
    if (role!='query' or re.fullmatch('[a-fA-F0-9]{64}',udid or '')is None or
            module['app'].get('bundleName')!=QUERY or
            [v.get('name')for v in module['module'].get('requestPermissions',[])]!=[READ]):
        raise ValueError('exact real read-only wallpaper query role required')
    profile['bundle-info'].update({'bundle-name':QUERY,'apl':'system_basic','app-feature':'hos_system_app'})
    profile['debug-info']['device-ids']=[udid]
    # availableLevel == system_basic: no ACL/provision exception is requested.
    profile['acls']['allowed-acls']=[];profile['permissions']['restricted-permissions']=[]
    return profile


def validate_plan(value):
    value=json.loads(json.dumps(value))
    value.setdefault('settings_main',{'bundle':SETTINGS,'identifier':'theme_settings'})
    value.setdefault('settings_navigation',[{'bundle':SETTINGS,'identifier':'theme_settings'}])
    required={'settings_main','settings_navigation','screens','settings_ability','photos_ability','photos_main'}
    if not required<=value.keys():raise ValueError('actual source/UI plan lacks main marker, ability or system viewport')
    def selector(item,owner=None):
        if (not isinstance(item,dict)or not set(item)<={'bundle','identifier','text'}or
                (('identifier'in item)==('text'in item))or
                any(not isinstance(v,str)or not 1<=len(v)<=256 for v in item.values())or
                owner and item.get('bundle',owner)!=owner):
            raise ValueError('one actual source selector required; no coordinates or success flags')
    selector(value['settings_main'],SETTINGS);selector(value['photos_main'],PHOTOS)
    for item in value['settings_navigation']:selector(item,SETTINGS)
    for kind in ('desktop','lock'):
        selector(value['screens'][kind])
        if value['screens'][kind].get('bundle')not in ('com.ohos.sceneboard','com.ohos.systemui','com.ohos.systemui.screenlock'):
            raise ValueError('real profile system-screen identity required')
    for key in ('photos_navigation','photo_browser_navigation','lock_navigation'):
        for item in value.get(key,[]):selector(item)
    for key in ('settings_ability','photos_ability'):
        if re.fullmatch(r'[a-zA-Z0-9_.]+',value[key]or '')is None:raise ValueError('actual BMS-declared ability required')
    return value


def declared_ability(dump,bundle,ability):
    value=json.loads(dump.removeprefix(bundle+':\n')); app=value['applicationInfo']
    if (app.get('name')or app.get('bundleName'))!=bundle:raise ValueError('wrong actual installed package')
    found=[]
    def walk(item):
        if isinstance(item,dict):
            for key,child in item.items():
                if key=='abilityInfos'and isinstance(child,list):found.extend(v.get('name')for v in child if isinstance(v,dict))
                else:walk(child)
        elif isinstance(item,list):
            for child in item:walk(child)
    walk(value)
    if ability not in found:raise ValueError('requested page ability absent from actual BMS declaration: '+bundle)
    return value


class Transport(Coordinator):
    """Own only command evidence; reuse actual transport/home, no fake UI state."""
    def __init__(self,args,plan):
        self.args=args;self.output=args.output/'transport';self.output.mkdir()
        self.guest=EnclosingAcceptanceGuest(args.boot,args.archive,args.hdc,self.output/'guest')
        self.boot_id=self.guest.env['boot_id'];self.deadline=None;self.plan=plan
        self.value={'commands':[],'power_keys':[]};self.ui=GuestUi(self.command,args.hdc,self.guest.target,self.output/'ui')


class OwnedPolicy:
    """Suspend only the parent's proven finite override, then restore exactly it."""
    def __init__(self,transport,owner,report):
        self.transport=transport;self.owner=owner;self.report=report;self.suspended=False;self.states={}
        self.restorable=False

    def read(self,label):
        raw=self.transport.shell('hidumper -s 3301 -a "-a"',label)
        self.states[label]={'state':power_timeout(raw),'raw':self.transport.text(raw,label),
            'command_index':len(self.transport.value['commands'])-1,
            'command':dict(self.transport.value['commands'][-1])}
        return self.states[label]['state']

    def same_boot(self,label):
        raw=self.transport.shell('cat /proc/sys/kernel/random/boot_id',label)
        proof={'raw':self.transport.text(raw,label),'command_index':len(self.transport.value['commands'])-1,
            'command':dict(self.transport.value['commands'][-1])}
        self.report.setdefault('boots',{})[label]=proof
        if raw.strip()!=self.transport.boot_id:raise ValueError('policy restoration belongs to another boot')

    def suspend(self,archive_sha,boot_id,boot_path):
        current=self.read('wrapper-policy-before')
        self.original=current
        if self.owner is None:
            if current['override_ms']is not None:raise ValueError('no parent ownership proof for existing PowerMgr override')
            self.restorable=True;self.report.update(mode='no_parent_override',states=self.states);return
        path=Path(self.owner).resolve();value=json.loads(path.read_text())
        setup=value['application_test_setup'];states=setup['policy_states']
        boot=value['checks']['boot']
        if (value.get('scope')!='new_packaged_qemu_behavior' or value['package']['sha256']!=archive_sha or
                boot['sha256']!=sha(boot['evidence'])or
                validate_binding(json.loads(Path(boot['evidence']).read_text()),archive_sha)!=
                    validate_binding(json.loads(Path(boot_path).read_text()),archive_sha)or
                json.loads(Path(boot['evidence']).read_text())['test_environment']['boot_id']!=boot_id or
                setup.get('method')!='existing_power-shell_development_override'or setup.get('restored')is not False):
            raise ValueError('same parent suite must prove ownership of this exact PowerMgr override')
        verify_policy_states(states['before'],states['setup'],states['before'])
        if current!=states['setup']:raise ValueError('parent override was replaced; refuse to clear another client')
        snapshot=self.transport.output/'parent-suite-owner-snapshot.json';snapshot.write_bytes(path.read_bytes())
        self.report.update(mode='temporarily_suspend_proven_parent_test_override_NOT_default_power_gate',
                           owner=record(snapshot),original_owner_path=str(path),states=self.states)
        self.restorable=True
        self.suspended=True  # Restore even if the command reply is lost.
        if self.transport.shell('power-shell timeout -r','pause-parent-owned-timeout').strip()!='Restore screen off time':
            raise ValueError('actual PowerMgr refused owned override pause')
        if self.read('wrapper-policy-paused')!=states['before']:raise ValueError('real original power policy not restored')

    def restore(self):
        self.same_boot('wrapper-policy-restore-before')
        self.report['account_before_restore']=self.transport.identity('wrapper-policy-account-before')
        navigation_error=None
        try:
            self.transport.home()  # Let the real lock consumer restore its own override.
        except (OSError,ValueError,KeyError,subprocess.SubprocessError)as error:
            navigation_error=type(error).__name__+': '+str(error)
            self.report['navigation_failure']=navigation_error
        # Still collect finite readbacks and recheck this boot before mutation.
        self.same_boot('wrapper-policy-after-navigation')
        self.report['account_after_navigation']=self.transport.identity('wrapper-policy-account-after')
        current=self.read('wrapper-policy-before-resume')
        target=dict(self.original,override_ms=None)if self.suspended else self.original
        if current!=target:raise ValueError('unknown nested power override remains; never clear it')
        if self.suspended:
            reply=self.transport.shell('power-shell timeout -o '+str(self.original['override_ms']),'resume-parent-owned-timeout')
            if reply.strip()!='Override screen off time to '+str(self.original['override_ms']):raise ValueError('parent timeout resume failed')
        if self.read('wrapper-policy-restored')!=self.original:raise ValueError('parent policy not restored exactly')
        self.report['restored']=True
        return navigation_error


def stop_child(process):
    if process.poll()is None:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()


def run_pair(runtime_argv,coordinator_argv,output,timeout):
    """Only the waiting coordinator drives UI; no parent HDC while children run."""
    rows=[];children=[];deadline=time.monotonic()+timeout
    try:
        for name,argv in [('runtime',runtime_argv),('coordinator',coordinator_argv)]:
            path=output/(name+'-process.log');stream=path.open('x')
            try:process=subprocess.Popen(list(map(str,argv)),stdout=stream,stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,start_new_session=True)
            finally:stream.close()
            children.append(process);rows.append({'label':name,'argv':list(map(str,argv)),'log':str(path),'exit_code':None})
            if name=='runtime':
                # Directory/receipt writer must exist before the consumer starts.
                end=min(deadline,time.monotonic()+30)
                while not (output/'runtime/runtime.json').is_file():
                    if process.poll()is not None or time.monotonic()>=end:raise ValueError('runtime did not start its real request writer')
                    time.sleep(.05)
        while any(p.poll()is None for p in children):
            if time.monotonic()>=deadline:raise ValueError('wallpaper pair exceeded original bounded deadline')
            if any(p.poll()not in (None,0)for p in children):raise ValueError('wallpaper child failed; cancel peer without ACK')
            time.sleep(.1)
        if any(p.returncode!=0 for p in children):raise ValueError('wallpaper child failed')
    finally:
        for process,row in zip(children,rows):
            stop_child(process);row.update(exit_code=process.returncode,sha256=sha(row['log']))
        write_json(output/'child-processes.json',rows)
    return rows


def sign_query(args):
    from sign_certificate_probe import sign
    sign(args,configure=query_profile)


def save_report(path,value):
    """The sole mutable wrapper journal; raw artifacts remain exclusive."""
    path=Path(path)
    if path.is_symlink()or path.exists()and (not path.is_file()or path.stat().st_nlink!=1):
        raise ValueError('owned single-link wrapper journal required')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def verify_guest_commands(commands,target):
    for row in commands:
        raw=checked({k:row[k]for k in ('path','sha256')}).read_text().replace('\r','');argv=row['argv']
        if row.get('exit_code')!=0 or row.get('timed_out'):raise ValueError('guest command failed/timed out')
        if len(argv)==3 and argv[1:]==['tconn',target]:continue
        if len(argv)<5 or argv[1:3]!=['-t',target]:raise ValueError('command escaped enclosing guest')
        if argv[3]=='shell':
            script=argv[4];markers=re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=',script)
            if len(markers)!=1 or raw.count(markers[0])!=1:raise ValueError('missing actual guest exit nonce')
            marker=markers[0]
            if raw.rstrip().endswith(marker+'0'):continue
            # Only GuestUi's exact documented window-enumeration transition.
            prefix=script.split('; task_ui_rc=$?; printf ',1)[0]
            parts=prefix.split(' && uitest dumpLayout -p ')
            transition=(len(parts)==2 and parts[0].startswith('test ! -e ')and parts[0].removeprefix('test ! -e ')==parts[1]and
                re.fullmatch(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.json',parts[1])is not None)
            if not (transition and raw.rstrip().endswith(marker+'1')and
                    raw.rsplit('\n'+marker,1)[0].strip()=='DumpLayout failed:Get window nodes failed'):
                raise ValueError('actual guest failure cannot be treated as a transition')
        elif argv[3]=='install':
            if not re.search('success',raw,re.I)or re.search('fail',raw,re.I):raise ValueError('actual coordinator install failed')
        elif argv[3]!='file':raise ValueError('unexpected guest operation')


def readonly_token_preflight_failure(coordinator, row, index, target):
    """Preserve one exact failed read-only token query; never forgive cleanup."""
    actions=coordinator.get('actions',[])
    if (len(actions)!=1 or actions[0].get('action')!=ordered_actions()[0] or
            'ack'in actions[0] or not coordinator.get('failures')or
            row.get('label')!='actual-token-query' or row.get('exit_code')!=0 or row.get('timed_out')):
        raise ValueError('failed operation is not the initial read-only token preflight')
    run,boot=coordinator['run_id'],coordinator['boot_id']
    request=request_file(checked(actions[0]['request']),run,boot,1)
    if request['details']!={'required_permission':'ohos.permission.SET_WALLPAPER'}:
        raise ValueError('unexpected initial preflight details')
    inputs=json.loads(checked(coordinator['inputs']).read_text());item=inputs['tools']['token']
    proof=verify_helper_receipt('token',checked(item['binary']),checked(item['source']),item['build_receipt'])
    if coordinator['helper_bindings']['token']['build']!=proof:
        raise ValueError('failed token query was not the exact product-bound read-only helper')
    argv=row['argv'];raw=checked({k:row[k]for k in ('path','sha256')}).read_text().replace('\r','')
    if len(argv)!=5 or argv[1:4]!=['-t',target,'shell'] or '[Fail]'in raw:
        raise ValueError('failed token observation has no exact guest transport')
    markers=re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=',argv[4])
    if len(markers)!=1 or raw.count(markers[0])!=1 or not raw.endswith('\n'+markers[0]+'1\n'):
        raise ValueError('failed token observation lacks its exact native exit1')
    for role,bundle in (('seed',SEED),('settings',SETTINGS)):
        baseline=coordinator['BMS_observations'][role]
        replay_observation(baseline,'bm dump -n '+bundle,target,commands=coordinator['commands'])
        uid,_=bms_identity(baseline['raw'],bundle,ordinary=role=='seed')
        script='unset LD_LIBRARY_PATH LD_PRELOAD; '+shlex.join([
            '/data/local/tmp/wallpaper-coordinator-'+run+'/token',run,str(uid),bundle,'ohos.permission.SET_WALLPAPER'])
        tail='; task_ui_rc=$?; printf "\\n'+markers[0]+'%s\\n" "$task_ui_rc"'
        if argv[4]==script+tail and baseline['command_index']<index:
            return {'command_index':index,'command':row,'inner_exit_code':1,
                    'classification':'preserved_original_readonly_token_preflight_failure_NOT_success'}
    raise ValueError('failed command was not the exact read-only helper arguments')


def asset_cleanup_proof(output):
    """Permit safe reuse after a pixel failure only with completed raw cleanup."""
    from batch_media_verify_wallpaper_runtime import stage_files, CFG
    runtime=json.loads((output/'runtime/runtime.json').read_text());coo=json.loads((output/'coordinator/coordinator.json').read_text())
    if len(coo.get('actions',[]))<3:
        if [a['action']for a in coo['actions']]!=ordered_actions()[:len(coo['actions'])]:raise ValueError('unexpected early actions')
        if any(a['action']not in ordered_actions()[:3]for a in runtime.get('actions',[])):
            raise ValueError('runtime progressed beyond unstarted import')
        if coo.get('ui_actions')or coo.get('queries')or runtime.get('stages'):
            raise ValueError('early preflight already drove media/UI observations')
        target=json.loads(checked(coo['boot']).read_text())['test_environment']['target']
        preserved=[]
        for index,command in enumerate(coo['commands']):
            try:verify_guest_commands([command],target)
            except ValueError:
                preserved.append(readonly_token_preflight_failure(coo,command,index,target))
        return {'runtime':record(output/'runtime/runtime.json'),'coordinator':record(output/'coordinator/coordinator.json'),
                'no_media_mutation_action_started':True,'preserved_readonly_preflight_failures':preserved}
    if len(coo.get('actions',[]))!=21 or [a['action']for a in coo['actions']]!=ordered_actions():
        raise ValueError('partial UI flow: created assets/default restoration cleanup unproven')
    for row in coo['actions'][-2:]:
        if 'ack'not in row:raise ValueError('cleanup action not completed')
        checked(row['ack'])
    uris=json.loads(checked(runtime['import_observation']).read_text())['uris']
    if [row['phase']for row in coo.get('queries',[])]!=['before','after']:raise ValueError('actual deletion queries incomplete')
    for row in coo['queries']:
        request=json.loads(checked(row['request']).read_text())
        actual_query(checked(row['raw']['file']).read_text(),coo['run_id'],request['nonce'],row['phase'],uris)
    restored=[s for s in runtime['stages']if s['name']=='lock-restore']
    if len(restored)!=1:raise ValueError('both real wallpaper targets not restored')
    files=stage_files(restored[0])
    if set(files)!={CFG}:raise ValueError('restore left owned user wallpaper resources')
    config=json.loads(files[CFG][0].read_text())
    if config.get('SystemResType')!=0 or config.get('LockScreenResType')!=0:raise ValueError('default wallpaper types not restored')
    private=[c for c in runtime['commands']if c['label']=='owned-private-inputs-absent']
    if len(private)!=1:raise ValueError('actual final private-input absence query missing')
    row=private[0];raw=checked({k:row[k]for k in ('path','sha256')}).read_text()
    markers=re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=',row['argv'][4])
    if row['exit_code']!=0 or len(markers)!=1 or not raw.rstrip().endswith(markers[0]+'0'):
        raise ValueError('actual private-input cleanup did not finish')
    return {'runtime':record(output/'runtime/runtime.json'),'coordinator':record(output/'coordinator/coordinator.json'),
            'active_assets_absent':5,'default_resources_restored':True,'private_inputs_absent':True}


def verify_evidence(evidence_path, archive_path, boot_path):
    """Recompute raw runtime, query, helper, policy and cryptographic evidence.

    No guest command is issued. Java/OpenSSL verify existing artifacts only;
    their temporary extraction files are not application/build output.
    """
    evidence_path=Path(evidence_path);value=json.loads(evidence_path.read_text());archive_sha=sha(archive_path)
    if (value.get('status')!='pass' or value.get('scope')!=SCOPE or
            value.get('archive_sha256')!=archive_sha or sha(checked(value['archive']))!=archive_sha or
            sha(checked(value['wrapper']))!=sha(Path(__file__))or value.get('failures')!=[]or
            value.get('cleanup_verified')is not True or value.get('enclosing_guest_preserved')is not True or
            value.get('cleanup_complete')is not True or value.get('cleanup_errors')!=[]or
            value.get('first_artifact_behavior_gate_passed')is not False or value.get('closed_requirement_ids')!=[]):
        raise ValueError('complete unchanged wallpaper wrapper evidence required')
    env=validate_binding(json.loads(checked(value['boot']).read_text()),archive_sha)
    current=validate_binding(json.loads(Path(boot_path).read_text()),archive_sha)
    if env!=current or any(value.get(k)!=env[e]for k,e in
            [('boot_id','boot_id'),('arch','guest_arch'),('device','device_type'),('udid','udid'),('target','target')]):
        raise ValueError('wallpaper wrapper escaped actual parent guest/environment')
    if sha(checked(value['native_verifier']))!=sha(Path(native_binding.__file__)):
        raise ValueError('native archive/mapping verifier implementation changed')
    native=json.loads(checked(value['native_archive']).read_text())
    with tempfile.TemporaryDirectory(prefix='wallpaper-current-archive-')as temporary:
        actual=native_binding.archive_native(archive_path,boot_path,Path(temporary).resolve()/'native')
    if actual!=native:raise ValueError('current archive/native GN/image proof differs')
    artifacts=json.loads(checked(value['artifacts']).read_text())
    if value.get('asset_cleanup')!=asset_cleanup_proof(evidence_path.parent):raise ValueError('raw asset/default cleanup differs')
    inputs=json.loads(checked(value['coordinator_inputs']).read_text())
    plan=validate_plan(json.loads(checked(value['ui_plan']).read_text()))
    if plan!=validate_plan(json.loads(checked(artifacts['ui_plan']).read_text())):raise ValueError('UI source plan differs')
    challenge=json.loads(checked(artifacts['challenge']).read_text());check_challenge(challenge)
    result=verify(checked(value['runtime']))
    if json.loads(checked(value['independent_verification']).read_text())!=result or result['boot_id']!=env['boot_id']:
        raise ValueError('independent runtime file/pixel verification differs')
    children=json.loads(checked(value['child_processes']).read_text())
    if children!=value['children']or [r['label']for r in children]!=['runtime','coordinator']:
        raise ValueError('both actual child process records required')
    for row in children:
        checked({'path':row['log'],'sha256':row['sha256']})
        if row['exit_code']!=0:raise ValueError('failed runtime/coordinator process')
    coo=json.loads(checked(value['coordinator']).read_text())
    verify_guest_commands(coo['commands'],env['target'])
    if (coo.get('status')!='completed_actions_NOT_runtime_acceptance' or coo.get('boot_id')!=env['boot_id']or
            coo.get('run_id')!=challenge['run_id']or coo.get('failures')!=[]or len(coo.get('actions',[]))!=21):
        raise ValueError('all real coordinator actions required')
    if not 2 <= len(coo.get('tokens',[])) <= 64:
        raise ValueError('actual indexed native token observations required')
    for token_record in coo['tokens']:
        token_proof=json.loads(checked(token_record).read_text());role=token_proof['role']
        bundle={'seed':SEED,'settings':SETTINGS,'query':QUERY}[role]
        if token_proof['helper']!=inputs['tools']['token']:
            raise ValueError('native token helper differs from product-bound coordinator input')
        verify_token_observation(token_record,run=challenge['run_id'],boot=env['boot_id'],
            target=env['target'],bundle=bundle,permission=READ if role=='query'else 'ohos.permission.SET_WALLPAPER',
            original_BMS=coo[role+'_BMS'],commands=coo['commands'])
    if inputs.get('native')!=value['native_archive']or inputs.get('renderer_provider_hap')!=value['renderer_provider']['hap']:
        raise ValueError('coordinator native/source HAP proof differs from independently re-read current archive')
    verify_native_runtime(value,coo,native,env)
    for i,row in enumerate(coo['actions'],1):
        path=checked(row['request'])
        if path.parent.resolve()!=(evidence_path.parent/'actions').resolve():raise ValueError('request outside owned action directory')
        request=request_file(path,challenge['run_id'],env['boot_id'],i);ack=checked(row['ack'])
        for key in ('power_before','power_after'):
            if row[key]['state']!=power_timeout(checked(row[key]['raw']).read_text()):raise ValueError('actual action power state differs')
        expected={k:request[k]for k in ('schema_version','run_id','boot_id','sequence','nonce','action')}
        if (row['sequence']!=i or row['action']!=ordered_actions()[i-1]or row['finished_ns']<row['began_ns']or
                ack!=path.with_name(path.name.replace('.request.json','.ack.json'))or
                ack.stat().st_mode&0o777!=0o600 or ack.stat().st_uid!=os.getuid()or ack.stat().st_nlink!=1 or
                json.loads(ack.read_text())!=expected):raise ValueError('actual action/atomic ACK ordering differs')
    for name in ('token','default'):
        item=inputs['tools'][name]
        proof=verify_helper_receipt(name,checked(item['binary']),checked(item['source']),item['build_receipt'])
        observed=coo['helper_bindings'][name]
        if observed['build']!=proof or len(observed['actual_guest_DSOs'])!=len(proof['product_DSOs']):raise ValueError('helper DSO evidence incomplete')
        for expected,actual in zip(proof['product_DSOs'],observed['actual_guest_DSOs']):
            if actual['soname']!=expected['soname']:raise ValueError('installed guest SONAME observation differs')
            verify_runtime_guest_observation(proof,expected['soname'],actual,coo['commands'],
                                             target=env['target'],archive_sha256=sha(archive_path))
    runtime=json.loads(checked(value['runtime']).read_text())
    uris=json.loads(checked(runtime['import_observation']).read_text())['uris']
    if [r['phase']for r in coo['queries']]!=['before','after']:raise ValueError('real positive and deletion query required')
    for query in coo['queries']:
        request=json.loads(checked(query['request']).read_text())
        raw=checked(query['raw']['file']).read_text()
        actual=actual_query(raw,challenge['run_id'],request['nonce'],request['phase'],uris)
        if json.loads(checked(query['normalized']).read_text())!=actual:raise ValueError('actual cursor query was normalized incorrectly')
    policy=value['power_policy'];states=policy['states']
    transport=json.loads(checked(value['transport']).read_text());verify_guest_commands(transport['commands'],env['target'])
    cleanup_rows=[row for row in transport['commands']if row['label']=='remove-only-owned-wallpaper-helpers']
    remote='/data/local/tmp/wallpaper-coordinator-'+challenge['run_id']
    if len(cleanup_rows)!=1 or remote not in cleanup_rows[0]['argv'][4]or 'rmdir '+remote not in cleanup_rows[0]['argv'][4]:
        raise ValueError('actual owned helper removal command missing')
    parsed={name:power_timeout(checked(row['raw']).read_text())for name,row in states.items()}
    for row in states.values():
        replay_observation(row,'hidumper -s 3301 -a "-a"',env['target'],commands=transport['commands'])
    for label in ('wrapper-policy-restore-before','wrapper-policy-after-navigation'):
        observed=policy['boots'][label]
        if replay_observation(observed,'cat /proc/sys/kernel/random/boot_id',env['target'],
                commands=transport['commands']).strip()!=env['boot_id']:
            raise ValueError('policy restoration raw boot changed')
    from account_state import parse_snapshot
    account_script='echo "bootevent.account.ready=$(param get bootevent.account.ready)"; hidumper -s AccountMgr -a "-os_account_infos"'
    for key,label in (('account_before_restore','wrapper-policy-account-before-account'),
                      ('account_after_navigation','wrapper-policy-account-after-account')):
        matches=[(i,row)for i,row in enumerate(transport['commands'])if row.get('label')==label]
        if len(matches)!=1:raise ValueError('one actual policy account observation required')
        index,command=matches[0]
        raw=replay_observation({'raw':policy[key],'command':command,'command_index':index},
            account_script,env['target'],commands=transport['commands'])
        if not all(parse_snapshot(raw).values()):raise ValueError('policy restoration left foreground account100')
    if any(parsed[k]!=row['state']for k,row in states.items())or policy.get('restored')is not True:raise ValueError('actual power readback proof missing')
    before=parsed['wrapper-policy-before'];restored=parsed['wrapper-policy-restored']
    if before!=restored:raise ValueError('parent policy not restored')
    if policy['mode']=='no_parent_override':
        if before['override_ms']is not None:raise ValueError('unowned override')
    elif policy['mode']=='temporarily_suspend_proven_parent_test_override_NOT_default_power_gate':
        owner=json.loads(checked(policy['owner']).read_text());owned=owner['application_test_setup']['policy_states']
        verify_policy_states(owned['before'],owned['setup'],owned['before'])
        if before!=owned['setup']or parsed['wrapper-policy-paused']!=owned['before']or parsed['wrapper-policy-before-resume']!=owned['before']:
            raise ValueError('proven owned override suspension/resume differs')
    else:raise ValueError('unknown power policy ownership mode')
    import batch_apps_contact_picker_coordinator as signatures
    if sha(checked(value['shared_signer']))!=sha(Path(signatures.__file__)):raise ValueError('actual common signer implementation changed')
    signer=artifacts['signer'];dist=Path(signer['dist']);jar=checked(signer['jar'])
    with tempfile.TemporaryDirectory(prefix='wallpaper-evidence-verify-')as temporary:
        def actual_command(argv,label):
            completed=subprocess.run(list(map(str,argv)),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90)
            if completed.returncode:raise ValueError('actual signature re-verification failed: '+label)
            return completed.stdout+completed.stderr
        provider=signatures.provider_from_image(boot_path,artifacts['provider'],Path(temporary)/'renderer-provider',dist,jar,
            actual_command,provider_name='theme',device=env['device_type'])
        verify_provider_proof(value['renderer_provider'],provider,native)
        for role,bundle,permissions in [('seed',SEED,[]),('query',QUERY,[READ])]:
            item=caller_sources(artifacts[role]);signed=checked(inputs[role]['signed_hap'])
            contract=Path(temporary)/('contract-'+role);contract.mkdir()
            actual_hap=validate_hap(inputs[role],role,challenge,env['udid'],contract)
            if role=='seed' and json.loads(checked(runtime['import_observation']).read_text()).get('app_label')!=actual_hap['app_label']:
                raise ValueError('Photos consent caller label differs from the actual SDK-bound label')
            proof=value[role+'_signing'];checked(proof['signature_verification']);checked(proof['decoded_profile'])
            signatures.verify_signed_payload(checked(item['unsigned_hap']), signed)
            actual=signatures.verify_signed_hap_artifacts(signed,bundle,permissions,env['udid'],dist,jar,Path(temporary)/role,
                actual_command,apl='normal'if role=='seed'else'system_basic',system_app=role=='query')
            if actual['verified_profile']!=proof['verified_profile']:raise ValueError('actual cryptographic profile replay differs')
    for command in value['commands']:
        raw=checked({k:command[k]for k in ('path','sha256')}).read_text()
        if command['exit_code']!=0 and not command['label'].startswith('remove-only-old-'):raise ValueError('failed actual wrapper command')
    cleanup=[c for c in value['commands']if c['label']=='uninstall-owned-wallpaper-observer']
    if len(cleanup)!=2 or any(not re.search('success',checked({k:c[k]for k in ('path','sha256')}).read_text(),re.I)for c in cleanup):
        raise ValueError('both owned observers must be actually removed')
    return {**result,'native_fallback_and_renderer_verified':True}


def verify_native_runtime(value,coordinator,native,env):
    """Independent composition; no claimed direct service-token/PID association."""
    import batch_apps_wallpaper_connection as connections
    if sha(checked(value['connection_verifier']))!=sha(Path(connections.__file__)):
        raise ValueError('actual AMS connection verifier changed')
    module='phone_wallpaper'if env['device_type']=='phone'else'pad_wallpaper'
    actual=connections.verify_runtime_connections(checked(value['runtime']),target=env['target'],module_name=module)
    if json.loads(checked(value['native_connections']).read_text())!=actual:
        raise ValueError('actual two public desktop stage AMS connection replay differs')
    mappings=native_binding.verify_mappings(coordinator,native,target=env['target'])
    if json.loads(checked(value['native_mappings']).read_text())!=mappings:
        raise ValueError('actual same-boot native mapping replay differs')
    haps=native_binding.verify_renderer_haps(coordinator,native,checked(value['renderer_provider']['hap']),target=env['target'])
    if any(hap['uid']!=stage['uid']for hap,stage in zip(haps,actual['stages'])):
        raise ValueError('actually installed renderer UID differs from actual AMS connected process')
    return {'connections':actual,'mappings':mappings,'installed_renderer_haps':haps}


def verify_provider_proof(stored,actual,native):
    for key in ('system_image','image_identity','archive_guard','sdk','production','signer_inputs'):
        if stored[key]!=actual[key]:raise ValueError('source-bound current-image Wallpaper provider differs: '+key)
    for key in ('hap','embedded_profile'):
        if checked(stored[key]).read_bytes()!=checked(actual[key]).read_bytes():
            raise ValueError('source-bound current-image Wallpaper bytes differ: '+key)
    if (stored['system_image']!=native['system_image']or
            stored['archive_guard']['sha256']!=native['files_sha256']['contacts-theme-provider-evidence.json']):
        raise ValueError('source provider proof does not belong to the independently re-read current archive')


def run(args):
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    report={'schema_version':1,'status':'fail','scope':SCOPE,
        'archive':record(args.archive),'archive_sha256':sha(args.archive),'boot':record(args.boot),
        'artifacts':record(args.artifacts),'wrapper':record(Path(__file__)),'commands':[],'failures':[],'cleanup_verified':False,
        'enclosing_guest_preserved':False,'cleanup_complete':False,'cleanup_errors':[],
        'children_started':False,'first_artifact_behavior_gate_passed':False,'closed_requirement_ids':[]}
    transport=None;policy=None;installed=[]
    def save():save_report(args.output/'evidence.json',report)
    def command(argv,label,timeout=300,allow_failure=False):
        argv=list(map(str,argv));log=args.output/(str(len(report['commands'])).zfill(3)+'-'+label+'.log')
        with log.open('x')as stream:
            child=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            try:child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:stop_child(child)
        row={'label':label,'argv':argv,'exit_code':child.returncode,**record(log)};report['commands'].append(row);save()
        text=log.read_text(errors='replace')
        from hdc_transport import failed
        if not allow_failure and (child.returncode or '[Fail]'in text or argv[0]==str(args.hdc)and failed(text,'')):
            raise ValueError('actual wrapper command failed: '+label)
        return text
    try:
        artifacts=json.loads(args.artifacts.read_text());challenge=checked(artifacts['challenge']);value=json.loads(challenge.read_text());check_challenge(value)
        original_boot=args.boot.resolve();snapshot=original_boot.with_name('wallpaper-'+value['run_id']+'-boot.json')
        descriptor=os.open(snapshot,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb')as stream:stream.write(original_boot.read_bytes())
        args.boot=snapshot;report['boot']=record(snapshot);report['original_boot_at_start']=record(original_boot)
        plan=validate_plan(json.loads(checked(artifacts['ui_plan']).read_text()));plan_path=args.output/'actual-ui-plan.json';write_json(plan_path,plan)
        transport=Transport(args,plan);transport.wake_if_asleep('requested-wallpaper-suite-start');transport.guest.start();transport.identity('wrapper-initial')
        env=transport.guest.env;report.update(boot_id=env['boot_id'],arch=env['guest_arch'],device=env['device_type'],target=env['target'],udid=env['udid'])
        if env['guest_arch']!='arm64':raise ValueError('provided actual product helper builder currently supports arm64 only')
        native=native_binding.archive_native(args.archive,args.boot,args.output/'native-archive')
        write_json(args.output/'native-archive.json',native)
        report.update(native_archive=record(args.output/'native-archive.json'),native_verifier=record(Path(native_binding.__file__)))
        save()
        if plan.get('device_type',env['device_type'])!=env['device_type']:raise ValueError('source/UI plan belongs to another device profile')
        screenshot=transport.ui.screenshot(label='actual-challenge-geometry')
        from PIL import Image
        with Image.open(screenshot)as image:
            if image.size!=(value['width'],value['height']):raise ValueError('SDK02 challenge differs from actual display geometry')
        report['actual_display']=record(screenshot)
        for bundle,key in ((SETTINGS,'settings_ability'),(PHOTOS,'photos_ability')):
            dump=transport.shell('bm dump -n '+bundle,'wrapper-source-ability')
            declared_ability(dump,bundle,plan[key]);report[bundle+'-BMS']=transport.text(dump,'wrapper-declared-ability')
        import batch_apps_contact_picker_coordinator as signer_tools
        signer=artifacts['signer'];dist=Path(signer['dist']).resolve();jar=checked(signer['jar'])
        _,_,signing_inputs=signer_tools.signer_inputs(dist,jar)
        report['shared_signer']=record(Path(signer_tools.__file__))
        report['signer_inputs']=signing_inputs;inputs={'tools':adapt_helpers(artifacts['helpers'],args.output),'native':report['native_archive']}
        provider=signer_tools.provider_from_image(args.boot,artifacts['provider'],args.output/'renderer-provider',dist,jar,
            command,provider_name='theme',device=env['device_type'])
        verify_provider_proof(provider,provider,native)
        report['renderer_provider']=provider;inputs['renderer_provider_hap']=provider['hap']
        for role in ('seed','query'):
            item=caller_sources(artifacts[role]);unsigned=checked(item['unsigned_hap']);page=checked(item['compiled_page'])
            adapt_sdk_build(item,page,unsigned,args.output/(role+'-SDK-target.json'))
            if role=='seed':
                proof=signer_tools.sign_normal_hap(unsigned,SEED,[],env['udid'],dist,jar,args.output/'seed-signing',command)
                signed=checked(proof['signed_hap'])
            else:
                signed=args.output/(role+'-signed.hap')
                command([sys.executable,Path(__file__),'sign-query','--signer-dist',dist,'--jar',jar,
                    '--unsigned',unsigned,'--output',signed,'--udid',env['udid'],'--role','query'],'sign-query-exact-role')
                proof=signer_tools.verify_signed_hap_artifacts(signed,QUERY,[READ],env['udid'],dist,jar,
                    args.output/'query-signing-verification',command,apl='system_basic',system_app=True)
                signer_tools.verify_signed_payload(unsigned, signed)
            report[role+'_signing']=proof
            adapter=args.output/(role+'-coordinator-signing.json')
            write_json(adapter,{'status':'pass','scope':'actual_signature_profile_and_codesign_NOT_guest',
                'role':role,'unsigned_sha256':sha(unsigned),'signed_sha256':sha(signed),'verified_profile':proof['verified_profile'],
                'actual_shared_signing':proof})
            item.update(signed_hap=record(signed),signing_receipt=record(adapter))
            validate_hap(item,role,value,env['udid'],args.output);inputs[role]=item
            bundle=SEED if role=='seed'else QUERY
            # Disposable caller only. A real fresh install must lose old grants.
            command([args.hdc,'-t',env['target'],'uninstall',bundle],'remove-only-old-'+role,allow_failure=True)
            installed.append(bundle)
            reply=command([args.hdc,'-t',env['target'],'install',signed],'install-exact-'+role)
            if not re.search('success',reply,re.I)or re.search('failed',reply,re.I):raise ValueError('actual caller install failed')
        if signer_tools.signer_inputs(dist,jar)[2]!=signing_inputs:raise ValueError('signer source changed during actual use')
        inputs_path=args.output/'coordinator-inputs.json';write_json(inputs_path,inputs)
        policy=OwnedPolicy(transport,args.suite_evidence,report.setdefault('power_policy',{}))
        policy.suspend(report['archive_sha256'],env['boot_id'],original_boot);save()
        actions=args.output/'actions';actions.mkdir(mode=0o700)
        common=['--boot',args.boot,'--archive',args.archive,'--challenge',challenge,'--plan',plan_path,'--hdc',args.hdc,'--actions',actions]
        report['children_started']=True;save()
        report['children']=run_pair([sys.executable,HERE/'batch_media_wallpaper_runtime.py','run',*common,
            '--output',args.output/'runtime','--action-timeout','180'],
            [sys.executable,HERE/'batch_media_wallpaper_coordinator.py','run',*common,'--inputs',inputs_path,
             '--output',args.output/'coordinator','--runtime-output',args.output/'runtime','--install-callers',
             '--action-seconds','175'],args.output,args.timeout)
        report.update(runtime=record(args.output/'runtime/runtime.json'),coordinator=record(args.output/'coordinator/coordinator.json'),
                      coordinator_inputs=record(inputs_path),ui_plan=record(plan_path),child_processes=record(args.output/'child-processes.json'))
        independent=verify(args.output/'runtime/runtime.json');write_json(args.output/'independent-verification.json',independent)
        if independent.get('status')!='pass':raise ValueError('independent wallpaper file/pixel oracle failed')
        report['independent_verification']=record(args.output/'independent-verification.json')
        import batch_apps_wallpaper_connection as connections
        connection_proof=connections.verify_runtime_connections(args.output/'runtime/runtime.json',target=env['target'],
            module_name='phone_wallpaper'if env['device_type']=='phone'else'pad_wallpaper')
        write_json(args.output/'native-connections.json',connection_proof)
        mapping_proof=native_binding.verify_mappings(json.loads((args.output/'coordinator/coordinator.json').read_text()),native,target=env['target'])
        write_json(args.output/'native-mappings.json',mapping_proof)
        report.update(connection_verifier=record(Path(connections.__file__)),native_connections=record(args.output/'native-connections.json'),
            native_mappings=record(args.output/'native-mappings.json'))
        verify_native_runtime(report,json.loads((args.output/'coordinator/coordinator.json').read_text()),native,env)
        report['status']='pass'
    except (OSError,ValueError,KeyError,TypeError,ImportError,tarfile.TarError,EOFError,subprocess.SubprocessError)as error:
        report['failures'].append(type(error).__name__+': '+str(error))
    finally:
        if transport:
            try:
                for bundle in installed:
                    transport.shell('aa force-stop '+bundle,'stop-owned-wallpaper-observer')
                    reply=command([args.hdc,'-t',transport.guest.target,'uninstall',bundle],'uninstall-owned-wallpaper-observer')
                    if not re.search('success',reply,re.I):raise ValueError('observer uninstall failed')
                remote='/data/local/tmp/wallpaper-coordinator-'+value['run_id']
                cleanup=('if test -e '+remote+' || test -L '+remote+'; then test -d '+remote+' && test ! -L '+remote+
                    ' && test "$(stat -c \'%u %a\' '+remote+')" = "0 700" || exit 1; ')
                for name,item in (inputs.get('tools',{})if 'inputs'in locals()else{}).items():
                    path=remote+'/'+name;digest=item['binary']['sha256']
                    cleanup+=('if test -e '+path+' || test -L '+path+'; then test -f '+path+' && test ! -L '+path+
                        ' && test "$(sha256sum '+path+')" = "'+digest+'  '+path+'" && rm '+path+' || exit 1; fi; ')
                cleanup+='rmdir '+remote+'; fi'
                transport.shell(cleanup,'remove-only-owned-wallpaper-helpers')
                report['cleanup_verified']=True
            except (OSError,ValueError,KeyError,subprocess.SubprocessError)as error:
                report['cleanup_errors'].append('observer/helper cleanup failed: '+str(error));report['status']='fail'
            try:
                if policy and policy.restorable:
                    navigation_error=policy.restore()
                    if navigation_error:
                        report['failures'].append('final Home navigation failed: '+navigation_error);report['status']='fail'
            except (OSError,ValueError,KeyError,subprocess.SubprocessError)as error:
                report['cleanup_errors'].append('policy restoration failed: '+str(error));report['status']='fail'
            try:
                transport.identity('wrapper-final');transport.guest.healthy()
                if sha(args.archive)!=report['archive_sha256']:raise ValueError('archive changed')
                report['enclosing_guest_preserved']=True
            except (OSError,ValueError,KeyError,subprocess.SubprocessError)as error:
                report['cleanup_errors'].append('policy/guest restoration failed: '+str(error));report['status']='fail'
            report['transport']=record(transport.save())
        if report['children_started']:
            try:report['asset_cleanup']=asset_cleanup_proof(args.output)
            except (OSError,ValueError,KeyError,TypeError)as error:
                report['cleanup_errors'].append('created assets/private inputs/default resources cleanup unproven: '+str(error))
                report['status']='fail'
        report['cleanup_complete']=not report['cleanup_errors']and (transport is None or report['cleanup_verified']and report['enclosing_guest_preserved'])
        save()
        if report['status']=='pass':
            try:verify_evidence(args.output/'evidence.json',args.archive,original_boot)
            except (OSError,ValueError,KeyError,TypeError,ImportError,tarfile.TarError,EOFError,subprocess.SubprocessError)as error:
                report['status']='fail';report['failures'].append('independent wrapper replay failed: '+str(error));save()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);modes=parser.add_subparsers(dest='mode',required=True)
    run_parser=modes.add_parser('run')
    for name in ('boot','archive','artifacts','output'):run_parser.add_argument('--'+name,type=Path,required=True)
    run_parser.add_argument('--suite-evidence',type=Path);run_parser.add_argument('--hdc',required=True)
    run_parser.add_argument('--timeout',type=int,default=5400,help='bounded wall seconds, 300..7200')
    signer=modes.add_parser('sign-query')
    for name in ('signer-dist','jar','unsigned','output'):signer.add_argument('--'+name,type=Path,required=True)
    signer.add_argument('--udid',required=True);signer.add_argument('--role',choices=['query'],required=True)
    argv=sys.argv[1:]
    if not argv or argv[0]not in ('run','sign-query'):argv=['run',*argv]
    args=parser.parse_args(argv)
    if args.mode=='sign-query':sign_query(args);return 0
    if not 300<=args.timeout<=7200:parser.error('timeout must be 300..7200 seconds')
    value=run(args);print(json.dumps({'status':value['status'],'failures':value['failures']}));return int(value['status']!='pass')


if __name__=='__main__':raise SystemExit(main())
