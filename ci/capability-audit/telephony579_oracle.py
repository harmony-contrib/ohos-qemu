"""Pure replay of L22 from original closed IO, not the producer's verdict.

The original APN verifier remains mandatory and preserves its UI/QMP/47/82
contracts. This verifier derives only the explicit finite transaction matrix;
it cannot close the original whole telephony ID or change unsupported policy.
"""
from pathlib import Path
import json
import re
import shlex
import zipfile

from capability578_owned_io import require, reference
from capability578_callers import compiled_fields_match
from settings_idle579_bindings import load_ref
from hap_identity_binding import strict_json, bms_application_identity
from guest_process_identity import identity_shell, starttime_shell
from guest_ui import command_exit
from batch_network_openvpn_runtime_collect import snapshot_script, parse_snapshot
from apn579_owned_oracle import verify as verify_apn, retained
from apn579_protocol import peer_rows
from telephony579_raw import caller_rows, terminal, wire_commands, submit_pdu, packet_pair, status_report
from telephony579_project import CASE, ROLES, bundle, permissions, module_fields, source_files
from telephony579_tun import product_input, handover, service_script, service_observation

IDENTIFIER = 'behavior:telephony-no-modem-or-sim'
STEPS = ('actual-malformed-parameters','actual-role-rejections','cs-outgoing-and-incoming','cs-real-no-carrier',
    'sms-submit-and-delivery','sms-actual-modem-error','cellular-two-uid-independent-packets-and-carrier-recovery',
    'cs-real-native-at-timeout','ril-device-reset-and-rebind','idle-caller-generation-rebuild','cs-after-caller-rebuild','sms-after-caller-rebuild','cellular-after-caller-rebuild')
NETWORK = 'ip address show; ip route show table all; ip rule show'


def verify(io, evidence_ref, modem_ref):
    value = strict_json(load_ref(evidence_ref).decode())
    modem = strict_json(load_ref(modem_ref).decode())
    require(value['schema'] == 'actual-telephony579-transactions/v1' and
        value['run_id'] == modem['run'] == io.run_id and value['boot_id'] == modem['boot_id'] == io.boot_id and
        value['archive_sha256'] == modem['archive_sha256'] == io.archive_sha256 and
        Path(value['original_apn_output']) == Path(modem_ref['path']) and
        value['peer_identity'] == modem['peer_identity'] and value['native_helper'] == modem['native_helper'],
        'same new archive/original APN/held peer/run/boot/source helper required')
    original_apn = verify_apn(io,modem_ref)
    originals = [retained(io,r) for r in io.receipts]
    commands = value['commands']
    require(type(commands) is list and commands and len(commands) < 30000,'bounded original command list required')
    for item in commands:
        record = item['receipt']
        require(record in originals and record['boot_id'] == io.boot_id and record['timed_out'] is False,
            'L22 command is not an original same-boot OwnedIO record')
        text = load_ref(item['body']).decode(); load_ref(record['stderr'])
        if 'script' in item:
            prefix = shlex.join(['sh','-c',item['script']]); argv = record['argv']
            require(argv[:4] == [io.hdc,'-t',io.target,'shell'] and len(argv) == 5 and argv[4].startswith(prefix),
                'exact original guest shell script/target required')
            match = re.fullmatch(r'; cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"',argv[4][len(prefix):])
            require(match is not None,'actual original CAP shell status footer required')
            body,code = command_exit(load_ref(record['stdout']).decode(),match[1])
            require(record['exit_code'] == 0 and code == record['shell_exit_code'] and body == text and
                record['shell_stdout'] == item['body'],'original raw footer/body/status differs')
        else: require(record['stdout'] == item['body'],'direct original raw body differs')

    def body(index):
        require(type(index) is int and 0 <= index < len(commands),'actual command index required')
        return load_ref(commands[index]['body']).decode()
    def script(index):
        body(index)
        return commands[index].get('script')
    def successful(index):
        record = commands[index]['receipt']
        require(record.get('shell_exit_code',record['exit_code']) == 0,'actual original guest command failed')

    roles = value['roles']
    require(set(roles) == set(ROLES),'exact system/normal/denied real callers required')
    identities = {}
    for role in ROLES:
        item = roles[role]; prepared = item['prepared']; name = bundle(CASE,role)
        require(prepared['bundle'] == name and prepared['identity']['fingerprint'] and
            item['remote'] == '/data/app/el2/100/base/' + name + '/haps/entry/files', 'fixed actual HAP source role/path required')
        for key in ('unsigned','signed','signing','verified_profile'): load_ref(prepared[key])
        for key in ('build_commands','sign_commands','verify_commands'):
            require(prepared[key] and all(r in originals and r['exit_code'] == 0 for r in prepared[key]),
                'actual role compile/sign/verification did not run on original IO')
        require(any('BUILD SUCCESSFUL' in load_ref(r['stdout']).decode() + load_ref(r['stderr']).decode()
            for r in prepared['build_commands']),'actual role compilation did not complete')
        for path,text in source_files(CASE,io.run_id,role,{}).items():
            require((Path(prepared['project']) / path).read_bytes() == text.encode(),'compiled normal HAP source overlay changed')
        profile = strict_json(load_ref(prepared['verified_profile']).decode())
        require(profile['bundle-info']['bundle-name'] == name and
            profile['bundle-info']['apl'] == ('normal' if role == 'ordinary' else 'system_core') and
            profile['bundle-info']['app-feature'] == ('hos_normal_app' if role == 'ordinary' else 'hos_system_app') and
            profile['debug-info']['device-ids'] == [io.udid] and
            profile['acls']['allowed-acls'] == permissions(CASE,role) and
            profile['permissions']['restricted-permissions'] == permissions(CASE,role), 'actual caller authority differs')
        with zipfile.ZipFile(prepared['unsigned']['path']) as a, zipfile.ZipFile(prepared['signed']['path']) as b:
            names = a.namelist(); actual = strict_json(a.read('module.json').decode())
            require(len(names) == len(set(names)) and len(b.namelist()) == len(set(b.namelist())) and
                set(b.namelist()) == set(names) | {'.pages.info'} and a.read('ets/modules.abc') and
                all(a.read(n) == b.read(n) for n in names) and actual['app']['bundleName'] == name and
                compiled_fields_match(actual['module'],module_fields(CASE,role,{})), 'actual signed HAP payload/module differs')
        require(item['identities'],'actual BMS identity is missing')
        for observation in item['identities']:
            index = observation['command']; require(script(index) == 'bm dump -n ' + name,'actual BMS request differs'); successful(index)
            raw = body(index); identity = bms_application_identity(raw,name); doc = strict_json(raw[raw.index('{'):])
            require(identity == observation['identity'] == item['identity'] and
                doc['applicationInfo']['isSystemApp'] is (role != 'ordinary') and
                doc['applicationInfo']['appPrivilegeLevel'] == ('normal' if role == 'ordinary' else 'system_core') and
                set(doc['reqPermissions']) == set(permissions(CASE,role)),'actual BMS UID/token/role differs')
        identities[role] = item['identity']
        original = strict_json(body(item['identities'][0]['command']).split(':',1)[1])
        paths = [m['hapPath'] for m in original['hapModuleInfos'] if m.get('hapPath')]
        require(len(paths) == 1 and script(item['installed_hash_command']) == 'sha256sum ' + shlex.quote(paths[0]) and
            body(item['installed_hash_command']).split() == [prepared['signed']['sha256'],paths[0]],
            'installed real HAP does not have normal signed bytes')
    require(len({i['uid'] for i in identities.values()}) == len(ROLES) and
        len({i['token_id'] for i in identities.values()}) == len(ROLES),'three independent UID/token callers required')

    files, prefixes = {}, {}
    for read in value['reads']:
        role, marker, index = read['role'],read['marker'],read['command']
        require(role in roles and re.fullmatch('__L22_[a-f0-9]{32}__',marker),'fixed original journal role/frame nonce required')
        expected = ('for l22_file in ' + roles[role]['remote'] + '/telephony579-' + io.run_id + '-*.jsonl; do '
            'test -f "$l22_file" || continue; test ! -L "$l22_file" || exit 1; '
            'printf "' + marker + 'BEGIN:%s\\n" "$l22_file"; cat "$l22_file" || exit 1; '
            'printf "\\n' + marker + 'END\\n"; done')
        require(script(index) == expected,'journal is not the actual original fixed cat frame'); successful(index)
        pieces = body(index).split(marker + 'BEGIN:'); require(pieces[0] == '','raw frame prefix differs')
        for piece in pieces[1:]:
            path,tail = piece.split('\n',1)
            match = re.fullmatch(re.escape(roles[role]['remote'] + '/telephony579-' + io.run_id + '-') + r'([1-9][0-9]*)\.jsonl',path)
            require(match and tail.endswith('\n' + marker + 'END\n'),'complete actual fixed raw journal frame required')
            raw = tail[:-len('\n' + marker + 'END\n')]
            require(raw.startswith(prefixes.get(path,'')),'actual append-only journal was replaced/truncated')
            if raw.endswith('\n'):
                files[path] = caller_rows(raw,io.run_id,io.boot_id,role,identities[role]['uid'],int(match[1]))
                prefixes[path] = raw
    require(set(files) == set(value['writers']),'every actual read file needs an independently bound live writer')
    for path,writer in value['writers'].items():
        role = writer['role']; pid = writer['pid']; ticks = writer['start_ticks']; uid = identities[role]['uid']
        require(writer['path'] == path and writer['uid'] == uid and writer['exited'] is True and
            script(writer['identity_command']) == identity_shell(bundle(CASE,role)) and
            body(writer['identity_command']).split() == list(map(str,[pid,ticks,uid,uid,uid,uid])),
            'actual original PID/start and all four UIDs do not bind the writer')
        sandbox = '/proc/' + str(pid) + '/root/data/storage/el2/base/haps/entry/files/' + Path(path).name
        require(script(writer['inode_command']) == 'test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(path) + ' ' + shlex.quote(sandbox) and
            body(writer['inode_command']).splitlines() == [writer['inode']]*2 and
            re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(uid) + ':regular file',writer['inode']) and
            script(writer['after_command']) == starttime_shell(str(pid)) and body(writer['after_command']).strip() == str(ticks),
            'read wire, real sandbox inode and original live process are not the same object')
        seal_index = writer['seal_inode_command']
        require(script(seal_index) == 'test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(path) and body(seal_index).strip() == writer['inode'] and writer.get('sealing') is False,
            'original final post-exit read is not sealed to the same original file inode/UID')
    require(len(roles['system']['generations']) == 2 and
        all(len(roles[r]['generations']) == 1 for r in ('ordinary','denied')) and
        all(set(roles[r]['generations']) == {p for p,w in value['writers'].items() if w['role'] == r} for r in ROLES),
        'one actual rebuilt system generation and independent normal/denied generations required')
    first,last = (value['writers'][p] for p in roles['system']['generations'])
    require((first['pid'],first['start_ticks']) != (last['pid'],last['start_ticks']), 'system process was not actually rebuilt')
    rows = [r for observed in files.values() for r in observed]
    issued, results = {}, {}
    for issue in value['requests']:
        role,request,index = issue['role'],issue['request'],issue['command']; op = request['operation_id']
        require(role in roles and op not in issued and request['run_id'] == io.run_id and request['boot_id'] == io.boot_id,
            'actual request run/boot/unique nonce differs')
        expected = shlex.join(['aa','start','-b',bundle(CASE,role),'-a','EntryAbility','--ps','request',
            json.dumps(request,separators=(',',':'),allow_nan=False)])
        require(script(index) == expected,'actual original aa request bytes differ'); successful(index)
        selected = terminal([r for r in rows if r['role'] == role],request)
        issued[op] = (role,request); results[op] = selected
    require({r['operation_id'] for r in rows} == set(issued),'unissued operation in real journal')

    def selection(role, action):
        return [(request,results[op]) for op,(r,request) in issued.items() if r == role and request['action'] == action]
    def success(selected):
        require(not any(r['kind'] == 'error' for r in selected) and len([r for r in selected if r['kind'] == 'return']) == 1,
            'actual normal operation did not succeed')
    def returned(selected):
        success(selected); return next(r['value'] for r in selected if r['kind'] == 'return')

    peer_read = modem['peer_reads'][-1]
    peer_text = load_ref(modem['commands'][peer_read['command']]['body']).decode()
    peer = peer_rows(peer_text,io.run_id,io.boot_id,value['peer_identity']['pid'],0)
    require(peer[-1]['kind'] == 'closed','same original peer must reach real zero-exit closed state')
    wires = wire_commands(peer)
    for control in value['controls']:
        action,op,actual = control['action'],control['operation'],control['receipt']
        require(actual['key'] == value['peer_key'] and actual['boot_id'] == io.boot_id and
            load_ref(actual['raw']) == (op + '\t' + action + '\n').encode() and
            actual['pid'] == io.held_transports[value['peer_key']]['pid'] and
            Path(actual['raw']['path']).is_relative_to(Path(io.output)), 'actual same original peer stdin differs')
        observed = [r for r in peer if r['operation_id'] == op]
        require(observed and observed[0]['kind'] == 'control' and bytes.fromhex(observed[0]['hex']) == action.encode() and
            any(r['kind'] in ('tx','backend') and r['seq'] > observed[0]['seq'] for r in observed),
            'actual stdin is not consumed by this endpoint and effect')
    expected_controls = ['l22-on','l22-answer','l22-incoming','l22-dial-error','l22-sms-report','l22-sms-error','l22-sms-clear',
        'l22-carrier-drop','l22-register','l22-dial-timeout','l22-carrier-drop','l22-register','l22-answer','l22-incoming','l22-sms-report',
        'l22-carrier-drop','l22-register','l22-carrier-drop','l22-off']
    require([r['action'] for r in value['controls']] == expected_controls,'complete fixed actual finite endpoint matrix differs')
    scoped = [r for r in peer if r['kind'] == 'control' and bytes.fromhex(r['hex']).startswith(b'l22-')]
    require([r['operation_id'] for r in scoped] == [r['operation'] for r in value['controls']], 'unrecorded actual L22 peer action')

    for action in ('invalid-dial','invalid-sms','invalid-data'):
        malformed = selection('system',action)
        require(len(malformed) == 1,'fixed actual malformed argument call missing')
        observed = malformed[0][1]
        errors = [r for r in observed if r['kind'] == 'error']
        require(len(errors) == 1 and errors[0]['code'] == 401 and not any(r['kind'] == 'return' for r in observed),
            'actual malformed call must reject401 before crossing the modem boundary')
        start = observed[0]['monotonic_ms']; stop = next(r['monotonic_ms'] for r in observed if r['kind'] == 'end')
        require(not any(w['raw'].startswith((b'ATD',b'AT+CMGS=',b'AT^NDISDUP=')) and start <= w['start'] <= stop for w in wires),
            'malformed API arguments reached actual radio transaction wire')

    # Role denials must be distinct real native 201/202 with no AT side effect.
    for role in ('ordinary','denied'):
        selected = [(request,observed) for op,(r,request) in issued.items() if r == role and request['action'] in ('dial','data-on','data-off','sms')
            for observed in [results[op]]]
        require([r['action'] for r,_ in selected] == ['dial','data-on','data-off','sms'], 'full role matrix missing')
        begin = selected[0][1][0]['monotonic_ms']
        end = next(r['monotonic_ms'] for r in selected[-1][1] if r['kind'] == 'end')
        for request,observed in selected:
            expected = 201 if role == 'denied' or request['action'] == 'sms' else 202
            errors = [r for r in observed if r['kind'] == 'error']
            require(len(errors) == 1 and errors[0]['code'] == expected and not any(r['kind'] == 'return' for r in observed),
                'actual role denial does not match real product permission/system-app order')
        quiet = [(r,o) for r,o in selection('system','quiet') if o[0]['monotonic_ms'] >= end]
        require(quiet and quiet[0][0]['wait_ms'] == 5000,'independent drain/state consumer window required')
        success(quiet[0][1]); end = quiet[0][1][-1]['monotonic_ms']
        require(not any(w['start'] >= begin and w['end'] <= end and
            (w['raw'].startswith((b'ATD',b'AT+CMGS=',b'AT^NDISDUP=')) or w['kind'] == 'sms-pdu') for w in wires),
            'denied HAP caused an actual dial/SMS/PDP wire transaction')

    # The independent native source reports detailed states after actual AT
    # exchanges. Require two full outgoing/incoming cycles on separate PIDs.
    details = [r for r in rows if r['role'] == 'system' and r['kind'] == 'callback' and
        r['value'].get('type') == 'callDetailsChange']
    dials = selection('system','dial'); hangs = selection('system','hangup'); answers = selection('system','answer')
    require(len(dials) == 4 and len(hangs) == 4 and len(answers) == 2,'two call cycles and real NO CARRIER case required')
    def idle_after(at):
        for request,observed in selection('system','state'):
            end = next(r['monotonic_ms'] for r in observed if r['kind'] == 'end')
            if end >= at and returned(observed).get('getCallState') == 0: return end
        raise ValueError('actual independent native idle-state consumer after release absent')
    positive_dials = [dials[0],dials[3]]
    for number,(request,observed) in enumerate(positive_dials):
        success(observed); begin = observed[0]['monotonic_ms']; finish = idle_after(hangs[number*2][1][-1]['monotonic_ms'])
        commands_in_window = [w for w in wires if begin <= w['start'] <= w['end'] <= finish]
        require(sum(w['raw'] == b'ATD5550100;' for w in commands_in_window) == 1 and
            any(w['raw'] == b'AT+CLCC' for w in commands_in_window) and
            any(w['raw'] == b'AT+CHLD=11' for w in commands_in_window), 'outgoing actual AT/CLCC/release chain absent')
        actual = [r for r in details if r['pid'] == observed[0]['pid'] and begin <= r['monotonic_ms'] <= finish]
        states = [r['value']['value']['callState'] for r in actual]
        require(2 in states and 0 in states and 6 in states and states.index(2) < states.index(0) < states.index(6), 'actual outgoing dialing-to-active callback chain missing')
        success(hangs[number*2][1]); success(answers[number][1]); success(hangs[number*2+1][1])
        incoming_control = [r for r in value['controls'] if r['action'] == 'l22-incoming'][number]
        sent = [r for r in peer if r['operation_id'] == incoming_control['operation'] and r['kind'] == 'tx']
        require(any(b'+CRING: VOICE' in bytes.fromhex(r['hex']) for r in sent) and
            any(b'^CCALLSTATE: 1,4,0' in bytes.fromhex(r['hex']) for r in sent),'actual incoming lower-layer ring bytes missing')
        start = sent[-1]['monotonic_ms']; finish = idle_after(hangs[number*2+1][1][-1]['monotonic_ms'])
        incoming = [r for r in details if r['pid'] == answers[number][1][0]['pid'] and start <= r['monotonic_ms'] <= finish]
        states = [r['value']['value']['callState'] for r in incoming]
        require(4 in states and 0 in states and 6 in states and states.index(4) < states.index(0) < states.index(6) and
            any(w['raw'] == b'ATA' and start <= w['start'] <= finish for w in wires),
            'actual incoming ring -> API answer -> ATA -> active missing')
    # Error path cannot be certified solely by a native rejection/getter.
    negative = dials[1][1]; begin = negative[0]['monotonic_ms']; end = negative[-1]['monotonic_ms'] + 30000
    require(any(w['raw'] == b'ATD5550100;' and begin <= w['start'] <= end for w in wires) and
        any(r['kind'] == 'tx' and bytes.fromhex(r['hex']) == b'\r\nNO CARRIER\r\n' and
            begin <= r['monotonic_ms'] <= end for r in peer),'real NO CARRIER lower-layer error missing')

    timeout_request,timeout_rows = dials[2]
    tbegin = timeout_rows[0]['monotonic_ms']
    wire = [w for w in wires if w['raw'] == b'ATD5550100;' and w['start'] >= tbegin]
    require(wire,'actual native timeout must consume an ATD command')
    stalled = wire[0]
    marker = [r for r in peer if r['kind'] == 'backend' and
        bytes.fromhex(r['hex']) == b'ATD-consumed-without-response' and r['seq'] > stalled['peer_seq']]
    require(len(marker) == 1 and marker[0]['monotonic_ms'] - stalled['start'] < 1000,
        'real endpoint did not consume and withhold this AT response')
    failure_events = [r for r in timeout_rows if r['kind'] == 'error'] + [r for r in details if
        r['monotonic_ms'] >= tbegin and r['value']['value'].get('callState') == 6]
    require(failure_events and min(r['monotonic_ms'] for r in failure_events) >= stalled['start'] + 49000 and
        not any(r['kind'] == 'tx' and stalled['start'] < r['monotonic_ms'] < stalled['start'] + 49000 for r in peer),
        'real original 50s native AT timeout/absent response boundary not observed')
    log_index = value['native_timeout_log_command']
    require(script(log_index) == 'hilog -x' and 'pthread cond timedwait is timeout' in body(log_index),
        'actual packaged RIL native timeout log missing')
    reset = value['ril_reset']; before,after = reset['before'],reset['after']
    require(before in modem['services'] and after in modem['services'] and
        (before['pid'],before['start_ticks']) != (after['pid'],after['start_ticks']) and
        before['uid'] == after['uid'] and before['config'] == after['config'] and
        any(s['pid'] == before['pid'] and s['start_ticks'] == before['start_ticks'] for s in modem['stopped_ril_generations']),
        'actual original packaged RIL generation/UID/init/DSO reset and stopped generation missing')
    require(type(reset['stop_command_start']) is int and type(reset['command_end']) is int and
        0 <= reset['stop_command_start'] < reset['command_end'] <= len(modem['commands']) and
        any(c.get('script') == 'service_control stop riladapter_host' for c in modem['commands'][reset['stop_command_start']:reset['command_end']]) and
        any(c.get('script') == 'service_control start riladapter_host' for c in modem['commands'][reset['stop_command_start']:reset['command_end']]),
        'native device generation was not actually rebuilt by the same original service context')

    # Link actual NAPI send/delivery to independently decoded destination and
    # fresh content in the raw consumed Ctrl-Z TPDU and actual +CDS response.
    messages = selection('system','sms'); require(len(messages) == 3,'SMS submit/delivery/error/rebuilt positive matrix required')
    for number,(request,observed) in enumerate(messages):
        success(observed); nonce = request['nonce']; begin = observed[0]['monotonic_ms']; finish = next(r['monotonic_ms'] for r in observed if r['kind'] == 'end')
        actual = [(w,submit_pdu(w['raw'])) for w in wires if w['kind'] == 'sms-pdu' and begin <= w['start'] <= w['end'] <= finish]
        require(actual and all(p['destination'] == '5550100' and p['text'] == 'L22-' + nonce for _,p in actual),
            'actual endpoint did not consume this role/fresh destination/text')
        for wire,pdu in actual:
            prior = [w for w in wires if w['kind'] == 'at' and w['raw'].startswith(b'AT+CMGS=') and w['peer_seq'] < wire['peer_seq']]
            require(prior and int(prior[-1]['raw'].split(b'=')[1]) == pdu['tpdu_octets'], 'actual CMGS TPDU count differs')
            require(any(r['kind'] == 'backend' and bytes.fromhex(r['hex']) == wire['raw'] and
                wire['start'] <= r['monotonic_ms'] <= finish for r in peer), 'endpoint did not independently record consumed TPDU')
        completion = [r for r in observed if r['kind'] == 'sms-completion']
        require(len(completion) == 1 and completion[0]['value'].get('timeout') is not True,'actual SMS callback timeout is unresolved')
        if number == 1:
            require(completion[0]['value']['result']['result'] != 0 and
                any(r['kind'] == 'tx' and b'+CMS ERROR: 500' in bytes.fromhex(r['hex']) and
                    begin <= r['monotonic_ms'] <= finish for r in peer), 'actual modem error did not reach failed SMS sendCallback')
        else:
            require(len(actual) == 1 and completion[0]['value'] == {'code':0,'result':{'result':0}} and actual[0][1]['status_report_requested'],
                'actual single SMS success and delivery request absent')
            delivery = [r for r in observed if r['kind'] == 'sms-delivery-callback']
            require(len(delivery) == 1 and delivery[0]['code'] == 0,'actual delivery callback is missing')
            result = delivery[0]['value']['result']['pdu']
            require(type(result) is list and all(type(n) is int and 0 <= n <= 127 for n in result),'actual native delivery hex byte array malformed')
            text = bytes(result).decode('ascii').upper()
            matching = [r for r in peer if r['kind'] == 'tx' and re.fullmatch(rb'\r\n\+CDS: [1-9][0-9]*\r\n' + text.encode() + rb'\r\n',bytes.fromhex(r['hex']))]
            decoded = status_report(text)
            submitted = [re.fullmatch(rb'\r\n\+CMGS: ([0-9]+)\r\n\r\nOK\r\n',bytes.fromhex(r['hex'])) for r in peer
                if r['kind'] == 'tx' and begin <= r['monotonic_ms'] <= finish]
            references = [int(m[1]) for m in submitted if m is not None]
            require(decoded['destination'] == actual[0][1]['destination'] and decoded['status'] == 0 and
                references == [decoded['message_reference']], 'real delivery report recipient/reference/status is not this submission')
            require(len(matching) == 1 and begin <= matching[0]['monotonic_ms'] <= delivery[0]['monotonic_ms'],
                'delivery callback is not joined to actual endpoint +CDS bytes')

    packets = []
    for role,expected_count in (('system',2),('ordinary',4)):
        observed = selection(role,'udp'); require(len(observed) == expected_count,'full two-role packet/reattach/rebuild matrix missing')
        for request,result in observed:
            actual = returned(result); payload = 'L22-' + io.run_id + '-' + role + '-' + request['nonce']
            require(actual['payload'] == payload and actual['reply'] == 'L22-REPLY:' + payload and type(actual['netId']) is int,
                'actual caller fresh wire reply/netId differs')
            candidates = [r['value'] for r in result if r['kind'] == 'network-candidate']
            require(any(n['netId'] == actual['netId'] and 0 in n['caps']['bearerTypes'] and n['properties']['interfaceName'] == 'usb0'
                for n in candidates),'actual network bearer/interface consumer absent')
            bound = [r for r in result if r['kind'] == 'udp-bound']; callbacks = [r for r in result if r['kind'] == 'udp-callback']
            require(len(bound) == len(callbacks) == 1 and callbacks[0]['value']['text'] == actual['reply'] and
                any(r['kind'] == 'udp-closed' for r in result),'actual bound socket receive/close absent')
            pair = packet_pair(peer,payload)
            require(bound[0]['monotonic_ms'] <= pair[0][0]['monotonic_ms'] <= pair[1][0]['monotonic_ms'] <= callbacks[0]['monotonic_ms'],
                'actual caller socket and independent endpoint packet causality differs')
            packets.append({'role':role,'uid':identities[role]['uid'],'payload':payload,'net_id':actual['netId']})
    require(any(w['raw'] == b'AT^NDISDUP=1,1' for w in wires) and
        any(w['raw'] == b'AT^NDISDUP=1,0' for w in wires) and any(w['raw'] == b'AT^DHCP?' for w in wires),
        'actual PDP activate/address/deactivate source chain missing')
    for index_key in ('network_before_command','network_connected_command','network_after_command'):
        require(script(value[index_key]) == NETWORK,'actual kernel network observation script differs'); successful(value[index_key])
    require(body(value['network_before_command']) == body(value['network_after_command']) == value['network_before'],
        'actual original routes/rules/addresses not restored')
    require('usb0' in body(value['network_connected_command']) and re.search(r'^iff:\s+usb0$',body(value['tun_binding_command']),re.M),
        'actual TUN fd ownership and installed kernel network observations missing')
    tun_script = ('test -d /sys/class/net/usb0 && cat /sys/class/net/usb0/ifindex && '
        'l22_tun_count=0; for l22_fd in /proc/' + str(value['peer_identity']['pid']) + '/fd/*; do '
        'l22_target=$(readlink "$l22_fd") || exit 1; if test "$l22_target" = /dev/tun; then '
        'printf "TUNFD=%s\\n" "$l22_fd"; cat /proc/' + str(value['peer_identity']['pid']) + '/fdinfo/${l22_fd##*/} || exit 1; '
        'l22_tun_count=$((l22_tun_count + 1)); fi; done; test "$l22_tun_count" = 1')
    require(script(value['tun_binding_command']) == tun_script,'actual TUN fd observation was not the held original peer')
    native,guest,digest = product_input({'telephony579':io.telephony579_product},io.archive_sha256,
        strict_json(load_ref(value['native_product_export']).decode())['product'])
    require(value['native_product_export'] == io.telephony579_product['product_export'] and
        value['native_library_path'] == guest and value['native_library_sha256'] == digest,
        'actual normal native product input identity, never a loose JSON verdict')
    controls = [r for r in value['controls'] if r['action'] == 'l22-on']
    require(len(controls) == 1,'one original same-peer native endpoint acquisition')
    facts = handover(peer,run=io.run_id,boot=io.boot_id,operation=controls[0]['operation'],
        peer_pid=value['peer_identity']['pid'])
    require(facts == value['native_handover'] and body(value['tun_binding_command']).splitlines()[0] == str(facts['ifindex']),
        'complete original kernel-authenticated handover and independent interface ifindex')
    index = value['native_service_command']; successful(index)
    require(script(index) == service_script(facts['pid'],guest,digest,io.boot_id),
        'native maps/uid/context/generation were not read from the actual SCM peer')
    require(service_observation(body(index),facts,guest,digest) == value['native_service_observation'],
        'native process/source/image observation differs on independent replay')
    frames = value['call_active_frames']
    require(len(frames) == 2,'two original actual active-call QMP observations required')
    for frame in frames:
        path = Path(frame['path']); pixels = load_ref(frame)
        require(path.is_relative_to(Path(io.output)) and pixels.startswith(b'P6\n'),'actual original QEMU frame required')
        observations = [r for r in io.qmp_receipts if r['execute'] == 'screendump' and r['arguments'] == {'filename':str(path)}]
        require(len(observations) == 1 and observations[0]['completed'] is True and observations[0]['boot_id'] == io.boot_id,
            'frame is not an original completed same-boot QMP request')
        qmp = observations[0]
        request_wire = [strict_json(line) for line in load_ref(qmp['request']).decode().splitlines()]
        response_wire = [strict_json(line) for line in load_ref(qmp['response']).decode().splitlines()]
        requests = [r for r in request_wire if r.get('execute') == 'screendump' and r.get('arguments') == {'filename':str(path)}]
        require(len(requests) == 1 and 'id' in requests[0] and any(r.get('id') == requests[0]['id'] and 'return' in r and 'error' not in r
            for r in response_wire),'original request/response QMP wire does not prove this screendump')
        # This is retained diagnostic frame identity, not an assertion that
        # an unexamined pixel contains a particular call UI element.

    for role in ROLES:
        observations = [r for r in value['cleanup'] if r['role'] == role and r['kind'] == 'uninstalled']
        require(len(observations) == 2,'two complete independent post-uninstall UID scans required')
        for observation in observations:
            index = observation['command']; raw = body(index); first_line = raw.splitlines()[0].split('|')
            require(len(first_line) == 8 and first_line[:2] == ['BEGIN','PROCESS_V2'],'actual process scanner header differs')
            nonce = first_line[2]
            require(script(index) == snapshot_script(nonce,io.boot_id,mode='uid',uid=identities[role]['uid'],bundle=bundle(CASE,role)),
                'actual source-defined complete UID snapshot program differs')
            require(not parse_snapshot(raw,nonce,io.boot_id,mode='uid',uid=identities[role]['uid'],bundle=bundle(CASE,role))['processes'],
                'owned caller UID process remains after teardown')
    require(value['cleanup_complete'] is True and value.get('cleanup_errors') == [] and value['failures'] == [] and
        [s['name'] for s in value['steps']] == list(STEPS) and all(s['status'] == 'observed' for s in value['steps']),
        'actual incomplete/failed matrix is unresolved and cannot be relabeled')
    require(value['whole_L22_pass'] is False and value['new_package_acceptance'] is False and value['remaining'],
        'finite transactions cannot replace original whole-ID obligations')
    return {'schema':'raw-telephony579-finite-transactions-replay/v1','original_id':IDENTIFIER,
        'archive_sha256':io.archive_sha256,'boot_id':io.boot_id,'run_id':io.run_id,
        'original_apn_raw_replay':original_apn,'actual_caller_identities':identities,
        'independent_packet_transactions':packets,'finite_matrix_raw_replayed':True,
        'whole_id_closure':False,'formally_closed':[],'runtime_pass':False,
        'remaining_obligations':value['remaining'],'requires_original_communications_rtt_5a_and_owner_finish':True}
