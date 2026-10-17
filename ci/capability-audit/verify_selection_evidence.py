"""Replay exact compiler, signed callers, consent, guest actions and clipboard proof."""
import json
from pathlib import Path
import re
from build_arkui_selection_probe import BUNDLE, SCOPE, ROLES, CONTRACTS
from guest_ui import select_node
from insight_contract_common import checked_file
from run_root_probe import digest, TRUSTED_SIGNER_IMAGE_ID, TRUSTED_SIGNER_SOURCE_VOLUME
from selection_contract_common import verify_application
from selection_menu_runtime import menu_button
from selection_permission_runtime import consent_node
from verify_selection_results import PHASES, rows, verify, verify_presentations

ROOT = Path(__file__).resolve().parents[2]


def selection_signing_argv(application, role, udid):
    if role not in ROLES or re.fullmatch('[a-fA-F0-9]{64}', udid) is None:
        raise ValueError('exact selection signing role and device required')
    unsigned = Path(application['unsigned_hap']['path'])
    signed = Path(application['signed_hap']['path'])
    if not unsigned.is_absolute() or not signed.is_absolute():
        raise ValueError('absolute selection HAP paths required')
    output = signed.parents[1]
    return ['docker','run','--rm','--platform','linux/amd64',
        '--mount','type=volume,src='+TRUSTED_SIGNER_SOURCE_VOLUME+',dst=/ohos,readonly',
        '--mount','type=bind,src='+str(ROOT)+',dst=/work,readonly',
        '--mount','type=bind,src='+str(output)+',dst=/probe',TRUSTED_SIGNER_IMAGE_ID,
        'python3','/work/ci/capability-audit/sign_arkui_selection_probe.py',
        '--signer-dist','/ohos/developtools/hapsigner/dist',
        '--jar','/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
        '--unsigned','/probe/'+unsigned.relative_to(output).as_posix(),
        '--output','/probe/'+signed.relative_to(output).as_posix(),'--role',role,'--udid',udid]


def verify_signing_installation(application, role, udid, hdc, target, build_index, signing, installation):
    sign_index, sign, sign_log = signing
    install_index, install, install_log = installation
    if (not build_index < sign_index < install_index or
            sign.get('exit_code') != 0 or install.get('exit_code') != 0 or
            sign['argv'] != selection_signing_argv(application, role, udid) or
            install['argv'] != [hdc,'-t',target,'install',application['signed_hap']['path']] or
            not re.search('success',install_log,re.I) or re.search('failed to install',install_log,re.I) or
            any(marker not in sign_log for marker in ('verify codesign success','Digest verify result: true',
                'verify-app success','verify permission sign success'))):
        raise ValueError('exact device-bound selection signature and actual installation required')


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status') != 'pass' or document.get('scope') != SCOPE or document.get('failures') != [] or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('target') != target or
            document.get('caller_cleanup_verified') is not True or document.get('contracts') != CONTRACTS or
            set(document.get('callers', {})) != set(ROLES) or
            re.fullmatch('[a-fA-F0-9]{64}', document.get('udid', '')) is None):
        raise ValueError('complete three-role selection proof on this exact package guest required')
    hdc = str(checked_file(document['hdc'])); commands = []
    for row in document.get('commands', []):
        path = Path(row['log']); argv = row['argv']
        if (path.is_symlink() or digest(path) != row['sha256'] or type(row['exit_code']) is not int or
                row.get('timed_out') or not isinstance(argv, list) or any(type(arg) is not str for arg in argv) or
                not isinstance(row.get('started_monotonic'), (int, float)) or
                row.get('finished_monotonic', 0) < row['started_monotonic']):
            raise ValueError('selection actual command journal changed or malformed')
        commands.append((path.name.split('-', 1)[1][:-4], row, path.read_text().replace('\r', '')))
    def one(label):
        matches = [(i, row, reply) for i, (name, row, reply) in enumerate(commands) if name == label]
        if len(matches) != 1 or matches[0][1]['exit_code'] != 0:
            raise ValueError('one successful actual selection command required: ' + label)
        return matches[0]
    def shell(label, script, expected=None):
        index, row, reply = one(label); argv = row['argv']
        if (argv[:4] != [hdc, '-t', target, 'shell'] or len(argv) != 5 or
                not argv[4].startswith(script + '; task_selection_rc=$?; printf "\\n__SELECTION_SHELL_EXIT_')):
            raise ValueError('selection actual script/transport differs: ' + label)
        match = re.search(r'(?:^|\n)__SELECTION_SHELL_EXIT_[a-f0-9]{32}__=0\s*$', reply)
        body = reply[:match.start()] if match else None
        if body is None or (expected is not None and body != expected):
            raise ValueError('selection observation lost its successful actual guest origin: ' + label)
        return index, body, row
    _, observed, _ = shell('guest-identity', 'id -u; param get const.product.devicetype; uname -m')
    if observed.split() != ['0', device, {'arm64':'aarch64','armv7a':'armv7l','x86_64':'x86_64'}[arch]]:
        raise ValueError('selection actual guest architecture/profile differs')
    shell('boot-before', 'cat /proc/sys/kernel/random/boot_id', boot_id + '\n')
    shell('boot-final', 'cat /proc/sys/kernel/random/boot_id', boot_id + '\n')
    def ui_read(path):
        path = Path(path); actual = json.loads(path.read_text())
        if path.is_symlink(): raise ValueError('regular selection UI hierarchy required')
        sequence = str(int(path.name.split('-', 1)[0])); matches = []
        for index, (name, row, reply) in enumerate(commands):
            argv = row['argv']
            if row['exit_code'] != 0 or len(argv) != 5 or argv[:4] != [hdc, '-t', target, 'shell']: continue
            if not re.match(r'cat /data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-' + sequence + r'\.json; task_ui_rc=\$\?;', argv[4]): continue
            match = re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$', reply)
            if match and json.loads(reply[:match.start()]) == actual: matches.append(index)
        if len(matches) != 1: raise ValueError('selection hierarchy lacks its exact successful guest read')
        return matches[0], actual
    def ui_action(action, kind, label, identifier=None, labels=None):
        if action.get('kind') != kind or action.get('label') != label:
            raise ValueError('selection action kind or challenge differs')
        hierarchy_index, layout = ui_read(action['layout'])
        if kind == 'control':
            if action.get('identifier') != identifier: raise ValueError('selection control identity differs')
            node = select_node(layout, BUNDLE, identifier=identifier, clickable=True)
            suffix = '-actual-node-center'; input_name = 'click'
        elif kind == 'menu':
            if action.get('menu_labels') != labels: raise ValueError('selection native menu labels differ')
            node = menu_button(layout, BUNDLE, labels); suffix = '-actual-menu-button-center'; input_name = 'click'
        elif kind == 'longpress':
            node = select_node(layout, BUNDLE, identifier='selection-alpha')
            suffix = '-actual-text-center'; input_name = 'longClick'
        else:
            node = consent_node(layout); suffix = '-actual-consent-button-center'; input_name = 'click'
            checked_file(dict(path=action['layout'],sha256=action['layout_sha256']))
            picture = checked_file(dict(path=action['screenshot'],sha256=action['screenshot_sha256']))
            compositor(picture)
        if action['selected_node'] != node: raise ValueError('selection action used a foreign or non-clickable node')
        x, y, w, h = node['rect']; script = 'uitest uiInput ' + input_name + ' ' + str(x + w // 2) + ' ' + str(y + h // 2)
        index, row, reply = one(label + suffix)
        if (not hierarchy_index < index or row['argv'][:4] != [hdc, '-t', target, 'shell'] or
                len(row['argv']) != 5 or not row['argv'][4].startswith(script + '; task_ui_rc=$?;') or
                not re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$', reply)):
            raise ValueError('selection action lacks its ordered successful actual UITest input')
        return hierarchy_index, index
    def compositor(path):
        sequence = str(int(Path(path).name.split('-', 1)[0])); matches = []
        for index, (name, row, reply) in enumerate(commands):
            argv = row['argv']
            if (row['exit_code'] == 0 and len(argv) == 7 and argv[:5] == [hdc, '-t', target, 'file', 'recv'] and
                    argv[6] == str(path) and re.fullmatch(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-' + sequence + r'\.png', argv[5])):
                captures = []
                for ci, (cn, cr, cp) in enumerate(commands[:index]):
                    ca = cr['argv']
                    if (cr['exit_code'] == 0 and len(ca) == 5 and ca[:4] == [hdc, '-t', target, 'shell'] and
                            ca[4].startswith('test ! -e ' + argv[5] + ' && uitest screenCap -p ' + argv[5] + '; task_ui_rc=$?;') and
                            re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=0\s*$', cp)):
                        captures.append(ci)
                if len(captures) == 1: matches.append((captures[0], index))
        if len(matches) != 1: raise ValueError('selection pixels lack their actual compositor capture and transfer')
        return matches[0]
    previous_role_end = -1
    for role in ROLES:
        caller = document['callers'][role]; nonce = caller['run_id']; app = caller['application']
        if caller.get('status') != 'pass' or caller.get('caller_cleanup_verified') is not True or caller.get('contracts') != CONTRACTS:
            raise ValueError('all three ordinary selection roles must pass completely')
        uid = verify_application(app, nonce, role, arch, document['udid'])
        inputs = json.loads(checked_file(app['inputs']).read_text())
        build_index, build, build_log = one(role + '-build-real-selection-caller')
        expected = ['--sdk',inputs['sdk'],'--output',inputs['project'],'--arch',arch,'--run-id',nonce,
            '--hvigor-home',inputs['hvigor_home'],'--node-home',inputs['node_home'],'--role',role]
        if (build_index <= previous_role_end or build['argv'][1:] != [str(ROOT/'ci/capability-audit/build_arkui_selection_probe.py'),*expected] or
                any(marker not in build_log for marker in ('CompileArkTS','BUILD SUCCESSFUL','0 up-to-date'))):
            raise ValueError('fresh official checked selection compilation required for every role')
        signing = one(role + '-sign-real-selection-caller')
        installation = one(role + '-install-real-selection-caller')
        verify_signing_installation(app, role, document['udid'], hdc, target, build_index, signing, installation)
        install_index = installation[0]
        identity_index, _, _ = shell(role + '-actual-selection-BMS','bm dump -n '+BUNDLE,
                                   checked_file(app['application_identity']).read_text())
        start_index, _, _ = shell(role + '-start-real-selection-caller','aa start -a EntryAbility -b '+BUNDLE)
        if not install_index < identity_index < start_index: raise ValueError('selection identity or start preceded installation')
        previous_phase_end = start_index
        if role == 'reader':
            begin, end = ui_action(caller['permission_request'],'control','reader-permission-request','selection-grant')
            consent_begin, consent_end = ui_action(caller['permission_consent'],'consent','reader-permission-consent')
            if not start_index < begin < end < consent_begin < consent_end: raise ValueError('actual reader request/consent order differs')
            previous_phase_end = consent_end
        elif 'permission_request' in caller or 'permission_consent' in caller:
            raise ValueError('undeclared role borrowed actual user consent')
        phases = caller['phases']; verify_presentations(phases,nonce,role); last = ''; pid = None
        remote = '/data/app/el2/100/base/'+BUNDLE+'/files/arkui-selection-'+nonce+'-results.log'
        for cycle in (0,1):
            for phase in PHASES:
                record = phases[str(cycle)+':'+phase]; prefix = role+'-'+str(cycle)
                label = prefix+'-'+phase; path = checked_file(record['journal']); raw = path.read_text()
                read_index, _, read_command = shell(label+'-actual-native-journal','cat '+remote,raw)
                if not raw.startswith(last): raise ValueError('selection journal lost its actual append-only history')
                parsed = rows(raw,nonce,uid); pid = next(r['values'][2] for r in parsed if r['name']=='identity'); last = raw
                expected_actions = []
                if phase == 'initial': expected_actions = [('control',prefix+'-create','selection-start',None)]
                elif phase == 'removed': expected_actions = [('control',prefix+'-remove','selection-remove',None)]
                else:
                    part, state = phase.split('-'); action_label = prefix+'-'+part
                    if state == 'selected':
                        if part != 'veto': expected_actions.append(('control',action_label+'-prepare','selection-allow' if part=='allowed' else 'selection-join',None))
                        expected_actions.extend([('longpress',action_label+'-longpress',None,None),
                            ('menu',action_label+'-select-all',None,['全选','Select all','Select All'])])
                    elif state == 'copied': expected_actions = [('menu',action_label+'-copy',None,['复制','Copy'])]
                    else: expected_actions = [('control',action_label+('-deferred-read' if state=='deferred' else '-clear'),
                                               'selection-read' if state=='deferred' else 'selection-clear',None)]
                if len(record['actions']) != len(expected_actions): raise ValueError('selection phase action set differs')
                action_end = previous_phase_end
                for action, (kind, action_label, identifier, labels) in zip(record['actions'],expected_actions):
                    begin, end = ui_action(action,kind,action_label,identifier,labels)
                    if not action_end < begin < end < read_index: raise ValueError('selection phase action order differs')
                    action_end = end
                for sample in record['presentation']['samples'][-3:]:
                    picture = checked_file(dict(path=sample['screenshot'],sha256=sample['screenshot_sha256']))
                    layout = checked_file(dict(path=sample['layout'],sha256=sample['layout_sha256']))
                    hierarchy, _ = ui_read(layout); cap, transfer = compositor(picture)
                    if not action_end < hierarchy < cap < transfer < read_index:
                        raise ValueError('selection presentation did not follow its actual phase action')
                previous_phase_end = read_index
                if phase == 'removed':
                    quiet_index, _, quiet = shell(prefix+'-removed-quiet','cat '+remote,raw)
                    if (record.get('quiet_seconds',0) < 2 or record.get('quiet_journal_sha256') != digest(path) or
                            quiet['started_monotonic'] - read_command['finished_monotonic'] < 2):
                        raise ValueError('actual post-removal selection callback quiet interval missing')
                    previous_phase_end = quiet_index
        if verify(last,nonce,uid,role) != CONTRACTS: raise ValueError('selection exact contracts differ')
        if caller.get('cleanup') != dict(process_absent=True,actual_pid=pid,actual_pid_absent=True):
            raise ValueError('selection cleanup summary differs from actual PID')
        running = [(i,name) for i,(name,row,reply) in enumerate(commands) if name.startswith(role+'-running-pid-')]
        valid = []
        for index,name in running:
            _,body,_ = shell(name,'pidof '+BUNDLE+' || true')
            if body.strip() == str(pid): valid.append(index)
        if len(valid) != 1 or not start_index < valid[0] < previous_phase_end:
            raise ValueError('selection journal PID lacks the actual started caller process')
        stop_index, _, _ = shell(role+'-stop-owned-selection-caller','aa force-stop '+BUNDLE)
        name_index, _, _ = shell(role+'-cleanup-name-absence','pidof '+BUNDLE+' || true','')
        pid_index, _, _ = shell(role+'-cleanup-actual-pid-absence','test ! -e /proc/'+str(pid),'')
        if not previous_phase_end < stop_index < name_index < pid_index: raise ValueError('selection cleanup ordering differs')
        previous_role_end = pid_index
    final_index, _, _ = shell('boot-final','cat /proc/sys/kernel/random/boot_id',boot_id+'\n')
    if final_index <= previous_role_end: raise ValueError('selection final boot check preceded caller cleanup')
    return list(CONTRACTS)
