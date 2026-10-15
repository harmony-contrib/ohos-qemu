"""Bind exact typed Settings compilation, installation, actions and native proof."""
import copy
import json
from pathlib import Path
import re
import zipfile
from build_settings_all_navigation_probe import BUNDLE, SCOPE, CONTRACTS, verify_inputs
from guest_ui import select_node
import math
from settings_all_navigation_runtime import observation
from verify_settings_navigation_results import settings_identity
from insight_contract_common import checked_file, identity
from run_root_probe import digest
from sign_ethernet_control_probe import configure_profile
from verify_settings_all_navigation_results import verify_rows, supported_routes, ROUTES, PARAMETERS


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status')!='pass' or document.get('scope')!=SCOPE or document.get('failures')!=[] or
        document.get('archive_sha256')!=archive_sha or document.get('boot_id')!=boot_id or
        document.get('arch')!=arch or document.get('device')!=device or document.get('target')!=target or
        document.get('caller_cleanup_verified') is not True or document.get('contracts')!=CONTRACTS or
        re.fullmatch('[0-9a-fA-F]{64}',document.get('udid','')) is None):
        raise ValueError('complete typed Settings proof on the exact packaged guest required')
    app=document['application'];paths={key:checked_file(app[key]) for key in
        ('inputs','signed_hap','unsigned_hap','signing_receipt','application_identity')}
    inputs=json.loads(paths['inputs'].read_text());verify_inputs(inputs)
    nonce=document['run_id']
    if inputs['run_id']!=nonce or inputs['arch']!=arch or inputs['project']!=app['project']:
        raise ValueError('settings_all caller nonce/ABI/project differs')
    uid=identity(paths['application_identity'].read_text(),BUNDLE,'normal')
    if app['actual_uid']!=uid:raise ValueError('actual settings_all BMS UID differs')
    signing=json.loads(paths['signing_receipt'].read_text())
    with zipfile.ZipFile(paths['unsigned_hap']) as unsigned,zipfile.ZipFile(paths['signed_hap']) as signed:
        if len(signed.namelist())!=len(set(signed.namelist())):raise ValueError('duplicate signed settings_all HAP entries')
        # The pinned PageInfoGenerator adds the executable-page bitmap for code signing.
        if (set(signed.namelist())!=set(unsigned.namelist())|{'.pages.info'} or
            not signed.read('.pages.info') or len(signed.read('.pages.info'))%8!=0):
            raise ValueError('signed settings_all HAP file set changed')
        for name in unsigned.namelist():
            if unsigned.read(name)!=signed.read(name):raise ValueError('signing changed the compiled settings_all caller')
        compiled=json.loads(signed.read('module.json'));abc=signed.read('ets/modules.abc')
        if len(abc)<1000:raise ValueError('actual settings_all compiled ABC missing')
    profile=signing.get('verified_profile',{})
    if (signing.get('status')!='pass' or signing.get('role')!='normal' or
        signing.get('scope')!='actual_signature_profile_and_codesign_NOT_guest' or
        signing.get('signed_sha256')!=digest(paths['signed_hap']) or
        signing.get('unsigned_sha256')!=digest(paths['unsigned_hap']) or
        compiled['module'].get('deviceTypes')!=['default'] or
        compiled['module'].get('requestPermissions')!=[] or
        configure_profile(copy.deepcopy(profile),'normal',document['udid'],compiled)!=profile):
        raise ValueError('exact ordinary device-bound settings_all signature required')
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
            raise ValueError('actual settings_all command journal changed or malformed')
        commands.append((path.name.split('-',1)[1][:-4],row,path.read_text().replace('\r','')))
        previous_command_end=row['finished_monotonic']
    def one(label):
        matches=[(i,row,reply) for i,(name,row,reply) in enumerate(commands) if name==label]
        if len(matches)!=1 or matches[0][1]['exit_code']!=0:raise ValueError('one successful settings_all command required: '+label)
        return matches[0]
    def shell(label,script,expected=None):
        index,row,reply=one(label);argv=row['argv']
        if (len(argv)!=5 or argv[:4]!=[hdc,'-t',target,'shell'] or
            not argv[4].startswith(script+'; task_settings_all_rc=$?; printf "\\n__SETTINGS_ALL_SHELL_EXIT_')):
            raise ValueError('actual settings_all script/transport differs: '+label)
        match=re.search(r'(?:^|\n)__SETTINGS_ALL_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
        actual=reply[:match.start()] if match else None
        correct=(actual is not None and actual.split()==expected.split()) if label=='guest-identity' else (actual is not None and (expected is None or actual==expected))
        if not match or not correct:raise ValueError('settings_all observation lacks actual successful guest origin: '+label)
        return index,row
    _,build,build_log=one('build-real-settings_all-caller')
    expected_args=['--sdk',inputs['sdk'],'--output',inputs['project'],'--arch',arch,'--run-id',nonce,
        '--hvigor-home',inputs['hvigor_home'],'--node-home',inputs['node_home']]
    if (build['argv'][1:]!=[str(Path(__file__).with_name('build_settings_all_navigation_probe.py')),*expected_args] or
        'CompileArkTS' not in build_log or 'BUILD SUCCESSFUL' not in build_log or '0 up-to-date' not in build_log):
        raise ValueError('fresh official checked settings_all compilation required')
    sign_index,sign,sign_log=one('sign-real-settings_all-caller');install_index,install,reply=one('install-real-settings_all-caller')
    if (sign_index>=install_index or sign['argv'][:3]!=['docker','run','--rm'] or
        sign['argv'][-4:]!=['--role','normal','--udid',document['udid']] or
        install['argv'][1:]!=['-t',target,'install',str(paths['signed_hap'])] or
        not re.search('success',reply,re.I) or re.search('failed to install',reply,re.I)):
        raise ValueError('actual signed settings_all installation required')
    if not all(marker in sign_log for marker in ('verify codesign success','Digest verify result: true',
        'verify-app success','verify permission sign success')):
        raise ValueError('actual settings_all code signature, digest and permissions not verified')
    identity_index,_=shell('actual-settings_all-BMS','bm dump -n '+BUNDLE,paths['application_identity'].read_text())
    if identity_index<=install_index:raise ValueError('settings_all identity preceded installation')
    shell('guest-identity','id -u; param get const.product.devicetype; uname -m',
        '0\n'+device+'\n'+{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[arch]+'\n')
    boot_before,_=shell('boot-before','cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    boot_final,_=shell('boot-final','cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    pid=document['cleanup']['actual_pid']
    if type(pid) is not int or pid<=0:raise ValueError('actual Settings PID required')
    settings_path=checked_file(document['settings_identity']);settings_uid=settings_identity(settings_path.read_text())
    if settings_uid!=document['settings_uid'] or settings_uid==uid:raise ValueError('actual Settings provider identity differs')
    provider_index,_=shell('actual-settings-provider-BMS','bm dump -n com.ohos.settings',settings_path.read_text())
    parameters=document['parameters'];support=supported_routes(device,parameters)
    if document['supported_routes']!=support:raise ValueError('actual source profile boundary summary differs')
    for parameter in PARAMETERS:
        index,row,reply=one('actual-parameter-'+parameter)
        prefix='param get '+parameter+'; task_settings_all_rc=$?; printf "\\n__SETTINGS_ALL_SHELL_EXIT_'
        if row['argv'][:4]!=[hdc,'-t',target,'shell'] or not row['argv'][4].startswith(prefix):
            raise ValueError('actual Settings parameter read origin differs')
        match=re.search(r'(?:^|\n)__SETTINGS_ALL_SHELL_EXIT_[a-f0-9]{32}__=([01])\s*$',reply)
        if not match or reply[:match.start()].strip()!=parameters[parameter]:raise ValueError('actual Settings parameter readback differs')
        if match.group(1)!='0' and parameters[parameter]!='Get parameter "'+parameter+'" fail! errNum is:106!':
            raise ValueError('failed Settings parameter query cannot imply support')
    strings=json.loads((Path(inputs['project'])/'AppScope/resources/base/element/string.json').read_text())['string']
    app_label=next(item['value'] for item in strings if item['name']=='app_name')
    if app_label!=document['app_label']:raise ValueError('actual compiled Settings caller label differs')
    remote='/data/app/el2/100/base/'+BUNDLE+'/files/settings-navigation-'+nonce+'-results.log'
    startup_path=checked_file(document['startup']);last=startup_path.read_text()
    initial=verify_rows(last,nonce,uid,pid,startup=True);methods=initial['methods']
    startup_index,_=shell('startup-final-journal','cat '+remote,last)
    fresh_index,_=shell('fresh-journal-absence','test ! -e '+remote,'')
    start_index,_=shell('start-real-settings_all-caller','aa start -a EntryAbility -b '+BUNDLE)
    running=[]
    for label,row,reply in commands:
        if label.startswith('running-pid-'):
            match=re.search(r'(?:^|\n)__SETTINGS_ALL_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
            if match and reply[:match.start()].strip()==str(pid):
                index,_=shell(label,'pidof '+BUNDLE+' || true',reply[:match.start()]);running.append(index)
    if len(running)!=1 or not start_index<running[0]<startup_index:
        raise ValueError('Settings native PID lacks actual started process origin')
    if not boot_before<install_index<identity_index<fresh_index<start_index<startup_index<provider_index:
        raise ValueError('actual Settings installation/freshness/startup order differs')
    phases=document['phases'];expected=[str(cycle)+':'+route for cycle in (1,2) for route in ROUTES]
    if list(phases)!=expected:raise ValueError('complete ordered two-round Settings route proof required')
    previous=startup_index
    def ui_origin(record):
        ui_path=checked_file(record);layout=json.loads(ui_path.read_text());sequence=str(int(ui_path.name.split('-',1)[0]))
        matches=[]
        for i,(label,row,reply) in enumerate(commands):
            match=re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)
            if (row['exit_code']==0 and row['argv'][:4]==[hdc,'-t',target,'shell'] and
                re.match(r'cat /data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-'+sequence+r'\.json; task_ui_rc=\$\?;',row['argv'][4]) and
                match and json.loads(reply[:match.start()])==layout):matches.append(i)
        if len(matches)!=1:raise ValueError('Settings hierarchy lacks its exact actual guest origin')
        return matches[0],layout
    def presentation(value,route,is_supported,lower):
        if (value.get('status')!='pass_presentation_only' or value.get('timeout_seconds')!=60 or
            type(value.get('started')) not in (int,float) or type(value.get('deadline')) not in (int,float) or
            not math.isfinite(value['started']) or not math.isfinite(value['deadline']) or
            value['deadline']!=value['started']+60 or len(value.get('samples',[]))<3):
            raise ValueError('bounded actual Settings stable presentation required')
        if value['started']<commands[lower][1]['finished_monotonic']:
            raise ValueError('Settings presentation window preceded its actual request/result')
        previous_after=value['started'];seen=set()
        for sample in value['samples']:
            before,after=sample.get('started'),sample.get('finished')
            if (type(before) not in (int,float) or type(after) not in (int,float) or
                not math.isfinite(before) or not math.isfinite(after) or before<previous_after or after<before or
                after>value['deadline']):raise ValueError('Settings capture timing invalid or extended')
            previous_after=after
            for field in ('layout','screenshot','AMS'):
                if field in sample:
                    path=checked_file(sample[field])
                    if str(path) in seen:raise ValueError('Settings reused a presentation file')
                    seen.add(str(path))
        fingerprints=[];upper=lower
        for sample in value['samples'][-3:]:
            if sample.get('not_ready'):raise ValueError('Settings final presentation remained unready')
            hierarchy_index,layout=ui_origin(sample['layout']);picture=checked_file(sample['screenshot']);ams=checked_file(sample['AMS'])
            actual=observation(layout,picture,ams.read_text(),route,is_supported,nonce,methods,app_label,settings_uid,uid,pid)
            if actual!=sample.get('observation'):raise ValueError('Settings painting/provider summary differs from real capture')
            transfers=[(i,row) for i,(label,row,reply) in enumerate(commands) if row['exit_code']==0 and
                len(row['argv'])==7 and row['argv'][:5]==[hdc,'-t',target,'file','recv'] and row['argv'][6]==str(picture)]
            if len(transfers)!=1:raise ValueError('Settings actual compositor transfer missing')
            transfer_index,transfer=transfers[0];remote_picture=transfer['argv'][5]
            if not re.fullmatch(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[0-9]+\.png',remote_picture):
                raise ValueError('Settings pixels came from a foreign remote source')
            script='test ! -e '+remote_picture+' && uitest screenCap -p '+remote_picture+'; task_ui_rc=$?;'
            captures=[i for i,(label,row,reply) in enumerate(commands) if row['exit_code']==0 and
                row['argv'][:4]==[hdc,'-t',target,'shell'] and row['argv'][4].startswith(script) and
                re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)]
            if len(captures)!=1:raise ValueError('Settings actual compositor capture missing')
            ams_index,_=shell(sample['label']+'-AMS-'+str(value['samples'].index(sample)+1),'aa dump -a -u 100',ams.read_text())
            if not upper<hierarchy_index<captures[0]<transfer_index<ams_index:raise ValueError('Settings capture/provider commands unordered')
            if (sample['started']>commands[hierarchy_index][1]['started_monotonic'] or
                sample['finished']<commands[ams_index][1]['finished_monotonic']):
                raise ValueError('Settings frame timing differs from actual commands')
            fingerprints.append((actual['node']['rect'],actual['node']['attributes']['text'],actual['binding'],actual['pixels']['crop_sha256']))
            upper=max(upper,ams_index)
        if not fingerprints[0]==fingerprints[1]==fingerprints[2]:raise ValueError('Settings page did not paint three stable requested frames')
        return upper
    for key in expected:
        cycle,route=key.split(':',1);prefix='settings-all-'+cycle+'-'+route;phase=phases[key]
        if phase['supported'] is not support[route]:raise ValueError('Settings route support summary changed')
        action=phase['action'];hierarchy_index,layout=ui_origin({'path':action['layout'],'sha256':action['layout_sha256']})
        node=select_node(layout,BUNDLE,identifier='settings-probe-'+route,clickable=True)
        if node!=action['selected_node'] or action['identifier']!='settings-probe-'+route or action['label']!=prefix:
            raise ValueError('Settings action selected another native control')
        x,y,w,h=node['rect'];click_index,click,reply=one(prefix+'-actual-node-center')
        if (not previous<hierarchy_index<click_index or click['argv'][:4]!=[hdc,'-t',target,'shell'] or
            not click['argv'][4].startswith('uitest uiInput click '+str(x+w//2)+' '+str(y+h//2)+'; task_ui_rc=$?;') or
            not re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)):raise ValueError('Settings native click origin/order differs')
        path=checked_file(phase['journal']);raw=path.read_text()
        if not raw.startswith(last) or len(raw.splitlines())!=len(last.splitlines())+1:raise ValueError('Settings native journal replaced or reordered')
        candidates=[]
        for label,row,reply in commands:
            if label.startswith(prefix+'-poll-'):
                match=re.search(r'(?:^|\n)__SETTINGS_ALL_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
                if match and reply[:match.start()]==raw:candidates.append(label)
        if len(candidates)!=1:raise ValueError('Settings route lacks its exact native journal read')
        read_index,_=shell(candidates[0],'cat '+remote,raw)
        if read_index<=click_index:raise ValueError('Settings route result preceded request')
        end=presentation(phase['presentation'],route,support[route],read_index)
        if support[route]:
            back_index,_=shell(prefix+'-back','uitest uiInput keyEvent Back')
            if back_index<=end:raise ValueError('Settings Back preceded actual provider presentation')
            end=back_index
        elif any(label==prefix+'-back' for label,row,reply in commands):raise ValueError('unsupported Settings boundary falsely sent Back')
        end=presentation(phase['returned'],route,False,end)
        boot_index,_=shell(prefix+'-same-boot','cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
        if boot_index<=end:raise ValueError('Settings boot preservation not observed after return')
        previous=boot_index;last=raw
    final=checked_file(document['actual_results'])
    if final.read_text()!=last or document['native_results']!=verify_rows(last,nonce,uid,pid):raise ValueError('Settings final native results differ')
    quiet_index,quiet=shell('final-journal-quiet','cat '+remote,last)
    if (type(document.get('quiet_seconds')) not in (int,float) or
        not math.isfinite(document['quiet_seconds']) or document['quiet_seconds']<2 or
        quiet['started_monotonic']-commands[previous][1]['finished_monotonic']<2):
        raise ValueError('Settings actual final quiet interval missing')
    if document['cleanup']!=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True):raise ValueError('Settings actual caller cleanup differs')
    stop_index,_=shell('stop-owned-settings_all-caller','aa force-stop '+BUNDLE,'force stop process successfully.\n')
    name_index,_=shell('cleanup-name-absence','pidof '+BUNDLE+' || true','')
    absence_index,_=shell('cleanup-actual-pid-absence','test ! -e /proc/'+str(pid),'')
    if not quiet_index<boot_final<stop_index<name_index<absence_index:
        raise ValueError('Settings actual stop/exit provenance is unordered')
    return CONTRACTS
