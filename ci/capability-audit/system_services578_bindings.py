"""Business bindings to the ORIGINAL held Owner's primitive IO.

No Owner/Runner, resource lease, process launcher, server/socket constructor,
SDK lookup, alternate HDC server or package runner. All actual execution is
through root_io, whose receipts retain original argv/exit/stdout/stderr.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

from system_services578_project import ROLES, bundle, require, validate
from system_services578_peer import PeerState, handler_factory, wrap_accepted_socket, fixture_spec

ACTIONS = {
    'domain': {'identity', 'probe', 'query', 'query-invalid', 'open', 'open-http', 'open-other', 'exit'},
    'session': {'identity', 'probe', 'window-create', 'window-properties', 'window-update', 'window-hide',
        'window-show', 'window-destroy', 'invalid-window', 'system-api', 'foreign-window', 'pip-start',
        'pip-info', 'pip-stop', 'ball-start', 'ball-info', 'ball-update', 'ball-stop', 'view-start',
        'view-info', 'view-stop', 'cleanup', 'exit'},
    'ads': {'identity', 'probe', 'invalid', 'load', 'multi', 'invalid-display', 'exit'}}


def account_snapshot(text):
    accounts = {}
    current = None
    for line in text.replace('\r', '').splitlines():
        line = line.strip()
        match = re.fullmatch(r'ID:\s*(0|[1-9][0-9]*)', line)
        if match:
            current = int(match[1])
            require(current not in accounts, 'duplicate actual AccountMgr ID')
            accounts[current] = []
        elif line.startswith('ID:'):
            current = None
        elif current is not None and line.startswith('isForeground:'):
            accounts[current].append(line.removeprefix('isForeground:').strip())
    active = [user for user, values in accounts.items() if values in (['1'], ['true'])]
    require(len(active) == 1, 'one actual foreground OS account required')
    return accounts, active[0]


def json_object(text):
    # BMS prints a command header before its JSON. Parse only actual JSON data;
    # do not treat diagnostics, executable strings or an expected dict as data.
    decoder = json.JSONDecoder()
    for at, char in enumerate(text):
        if char == '{':
            try:
                value, _end = decoder.raw_decode(text[at:])
            except ValueError:
                continue
            if type(value) is dict:
                return value
    raise ValueError('actual BMS JSON object missing')


def dictionaries(value):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif type(value) is list:
        for child in value:
            yield from dictionaries(child)


def bind(root_io):
    """Return the seven fixed callbacks, bound to one existing held guest."""
    io = root_io
    root = Path(io.output) / 'system_services578'
    root.mkdir(parents=True, exist_ok=True)
    require(root.is_absolute() and not root.is_symlink(), 'original owned output directory required')
    state = {'case': None, 'run': None, 'callers': {}, 'active': None, 'original_user': None,
        'secondary': None, 'installed': set(), 'last': {}, 'counter': 0, 'journal_prefixes': {},
        'network': False, 'mounts': {}, 'hosts_backup': None, 'ca_path': None, 'rport': None,
        'temporary': [], 'closed': False, 'power_override': None, 'feature_info': {},
        'hosts_changed': False, 'account_created': False, 'accounts_before': set(), 'pending_close': {},
        'feature_requests': {}}

    def save(label, content):
        state['counter'] += 1
        path = root / (str(state['counter']).zfill(5) + '_' + label)
        data = content.encode() if type(content) is str else content
        path.write_bytes(data)
        return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}

    def save_json(label, value):
        return save(label + '.json', json.dumps(value, indent=2, ensure_ascii=False) + '\n')

    def ref(path):
        path = Path(path)
        require(path.is_file() and not path.is_symlink(), 'actual received file required')
        return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def shell(script, label, timeout=60, allow_failure=False):
        require(re.fullmatch('[A-Za-z0-9_-]+', label), 'bounded original Guest shell label required')
        row = io.shell(script, 'services578_' + label, timeout=timeout, allow_failure=allow_failure)
        require(row['boot_id'] == io.boot_id and (allow_failure or row['exit_code'] == 0), 'held guest command failed')
        return row

    def begin(label):
        at = (len(io.receipts), len(io.qmp_receipts))
        require(shell('cat /proc/sys/kernel/random/boot_id', label + '_boot')['stdout'].strip() == io.boot_id,
                'original held guest boot changed')
        return at

    def result(at, **extra):
        command_at, qmp_at = at
        records = [io.ref_receipt(row) for row in io.receipts[command_at:] if type(row) is dict and 'argv' in row]
        require(records, 'original root IO did not retain actual command receipts')
        return dict(boot_id=io.boot_id, commands=records, qmp_records=io.qmp_receipts[qmp_at:], **extra)

    def hdc(args, label, timeout=60):
        row = io.command([str(io.hdc), '-t', io.target, *args], 'services578_' + label, timeout=timeout)
        require(row['exit_code'] == 0 and '[Fail]' not in row['stdout'] + row['stderr'], 'original HDC operation failed')
        return row

    def account_read(label):
        row = shell('hidumper -s AccountMgr -a "-os_account_infos"', label)
        accounts, active = account_snapshot(row['stdout'])
        return accounts, active, row

    def role_check(role):
        require(state['case'] in ROLES and role in ROLES[state['case']], 'fixed compiled role required')

    def remote_files(role):
        role_check(role)
        return '/data/app/el2/' + str(state['active']) + '/base/' + bundle(state['case'], role) + '/files'

    def pull(role, label):
        state['counter'] += 1  # Every actual pull gets immutable local bytes.
        directory = remote_files(role)
        pattern = directory + '/services578-' + state['run'] + '-*.jsonl'
        listing = shell('ls ' + pattern, label + '_list', allow_failure=True)
        require(listing['exit_code'] in (0, 1, 2), 'actual journal listing failed')
        files = listing['stdout'].strip().splitlines() if listing['exit_code'] == 0 else []
        contents = []
        rows = []
        for number, remote in enumerate(sorted(files)):
            require(re.fullmatch(re.escape(directory + '/services578-' + state['run'] + '-') + r'[1-9][0-9]*\.jsonl', remote),
                    'unexpected caller journal path')
            local = root / ('journal_' + str(state['active']) + '_' + role + '_' + str(state['counter']) + '_' + str(number) + '.jsonl')
            io.receive(remote, local, 'services578_' + label + '_receive_' + str(number))
            data = local.read_bytes()
            key = (state['active'], role, remote)
            previous = state['journal_prefixes'].get(key, b'')
            require(data.startswith(previous), 'actual append-only journal was truncated/replaced')
            state['journal_prefixes'][key] = data
            contents.append(data)
            rows.extend(json.loads(line) for line in data.decode().splitlines() if line)
        return b''.join(contents), rows

    def launch(role, action, request):
        role_check(role)
        require(action in ACTIONS[state['case']] and request == {
            'run_id': state['run'], 'request_id': request['request_id'], 'action': action} and
            re.fullmatch('[a-z0-9_-]{1,64}', request['request_id']), 'fixed source action and bounded request required')
        parts = ['aa', 'start', '-b', bundle(state['case'], role), '-a', 'EntryAbility', '-m', 'entry',
                 '-u', str(state['active'])]
        for key in ('run_id', 'request_id', 'action'):
            parts.extend(['--ps', key, request[key]])
        row = shell(shlex.join(parts), 'start_' + role + '_' + request['request_id'], timeout=60)
        require('start ability successfully' in row['stdout'].lower(), 'actual AMS rejected compiled caller')
        state['last'][role] = request
        if action.endswith('-start') and action.split('-')[0] in ('pip', 'ball', 'view'):
            state['feature_requests'][(role, action.split('-')[0])] = request['request_id']

    def terminal(rows, role, request_id):
        selected = [r for r in rows if r.get('request_id') == request_id]
        if request_id == 'lifecycle':
            return True  # Still requires a real nonempty immutable role journal.
        if any(r.get('event') in ('error', 'request-error', 'page-error') for r in selected):
            return True
        pending = state['pending_close'].get(role)
        if pending and pending['request_id'] == request_id:
            feature = pending['feature']
            stopped = {'pip': 4, 'ball': 2, 'view': 3}[feature]
            return any(r.get('event') == feature + '-state' and json.loads(r['value']).get('state') == stopped for r in selected)
        request = state['last'].get(role)
        if not request or request['request_id'] != request_id:
            return any(r.get('event') == 'routed' for r in selected)
        action = request['action']
        if action in ('load', 'multi', 'invalid'):
            return any(r.get('event') in ('ad-failure', 'ad-success') for r in selected)
        if action.endswith('-start') or action.endswith('-stop'):
            feature = action.split('-')[0]
            goal = {'pip': (2, 4), 'ball': (1, 2), 'view': (1, 3)}[feature][action.endswith('-stop')]
            return any(r.get('event') == feature + '-state' and json.loads(r['value']).get('state') == goal for r in selected)
        return any(r.get('event') == 'done' for r in selected)

    def collect(role, request_id):
        at = begin('collect_' + role)
        role_check(role)
        require(re.fullmatch('[a-z0-9_-]{1,64}', request_id), 'bounded actual request ID required')
        deadline = time.monotonic() + 30
        quiet_since = None
        previous = None
        while True:
            content, rows = pull(role, 'collect_' + role)
            now = time.monotonic()
            if content != previous:
                previous, quiet_since = content, now
            if quiet_since is None:
                quiet_since = now
            complete = terminal(rows, role, request_id)
            # A receiver may be intentionally absent for this route. Preserve a
            # finite real quiet interval; never fabricate a terminal row.
            receiver = state['case'] == 'domain' and role in ('target', 'other') and request_id.startswith('open')
            if (complete and now - quiet_since >= 1) or (receiver and now - quiet_since >= 3) or now >= deadline:
                break
            time.sleep(.25)
        for row in rows:
            if row.get('event') == 'feature-info':
                name = row['action'].split('-')[0]
                state['feature_info'][(role, name)] = json.loads(row['value'])
        journal = save('journal_' + role + '_' + request_id + '.jsonl', content)
        require(content, 'no actual role lifecycle journal; absence is not a fabricated empty success')
        pending = state['pending_close'].get(role)
        if pending and pending['request_id'] == request_id:
            state['pending_close'].pop(role)
        return result(at, journal=journal)

    def prepare_callers(case, run_id, roles):
        validate(case, run_id, roles[0], fixture_spec(run_id)['hosts'] if case == 'domain' else None)
        require(tuple(roles) == ROLES[case] and state['case'] is None and run_id == io.run_id,
                'exact original prepare once and held root run nonce required')
        at = begin('prepare')
        accounts, active, _row = account_read('prepare_accounts')
        state.update(case=case, run=run_id, active=active, original_user=active)
        require(active == 100, 'actual original foreground account100 required')
        params = {'udid': io.udid, 'primary_user': active,
                  'hosts': fixture_spec(run_id)['hosts'] if case == 'domain' else None}
        built = io.prepare_callers('system_services578', case, run_id, roles, params)
        require(built['case'] == case and built['run_id'] == run_id and built['boot_id'] == io.boot_id,
                'original build/sign receipts not bound to actual run/boot')
        state['callers'] = built['callers']
        if case == 'domain':
            state['accounts_before'] = set(accounts)
            created = shell('acm create -n services578_' + run_id[:12] + ' -t normal', 'create_account')
            require('create the local account successfully.' in created['stdout'], 'real account creation rejected')
            state['account_created'] = True
            after, _active, _row = account_read('created_accounts')
            new = set(after) - set(accounts)
            require(len(new) == 1, 'actual newly allocated secondary account ID is ambiguous')
            state['secondary'] = next(iter(new))
            built['secondary_user'] = state['secondary']
        built['environment_commands'] = result(at)['commands']
        return built

    def install(role):
        at = begin('install_' + role)
        role_check(role)
        local = Path(state['callers'][role]['signed']['path'])
        remote = '/data/local/tmp/services578_' + state['run'] + '_' + role + '.hap'
        io.send(local, remote, 'services578_send_' + role)
        state['temporary'].append(remote)
        row = shell(shlex.join(['bm', 'install', '-r', '-p', remote, '-u', str(state['active'])]), 'install_' + role, timeout=600)
        require('install bundle successfully.' in row['stdout'], 'real BMS installation rejected')
        state['installed'].add((state['active'], role))
        bms = shell(shlex.join(['bm', 'dump', '-n', bundle(state['case'], role), '-u', str(state['active'])]), 'bms_' + role)
        document = json_object(bms['stdout'])
        request_id = 'identity_' + str(state['counter'])
        launch(role, 'identity', {'run_id': state['run'], 'request_id': request_id, 'action': 'identity'})
        actual = collect(role, request_id)
        rows = [json.loads(line) for line in Path(actual['journal']['path']).read_text().splitlines() if line]
        rows = [r for r in rows if r['request_id'] == request_id and r['event'] == 'self-identity' and r['code'] == 0]
        require(len(rows) == 1, 'real installed caller signature self-query missing')
        actual_identity = json.loads(rows[0]['value'])
        uid = rows[0]['uid']
        applications = [d for d in dictionaries(document) if d.get('bundleName') == bundle(state['case'], role)
                        and d.get('uid') == uid and d.get('fingerprint') == actual_identity['fingerprint']]
        require(applications and actual_identity['bundle'] == bundle(state['case'], role),
                'actual kernel caller/BMS/self signature identities disagree')
        require(actual_identity['fingerprint'] == state['callers'][role]['identity']['fingerprint'],
                'installed BMS certificate differs from cryptographically verified HAP signer')
        identity = dict(actual_identity, uid=uid, user_id=state['active'], bms_raw=bms['stdout_ref'],
                        self_query_raw=actual['journal'])
        if state['case'] == 'domain' and role in ('target', 'other'):
            domain_terminal(role)
        return result(at, identity=save_json('identity_' + role, identity))

    def domain_terminal(role):
        deadline = time.monotonic() + 30
        marker = re.escape(bundle('domain', role)) + r':\n((?:[ \t].*(?:\n|$))+)'
        while True:
            dump = shell('hidumper -s 6200', 'domain_terminal')['stdout'].replace('\r', '')
            section = re.search(marker, dump)
            if section and ':unknown' not in section[1].lower():
                return
            require(time.monotonic() < deadline, 'real OS domain verification did not reach a terminal state')
            time.sleep(.25)

    def start(role, action, request):
        at = begin('start_' + role)
        if state['case'] == 'domain' and role == 'grant' and action == 'query':
            domain_terminal('target')
        launch(role, action, request)
        return result(at)

    def mounts(text):
        return {parts[1]: parts[3].split(',') for line in text.splitlines()
                if len(parts := line.split()) >= 4 and parts[1].startswith('/')}

    def network(action, payload):
        at = begin('network_' + action)
        require(state['case'] == 'domain' and action in ('start', 'publish', 'collect'), 'fixed owned HTTPS action required')
        if action == 'start':
            spec = fixture_spec(state['run'])
            require(payload == {'hosts': spec['hosts'], 'run_id': state['run']} and not state['network'], 'exact fixture start once required')
            previous = hdc(['fport', 'ls'], 'rport_before')['stdout']
            require(not re.search(r'^tcp:443\s', previous, re.M), 'guest443 reverse mapping is already owned')
            state['mounts'] = mounts(shell('cat /proc/mounts', 'mounts_before')['stdout'])
            metadata = shell("stat -c '%a %u %g' /system/etc/hosts", 'hosts_metadata')['stdout'].strip().split()
            require(len(metadata) == 3 and all(re.fullmatch('[0-9]+', v) for v in metadata), 'original hosts ownership/mode missing')
            state['hosts_metadata'] = metadata
            backup = root / ('hosts_before_' + state['run'])
            io.receive('/system/etc/hosts', backup, 'services578_hosts_before')
            state['hosts_backup'] = backup
            peer = io.https_start(spec, PeerState, handler_factory, wrap_accepted_socket)
            state['network'] = True
            require(type(peer['host_port']) is int and 1024 <= peer['host_port'] <= 65535 and
                    re.fullmatch('[a-f0-9]{8}', peer['ca_subject_hash']), 'real high-port TLS listener/actual CA subject hash required')
            state['peer'] = peer
            # Root start already serves real empty association bytes. Keep the
            # explicit revoke generation available for its later runtime case.
            ca_path = '/system/etc/security/certificates/' + peer['ca_subject_hash'] + '.0'
            check = shell('test ! -e ' + shlex.quote(ca_path), 'ca_no_collision', allow_failure=True)
            require(check['exit_code'] == 0, 'refuse to overwrite an existing system trust anchor')
            hdc(['target', 'mount'], 'owned_target_mount')
            replacement = root / ('hosts_fixture_' + state['run'])
            replacement.write_bytes(backup.read_bytes() + b'\n' + spec['hosts_line'].encode())
            hosts_remote = '/data/local/tmp/services578_' + state['run'] + '_hosts'
            ca_remote = '/data/local/tmp/services578_' + state['run'] + '_ca'
            io.send(replacement, hosts_remote, 'services578_hosts_send')
            io.send(Path(peer['ca']['path']), ca_remote, 'services578_ca_send')
            state['temporary'].extend([hosts_remote, ca_remote])
            # Overwrite the existing hosts inode, preserving its original label.
            state['hosts_changed'] = True
            shell('cat ' + shlex.quote(hosts_remote) + ' > /system/etc/hosts', 'hosts_install')
            state['ca_path'] = ca_path
            shell('cat ' + shlex.quote(ca_remote) + ' > ' + shlex.quote(ca_path), 'ca_install')
            shell('chmod 644 ' + shlex.quote(ca_path), 'ca_mode')
            shell('ls -lZ /system/etc/hosts ' + shlex.quote(ca_path), 'fixture_labels')
            hosts_actual = shell('cat /system/etc/hosts', 'hosts_readback')['stdout']
            require(hosts_actual.encode() == replacement.read_bytes(), 'actual guest hosts bytes differ')
            copied_ca = root / ('ca_readback_' + state['run'] + '.pem')
            io.receive(ca_path, copied_ca, 'services578_ca_readback')
            require(copied_ca.read_bytes() == Path(peer['ca']['path']).read_bytes(), 'actual guest trust anchor differs')
            mapping = ['tcp:443', 'tcp:' + str(peer['host_port'])]
            hdc(['rport', *mapping], 'rport_install')
            state['rport'] = mapping
            actual_ports = hdc(['fport', 'ls'], 'rport_readback')['stdout']
            require(' '.join(state['rport']) + ' [Reverse]' in actual_ports, 'exact owned guest reverse mapping missing')
            fixture = dict(spec, ca_guest_path=ca_path, ca=peer['ca'], certificates=peer['certificates'],
                host_port=peer['host_port'], rport=state['rport'], hosts_before=ref(backup),
                hosts_after=save('hosts_readback.txt', hosts_actual), mounts_before=state['mounts'],
                transport_peer_ip=peer['transport_peer_ip'])
            return result(at, fixture=save_json('https_fixture', fixture))
        require(state['network'], 'root-owned HTTPS fixture has not started')
        if action == 'publish':
            io.https_publish(payload)
            return result(at, published=save_json('https_publish', payload))
        captured = io.https_collect()
        require(payload['generation'] in ('match', 'fingerprint-mismatch', 'revoke', 'server-error', 'untrusted-cert', 'wrong-host', 'retry'),
                'fixed peer capture generation required')
        return result(at, requests=captured['requests'], connections=captured['connections'],
                      transport_peer_ip=state['peer']['transport_peer_ip'])

    def actual_close(role, feature):
        from guest_ui import bounds
        if feature == 'ball':
            # FloatingBall's consumer owns its cancel action. Exercise the
            # actual caller button, then require both its touch marker and the
            # native STOPPED callback. No native callback is synthesized here.
            request = {'run_id': state['run'], 'request_id': 'cancel_ball_' + str(state['counter']), 'action': 'probe'}
            launch(role, 'probe', request)
            selected = io.ui.click(bundle('session', role), identifier='services578-ball-cancel',
                                   label='services578_actual_ball_user_cancel')
            return {'selected_node': selected, 'cancel_surface': 'actual_caller_cancel_control'}
        info = state['feature_info'].get((role, feature))
        require(info and type(info.get('windowId')) is int, 'actual current feature Window ID required')
        details = shell('hidumper -s 4606 -a "-w ' + str(info['windowId']) + '"', 'close_actual_window')['stdout']
        rect = re.search(r'^WindowRect:\s*\[\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+)\s*\]', details, re.M)
        require(rect and 'IsVisible: true' in details, 'actual feature is not a visible SceneSession')
        wx, wy, ww, wh = map(int, rect.groups())
        selected = []
        for attempt in range(2):
            layout, path = io.ui.layout(label='services578_close_' + feature)
            selected = []
            pending = list(layout) if type(layout) is list else [layout]
            while pending:
                node = pending.pop()
                attrs = node.get('attributes', {})
                if attrs.get('visible') == 'true' and attrs.get('enabled') == 'true' and attrs.get('clickable') == 'true':
                    accessible = [attrs.get(k, '') for k in ('text', 'description', 'accessibilityText')]
                    if attrs.get('id') == 'control_exit' or any(v in ('Close', '关闭', 'Close window', '关闭窗口',
                        'Close picture-in-picture', '关闭画中画', '关闭悬浮窗') for v in accessible):
                        left, top, width, height = bounds(attrs.get('bounds'))
                        if wx <= left + width // 2 < wx + ww and wy <= top + height // 2 < wy + wh:
                            selected.append({'attributes': attrs, 'rect': (left, top, width, height)})
                pending.extend(node.get('children', []))
            if selected or feature != 'pip' or attempt:
                break
            io.ui.shell('uitest uiInput click ' + str(wx + ww // 2) + ' ' + str(wy + wh // 2),
                        'services578_show_actual_pip_controls')
        require(len(selected) == 1, 'one visible actual system close control required; no guessed coordinate/API fallback')
        node = selected[0]
        left, top, width, height = node['rect']
        io.ui.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2),
                    'services578_actual_system_close_' + feature)
        return {'layout': ref(path), 'selected_node': node}

    def switch_account(user):
        require(type(user) is int and user in (state['original_user'], state['secondary']), 'only original/newly owned account may be switched')
        from power_test_policy import power_timeout
        policy = power_timeout(shell('hidumper -s 3301 -a "-a"', 'account_policy_before')['stdout'])
        require(policy['override_ms'] in (None, 86400000), 'refuse to change a foreign PowerMgr override')
        state['power_override'] = policy['override_ms']
        if state['power_override'] is not None:
            shell('power-shell timeout -r', 'account_release_owned_timeout')
        row = shell('acm switch -i ' + str(user), 'switch_' + str(user), timeout=60)
        require('switch the local account successfully.' in row['stdout'], 'actual OS account switch rejected')
        deadline = time.monotonic() + 60
        while True:
            _accounts, actual, account = account_read('switched_account')
            if actual == user:
                break
            require(time.monotonic() < deadline, 'actual foreground OS account switch timed out')
            time.sleep(.5)
        state['active'] = actual
        # The original system-home preparation uses an ordinary actual lock
        # gesture and service/boot/policy readbacks; no common-event unlock shim.
        from run_application_home_probe import prepare as prepare_home
        home = {'boot_id': io.boot_id}
        io.ui.shell('uitest uiInput keyEvent Home', 'services578_account_actual_home')
        prepare_home(io.ui, home)
        listed = shell('bm dump -a -u ' + str(user), 'account_bundles')
        require('error:' not in listed['stdout'].lower(), 'actual per-user BMS list rejected')
        names = re.findall(r'(?m)^\s*((?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)\s*$', listed['stdout'])
        require(names, 'actual per-user BMS list has no recognizable bundle records')
        if state['power_override'] is not None:
            shell('power-shell timeout -o 86400000', 'account_restore_owned_timeout')
        require(power_timeout(shell('hidumper -s 3301 -a "-a"', 'account_policy_after')['stdout']) == policy,
                'original owned policy not restored after account switch')
        state['power_override'] = None
        return save_json('account_state', {'active_user_id': actual, 'installed_bundles': names,
            'account_raw': account['stdout_ref'], 'bms_raw': listed['stdout_ref'], 'home': home})

    def sleep_wake():
        from boot_package import kernel_sleeping, FATAL
        from power_test_policy import power_timeout
        from run_application_home_probe import prepare as prepare_home
        before = shell('hidumper -s 3301 -a "-a"', 'sleep_policy_before')
        policy = power_timeout(before['stdout'])
        require(policy['override_ms'] in (None, 86400000), 'refuse to change a foreign PowerMgr override')
        state['power_override'] = policy['override_ms']
        if policy['override_ms'] is not None:
            restored = shell('power-shell timeout -r', 'restore_original_owned_policy')
            require(restored['stdout'].strip() == 'Restore screen off time', 'actual original policy restore failed')
        foundation_before = shell('pidof foundation', 'sleep_foundation_before')['stdout_ref']
        render_before = shell('pidof render_service', 'sleep_render_before')['stdout_ref']
        serial_path = Path(io.guest.args.output) / 'qemu.log'
        deadline = time.monotonic() + max(60, policy['base_ms'] / 1000 + 30)
        # No HDC, hierarchy snapshots or recurring input during this quiet wait.
        while not kernel_sleeping(serial_path.read_text(errors='replace')):
            require(not FATAL.search(serial_path.read_text(errors='replace')), 'actual guest failure before suspend')
            require(time.monotonic() < deadline, 'actual default policy did not enter kernel s2idle')
            time.sleep(.5)
        before_key = save('serial_before_key.log', serial_path.read_bytes())
        io.qmp('system_powerdown')
        deadline = time.monotonic() + 30
        while kernel_sleeping(serial_path.read_text(errors='replace')):
            require(not FATAL.search(serial_path.read_text(errors='replace')), 'actual guest failure during wake')
            require(time.monotonic() < deadline, 'original QMP power key did not resume actual kernel')
            time.sleep(.25)
        after_key = save('serial_after_key.log', serial_path.read_bytes())
        home = {'boot_id': io.boot_id}
        prepare_home(io.ui, home)
        foundation_after = shell('pidof foundation', 'sleep_foundation_after')['stdout_ref']
        render_after = shell('pidof render_service', 'sleep_render_after')['stdout_ref']
        if state['power_override'] is not None:
            shell('power-shell timeout -o 86400000', 'restore_original_owned_test_timeout')
        after = shell('hidumper -s 3301 -a "-a"', 'sleep_policy_after')
        require(power_timeout(after['stdout']) == policy, 'original owned test policy was not restored')
        state['power_override'] = None
        return {'serial_before_key': before_key, 'serial_after_key': after_key, 'foundation_before': foundation_before,
            'foundation_after': foundation_after, 'render_before': render_before, 'render_after': render_after,
            'policy_before': before['stdout_ref'], 'policy_after': after['stdout_ref'], 'home': home}

    def input_action(action, payload):
        at = begin('input_' + action.replace('-', '_'))
        require(action in ('touch', 'home', 'force-stop', 'capture', 'close-feature', 'account-switch', 'sleep-wake'),
                'fixed actual user/resource action required')
        extra = {}
        if action == 'account-switch':
            extra['account_state'] = switch_account(payload['user_id'])
        else:
            role = payload['role']; role_check(role)
            if action == 'touch':
                require(payload['selector'] == 'services578-child-touch', 'fixed actual child control required')
                selected = io.ui.click(bundle(state['case'], role), identifier=payload['selector'], label='services578_child_touch')
                extra['selected'] = selected
            elif action == 'home':
                io.ui.shell('uitest uiInput keyEvent Home', 'services578_actual_home')
            elif action == 'force-stop':
                row = shell('aa force-stop ' + shlex.quote(bundle(state['case'], role)), 'force_stop_' + role)
                require('success' in row['stdout'].lower(), 'actual test-caller force-stop rejected')
            elif action == 'capture':
                frame = io.frame('services578_' + str(state['counter']))
                extra['frame'] = frame['frame'] if type(frame) is dict and 'frame' in frame else frame
                require(type(extra['frame']) is dict and set(extra['frame']) == {'path', 'sha256'}, 'actual original QMP frame Ref required')
            elif action == 'close-feature':
                require(payload['feature'] in ('pip', 'ball', 'view'), 'fixed real feature required')
                extra.update(actual_close(role, payload['feature']))
                state['pending_close'][role] = {'request_id': state['feature_requests'][(role, payload['feature'])], 'feature': payload['feature']}
            elif action == 'sleep-wake':
                extra.update(sleep_wake())
        return result(at, **extra)

    def cleanup():
        at = begin('cleanup')
        if state['closed'] or state['case'] is None:
            return result(at)
        errors = []

        def attempt(callback):
            try:
                callback()
                return True
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append(str(error))
                return False
        if state['power_override'] is not None:
            if attempt(lambda: shell('power-shell timeout -o 86400000', 'cleanup_restore_owned_timeout')):
                state['power_override'] = None
        if state['active'] != state['original_user']:
            attempt(lambda: switch_account(state['original_user']))
        if state['account_created'] and state['secondary'] is None:
            accounts, _active, _row = account_read('cleanup_allocated_account')
            added = set(accounts) - state['accounts_before']
            if len(added) == 1:
                state['secondary'] = next(iter(added))
            else:
                errors.append('cannot safely identify the newly allocated account for cleanup')
        def uninstall_owned(user, role):
            row = shell('bm uninstall -n ' + shlex.quote(bundle(state['case'], role)) + ' -u ' + str(user), 'cleanup_uninstall')
            require('uninstall bundle successfully.' in row['stdout'], 'actual owned caller uninstall failed')
            state['installed'].discard((user, role))

        for user, role in sorted(state['installed']):
            if user != state['original_user']:
                continue  # Only the newly created account owns the other copies.
            attempt(lambda user=user, role=role: uninstall_owned(user, role))
        if state['secondary'] is not None:
            def delete_secondary():
                user = state['secondary']
                row = shell('acm delete -i ' + str(user), 'cleanup_secondary_account', timeout=60)
                require('delete the local account successfully.' in row['stdout'], 'actual newly owned account deletion failed')
                accounts, _active, _row = account_read('cleanup_secondary_readback')
                require(user not in accounts, 'deleted test account remains in actual AccountMgr')
                state['installed'] = {(u, r) for u, r in state['installed'] if u != user}
                state['secondary'] = None
                state['account_created'] = False
            attempt(delete_secondary)
        if state['hosts_changed']:
            restore = '/data/local/tmp/services578_' + state['run'] + '_restore_hosts'
            state['temporary'].append(restore)
            def restore_hosts():
                io.send(state['hosts_backup'], restore, 'services578_restore_hosts_send')
                shell('cat ' + shlex.quote(restore) + ' > /system/etc/hosts', 'cleanup_hosts')
                mode, uid, gid = state['hosts_metadata']
                shell('chmod ' + mode + ' /system/etc/hosts', 'cleanup_hosts_mode')
                shell('chown ' + uid + ':' + gid + ' /system/etc/hosts', 'cleanup_hosts_owner')
                check = shell('cat /system/etc/hosts', 'cleanup_hosts_readback')
                require(check['stdout'].encode() == state['hosts_backup'].read_bytes(), 'original hosts bytes did not restore')
                require(shell("stat -c '%a %u %g' /system/etc/hosts", 'cleanup_hosts_metadata')['stdout'].strip().split() ==
                        state['hosts_metadata'], 'original hosts metadata did not restore')
                state['hosts_changed'] = False
            attempt(restore_hosts)
        if state['ca_path'] is not None:
            def remove_ca():
                shell('rm -f ' + shlex.quote(state['ca_path']), 'cleanup_only_owned_ca')
                shell('test ! -e ' + shlex.quote(state['ca_path']), 'cleanup_ca_readback')
                state['ca_path'] = None
            attempt(remove_ca)
        if state['rport'] is not None:
            def remove_rport():
                mapping = ' '.join(state['rport'])
                hdc(['fport', 'rm', mapping], 'cleanup_exact_rport')
                require(mapping + ' [Reverse]' not in hdc(['fport', 'ls'], 'cleanup_rport_readback')['stdout'],
                        'owned reverse mapping remains after removal')
                state['rport'] = None
            attempt(remove_rport)
        if state['network']:
            if attempt(io.https_close):
                state['network'] = False
        for path in sorted(set(state['temporary'])):
            attempt(lambda path=path: shell('rm -f ' + shlex.quote(path), 'cleanup_owned_temporary'))
        if state['mounts']:
            def restore_mounts():
                current = mounts(shell('cat /proc/mounts', 'cleanup_mounts_current')['stdout'])
                for point, flags in state['mounts'].items():
                    if 'ro' in flags and 'rw' in current.get(point, []):
                        shell('mount -o remount,ro ' + shlex.quote(point), 'cleanup_mount_readonly')
                final = mounts(shell('cat /proc/mounts', 'cleanup_mounts_readback')['stdout'])
                require(all('ro' not in flags or 'ro' in final.get(point, []) for point, flags in state['mounts'].items()),
                        'original read-only mount state did not restore')
            attempt(restore_mounts)
        def account_restored():
            _accounts, active, _row = account_read('cleanup_account_readback')
            require(active == state['original_user'], 'original foreground account was not restored')
        attempt(account_restored)
        state['closed'] = not errors
        require(not errors, 'actual owned cleanup failures: ' + '; '.join(errors))
        return result(at)

    io.register_cleanup(cleanup)
    return {'prepare_callers': prepare_callers, 'install': install, 'start': start, 'input': input_action,
            'collect': collect, 'network': network, 'cleanup': cleanup}
