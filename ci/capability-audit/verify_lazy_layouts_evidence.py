"""Bind exact typed lazy waterflow/dynamic compilation, installation, actions and native proof."""
import copy
import json
from pathlib import Path
import re
import zipfile
from build_arkui_lazy_layouts_probe import BUNDLE, SCOPE, CONTRACTS, verify_inputs
from guest_ui import select_node
from insight_contract_common import checked_file, identity
from run_root_probe import digest
from sign_ethernet_control_probe import configure_profile
from verify_lazy_layouts_results import rows, verify, verify_presentations


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status')!='pass' or document.get('scope')!=SCOPE or document.get('failures')!=[] or
        document.get('archive_sha256')!=archive_sha or document.get('boot_id')!=boot_id or
        document.get('arch')!=arch or document.get('device')!=device or document.get('target')!=target or
        document.get('caller_cleanup_verified') is not True or document.get('contracts')!=CONTRACTS or
        re.fullmatch('[0-9a-fA-F]{64}',document.get('udid','')) is None):
        raise ValueError('complete typed lazy waterflow/dynamic proof on the exact packaged guest required')
    app=document['application'];paths={key:checked_file(app[key]) for key in
        ('inputs','signed_hap','unsigned_hap','signing_receipt','application_identity')}
    inputs=json.loads(paths['inputs'].read_text());verify_inputs(inputs)
    nonce=document['run_id']
    if inputs['run_id']!=nonce or inputs['arch']!=arch or inputs['project']!=app['project']:
        raise ValueError('lazy caller nonce/ABI/project differs')
    uid=identity(paths['application_identity'].read_text(),BUNDLE,'normal')
    if app['actual_uid']!=uid:raise ValueError('actual lazy BMS UID differs')
    signing=json.loads(paths['signing_receipt'].read_text())
    with zipfile.ZipFile(paths['unsigned_hap']) as unsigned,zipfile.ZipFile(paths['signed_hap']) as signed:
        if len(signed.namelist())!=len(set(signed.namelist())):raise ValueError('duplicate signed lazy HAP entries')
        # The pinned PageInfoGenerator adds the executable-page bitmap for code signing.
        if (set(signed.namelist())!=set(unsigned.namelist())|{'.pages.info'} or
            not signed.read('.pages.info') or len(signed.read('.pages.info'))%8!=0):
            raise ValueError('signed lazy HAP file set changed')
        for name in unsigned.namelist():
            if unsigned.read(name)!=signed.read(name):raise ValueError('signing changed the compiled lazy caller')
        compiled=json.loads(signed.read('module.json'));abc=signed.read('ets/modules.abc')
        if len(abc)<1000:raise ValueError('actual lazy compiled ABC missing')
    profile=signing.get('verified_profile',{})
    if (signing.get('status')!='pass' or signing.get('role')!='normal' or
        signing.get('scope')!='actual_signature_profile_and_codesign_NOT_guest' or
        signing.get('signed_sha256')!=digest(paths['signed_hap']) or
        signing.get('unsigned_sha256')!=digest(paths['unsigned_hap']) or
        compiled['module'].get('deviceTypes')!=['default'] or
        configure_profile(copy.deepcopy(profile),'normal',document['udid'],compiled)!=profile):
        raise ValueError('exact ordinary device-bound lazy signature required')
    commands=[]
    for row in document.get('commands',[]):
        path=Path(row['log'])
        if (path.is_symlink() or digest(path)!=row['sha256'] or type(row['exit_code']) is not int or
            row.get('timed_out') or not isinstance(row.get('argv'),list) or
            any(type(arg) is not str for arg in row['argv']) or
            not isinstance(row.get('started_monotonic'),(int,float)) or
            row.get('finished_monotonic',0)<row['started_monotonic']):
            raise ValueError('actual lazy command journal changed or malformed')
        commands.append((path.name.split('-',1)[1][:-4],row,path.read_text().replace('\r','')))
    def one(label):
        matches=[(i,row,reply) for i,(name,row,reply) in enumerate(commands) if name==label]
        if len(matches)!=1 or matches[0][1]['exit_code']!=0:raise ValueError('one successful lazy command required: '+label)
        return matches[0]
    def shell(label,script,expected):
        index,row,reply=one(label);argv=row['argv']
        if (len(argv)!=5 or argv[1:4]!=['-t',target,'shell'] or
            not argv[4].startswith(script+'; task_lazy_rc=$?; printf "\\n__LAZY_SHELL_EXIT_')):
            raise ValueError('actual lazy script/transport differs: '+label)
        match=re.search(r'(?:^|\n)__LAZY_SHELL_EXIT_[a-f0-9]{32}__=0\s*$',reply)
        actual=reply[:match.start()] if match else None
        correct=(actual is not None and actual.split()==expected.split()) if label=='guest-identity' else actual==expected
        if not match or not correct:raise ValueError('lazy observation lacks actual successful guest origin: '+label)
        return index,row
    _,build,build_log=one('build-real-lazy-caller')
    expected_args=['--sdk',inputs['sdk'],'--output',inputs['project'],'--arch',arch,'--run-id',nonce,
        '--hvigor-home',inputs['hvigor_home'],'--node-home',inputs['node_home']]
    if (build['argv'][1:]!=[str(Path(__file__).with_name('build_arkui_lazy_layouts_probe.py')),*expected_args] or
        'CompileArkTS' not in build_log or 'BUILD SUCCESSFUL' not in build_log or '0 up-to-date' not in build_log):
        raise ValueError('fresh official checked lazy compilation required')
    sign_index,sign,sign_log=one('sign-real-lazy-caller');install_index,install,reply=one('install-real-lazy-caller')
    if (sign_index>=install_index or sign['argv'][:3]!=['docker','run','--rm'] or
        sign['argv'][-4:]!=['--role','normal','--udid',document['udid']] or
        install['argv'][1:]!=['-t',target,'install',str(paths['signed_hap'])] or
        not re.search('success',reply,re.I) or re.search('failed to install',reply,re.I)):
        raise ValueError('actual signed lazy installation required')
    if not all(marker in sign_log for marker in ('verify codesign success','Digest verify result: true',
        'verify-app success','verify permission sign success')):
        raise ValueError('actual lazy code signature, digest and permissions not verified')
    identity_index,_=shell('actual-lazy-BMS','bm dump -n '+BUNDLE,paths['application_identity'].read_text())
    if identity_index<=install_index:raise ValueError('lazy identity preceded installation')
    shell('guest-identity','id -u; param get const.product.devicetype; uname -m',
        '0\n'+device+'\n'+{'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[arch]+'\n')
    for label in ('boot-before','boot-final'):shell(label,'cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    remote='/data/app/el2/100/base/'+BUNDLE+'/files/arkui-lazy-layouts-'+nonce+'-results.log'
    phases=document['phases'];verify_presentations(phases,nonce);last='';pid=None;previous_phase_end=identity_index
    def actual_ui_read(label,expected_layout):
        matches=[(i,row,reply) for i,(name,row,reply) in enumerate(commands) if name==label and row['exit_code']==0]
        linked=[]
        for index,row,reply in matches:
            argv=row['argv'];match=re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)
            if (len(argv)==5 and argv[1:4]==['-t',target,'shell'] and
                argv[4].startswith('cat /data/local/tmp/qemu-capability-ui-') and match and
                json.loads(reply[:match.start()])==expected_layout):linked.append(index)
        if len(linked)!=1:raise ValueError('exact lazy action hierarchy lacks actual guest origin')
        return linked[0]
    for kind in ('water','dynamic'):
      for cycle in (0,1):
        for phase in ('initial','changed','bottom','top','removed'):
            record=phases[kind+':'+str(cycle)+':'+phase];path=checked_file(record['journal']);raw=path.read_text()
            label='lazy-journal-'+kind+'-'+str(cycle)+'-'+phase
            read_index,read_command=shell(label,'cat '+remote,raw)
            if not raw.startswith(last):raise ValueError('lazy journal lost its actual append-only history')
            parsed=rows(raw,nonce,uid);pid=parsed[0]['values'][2];last=raw
            click=record['click'];layout=Path(click['layout']);actual=json.loads(layout.read_text())
            identifier={'initial':'lazy-layouts-'+kind,'changed':'lazy-layouts-change','bottom':'lazy-layouts-last',
                'top':'lazy-layouts-first','removed':'lazy-layouts-remove'}[phase]
            node=select_node(actual,BUNDLE,identifier=identifier,clickable=True)
            if node!=click['selected_node']:raise ValueError('lazy action used a foreign UI control')
            x,y,w,h=node['rect'];script='uitest uiInput click '+str(x+w//2)+' '+str(y+h//2)
            prefix='lazy-create-'+kind+'-'+str(cycle) if phase=='initial' else 'lazy-'+kind+'-'+str(cycle)+'-'+phase
            action_index,action,reply=one(prefix+'-actual-node-center')
            hierarchy_index=actual_ui_read(prefix+'-read',actual)
            if (not previous_phase_end<hierarchy_index<action_index<read_index or
                len(action['argv'])!=5 or action['argv'][1:4]!=['-t',target,'shell'] or
                not action['argv'][4].startswith(script+'; task_ui_rc=$?;') or
                not re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)):
                raise ValueError('lazy action lacks its ordered actual successful UITest click')
            previous_phase_end=read_index
            if phase=='removed':
                quiet_index,quiet=shell('lazy-quiet-'+kind+'-'+str(cycle),'cat '+remote,raw)
                if (record.get('quiet_seconds',0)<2 or record.get('quiet_journal_sha256')!=digest(path) or
                    quiet['started_monotonic']-read_command['finished_monotonic']<2):
                    raise ValueError('actual post-removal callback quiet interval missing')
                previous_phase_end=quiet_index
            for sample in record['presentation']['samples'][-3:]:
                picture=checked_file(dict(path=sample['screenshot'],sha256=sample['screenshot_sha256']))
                ui_path=checked_file(dict(path=sample['layout'],sha256=sample['layout_sha256']))
                actual=json.loads(ui_path.read_text());found=False
                for name,row,reply in commands:
                    argv=row['argv'];match=re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$',reply)
                    if (row['exit_code']==0 and len(argv)==5 and argv[1:4]==['-t',target,'shell'] and
                        argv[4].startswith('cat /data/local/tmp/qemu-capability-ui-') and match and
                        json.loads(reply[:match.start()])==actual):found=True;break
                if not found:raise ValueError('lazy UI hierarchy lacks actual guest origin')
                transfers=[row for name,row,reply in commands if row['exit_code']==0 and len(row['argv'])==7 and
                    row['argv'][1:5]==['-t',target,'file','recv'] and row['argv'][6]==str(picture) and
                    row['argv'][5].startswith('/data/local/tmp/qemu-capability-ui-')]
                if len(transfers)!=1:raise ValueError('lazy pixels lack actual compositor transfer')
    contracts=verify(last,nonce,uid)
    if document.get('cleanup')!=dict(process_absent=True,actual_pid=pid,actual_pid_absent=True):
        raise ValueError('actual lazy caller cleanup summary differs')
    shell('cleanup-name-absence','pidof '+BUNDLE+' || true','')
    shell('cleanup-actual-pid-absence','test ! -e /proc/'+str(pid),'')
    return contracts
