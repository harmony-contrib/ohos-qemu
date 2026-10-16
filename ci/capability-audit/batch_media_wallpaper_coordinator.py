#!/usr/bin/env python3
"""Execute wallpaper audit requests on the same suite-owned acceptance guest.

No builds, new VM, grants, profile/ACL editing, media SQL or synthetic results.
SDK/sign receipts are validated before any app is driven. ACK is published only
after real operation evidence is complete; the frozen independent oracle still
decides the wallpaper result.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import socket
import stat
import subprocess
import time
import zipfile

from PIL import Image
from batch_media_wallpaper_runtime import Runtime, record, sha, write_json, SETTINGS, SEED, PHOTOS, CASES
from batch_media_verify_wallpaper_runtime import checked, check_challenge, seed_rows, thumbnail, photos_provider
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node
from boot_package import kernel_sleeping

HERE = Path(__file__).resolve().parent
FIXTURE = HERE/'fixtures/batch_media/wallpaper_receipts'
QUERY = 'org.harmonycontrib.wallpaperquery'
READ = 'ohos.permission.READ_IMAGEVIDEO'
SET = 'ohos.permission.SET_WALLPAPER'


def ordered_actions():
    names = ['verify-package-identities-and-permissions', 'resolve-service-default-resources',
             'import-five-PNGs-via-real-Photos-consent']
    for case in CASES[:4]: names += ['show-settings-main', 'show-real-'+case.split('-')[0]]
    return names + ['show-settings-main', 'cancel-real-Photos-picker', 'show-settings-main',
        'ordinary-denied-set-and-restore', 'show-settings-main', 'show-real-desktop', 'show-settings-main',
        'show-real-lock', 'delete-only-created-Photos-assets-via-real-UI', 'remove-owned-seed-private-inputs']


def request_file(path, run, boot, sequence):
    """A writer may still be finishing the fresh request: retry only JSON EOF."""
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        status = os.fstat(stream.fileno())
        if (not stat.S_ISREG(status.st_mode) or status.st_uid != os.getuid() or status.st_mode & 0o777 != 0o600 or
                status.st_nlink != 1 or status.st_size > 16384):
            raise ValueError('owned bounded 0600 single-link request required')
        raw = stream.read(16385)
    if not raw.endswith(b'\n'):raise NodeNotReady('request writer has not finished its complete line')
    try: value = json.loads(raw)
    except json.JSONDecodeError as error:
        if not raw.endswith(b'\n'): raise NodeNotReady('request not complete yet') from error
        raise ValueError('complete request has invalid JSON') from error
    if (set(value) != {'schema_version','run_id','boot_id','sequence','nonce','action','details'} or
            type(value['schema_version']) is not int or value['schema_version'] != 1 or value['run_id'] != run or value['boot_id'] != boot or
            type(value['sequence']) is not int or value['sequence'] != sequence or
            re.fullmatch('[a-f0-9]{32}', value['nonce']) is None or
            value['action'] != ordered_actions()[sequence-1] or not isinstance(value['details'], dict) or
            path.name != f'{run}-{sequence:03}-{value["nonce"]}.request.json'):
        raise ValueError('stale/reordered/misnamed/unexpected root request')
    return value


def publish_ack(path, request):
    value = {k: request[k] for k in ('schema_version','run_id','boot_id','sequence','nonce','action')}
    path = Path(path)
    temporary = path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        # One persistent owned publication guard excludes duplicate writers.
        # Publish by rename so the reader can never observe st_nlink==2 (its
        # frozen single-link ACK validation deliberately rejects hardlinks).
        os.mkdir(str(path)+'.once',0o700)
        if path.exists()or path.is_symlink():raise FileExistsError('ACK already exists')
        os.rename(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    return record(path)


def adapt_sdk_build(input_value, generated_page, unsigned, output):
    """Consume root SDK39's real exit_code/source_files/commands/haps schema."""
    evidence_path = checked(input_value['sdk_evidence'])
    evidence = json.loads(evidence_path.read_text())
    if (type(evidence.get('exit_code')) is not int or
            evidence.get('first_artifact_behavior_gate_passed') is not False or
            re.fullmatch('[a-f0-9]{40}', evidence.get('source_commit','')) is None or
            re.fullmatch('[a-f0-9]{64}', evidence.get('archive_sha256','')) is None or
            re.fullmatch('[a-f0-9]{64}', evidence.get('runner_sha256','')) is None or
            evidence.get('source_files',{}).get(input_value['source_key']) != sha(generated_page)):
        raise ValueError('actual successful SDK source/build evidence required, not a hand-written pass')
    haps = [v for v in evidence.get('haps',[]) if v.get('sha256') == sha(unsigned) and
            v.get('bytes') == unsigned.stat().st_size]
    commands = evidence.get('commands',[])
    if len(haps) != 1 or not commands:
        raise ValueError('complete SDK report and exact produced HAP required')
    compile_rows = [c for c in commands if c.get('label') == 'compile' and 'assembleHap' in c.get('argv',[])]
    project=haps[0].get('project') if haps else None
    if project:
        selected=[c for c in commands if c.get('project')==project or
                  (not c.get('project')and Path(c['log']).stem.startswith(project+'-'))]
        compile_rows=[c for c in compile_rows if c.get('project')==project or Path(c['log']).stem==project+'-compile']
        if not input_value['source_key'].startswith(project+'/'):
            raise ValueError('source file belongs to another project in the batch SDK report')
    else:selected=commands
    if (not selected or any(type(c.get('exit_code'))is not int or c['exit_code']!=0 for c in selected) or
            not project and evidence['exit_code']!=0):
        raise ValueError('all commands for the exact target project must succeed')
    if len(compile_rows) != 1:
        raise ValueError('one real official assembleHap command required')
    for command in commands:
        checked({'path':str(Path(command['log']).resolve()),'sha256':command['sha256']})
    if 'BUILD SUCCESSFUL' not in Path(compile_rows[0]['log']).read_text(errors='replace'):
        raise ValueError('actual SDK build completion absent from original compile log')
    value = {'status':'pass','scope':'exact_target_project_compile_ONLY_NOT_whole_SDK_batch_or_runtime',
             'actual_batch_exit_code':evidence['exit_code'],'target_project':project,
             'generated_page_sha256':sha(generated_page),'unsigned_sha256':sha(unsigned),
             'actual_sdk_evidence':record(evidence_path),'actual_compile_log':record(compile_rows[0]['log'])}
    write_json(output,value)
    return record(output)


def validate_hap(value, role, challenge, udid, output):
    page, unsigned, signed, signing_file = (checked(value[k]) for k in ('compiled_page','unsigned_hap','signed_hap','signing_receipt'))
    bundle = SEED if role == 'seed' else QUERY
    permissions = [] if role == 'seed' else [READ]
    template = checked(challenge['generated_page']).read_text() if role == 'seed' else (
        (FIXTURE/'Query.ets').read_text().replace('__WALLPAPER_RUN__',challenge['run_id']))
    if page.read_text() != template:
        raise ValueError('actual compiled caller source differs from exact role/run')
    signing = json.loads(signing_file.read_text())
    if (signing.get('status') != 'pass' or signing.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
            signing.get('unsigned_sha256') != sha(unsigned) or signing.get('signed_sha256') != sha(signed)):
        raise ValueError('actual verified signature/codesign receipt required')
    profile = signing['verified_profile']; info = profile['bundle-info']
    if (info.get('bundle-name') != bundle or profile['debug-info'].get('device-ids') != [udid] or
            info.get('apl') != ('normal' if role == 'seed' else 'system_basic') or
            info.get('app-feature') != ('hos_normal_app' if role == 'seed' else 'hos_system_app')):
        raise ValueError('actual signer identity/profile/device differs from the minimal caller role')
    permitted = set() if role == 'seed' else {READ}
    if (not set(profile['acls'].get('allowed-acls',[])) <= permitted or
            not set(profile['permissions'].get('restricted-permissions',[])) <= permitted):
        raise ValueError('caller profile has unrelated ACL or restricted permission')
    with zipfile.ZipFile(unsigned) as plain, zipfile.ZipFile(signed) as final:
        if (len(plain.namelist()) != len(set(plain.namelist())) or len(final.namelist()) != len(set(final.namelist())) or
                plain.read('module.json') != final.read('module.json') or plain.read('ets/modules.abc') != final.read('ets/modules.abc')):
            raise ValueError('signed HAP changed compiled module/ABC or has duplicate entries')
        raw = final.read('module.json'); module = json.loads(raw)
    declared=module['module'].get('requestPermissions',[])
    # Real SDK module output may retain reason/usedScene/resource metadata.
    # Compare permission identities, preserving legitimate user-consent data.
    if (module['app'].get('bundleName') != bundle or not isinstance(declared,list) or
            any(not isinstance(item,dict)for item in declared) or [item.get('name')for item in declared] != permissions):
        raise ValueError('actual compiled caller requested unexpected permissions')
    if value.get('ability') not in {v.get('name')for v in module['module'].get('abilities',[])}:
        raise ValueError('caller ability is not declared in the actual compiled HAP')
    label_path=page.parents[5]/'AppScope/resources/base/element/string.json'
    evidence=json.loads(checked(value['sdk_evidence']).read_text())
    prefix=value['source_key'].split('entry/',1)[0]
    if evidence['source_files'].get(prefix+'AppScope/resources/base/element/string.json')!=sha(label_path):
        raise ValueError('actual app label source is not bound by the SDK build')
    label_key=module['app'].get('label','').removeprefix('$string:')
    labels=[row['value']for row in json.loads(label_path.read_text())['string']if row.get('name')==label_key]
    if len(labels)!=1 or not isinstance(labels[0],str)or not 1<=len(labels[0])<=128:
        raise ValueError('one actual compiled application label required')
    module_path = output/(role+'-actual-module.json'); module_path.write_bytes(raw)
    return {'compiled_page':record(page),'compiled_module':record(module_path),'unsigned_hap':record(unsigned),'app_label':labels[0],
            'signed_hap':record(signed),'signing_receipt':record(signing_file),
            'build_receipt':adapt_sdk_build(value,page,unsigned,output/(role+'-adapted-build.json'))}


def actual_query(raw, run, nonce, phase, uris):
    if phase not in ('before','after')or len(uris)!=5 or len(set(uris))!=5:
        raise ValueError('exact before/after query for five unique created URIs required')
    value = json.loads(raw)
    if (set(value) != {'run_id','nonce','phase','queried_uris','active_uris','entries','began_ms','ended_ms'} or
            value['run_id'] != run or value['nonce'] != nonce or value['phase'] != phase or value['queried_uris'] != uris or
            type(value['began_ms']) is not int or type(value['ended_ms']) is not int or
            value['began_ms'] <= 0 or not 0 <= value['ended_ms']-value['began_ms'] <= 60000 or len(value['entries']) != 5):
        raise ValueError('actual complete fresh PhotoAccessHelper query required; errors are not empty results')
    active=[]
    for uri, entry in zip(uris,value['entries']):
        expected = {'uri':uri,'count':1 if phase == 'before' else 0,'actualUri':uri if phase == 'before' else ''}
        if entry != expected or type(entry['count'])is not int: raise ValueError('all five URI queries must prove before-present/after-absent')
        if entry['count'] == 1: active.append(entry['actualUri'])
    if value['active_uris'] != active:
        raise ValueError('query summary differs from real individual cursor counts/URIs')
    return {'queried_uris':uris,'active_uris':active}


class Coordinator(Runtime):
    """Reuse frozen transport/receive implementation, never its action writer."""
    def __init__(self,args):
        self.args=args; self.output=args.output.resolve(); self.output.mkdir(parents=True,exist_ok=False)
        self.runtime_output=args.runtime_output.resolve(); self.challenge=json.loads(args.challenge.read_text())
        check_challenge(self.challenge); self.run=self.challenge['run_id']
        self.plan=json.loads(args.plan.read_text()); self.inputs=json.loads(args.inputs.read_text())
        self.guest=EnclosingAcceptanceGuest(args.boot,args.archive,args.hdc,self.output/'guest')
        self.boot_id=self.guest.env['boot_id']; self.deadline=None
        self.value={'schema_version':1,'scope':'actual_wallpaper_action_coordinator_NOT_independent_runtime_gate',
            'status':'running','run_id':self.run,'boot_id':self.boot_id,'archive':record(args.archive),'boot':record(args.boot),
            'inputs':record(args.inputs),'plan':record(args.plan),'commands':[],'actions':[],'ui_actions':[],
            'queries':[],'tokens':[],'power_keys':[],'failures':[],'first_artifact_behavior_gate_passed':False}
        self.ui=GuestUi(self.command,args.hdc,self.guest.target,self.output/'ui')
        self.haps={role:validate_hap(self.inputs[role],role,self.challenge,self.guest.udid,self.output) for role in ('seed','query')}
        self.uids={}; self.uris=[]; self.remote='/data/local/tmp/wallpaper-coordinator-'+self.run
        self.tools={}; self.expected_sequence=1; self.save()

    def save(self):
        self.value['enclosing_guest_commands']=self.guest.report.get('commands',[])
        path=self.output/'coordinator.json'; path.write_text(json.dumps(self.value,ensure_ascii=False,indent=2)+'\n'); return path

    def command(self,argv,label):
        self.remaining()
        try:return super().command(argv,label)
        except subprocess.TimeoutExpired as error:
            def text(value):return value.decode(errors='replace')if isinstance(value,bytes)else(value or '')
            path=self.output/('timeout-'+str(len(self.value['commands'])).zfill(4)+'.log')
            path.write_text(text(error.stdout)+text(error.stderr))
            self.value['commands'].append({'argv':list(map(str,argv)),'label':label,'exit_code':None,
                'timed_out':True,**record(path)});self.save();raise

    def remaining(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ValueError('original action deadline expired; do not ACK incomplete work')

    def wait_node(self,bundle,*,identifier=None,text=None):
        end=min(time.monotonic()+30,self.deadline or float('inf'))
        while time.monotonic()<end:
            try:
                tree,path=self.ui.layout(label='coordinator-control')
                return tree,path,ready_node(tree,bundle,identifier=identifier,text=text,clickable=True)
            except (LayoutNotReady,NodeNotReady):time.sleep(0.2)
        raise ValueError('actual unique UI control unavailable')

    def observed_click(self,bundle,selector,*,host=None,frame=None):
        self.remaining(); tree,path,node=frame or self.wait_node(bundle,**selector)
        picture=self.ui.screenshot(label='before-real-action')
        dump=self.text(self.shell('aa dump -a -u 100','real-action-provider'),'real-action-provider')
        if host:photos_provider(checked(dump).read_text(),host)
        x,y,w,h=node['rect']; self.shell(f'uitest uiInput click {x+w//2} {y+h//2}','observed-real-control')
        action={'layout':record(path),'node':node,'screenshot':record(picture),'provider_dump':dump,
                'selector':selector,'ui_bundle':bundle,'host_ns':time.monotonic_ns()}
        self.value['ui_actions'].append(action); self.save(); return action

    def receipt(self,request,name):
        supplied=request['details'].get('output',request['details'].get('required_output'))
        expected=self.runtime_output/name
        if supplied is None or Path(supplied).resolve()!=expected or expected.exists() or expected.is_symlink():
            raise ValueError('fresh exact runtime receipt output path required')
        if not expected.parent.is_dir() or expected.parent.is_symlink() or expected.parent.stat().st_uid!=os.getuid():
            raise ValueError('runtime evidence directory is not owned')
        return expected

    def observe_identity(self,bundle,role):
        raw=self.shell('bm dump -n '+bundle,'actual-'+role+'-BMS'); saved=self.text(raw,'actual-'+role+'-BMS')
        value=json.loads(raw.removeprefix(bundle+':\n')); app=value['applicationInfo']
        uid=app.get('uid'); expected_apl='normal' if role=='seed' else 'system_basic'
        if ((app.get('name') or app.get('bundleName'))!=bundle or type(uid)is not int or uid//200000!=100 or
            app.get('appPrivilegeLevel')!=expected_apl or app.get('isSystemApp') is not (role!='seed')):
            raise ValueError('actual caller BMS identity differs from real signed role')
        self.uids[role]=uid; self.value[role+'_BMS']=saved; return uid

    def bind_installed_hap(self,role):
        raw=json.loads(checked(self.value[role+'_BMS']).read_text().removeprefix((SEED if role=='seed'else QUERY)+':\n'))
        paths=[]
        def visit(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key=='hapPath'and isinstance(item,str)and item.startswith('/data/app/'):paths.append(item)
                    else:visit(item)
            elif isinstance(value,list):
                for item in value:visit(item)
        visit(raw);paths=sorted(set(paths))
        if len(paths)==1:
            actual=self.receive(paths[0],'actual-installed-'+role+'-HAP',maximum=64*1024*1024)
            if actual['file']['sha256']!=self.haps[role]['signed_hap']['sha256']:raise ValueError('BMS-installed HAP differs from signed compiled input')
            self.value[role+'_installed_HAP']=actual
        elif not self.args.install_callers:
            raise ValueError('no unique BMS-retained HAP; use explicit --install-callers to bind the actual install command')

    def stage_file(self,local,remote,uid,*,fresh=True,mode='600'):
        self.remaining(); local=Path(local); quoted=shlex.quote(remote)
        if fresh:self.shell('test ! -e '+quoted+' && test ! -L '+quoted,'fresh-staged-file')
        elif not remote.endswith('/query-request.json'):raise ValueError('only the owned query request may be replaced')
        target=remote if fresh else remote+'.'+secrets.token_hex(8)+'.tmp'
        self.command([self.args.hdc,'-t',self.guest.target,'file','send',local,target],'stage-exact-owned-file')
        self.shell('chown '+str(uid)+':'+str(uid)+' '+shlex.quote(target)+' && chmod '+mode+' '+shlex.quote(target),
                   'staged-file-owner-mode')
        if not fresh:self.shell('test ! -L '+quoted+' && mv '+shlex.quote(target)+' '+quoted,'replace-owned-query-request')
        actual=self.shell('sha256sum '+quoted,'staged-file-sha').strip().split('  ',1)
        if actual!=[sha(local),remote]:raise ValueError('real guest staging bytes differ')

    def stage_tool(self,name):
        item=self.inputs['tools'][name]; binary,source,build=(checked(item[k]) for k in ('binary','source','build_receipt'))
        from batch_media_wallpaper_artifacts import verify_helper_receipt
        proof=verify_helper_receipt(name,binary,source,item['build_receipt'])
        expected=(FIXTURE/'token_query.cpp') if name=='token' else HERE/'fixtures/batch_media/wallpaper_runtime/default_resolver.cpp'
        receipt=json.loads(build.read_text()); data=binary.read_bytes()
        if (sha(source)!=sha(expected) or receipt.get('status')!='pass' or receipt.get('source_sha256')!=sha(source) or
            receipt.get('binary_sha256')!=sha(binary) or receipt.get('arch')!=self.guest.env['guest_arch'] or
            len(data)<20 or data[:4]!=b'\x7fELF' or int.from_bytes(data[18:20],'little')!=
            {'arm64':183,'armv7a':40,'x86_64':62}[self.guest.env['guest_arch']]):
            raise ValueError('actual compiled guest helper/source/ABI receipt required')
        observations=[]
        for dso in proof['product_DSOs']:
            soname=dso['soname']
            if re.fullmatch(r'[a-zA-Z0-9_+.\-]+\.so',soname)is None:raise ValueError('invalid product SONAME')
            paths=['/system/lib64/'+soname,'/system/lib64/platformsdk/'+soname,
                   '/system/lib64/chipsetsdk/'+soname,'/vendor/lib64/'+soname]
            raw=self.shell('for task_dso in '+' '.join(map(shlex.quote,paths))+
                '; do if test -f "$task_dso"; then sha256sum "$task_dso" || exit 1; fi; done','actual-helper-product-DSO')
            rows=[line.split('  ',1)for line in raw.splitlines()]
            if not rows or any(len(row)!=2 or row[0]!=dso['sha256']or row[1]not in paths for row in rows):
                raise ValueError('guest DSO differs from helper actual linker inputs: '+soname)
            observations.append({'soname':soname,'expected_sha256':dso['sha256'],
                                 'actual_hashes':self.text(raw,'actual-helper-DSO-hashes')})
        self.value.setdefault('helper_bindings',{})[name]={'build':proof,'actual_guest_DSOs':observations}
        remote=self.remote+'/'+name; self.stage_file(binary,remote,0,mode='500'); self.tools[name]=remote

    def token(self,role,permission):
        bundle={'seed':SEED,'settings':SETTINGS,'query':QUERY}[role]; uid=self.uids[role]
        raw=self.shell('unset LD_LIBRARY_PATH LD_PRELOAD; '+' '.join(shlex.quote(x) for x in [self.tools['token'],self.run,str(uid),bundle,permission]),'actual-token-query')
        value=json.loads(raw)
        if (value.get('run_id')!=self.run or value.get('boot_id')!=self.boot_id or value.get('bundle')!=bundle or
            value.get('uid')!=uid or value.get('user_id')!=100 or value.get('permission')!=permission or
            type(value.get('token_id'))is not int or value['token_id']<=0 or type(value.get('grant'))is not int or
            value['grant']not in (-1,0) or type(value.get('before_ns'))is not int or value['before_ns']<=0 or
            type(value.get('after_ns'))is not int or value['after_ns']<value['before_ns']):
            raise ValueError('actual token query is stale/mismatched/incomplete')
        result=self.text(raw,'actual-'+role+'-token'); self.value['tokens'].append(result); self.save(); return value,result

    def launch(self,bundle,ability):
        self.wake_if_asleep('before-'+bundle)
        value=self.shell('aa start -b '+shlex.quote(bundle)+' -a '+shlex.quote(ability),'start-real-'+bundle)
        if 'start ability successfully' not in value.lower():raise ValueError('actual caller did not launch')

    def qmp(self,execute):
        self.guest.healthy()
        if execute not in ('system_powerdown','query-status'):raise ValueError('no other QMP operations allowed')
        path=Path(self.guest.env['qmp_socket'])
        if not stat.S_ISSOCK(path.stat().st_mode):raise ValueError('actual enclosing QMP socket required')
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(10); connection.connect(str(path))
            with connection.makefile('rb') as stream:
                if 'QMP'not in json.loads(stream.readline()):raise ValueError('missing actual QMP greeting')
                for identifier,name in [('caps','qmp_capabilities'),('key',execute)]:
                    connection.sendall(json.dumps({'execute':name,'id':identifier}).encode()+b'\n')
                    while True:
                        line=stream.readline()
                        if not line:raise ValueError('QMP disconnected')
                        reply=json.loads(line)
                        if reply.get('id')==identifier:
                            if 'error'in reply or 'return'not in reply:raise ValueError('real QMP operation failed')
                            break
                return reply['return']

    def wake_if_asleep(self,label):
        serial=Path(self.args.boot).parent/'qemu.log'
        if not kernel_sleeping(serial.read_text(errors='replace')):return False
        before=self.text(serial.read_text(errors='replace'),'before-real-key')
        reply=self.qmp('system_powerdown')
        end=min(time.monotonic()+30,self.deadline or float('inf'))
        while time.monotonic()<end and kernel_sleeping(serial.read_text(errors='replace')):time.sleep(.2)
        if kernel_sleeping(serial.read_text(errors='replace')):raise ValueError('one real power key failed to resume')
        self.command([self.args.hdc,'tconn',self.guest.target],'reconnect-after-real-key')
        self.value['power_keys'].append({'label':label,'execute':'system_powerdown','before':before,'reply':reply,
            'after':self.text(serial.read_text(errors='replace'),'after-real-key'),'count':1})
        self.save();return True

    def system_node(self,kind):
        tree,path=self.ui.layout(label='actual-'+kind+'-window'); item=self.plan['screens'][kind]
        node=ready_node(tree,item['bundle'],identifier=item['identifier'])
        picture=self.ui.screenshot(label='actual-'+kind+'-screen')
        with Image.open(picture)as image:
            if node['rect']!=[0,0,image.width,image.height]:raise ValueError('system screen is not actual full viewport')
        return {'layout':record(path),'node':node,'screenshot':record(picture)}

    def home(self):
        self.wake_if_asleep('requested-home-interaction')
        try:self.system_node('desktop');return
        except (LayoutNotReady,NodeNotReady):pass
        try:
            lock=self.system_node('lock'); x,y,w,h=lock['node']['rect']
        except (LayoutNotReady,NodeNotReady):
            self.shell('uitest uiInput keyEvent Home','real-home-key')
        else:
            # Exactly one ordinary gesture on the observed full lock root.
            # If credentials remain, fail; never enter a PIN or force unlock.
            self.shell(f'uitest uiInput swipe {x+w//2} {y+h*85//100} {x+w//2} {y+h*20//100}','real-default-lock-swipe')
        end=min(time.monotonic()+20,self.deadline or float('inf'))
        while time.monotonic()<end:
            try:self.system_node('desktop');return
            except (LayoutNotReady,NodeNotReady):time.sleep(.25)
        raise ValueError('ordinary gesture/Home did not reach desktop; credential/unknown view is not bypassed')

    def show_settings(self):
        self.home(); self.launch(SETTINGS,self.plan['settings_ability'])
        selector=dict(self.plan['settings_main'])
        if selector.pop('bundle',SETTINGS)!=SETTINGS:raise ValueError('real Settings main marker required')
        end=min(time.monotonic()+30,self.deadline or float('inf'));backs=0
        while time.monotonic()<end:
            self.remaining()
            try:
                tree,path=self.ui.layout(label='settings-main-observed')
                ready_node(tree,SETTINGS,**selector);return
            except LayoutNotReady:time.sleep(.2);continue
            except NodeNotReady:
                # Back only while this actual Settings window owns the view.
                if not visible_bundle(tree,SETTINGS):time.sleep(.2);continue
                dump=self.shell('aa dump -a -u 100','Settings-before-real-Back')
                if not settings_foreground(dump,self.uids['settings']):time.sleep(.2);continue
                if backs>=8:raise ValueError('too many Settings pages; no guessed navigation fallback')
                self.shell('uitest uiInput keyEvent Back','return-one-real-Settings-page');time.sleep(.2)
                backs+=1
        raise ValueError('Settings main menu was not reached with bounded real Back actions')

    def show_lock(self):
        self.home()
        for selector in self.plan.get('lock_navigation',[]):
            owner=selector['bundle']
            if owner not in ('com.ohos.sceneboard','com.ohos.systemui'):raise ValueError('actual system lock control required')
            self.observed_click(owner,{k:v for k,v in selector.items()if k!='bundle'})
        end=min(time.monotonic()+65,self.deadline or float('inf'))
        woke=False
        while time.monotonic()<end:
            try:self.system_node('lock');return
            except (LayoutNotReady,NodeNotReady):pass
            if not woke:woke=self.wake_if_asleep('requested-lock-after-real-idle')
            time.sleep(.25)
        raise ValueError('actual system lock view not reached; no fake desktop/forced-lock fallback')

    def show_photos_gallery(self):
        self.home();self.launch(PHOTOS,self.plan['photos_ability'])
        marker=dict(self.plan['photos_main'])
        if marker.pop('bundle',PHOTOS)!=PHOTOS:raise ValueError('actual gallery main marker required')
        end=min(time.monotonic()+30,self.deadline or float('inf'));backs=0
        while time.monotonic()<end:
            try:
                tree,path=self.ui.layout(label='actual-gallery-main')
                ready_node(tree,PHOTOS,**marker);break
            except LayoutNotReady:time.sleep(.2);continue
            except NodeNotReady:
                if not visible_bundle(tree,PHOTOS):time.sleep(.2);continue
                if backs>=8:raise ValueError('gallery main was not reached by bounded real Back actions')
                self.shell('uitest uiInput keyEvent Back','return-one-real-Photos-page');backs+=1;time.sleep(.2)
        else:raise ValueError('actual gallery main view unavailable')
        for selector in self.plan.get('photos_navigation',[]):self.observed_click(PHOTOS,selector)

    def read_log(self,minimum):
        remote='/data/app/el2/100/base/'+SEED+'/files/wallpaper-'+self.run+'.jsonl'
        while True:
            self.remaining()
            raw=self.read_complete(remote,'actual-seed-progress')
            if raw and not raw.endswith('\n'):time.sleep(.1);continue
            rows=[json.loads(line) for line in raw.splitlines()]
            if any(row.get('name')in ('failure','denied.unexpected-success')for row in rows):raise ValueError('real caller reported failure')
            if len(rows)>=minimum:return raw
            time.sleep(.2)

    def read_complete(self,remote,label):
        # GuestUi.shell strips its own trailing newlines. Preserve the file's
        # final newline with a separate fresh EOF sentinel before that strip.
        marker='__WALLPAPER_EOF_'+secrets.token_hex(16)+'__'
        quoted=shlex.quote(remote)
        text=self.shell('if test -f '+quoted+'; then cat '+quoted+' || exit 1; fi && printf '+
                        shlex.quote('\n'+marker+'\n'),label)
        if not text.endswith('\n'+marker)or text.count(marker)!=1:raise ValueError('actual complete-file sentinel missing')
        return text[:-len(marker)-1]

    def query_assets(self,phase):
        self.home();self.launch(QUERY,self.inputs['query']['ability'])
        grant,_=self.token('query',READ)
        if grant['grant']!=0:
            self.observed_click(QUERY,{'identifier':'wallpaper_query_permission'})
            end=min(time.monotonic()+30,self.deadline or float('inf'))
            while time.monotonic()<end:
                try:
                    tree,path=self.ui.layout(label='actual-READ-permission')
                    node,permission=read_permission_node(tree,self.haps['query']['app_label']);break
                except(LayoutNotReady,NodeNotReady):time.sleep(.2)
            else:raise ValueError('actual query-app READ_IMAGEVIDEO consent dialog unavailable')
            self.observed_click('com.ohos.permissionmanager',{'text':permission['allow']},frame=(tree,path,node))
            grant,_=self.token('query',READ)
            if grant['grant']!=0:raise ValueError('actual user READ_IMAGEVIDEO decision did not grant query permission')
        nonce=secrets.token_hex(16)
        request=self.output/('query-'+phase+'-'+nonce+'.json')
        write_json(request,{'run_id':self.run,'nonce':nonce,'phase':phase,'uris':self.uris})
        remote='/data/app/el2/100/base/'+QUERY+'/files/'
        self.stage_file(request,remote+'query-request.json',self.uids['query'],fresh=False)
        result=remote+'query-'+self.run+'-'+nonce+'.json'
        self.shell('test ! -e '+shlex.quote(result),'fresh-real-query-output')
        self.observed_click(QUERY,{'identifier':'wallpaper_query_run'})
        while True:
            self.remaining()
            present=self.shell('if test -f '+shlex.quote(result)+'; then echo present; else echo absent; fi','real-query-completion').strip()
            if present=='present':
                complete=self.read_complete(result,'actual-query-complete-text')
                if complete.endswith('\n'):
                    json.loads(complete);break
                time.sleep(.1);continue
            if present!='absent':raise ValueError('query file presence unknown')
            time.sleep(.2)
        transfer=self.receive(result,'actual-query-'+phase,maximum=65536)
        raw=checked(transfer['file']).read_text(); normalized=actual_query(raw,self.run,nonce,phase,self.uris)
        path=self.output/('query-'+phase+'-normalized.json');write_json(path,normalized)
        token,_=self.token('query',READ)
        if token['grant']!=0:raise ValueError('query permission changed during actual cursor read')
        self.value['queries'].append({'phase':phase,'request':record(request),'raw':transfer,'normalized':record(path),
            'query_HAP':self.haps['query'],'actual_uid':self.uids['query'],'token':token})
        self.save();return record(path)

    def dispatch(self,request):
        action=request['action']
        if action=='verify-package-identities-and-permissions':
            if request['details']!={'required_permission':SET}:raise ValueError('unexpected permission action')
            for role,bundle in [('seed',SEED),('query',QUERY)]:
                if self.args.install_callers:
                    text=self.command([self.args.hdc,'-t',self.guest.target,'install',checked(self.haps[role]['signed_hap'])],'install-real-'+role)
                    if not re.search('success',text,re.I)or re.search('failed',text,re.I):raise ValueError('real caller install failed')
                self.observe_identity(bundle,role)
                self.bind_installed_hap(role)
            self.uids['settings']=self.observe_identity(SETTINGS,'settings')
            self.shell('test ! -e '+self.remote+' && mkdir -m 0700 '+self.remote,'fresh-owned-helper-directory')
            self.stage_tool('token');self.stage_tool('default')
            normal,_=self.token('seed',SET);settings,_=self.token('settings',SET)
            if normal['grant']!=-1 or settings['grant']!=0:raise ValueError('actual normal/Settings token boundaries differ')
        elif action=='resolve-service-default-resources':
            destination=self.receipt(request,'default-resolution.json')
            raw=self.shell('unset LD_LIBRARY_PATH LD_PRELOAD; '+shlex.quote(self.tools['default'])+' '+self.run,'actual-service-default-resolver')
            value=json.loads(raw)
            if value.get('run_id')!=self.run or value.get('boot_id')!=self.boot_id:raise ValueError('wrong real default resolver boot')
            result={'run_id':self.run,'boot_id':self.boot_id,'actual_GetCfgFiles_query':self.text(raw,'actual-default-query'),
                'query_binary':self.inputs['tools']['default']['binary'],'query_source':self.inputs['tools']['default']['source'],
                'query_build_receipt':self.inputs['tools']['default']['build_receipt']}
            for kind in ('desktop','lock'):
                description=value['descriptions'][kind];manifest=None
                if description['manifest_state']=='resolved':
                    item=self.receive(description['manifest_remote'],'actual-'+kind+'-manifest',maximum=65536)
                    manifest=item['file'];self.value.setdefault('default_manifests',[]).append(item)
                result[kind]={'remote':value['resolved'][kind],'manifest':manifest}
            write_json(destination,result)
        elif action=='import-five-PNGs-via-real-Photos-consent':
            destination=self.receipt(request,'import-observation.json')
            if request['details']['bundle']!=SEED or Path(request['details']['challenge']).resolve()!=self.args.challenge.resolve():
                raise ValueError('unexpected source/bundle for actual import')
            self.home();self.launch(SEED,self.inputs['seed']['ability']);actions=[]
            base='/data/app/el2/100/base/'+SEED+'/files/'
            self.shell('test ! -e '+base+'wallpaper-'+self.run+'.jsonl','fresh-seed-journal')
            for index,case in enumerate(CASES):
                self.stage_file(checked(self.challenge['images'][case]),base+case+'.png',self.uids['seed'])
                self.observed_click(SEED,{'identifier':'wallpaper_import_'+case})
                owner=self.plan.get('save_ui_bundle',SEED)
                if owner not in (SEED,PHOTOS):raise ValueError('wrong Photos save provider/host')
                control=self.observed_click(owner,{'identifier':'advanced_dialog_button_1'},host=SEED)
                control['case']=case;actions.append(control);self.read_log((index+1)*2)
            raw=self.read_log(10);_,self.uris=seed_rows(raw,self.run)
            write_json(destination,{'run_id':self.run,'boot_id':self.boot_id,'seed_uid':self.uids['seed'],
                                   'uris':self.uris,'consent_actions':actions,**self.haps['seed']})
        elif action=='show-settings-main':self.show_settings()
        elif action=='show-real-desktop':
            self.home()
            if request['details'].get('case')in ('desktop-1','desktop-2'):
                from batch_media_wallpaper_native import observe_maps, observe_renderer_hap
                observe_maps(self,request)
                observe_renderer_hap(self,request)
        elif action=='show-real-lock':self.show_lock()
        elif action=='cancel-real-Photos-picker':
            destination=self.receipt(request,'picker-cancel-observation.json')
            from photos_asset_ui import button_ancestor
            owner=self.plan.get('picker_ui_bundle',SETTINGS);end=time.monotonic()+30
            while time.monotonic()<end:
                try:
                    tree,path=self.ui.layout(label='real-picker-close')
                    ready_node(tree,owner,identifier='Third_Select_PickerClose')
                    node=button_ancestor(tree,owner,'Third_Select_PickerClose');break
                except (LayoutNotReady,NodeNotReady):time.sleep(.2)
            else:raise ValueError('actual Photos close button unavailable')
            image=self.ui.screenshot(label='real-picker-cancel')
            dump=self.text(self.shell('aa dump -a -u 100','actual-picker-cancel-AMS'),'actual-picker-cancel-AMS')
            photos_provider(checked(dump).read_text(),SETTINGS)
            x,y,w,h=node['rect'];self.shell(f'uitest uiInput click {x+w//2} {y+h//2}','real-picker-close-button')
            write_json(destination,{'run_id':self.run,'boot_id':self.boot_id,'ui_bundle':owner,'layout':record(path),
                                    'node':node,'screenshot':record(image),'provider_dump':dump})
        elif action=='ordinary-denied-set-and-restore':
            destination=self.receipt(request,'denied-observation.json')
            self.home();self.launch(SEED,self.inputs['seed']['ability'])
            normal,before=self.token('seed',SET);settings,provider=self.token('settings',SET)
            if normal['grant']!=-1 or settings['grant']!=0:raise ValueError('wrong actual denial identities')
            self.observed_click(SEED,{'identifier':'wallpaper_denied'});seed_rows(self.read_log(26),self.run,denial=True)
            normal,after=self.token('seed',SET)
            if normal['grant']!=-1:raise ValueError('ordinary caller gained wallpaper permission')
            write_json(destination,{'run_id':self.run,'boot_id':self.boot_id,'token_query':after,
                                    'settings_token_query':provider,'before_normal_token':before})
        elif action=='delete-only-created-Photos-assets-via-real-UI':
            destination=self.receipt(request,'cleanup-observation.json');before=self.query_assets('before')
            actions=[];selections=[]
            for case in CASES:
                self.show_photos_gallery()
                end=min(time.monotonic()+30,self.deadline or float('inf'))
                while time.monotonic()<end:
                    try:
                        tree,path=self.ui.layout(label='real-gallery-challenge');image=self.ui.screenshot(label='real-gallery-challenge')
                        node,metrics=thumbnail(tree,image,checked(self.challenge['images'][case]),owner=PHOTOS);break
                    except (LayoutNotReady,NodeNotReady):time.sleep(.2)
                else:raise ValueError('exact fresh Photo thumbnail unavailable for deletion')
                x,y,w,h=node['rect'];self.shell(f'uitest uiInput click {x+w//2} {y+h//2}','open-only-challenged-photo')
                selections.append({'case':case,'layout':record(path),'screenshot':record(image),'node':node,'metrics':metrics})
                for selector in self.plan.get('photo_browser_navigation',[]):self.observed_click(PHOTOS,selector)
                actions.append(self.observed_click(PHOTOS,{'identifier':'ToolBarButtonDelete'}))
                actions.append(self.observed_click(PHOTOS,{'identifier':'advanced_dialog_button_1'}))
            after=self.query_assets('after')
            write_json(destination,{'run_id':self.run,'boot_id':self.boot_id,'deleted_uris':self.uris,
                'actual_asset_query':after,'before_asset_query':before,'ui_actions':actions,'challenge_selections':selections,
                'raw_query_evidence':self.value['queries']})
        elif action=='remove-owned-seed-private-inputs':
            if request['details']!={'bundle':SEED}:raise ValueError('unexpected cleanup bundle')
            base='/data/app/el2/100/base/'+SEED+'/files/'
            for case in CASES:
                path=base+case+'.png';actual=self.receive(path,'before-own-private-delete-'+case)
                if actual['file']['sha256']!=self.challenge['images'][case]['sha256']:raise ValueError('refuse removal of unrelated private input')
                self.shell('rm '+shlex.quote(path)+' && test ! -e '+shlex.quote(path),'remove-only-owned-private-challenge')
        else:raise ValueError('unhandled root request')

    def run_requests(self):
        directory=self.args.actions
        if directory.is_symlink()or not directory.is_dir()or directory.stat().st_uid!=os.getuid():raise ValueError('owned request directory required')
        self.wake_if_asleep('start-requested-coordinator-interaction')
        self.guest.start()
        for sequence in range(1,22):
            waiting=time.monotonic()+self.args.idle_seconds; request=None; path=None
            while time.monotonic()<waiting:
                matches=list(directory.glob(self.run+f'-{sequence:03}-*.request.json'))
                if len(matches)>1:raise ValueError('multiple requests for one operation')
                if matches:
                    path=matches[0]
                    try:request=request_file(path,self.run,self.boot_id,sequence);break
                    except NodeNotReady:pass
                time.sleep(.1)
            if request is None:raise ValueError('no complete next root request before bounded idle deadline')
            self.deadline=time.monotonic()+self.args.action_seconds
            row={'request':record(path),'sequence':sequence,'action':request['action'],'began_ns':time.monotonic_ns()}
            self.value['actions'].append(row);self.wake_if_asleep('before-requested-action-'+str(sequence));self.identity('coordinator-before-'+str(sequence))
            row['power_before']=self.power_state('action-'+str(sequence)+'-power-before')
            self.dispatch(request);self.remaining();self.identity('coordinator-after-'+str(sequence))
            row['power_after']=self.power_state('action-'+str(sequence)+'-power-after')
            row['finished_ns']=time.monotonic_ns();row['ack']=publish_ack(path.with_name(path.name.replace('.request.json','.ack.json')),request)
            self.save();self.deadline=None
        self.value['status']='completed_actions_NOT_runtime_acceptance';self.save()

    def power_state(self,label):
        from power_test_policy import power_timeout
        raw=self.shell('hidumper -s 3301 -a "-a"',label)
        return {'raw':self.text(raw,label),'state':power_timeout(raw)}


def visible_bundle(tree,bundle):
    pending=[(v,'')for v in(tree if isinstance(tree,list)else[tree])];count=0
    while pending:
        node,parent=pending.pop();count+=1
        if count>100000 or not isinstance(node,dict):raise ValueError('invalid UI hierarchy')
        attrs=node.get('attributes',{});owner=attrs.get('bundleName')or parent
        if owner==bundle and attrs.get('visible')=='true':return True
        pending.extend((child,owner)for child in node.get('children',[]))
    return False


def ready_node(tree,bundle,**selector):
    try:return select_node(tree,bundle,**selector)
    except ValueError as error:
        if str(error)in ('selected UITest node is not actually visible','selected UITest node is not an enabled clickable control'):
            raise NodeNotReady(str(error))from error
        raise


def read_permission_node(tree,label):
    values=json.loads((FIXTURE/'read-permission-resources.json').read_text())
    candidates=[]
    for locale in values['locales']:
        title=locale['title'].replace('%s',label)
        try:
            ready_node(tree,'com.ohos.permissionmanager',text=title)
            selected=ready_node(tree,'com.ohos.permissionmanager',text=locale['allow'],clickable=True)
        except NodeNotReady:continue
        candidates.append((selected,locale))
    if len(candidates)!=1:raise NodeNotReady('one actual caller-named photo read permission and Allow action required')
    return candidates[0]


def settings_foreground(dump,uid):
    apps=re.split(r'(?=^    AppRunningRecord ID #)',dump,flags=re.M)
    return len([app for app in apps if f'process name [{SETTINGS}]'in app and 'state #FOREGROUND'in app and
                re.search(r'^      pid #[1-9][0-9]*  uid #'+str(uid)+r'$',app,re.M)])==1


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    prepare=sub.add_parser('prepare-query');prepare.add_argument('--challenge',type=Path,required=True);prepare.add_argument('--output',type=Path,required=True)
    run=sub.add_parser('run')
    for name in ('boot','archive','challenge','plan','inputs','output','runtime-output','actions'):run.add_argument('--'+name,type=Path,required=True)
    run.add_argument('--hdc',required=True);run.add_argument('--install-callers',action='store_true')
    run.add_argument('--action-seconds',type=int,default=80);run.add_argument('--idle-seconds',type=int,default=180)
    args=parser.parse_args()
    if args.mode=='prepare-query':
        challenge=json.loads(args.challenge.read_text());check_challenge(challenge);args.output.mkdir(parents=True,exist_ok=False)
        path=args.output/'Index.ets';path.write_text((FIXTURE/'Query.ets').read_text().replace('__WALLPAPER_RUN__',challenge['run_id']))
        write_json(args.output/'contract.json',{'run_id':challenge['run_id'],'bundle':QUERY,'required_apl':'system_basic',
            'request_permissions':[READ],'source':record(path),'template':record(FIXTURE/'Query.ets')});print(path);return 0
    if not 1<=args.action_seconds<=175 or not 1<=args.idle_seconds<=600:parser.error('bounded action/idle deadlines required')
    coordinator=None
    try:
        coordinator=Coordinator(args);coordinator.run_requests();return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError)as error:
        if coordinator:
            coordinator.value['status']='fail';coordinator.value['failures'].append(type(error).__name__+': '+str(error));coordinator.save()
        print(type(error).__name__+': '+str(error));return 1


if __name__=='__main__':raise SystemExit(main())
