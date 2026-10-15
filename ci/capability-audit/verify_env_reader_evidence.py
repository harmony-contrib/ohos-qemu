"""Bind exact typed environment/reader compilation, installation, actions and native proof."""
import copy
import json
from pathlib import Path
import re
import zipfile
from build_arkui_env_reader_probe import BUNDLE, SCOPE, CONTRACTS, verify_inputs
from guest_ui import select_node
from insight_contract_common import checked_file, identity
from run_root_probe import digest
from sign_ethernet_control_probe import configure_profile
from verify_env_reader_results import rows, verify, verify_presentations, READER_STEPS, ENV_PHASES


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status')!='pass' or document.get('scope')!=SCOPE or document.get('failures')!=[] or
        document.get('archive_sha256')!=archive_sha or document.get('boot_id')!=boot_id or
        document.get('arch')!=arch or document.get('device')!=device or document.get('target')!=target or
        document.get('caller_cleanup_verified') is not True or document.get('contracts')!=CONTRACTS or
        re.fullmatch('[0-9a-fA-F]{64}',document.get('udid','')) is None):
        raise ValueError('complete typed environment/reader proof on the exact packaged guest required')
    app=document['application'];paths={key:checked_file(app[key]) for key in
        ('inputs','signed_hap','unsigned_hap','signing_receipt','application_identity')}
    inputs=json.loads(paths['inputs'].read_text());verify_inputs(inputs)
    nonce=document['run_id']
    if inputs['run_id']!=nonce or inputs['arch']!=arch or inputs['project']!=app['project']:
        raise ValueError('env_reader caller nonce/ABI/project differs')
    uid=identity(paths['application_identity'].read_text(),BUNDLE,'normal')
    if app['actual_uid']!=uid:raise ValueError('actual env_reader BMS UID differs')
    signing=json.loads(paths['signing_receipt'].read_text())
    with zipfile.ZipFile(paths['unsigned_hap']) as unsigned,zipfile.ZipFile(paths['signed_hap']) as signed:
        if len(signed.namelist())!=len(set(signed.namelist())):raise ValueError('duplicate signed env_reader HAP entries')
        # The pinned PageInfoGenerator adds the executable-page bitmap for code signing.
        if (set(signed.namelist())!=set(unsigned.namelist())|{'.pages.info'} or
            not signed.read('.pages.info') or len(signed.read('.pages.info'))%8!=0):
            raise ValueError('signed env_reader HAP file set changed')
        for name in unsigned.namelist():
            if unsigned.read(name)!=signed.read(name):raise ValueError('signing changed the compiled env_reader caller')
        compiled=json.loads(signed.read('module.json'));abc=signed.read('ets/modules.abc')
        if len(abc)<1000:raise ValueError('actual env_reader compiled ABC missing')
    profile=signing.get('verified_profile',{})
    if (signing.get('status')!='pass' or signing.get('role')!='normal' or
        signing.get('scope')!='actual_signature_profile_and_codesign_NOT_guest' or
        signing.get('signed_sha256')!=digest(paths['signed_hap']) or
        signing.get('unsigned_sha256')!=digest(paths['unsigned_hap']) or
        compiled['module'].get('deviceTypes')!=['default'] or
        configure_profile(copy.deepcopy(profile),'normal',document['udid'],compiled)!=profile):
        raise ValueError('exact ordinary device-bound env_reader signature required')
    hdc=str(checked_file(document['hdc']));commands=[]
    for row in document.get('commands',[]):
        path=Path(row['log'])
        if (path.is_symlink() or digest(path)!=row['sha256'] or type(row['exit_code']) is not int or
            row.get('timed_out') or not isinstance(row.get('argv'),list) or
            any(type(arg) is not str for arg in row['argv']) or
            not isinstance(row.get('started_monotonic'),(int,float)) or
            row.get('finished_monotonic',0)<row['started_monotonic']):
            raise ValueError('actual env_reader command journal changed or malformed')
        commands.append((path.name.split('-',1)[1][:-4],row,path.read_text().replace('\r','')))
    def one(label):
        matches=[(i,row,reply) for i,(name,row,reply) in enumerate(commands) if name==label]
        if len(matches)!=1 or matches[0][1]['exit_code']!=0:raise ValueError('one successful env_reader command required: '+label)
        return matches[0]
    def shell(label,script,expected=None):
        index,row,reply=one(label);argv=row['argv']
        if (len(argv)!=5 or argv[:4]!=[hdc,'-t',target,'shell'] or
            not argv[4].startswith(script+'; task_env_reader_rc=$?; printf "\\n__ENV_READER_SHELL_EXIT_')):
            raise ValueError('actual env_reader script/transport differs: '+label)
        match=re.search(r'(?:^|\n)__ENV_READER_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
        actual=reply[:match.start()] if match else None
        correct=(actual is not None and actual.split()==expected.split()) if label=='guest-identity' else (actual is not None and (expected is None or actual==expected))
        if not match or not correct:raise ValueError('env_reader observation lacks actual successful guest origin: '+label)
        return index,row
    _,build,build_log=one('build-real-env_reader-caller')
    expected_args=['--sdk',inputs['sdk'],'--output',inputs['project'],'--arch',arch,'--run-id',nonce,
        '--hvigor-home',inputs['hvigor_home'],'--node-home',inputs['node_home']]
    if (build['argv'][1:]!=[str(Path(__file__).with_name('build_arkui_env_reader_probe.py')),*expected_args] or
        'CompileArkTS' not in build_log or 'BUILD SUCCESSFUL' not in build_log or '0 up-to-date' not in build_log):
        raise ValueError('fresh official checked env_reader compilation required')
    sign_index,sign,sign_log=one('sign-real-env_reader-caller');install_index,install,reply=one('install-real-env_reader-caller')
    if (sign_index>=install_index or sign['argv'][:3]!=['docker','run','--rm'] or
        sign['argv'][-4:]!=['--role','normal','--udid',document['udid']] or
        install['argv'][1:]!=['-t',target,'install',str(paths['signed_hap'])] or
        not re.search('success',reply,re.I) or re.search('failed to install',reply,re.I)):
        raise ValueError('actual signed env_reader installation required')
    if not all(marker in sign_log for marker in ('verify codesign success','Digest verify result: true',
        'verify-app success','verify permission sign success')):
        raise ValueError('actual env_reader code signature, digest and permissions not verified')
    identity_index,_=shell('actual-env_reader-BMS','bm dump -n '+BUNDLE,paths['application_identity'].read_text())
    if identity_index<=install_index:raise ValueError('env_reader identity preceded installation')
    shell('guest-identity','id -u; param get const.product.devicetype; uname -m',
        '0\n'+device+'\n'+{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[arch]+'\n')
    for label in ('boot-before','boot-final'):shell(label,'cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    remote='/data/app/el2/100/base/'+BUNDLE+'/files/arkui-env-reader-'+nonce+'-results.log'
    phases=document['phases'];verify_presentations(phases,nonce,document['density']);last='';pid=None
    start_index,_=shell('start-real-env_reader-caller','aa start -a EntryAbility -b '+BUNDLE)
    if start_index<=identity_index:raise ValueError('environment/reader started before its installed identity')
    previous_phase_end=start_index
    def actual_ui_read(label,expected_layout):
        matches=[(i,row,reply) for i,(name,row,reply) in enumerate(commands) if name==label and row['exit_code']==0]
        linked=[]
        for index,row,reply in matches:
            argv=row['argv'];match=re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)
            if (len(argv)==5 and argv[:4]==[hdc,'-t',target,'shell'] and
                argv[4].startswith('cat /data/local/tmp/qemu-capability-ui-') and match and
                json.loads(reply[:match.start()])==expected_layout):linked.append(index)
        if len(linked)!=1:raise ValueError('exact env_reader action hierarchy lacks actual guest origin')
        return linked[0]
    for family in ('env','reader'):
        steps=[('initial','env-reader-env'),('updated','env-reader-update'),('font-reset','env-reader-font-reset'),
               ('removed','env-reader-remove')] if family=='env' else [
            *[(name,control) for name,control,_,_ in READER_STEPS],('removed','env-reader-remove')]
        for cycle in (0,1):
            for phase,control in steps:
                key=family+':'+str(cycle)+':'+phase;prefix='env-reader-'+key.replace(':','-');record=phases[key]
                path=checked_file(record['journal']);raw=path.read_text()
                read_index,read_command=shell(prefix+'-actual-native-journal','cat '+remote,raw)
                if not raw.startswith(last):raise ValueError('environment/reader journal lost append-only history')
                parsed=rows(raw,nonce,uid);pid=parsed[0]['values'][2];last=raw
                expected_actions=[(control,prefix)]
                if family=='env' and phase!='removed':
                    expected_actions += [('env-reader-'+label+'-observe',prefix+'-observe-'+label)
                                         for label in ('outer','inner','outside')]
                if len(record['actions'])!=len(expected_actions):raise ValueError('environment/reader action set differs')
                for click,(identifier,label) in zip(record['actions'],expected_actions):
                    actual=json.loads(Path(click['layout']).read_text())
                    node=select_node(actual,BUNDLE,identifier=identifier,clickable=True)
                    if node!=click['selected_node'] or click.get('identifier')!=identifier or click.get('label')!=label:
                        raise ValueError('environment/reader action used a foreign UI control')
                    x,y,w,h=node['rect'];script='uitest uiInput click '+str(x+w//2)+' '+str(y+h//2)
                    action_index,action,reply=one(label+'-actual-node-center')
                    hierarchy_index=actual_ui_read(label+'-read',actual)
                    if (not previous_phase_end<hierarchy_index<action_index<read_index or len(action['argv'])!=5 or
                            action['argv'][:4]!=[hdc,'-t',target,'shell'] or
                            not action['argv'][4].startswith(script+'; task_ui_rc=$?;') or
                            not re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)):
                        raise ValueError('environment/reader action lacks ordered actual UITest input')
                    previous_phase_end=action_index
                # Both the early density observation and final snapshot are
                # native reads of the same append-only nonce-scoped journal.
                early=[(i,row,reply) for i,(name,row,reply) in enumerate(commands)
                       if name==prefix+'-before-presentation' and row['exit_code']==0]
                if len(early)!=1:raise ValueError('actual UIContext density read missing')
                match=re.search(r'(?:^|\n)__ENV_READER_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',early[0][2])
                before=early[0][2][:match.start()] if match else ''
                early_index,_=shell(prefix+'-before-presentation','cat '+remote,before)
                early_rows=rows(before,nonce,uid)
                if not raw.startswith(before) or not previous_phase_end<early_index<read_index:
                    raise ValueError('environment/reader early native read changed or preceded its action')
                densities=[r['values'][0] for r in early_rows if r['name']=='density']
                if not densities or any(v!=document['density'] for v in densities):
                    raise ValueError('compositor density differs from actual owning UIContext')
                for sample in record['presentation']['samples'][-3:]:
                    picture=checked_file(dict(path=sample['screenshot'],sha256=sample['screenshot_sha256']))
                    ui_path=checked_file(dict(path=sample['layout'],sha256=sample['layout_sha256']))
                    actual=json.loads(ui_path.read_text());sequence=str(int(ui_path.name.split('-',1)[0]));reads=[]
                    for index,(name,row,reply) in enumerate(commands):
                        argv=row['argv'];match=re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)
                        if (row['exit_code']==0 and len(argv)==5 and argv[:4]==[hdc,'-t',target,'shell'] and
                                re.match(r'cat /data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-'+sequence+r'\.json; task_ui_rc=\$\?;',argv[4]) and
                                match and json.loads(reply[:match.start()])==actual):reads.append(index)
                    if len(reads)!=1:raise ValueError('exact environment/reader hierarchy lacks actual guest origin')
                    transfers=[(i,row) for i,(name,row,reply) in enumerate(commands) if row['exit_code']==0 and
                        len(row['argv'])==7 and row['argv'][:5]==[hdc,'-t',target,'file','recv'] and
                        row['argv'][6]==str(picture) and row['argv'][5].startswith('/data/local/tmp/qemu-capability-ui-')]
                    if len(transfers)!=1:raise ValueError('environment/reader pixels lack actual compositor transfer')
                    transfer_index,transfer=transfers[0];remote_picture=transfer['argv'][5]
                    capture_script='test ! -e '+remote_picture+' && uitest screenCap -p '+remote_picture+'; task_ui_rc=$?;'
                    captures=[i for i,(name,row,reply) in enumerate(commands) if row['exit_code']==0 and
                        len(row['argv'])==5 and row['argv'][:4]==[hdc,'-t',target,'shell'] and
                        row['argv'][4].startswith(capture_script) and re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)]
                    if len(captures)!=1 or not early_index<reads[0]<captures[0]<transfer_index<read_index:
                        raise ValueError('environment/reader pixels did not follow their actual phase action and native density read')
                previous_phase_end=read_index
                if phase=='removed':
                    quiet_index,quiet=shell(prefix+'-quiet','cat '+remote,raw)
                    if (record.get('quiet_seconds',0)<2 or record.get('quiet_journal_sha256')!=digest(path) or
                            quiet['started_monotonic']-read_command['finished_monotonic']<2):
                        raise ValueError('actual post-removal environment/reader quiet interval missing')
                    previous_phase_end=quiet_index
    contracts=verify(last,nonce,uid)
    if document.get('cleanup')!=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True):
        raise ValueError('actual env_reader caller cleanup summary differs')
    running=[(i,name) for i,(name,row,reply) in enumerate(commands) if name.startswith('running-pid-')]
    verified=[]
    for index,name in running:
        matches=[reply for label,row,reply in commands if label==name]
        match=re.search(r'(?:^|\n)__ENV_READER_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',matches[0])
        body=matches[0][:match.start()] if match else ''
        shell(name,'pidof '+BUNDLE+' || true',body)
        if body.strip()==str(pid):verified.append(index)
    if len(verified)!=1 or not start_index<verified[0]<previous_phase_end:
        raise ValueError('environment/reader journal PID lacks its actual started process')
    shell('cleanup-name-absence' ,'pidof '+BUNDLE+' || true','')
    shell('cleanup-actual-pid-absence','test ! -e /proc/'+str(pid),'')
    return contracts
