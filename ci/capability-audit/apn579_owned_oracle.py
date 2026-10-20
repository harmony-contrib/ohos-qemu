"""Replay the owned modem/public prerequisite from actual original IO bytes.

Apps' existing full UI/QMP/permission/lifecycle verifier remains mandatory.
This replay does not turn this prerequisite or a no-SIM rejection into APN pass.
"""
from pathlib import Path
import re
import shlex

from capability578_owned_io import require
from settings_idle579_bindings import load_ref
from hap_identity_binding import strict_json
from guest_ui import command_exit, select_node
from apn579_project import BUNDLE
from apn579_protocol import peer_rows, readiness, public_state
from apn579_owned_bindings import canonical, helper_admission, ACTIONS, ROW_KEYS


def retained(io, raw):
    row = io.ref_receipt(raw)
    # Original OwnedIO retains HDC status/stdout and adds separate guest body
    # fields to the same raw row. Its returned adapter additionally names those
    # transport fields; normalize the retained row without changing either one.
    if 'shell_exit_code' in raw:
        row.update(shell_exit_code=raw['shell_exit_code'],shell_stdout=raw['shell_stdout_ref'])
    return row


def verify(io, ref):
    value = strict_json(load_ref(ref).decode())
    require(value['schema'] == 'actual-owned-virtual-sim579/v1' and value['run'] == io.run_id and
        value['boot_id'] == io.boot_id and value['archive_sha256'] == io.archive_sha256 and
        value['cleanup_complete'] is True and value['apps_joined'] is True and value['runtime_pass'] is True and
        value['failures'] == [], 'actual same-boot owned virtual-SIM/Apps cleanup did not complete')
    originals = [retained(io,row) for row in io.receipts]
    helper_admission(value['native_helper'])
    commands = value['commands']
    for item in commands:
        require(item['receipt'] in originals and item['receipt']['boot_id'] == io.boot_id and
            item['receipt']['timed_out'] is False, 'command is not an actual original held IO receipt')
        raw = load_ref(item['body']).decode()
        record = item['receipt']
        load_ref(record['stdout']); load_ref(record['stderr'])
        if 'script' in item:
            prefix = shlex.join(['sh','-c',item['script']])
            argv = record['argv']
            require(argv[:4] == [io.hdc,'-t',io.target,'shell'] and len(argv) == 5 and argv[4].startswith(prefix),
                    'actual shell script/target differs')
            suffix = argv[4][len(prefix):]
            match = re.fullmatch(r'; cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"',suffix)
            require(match is not None, 'actual nonce guest-status footer absent')
            body,status = command_exit(load_ref(record['stdout']).decode(),match[1])
            require(body == raw and status == record['shell_exit_code'] and record['exit_code'] == 0 and
                record['shell_stdout'] == item['body'], 'actual HDC/guest stdout or status was replaced')
        else:
            require(record['stdout'] == item['body'], 'actual direct command body differs')

    def body(index):
        require(type(index) is int and 0 <= index < len(commands), 'original raw command index required')
        return load_ref(commands[index]['body']).decode()

    layouts = {}
    for entry in value['ui']:
        if entry['kind'] != 'layout': continue
        observed = entry['original_commands']
        require(len(observed) == 2 and all(row in originals for row in observed),
                'original UITest dump/read command pair missing')
        scripts, outputs = [], []
        for row in observed:
            require(row['argv'][:4] == [io.hdc,'-t',io.target,'shell'] and row['exit_code'] == 0,
                    'actual original UITest target/transport status differs')
            match = re.fullmatch(r'(.*); task_ui_rc=\$\?; printf "\\n(__UITEST_EXIT_[a-f0-9]{32}__=)%s\\n" "\$task_ui_rc"',
                                 row['argv'][4],re.S)
            require(match is not None, 'actual UITest guest-status nonce footer missing')
            out,status = command_exit(load_ref(row['stdout']).decode(),match[2])
            require(status == 0, 'actual UITest guest command failed')
            scripts.append(match[1]); outputs.append(out)
        dump = re.fullmatch(r'test ! -e (/data/local/tmp/qemu-capability-ui-[A-Za-z0-9_-]+\.json) && '
            r'uitest dumpLayout -p (\S+) -b com\.ohos\.callsetting',scripts[0])
        require(dump is not None and dump[1] == dump[2] and scripts[1] == 'cat ' + dump[1],
                'actual finite UITest remote layout file differs')
        layout = strict_json(load_ref(entry['layout']).decode())
        require(strict_json(outputs[1]) == layout, 'retained observed layout differs from actual UITest raw stdout')
        layouts[entry['layout']['path']] = layout

    prefixes, files = {}, {}
    for read in value['journal_reads']:
        raw, marker = body(read['command']), read['marker']
        require(re.fullmatch('__APN579_[a-f0-9]{32}__',marker), 'source nonce journal frame required')
        parts = raw.split(marker+'BEGIN:')
        require(parts[0] == '', 'actual journal frame has unexpected prefix')
        for part in parts[1:]:
            path,tail = part.split('\n',1)
            require(tail.endswith('\n'+marker+'END\n'), 'complete actual sandbox file frame missing')
            text = tail[:-len('\n'+marker+'END\n')]
            require(text.startswith(prefixes.get(path,'')), 'actual caller journal reordered/truncated')
            if not text.endswith('\n'): continue
            prefixes[path] = text
            files[path] = [strict_json(line) for line in text.splitlines()]
    require(len(files) == len(value['writers']) == 1, 'one original live remembering caller generation required')
    writer = value['writers'][0]
    require(writer['path'] in files and writer['uid'] == value['identity']['uid'] and
        re.fullmatch('/data/app/el2/100/base/'+re.escape(BUNDLE)+'/haps/entry/files/apn-sim579-'+io.run_id+'-'+
            str(writer['pid'])+r'-[a-f0-9]{32}\.jsonl',writer['path']), 'actual controller writer path/UID/PID differs')
    rows = files[writer['path']]
    previous = -1
    for number,row in enumerate(rows,1):
        require(set(row) == ROW_KEYS and row['run'] == io.run_id and row['boot'] == io.boot_id and
            row['uid'] == writer['uid'] and row['pid'] == writer['pid'] and row['filesDir'] == writer['filesDir'] and
            type(row['seq']) is int and row['seq'] == number and type(row['uptimeMs']) is int and
            row['uptimeMs'] >= previous and type(row['code']) is int and type(row['value']) is str,
            'actual caller journal identity/sequence/uptime differs')
        previous = row['uptimeMs']
    requests = {}
    for request in value['requests']:
        op, action = request['operation'], request['action']
        require(re.fullmatch('[a-f0-9]{32}',op) and op not in requests and action in ACTIONS,
                'one finite source-defined public operation required')
        argv = ['aa','start','-b',BUNDLE,'-a','EntryAbility','--ps','run',io.run_id,'--ps','boot',io.boot_id,
                '--ps','operation',op,'--ps','action',action]
        require(commands[request['command']]['script'] == shlex.join(argv), 'actual native request action/nonce differs')
        observed = [row for row in rows if row['operation'] == op]
        require(observed and observed[0]['event'] == 'begin' and observed[0]['value'] == action and
            observed[-1]['event'] in ('done','error') and len([row for row in observed if row['event'] in ('done','error')]) == 1,
            'actual public request did not complete exactly once')
        requests[op] = (action,observed)
    require({row['operation'] for row in rows} == set(requests), 'journal contains an unissued public operation')

    def events(action,event,success=True):
        return [row for name,observed in requests.values() if name == action and
                (not success or observed[-1]['event'] == 'done') for row in observed if row['event'] == event]

    def has_snapshot(expected, action='inspect'):
        matches = [row for row in events(action,'snapshot') if strict_json(row['value']) == expected]
        require(matches, 'reported public state is absent from actual completed native snapshots')
        return matches[-1]

    baseline = value['original_no_sim']
    has_snapshot(baseline)
    require(baseline['hasSim'] is False and baseline['active'] is False and baseline['accounts'] == [] and
        baseline['defaultSlot'] == 0 and baseline['state'] in (0,1), 'actual original slot0/no-SIM boundary absent')
    public_state(has_snapshot(value['active_public'],'select-default'),True)
    public_state(has_snapshot(value['removed_public']),False)
    public_state(has_snapshot(value['bound_absent']),False)
    final = value['final_no_sim']
    has_snapshot(final)
    require(final['hasSim'] is False and final['active'] is False and final['accounts'] == [] and
        final['defaultSlot'] == baseline['defaultSlot'] and final['dataState'] in (-1,0), 'real final no-SIM/default slot differs')
    no_sim = value['no_sim_public_errors']
    require(len(no_sim) == 3 and all(row in events('open-apn','error',False) and row['code'] == -1 and
        row['value'] == 'null' for row in no_sim), 'original/removed/restored actual null no-SIM rejections missing')
    require(events('deactivate','deactivate.return') and events('restore-default','select.return'),
            'actual public reverse deactivate/default calls missing')

    original, ready = value['original_apn'], value['apps_precondition']
    remembered = events('apn-remember','apn')
    require(len(remembered) == 1 and canonical(strict_json(remembered[0]['value'])) == original,
            'original remembered APN state is not the real native read')
    require(ready['active'] is True and ready['numeric'] == '46000' and ready['slot'] == 0 and
        ready['simId'] == value['active_public']['accounts'][0]['simId'] and ready['preferred'] >= 0 and
        any(row['id'] == ready['preferred'] for row in ready['rows']), 'actual restorable preferred APN prerequisite incomplete')
    if original['preferred'] == -1:
        selected = [item for item in value['ui'] if item['kind'] == 'existing_profile_selection']
        require(len(selected) == 1 and selected[0]['profile'] == ready['preferred'] and
            ready == dict(original,preferred=ready['preferred']), 'UI baseline may only select an existing original row')
        chosen = [row for row in original['rows'] if row['id'] == ready['preferred']]
        require(len(chosen) == 1 and chosen[0]['apn'] == 'cmnet' and chosen[0]['mcc'] == '460' and chosen[0]['mnc'] == '00',
                'actual selected baseline is not the packaged default CMNET row')
        node = selected[0]['node']; x,y,w,h = node['rect']
        require(selected[0]['layout']['path'] in layouts and select_node(layouts[selected[0]['layout']['path']],
            'com.ohos.callsetting',identifier='system-apn-select-' + str(ready['preferred']),clickable=True) == node,
            'selected baseline control differs from the actual packaged UI hierarchy')
        require(commands[selected[0]['command']]['script'] ==
            'uitest uiInput click '+str(x+w//2)+' '+str(y+h//2), 'existing profile was not selected through observed UI geometry')
    else: require(original == ready, 'pre-existing preferred APN changed before Apps')
    restores = events('restore-preference','apn')
    returns = events('restore-preference','restore.return')
    require(len(restores) == len(returns) == 1 and strict_json(returns[0]['value']) is True and
        canonical(strict_json(restores[0]['value'])) == value['restored_apn'] == original,
        'actual public preferred APN reverse operation did not restore the full original state')

    raw = body(value['peer_reads'][-1]['command'])
    peer = value['peer_identity']
    wire_rows = peer_rows(raw,io.run_id,io.boot_id,peer['pid'],0)
    wire = readiness(wire_rows)
    require(wire == value['wire_initialization'] or all(cmd in wire['commands'] for cmd in value['wire_initialization']['commands']),
            'final actual AT journal lost the initialized command prefix')
    require(any(re.fullmatch(r'AT\^HVSST=[01],0',cmd) for cmd in wire['commands']),
            'actual public deactivate did not reach RIL AT')
    actions = []
    for control in value['peer_controls']:
        op, action, actual = control['operation'],control['action'],control['receipt']
        require(actual['boot_id'] == io.boot_id and actual['key'] and
            load_ref(actual['raw']) == (op+'\t'+action+'\n').encode(), 'actual owned stdin request bytes differ')
        subset = [row for row in wire_rows if row['operation_id'] == op]
        controls = [row for row in subset if row['kind'] == 'control']
        require(len(controls) == 1 and bytes.fromhex(controls[0]['hex']) == action.encode(), 'peer did not observe actual control')
        if action in ('insert','remove'):
            effects = [row for row in subset if row['kind'] == 'tx']
            expected = b'\r\n^SIMST: '+(b'1' if action == 'insert' else b'0')+b'\r\n'
            require(len(effects) == 1 and bytes.fromhex(effects[0]['hex']) == expected and
                controls[0]['seq'] < effects[0]['seq'], 'real inserted/removed SIM URC effect missing')
        elif action == 'stop':
            require(wire_rows[-1]['kind'] == 'closed' and wire_rows[-1]['operation_id'] == op and
                bytes.fromhex(wire_rows[-1]['hex']).decode() == peer['pty'], 'final actual PTY closure missing')
        actions.append(action)
    require(actions == ['insert','remove','stop'], 'finite insert/remove/stop sequence differs')
    exited = value['peer_wait']
    require(exited['boot_id'] == io.boot_id and exited['exit_code'] == exited['transport_exit_code'] == 0 and
        exited['argv'][:4] == [io.hdc,'-t',io.target,'shell'], 'original owned peer transport/guest exit differs')
    match = re.search(r'; cap578_rc=\$\?; printf "\\n(__CAP578_LONG_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"$',exited['argv'][4])
    require(match is not None, 'original long transport nonce footer absent')
    out,status = command_exit(load_ref(exited['transport_stdout']).decode(),match[1])
    require(out == load_ref(exited['stdout']).decode() and status == 0 and load_ref(exited['stderr']) is not None,
            'actual owned long transport stdout/footer/status differs')
    before, after = value['original_ril'],value['restored_ril']
    require(before['config'] == after['config'] == io.environment['communications578_services']['ril'] and
        (before['pid'],before['start_ticks']) != (after['pid'],after['start_ticks']) and
        before['boot_id'] == after['boot_id'] == io.boot_id, 'actual original packaged RIL restoration missing')
    apps = strict_json(load_ref(value['apps']).decode())
    require(apps['case'] == 'apn' and apps['boot_id'] == io.boot_id and apps['archive_sha256'] == io.archive_sha256 and
        apps['status'] == 'observed' and apps['failures'] == [] and apps['cleanup_verified'] is True and
        apps['apn']['positive_completed'] is True and canonical(apps['apn']['baseline']) == ready,
        'actual original full Apps APN UI result/precondition differs')
    return {'schema':'actual-owned-virtual-sim579-replay/v1','report':ref,'boot_id':io.boot_id,
            'archive_sha256':io.archive_sha256,'whole_id_closure':False,
            'requires_original_apps_ui_raw_review':True,'no_rf_pdp_ims_support_claim':True}
