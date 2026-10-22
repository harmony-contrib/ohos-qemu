"""Finite Apps579 business bindings on the original Owner's held IO.

No Owner, Collector, GuestUi, runner, subprocess, socket or lease is created.
The seven callbacks return actual raw records, never provider verdicts.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

from apps_providers579_project import ACTIONS, ROLES, bundle, require, validate
from guest_ui import NodeNotReady, LayoutNotReady, select_node, bounds


def raw(reference):
    require(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'immutable actual Ref required')
    path = Path(reference['path'])
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'regular actual file required')
    body = path.read_bytes()
    require(hashlib.sha256(body).hexdigest() == reference['sha256'], 'raw evidence changed')
    return body


def objects(value):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from objects(child)
    elif type(value) is list:
        for child in value:
            yield from objects(child)


def bms_json(text):
    for offset, char in enumerate(text):
        if char == '{':
            try:
                value, _ = json.JSONDecoder().raw_decode(text[offset:])
            except ValueError:
                continue
            if type(value) is dict:
                return value
    raise ValueError('actual BMS dump has no JSON object')


def bind(root_io):
    io = root_io
    output_root = Path(io.output) / 'apps_providers579'
    output_root.mkdir(parents=True, exist_ok=True)
    require(output_root.is_absolute() and not output_root.is_symlink(), 'original owned output required')
    output = None
    state = {'case': None, 'run': None, 'callers': {}, 'installed': set(), 'temporary': [],
             'serial': 0, 'prefix': {}, 'last': {}, 'identities': {}, 'closed': False,
             'radio_renamed': False, 'peer_transport': None, 'captures': {}, 'cleaned_roles': set()}
    state['owned_media'] = set()
    state['retired_media'] = set()
    state['wifi_dir'] = None
    state['wifi_peer_mode'] = None

    def save(name, body):
        require(output is not None and output.is_dir() and not output.is_symlink(), 'case-owned output not prepared')
        state['serial'] += 1
        path = output / ('%05d_' % state['serial'] + name)
        path.write_bytes(body.encode() if type(body) is str else body)
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def save_json(name, value):
        return save(name + '.json', json.dumps(value, indent=2, ensure_ascii=False) + '\n')

    def shell(script, label, *, timeout=60, allow_failure=False):
        require(re.fullmatch('[A-Za-z0-9_-]+', label), 'finite Guest shell label required')
        row = io.shell('set -e\n' + script, 'apps579_' + label, timeout=timeout, allow_failure=allow_failure)
        require(row['boot_id'] == io.boot_id and (allow_failure or row['exit_code'] == 0), 'original guest command failed')
        return row

    def begin(label):
        at = len(io.receipts), len(io.qmp_receipts)
        require(shell('cat /proc/sys/kernel/random/boot_id', label + '_boot')['stdout'].strip() == io.boot_id,
                'original guest boot changed')
        return at

    def result(at, **extra):
        return {'boot_id': io.boot_id, 'archive_sha256': io.archive_sha256,
                'commands': [io.ref_receipt(row) for row in io.receipts[at[0]:]],
                'qmp_records': io.qmp_receipts[at[1]:], **extra}

    def role_check(role):
        require(state['case'] in ROLES and role in ROLES[state['case']], 'fixed compiled role required')

    def directory(role):
        role_check(role)
        return '/data/app/el2/100/base/' + bundle(state['case'], role) + '/files'

    def request_check(role, action, request):
        role_check(role)
        require(action in ACTIONS[state['case']] and type(request) is dict and
                set(request) == {'run_id', 'request_id', 'action', 'payload'} and
                request['run_id'] == state['run'] and request['action'] == action and
                re.fullmatch('[a-z0-9_-]{1,64}', request['request_id']) and type(request['payload']) is dict,
                'source-defined action and nonce-bound request required')
        payload = request['payload']
        allowed = {'read-ungranted': {'uri', 'video'}, 'read-denied': {'uri'}, 'cleanup-owned': {'uri'},
                   'use-owned-fixture': {'uri'}, 'p2p-connect': {'peer_mac'}}.get(action, set())
        require(set(payload) <= allowed and all(type(v) in (str, bool, int) for v in payload.values()),
                'request JSON may contain data only, never executable/module/UI selectors')
        if 'peer_mac' in payload:
            require(re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}', payload['peer_mac']), 'actual P2P discovery address data')
        if 'uri' in payload:
            require(re.fullmatch(r'file://media/Photo/[A-Za-z0-9_./%-]{1,1024}', payload['uri']), 'actual Photo URI required')
        if action == 'cleanup-owned':
            require(role == 'janitor' and payload.get('uri') in state['owned_media'], 'only this run raw-journal-created media may be deleted')

    def launch(role, action, request):
        request_check(role, action, request)
        argv = ['aa', 'start', '-b', bundle(state['case'], role), '-a', 'EntryAbility', '-m', 'entry', '-u', '100']
        for key in ('run_id', 'request_id', 'action'):
            argv += ['--ps', key, request[key]]
        argv += ['--ps', 'payload', json.dumps(request['payload'], separators=(',', ':'))]
        row = shell(shlex.join(argv), 'start_' + role + '_' + request['request_id'])
        require('start ability successfully' in row['stdout'].lower(), 'actual AMS rejected caller')
        state['last'][role] = request

    def pull(role):
        base = directory(role)
        listing = shell('ls ' + base + '/apps579-' + state['run'] + '-*.jsonl', 'journal_list_' + role, allow_failure=True)
        require(listing['exit_code'] in (0, 1, 2), 'actual journal listing failed')
        contents, rows, files = [], [], []
        for remote in sorted(listing['stdout'].splitlines() if listing['exit_code'] == 0 else []):
            require(re.fullmatch(re.escape(base + '/apps579-' + state['run'] + '-') + r'[1-9][0-9]*\.jsonl', remote),
                    'unexpected caller journal path')
            state['serial'] += 1
            local = output / ('pull_%05d.jsonl' % state['serial'])
            io.receive(remote, local, 'apps579_journal_' + str(state['serial']))
            body = local.read_bytes()
            previous = state['prefix'].get(remote, b'')
            require(body.startswith(previous) and body.endswith(b'\n'), 'journal truncated/replaced/partial')
            state['prefix'][remote] = body
            parsed = [json.loads(line) for line in body.decode().splitlines() if line]
            for index, row in enumerate(parsed):
                require(row['run_id'] == state['run'] and row['kind'] == state['case'] and row['role'] == role and
                        row['bundle'] == bundle(state['case'], role) and row['seq'] == index and
                        type(row['uid']) is int and type(row['pid']) is int and
                        remote.endswith('-' + str(row['pid']) + '.jsonl'), 'caller identity/sequence mismatch')
                if role in state['identities']:
                    require(row['uid'] == state['identities'][role]['uid'], 'journal UID changed')
            contents.append(body); rows.extend(parsed)
            files.append({'remote': remote, 'raw': {'path': str(local), 'sha256': hashlib.sha256(body).hexdigest()}})
        return b''.join(contents), rows, files

    def collect(role, request_id):
        at = begin('collect_' + role)
        role_check(role)
        require(re.fullmatch('[a-z0-9_-]{1,64}', request_id), 'finite request ID required')
        deadline = time.monotonic() + 30
        previous, quiet = None, time.monotonic()
        while True:
            body, rows, files = pull(role)
            selected = [r for r in rows if r['request_id'] == request_id]
            if body != previous:
                previous, quiet = body, time.monotonic()
            terminal = any(r['event'] in ('done', 'error', 'request-error', 'page-error') for r in selected)
            if (terminal and time.monotonic() - quiet >= 1) or time.monotonic() >= deadline:
                break
            time.sleep(.25)
        require(body, 'actual caller journal absent')
        for row in rows:
            if row['role'] == 'normal' and row['event'] == 'creation-dialog-result':
                created = json.loads(row['value'])
                require(type(created) is list and len(created) <= 1, 'one owned fresh creation dialog result')
                state['owned_media'].update(uri for uri in created if uri not in state['retired_media'])
            if row['role'] == 'normal' and row['event'] == 'asset-created':
                uri = json.loads(row['value'])['uri']
                if uri not in state['retired_media']:
                    state['owned_media'].add(uri)
            if row['role'] == 'normal' and row['event'] == 'picker-result':
                picked = json.loads(row['value'])
                if picked['resultCode'] == 0 and picked['resultUri']:
                    if picked['resultUri'] not in state['retired_media']:
                        state['owned_media'].add(picked['resultUri'])
        if role == 'janitor':
            active = [json.loads(row['value']) for row in selected if row['event'] == 'cleanup-active-after']
            trash = [json.loads(row['value']) for row in selected if row['event'] == 'cleanup-trash-after']
            if len(active) == len(trash) == 1 and active[0]['uri'] == trash[0]['uri'] and active[0]['count'] == trash[0]['count'] == 0:
                state['owned_media'].discard(active[0]['uri'])
                state['retired_media'].add(active[0]['uri'])
        binaries = []
        for row in selected:
            if row['event'] not in ('media-bytes', 'capture-started'):
                continue
            value = json.loads(row['value'])
            suffix = ('apps579-media-' + request_id + '.bin' if row['event'] == 'media-bytes' else
                      'apps579-input-' + request_id + '.pcm')
            remote = directory(role) + '/' + suffix
            require(value['file'] == suffix or value['file'].endswith('/' + suffix), 'unexpected caller byte artifact')
            state['serial'] += 1
            local = output / ('binary_%05d_' % state['serial'] + suffix)
            io.receive(remote, local, 'apps579_binary_' + str(state['serial']))
            data = local.read_bytes()
            require(0 < len(data) <= 32 * 1024 * 1024, 'empty/unbounded actual media bytes')
            digest = hashlib.sha256(data).hexdigest()
            if row['event'] == 'media-bytes':
                require(value['size'] == len(data) and value['sha256'].lower() == digest, 'guest/host actual bytes disagree')
            binaries.append({'event': row['event'], 'request_id': request_id,
                             'raw': {'path': str(local), 'sha256': digest}, 'bytes': len(data)})
        return result(at, journal=save('journal_' + role + '_' + request_id + '.jsonl', body),
                      journal_files=files, binaries=binaries, terminal_observed=terminal)

    def prepare_callers(case, run_id, roles):
        nonlocal output
        validate(case, run_id)
        require(state['case'] is None and run_id == io.run_id and tuple(roles) == ROLES[case], 'prepare once on root nonce')
        output = output_root / (case + '_' + run_id)
        output.mkdir(exist_ok=False)
        at = begin('prepare')
        environment = io.test_environment if hasattr(io, 'test_environment') else io.guest.report['test_environment']
        profile = environment['device_type']
        require(profile in ('phone', '2in1'), 'actual boot package device profile required')
        account = shell('hidumper -s AccountMgr -a "-os_account_infos"', 'account')
        require(re.search(r'ID:\s*100\b(?:(?!ID:).)*isForeground:\s*(?:true|1)\b', account['stdout'], re.S),
                'original account100 must be foreground')
        state.update(case=case, run=run_id)
        if roles:
            built = io.prepare_callers('apps_providers579', case, run_id, roles, {'profile': profile, 'udid': io.udid})
            require(built['case'] == case and built['run_id'] == run_id and built['boot_id'] == io.boot_id,
                    'root build/sign binding differs')
            state['callers'] = built['callers']
        else:
            built = {'case': case, 'run_id': run_id, 'boot_id': io.boot_id, 'callers': {}}
        return dict(built, profile=profile, archive_sha256=io.archive_sha256, environment_records=result(at))

    def install(role):
        at = begin('install_' + role)
        role_check(role)
        local = Path(state['callers'][role]['signed']['path'])
        remote = '/data/local/tmp/apps579_' + state['run'] + '_' + role + '.hap'
        io.send(local, remote, 'apps579_send_' + role); state['temporary'].append(remote)
        installed = shell(shlex.join(['bm', 'install', '-r', '-p', remote, '-u', '100']), 'install_' + role, timeout=600)
        require('install bundle successfully.' in installed['stdout'], 'real BMS install failed')
        state['installed'].add(role)
        bms = shell(shlex.join(['bm', 'dump', '-n', bundle(state['case'], role), '-u', '100']), 'bms_' + role)
        identity_id = 'identity_' + role
        launch(role, 'identity', {'run_id': state['run'], 'request_id': identity_id, 'action': 'identity', 'payload': {}})
        observed = collect(role, identity_id)
        rows = [json.loads(line) for line in raw(observed['journal']).decode().splitlines() if line]
        selected = [r for r in rows if r['request_id'] == identity_id and r['event'] == 'self-identity' and r['code'] == 0]
        require(len(selected) == 1, 'actual installed identity self-query required')
        identity = dict(json.loads(selected[0]['value']), uid=selected[0]['uid'], user_id=100,
                        bms_raw=bms['stdout_ref'], self_query_raw=observed['journal'])
        require(identity['bundle'] == bundle(state['case'], role) and
                identity['fingerprint'] == state['callers'][role]['identity']['fingerprint'], 'real signer differs')
        require(any(o.get('bundleName') == identity['bundle'] and o.get('uid') == identity['uid'] and
                    o.get('fingerprint') == identity['fingerprint'] for o in objects(bms_json(bms['stdout']))),
                'BMS/kernel/self identities disagree')
        state['identities'][role] = identity
        return result(at, identity=save_json('identity_' + role, identity))

    def start(role, action, request):
        at = begin('start_' + role)
        launch(role, action, request)
        return result(at, request=save_json('request_' + role + '_' + request['request_id'], request),
                      identity=save_json('request_identity_' + role, state['identities'][role]))

    def snapshot(label):
        layout, path = io.ui.layout(label='apps579_' + label)
        return {'layout': save_json(label + '_layout', layout), 'original_layout': str(path),
                'frame': io.frame('apps579_' + label),
                'windows': shell('hidumper -s 4606 -a "-a"', label + '_windows')['stdout_ref'],
                'processes': shell('ps -ef', label + '_processes')['stdout_ref']}

    # Text alternatives come from the fixed provider resources. Only one
    # visible enabled node in the actual specified bundle is accepted.
    controls = {
        'location-accept': ('com.ohos.locationdialog', ('Agree', '同意')),
        'location-reject': ('com.ohos.locationdialog', ('Cancel', '取消')),
        'location-details': ('com.ohos.locationdialog', ('Statement About Location Services and Privacy', '定位服务与隐私声明')),
        'vpn-allow': ('com.ohos.vpndialog', ('Allow', '允许')),
        'vpn-deny': ('com.ohos.vpndialog', ('Cancel', '取消'))}

    def nodes(layout, owners, types):
        pending = [(r, '') for r in (layout if type(layout) is list else [layout])]
        selected = {}
        while pending:
            node, inherited = pending.pop()
            attrs = node['attributes']; owner = attrs.get('bundleName') or inherited
            if owner in owners and attrs.get('visible') == 'true' and attrs.get('enabled') == 'true' and attrs.get('type') in types:
                rect = tuple(bounds(attrs.get('bounds')))
                selected[rect] = {'attributes': attrs, 'bundle': owner, 'rect': list(rect)}
            pending.extend((c, owner) for c in node.get('children', []))
        return list(selected.values())

    def input(action, payload):
        at = begin('input_' + action)
        require(type(payload) is dict, 'finite input data required')
        if action == 'snapshot':
            require(set(payload) == {'label'} and re.fullmatch('[a-z0-9_-]{1,48}', payload['label']), 'finite snapshot label')
            return result(at, observation=snapshot(payload['label']))
        if action == 'back':
            require(payload == {}, 'Back has no injected semantic payload')
            io.ui.shell('uitest uiInput keyEvent Back', 'apps579_real_back')
        elif action == 'force-stop':
            require(set(payload) == {'role'}, 'owned caller role required')
            role_check(payload['role'])
            shell(shlex.join(['aa', 'force-stop', bundle(state['case'], payload['role']), '-u', '100']), 'owned_force_stop')
        elif action in controls:
            require(payload == {}, 'fixed real provider control required')
            provider, texts = controls[action]
            layout, path = io.ui.layout(label='apps579_' + action)
            matches = []
            for text in texts:
                try:
                    matches.append(select_node(layout, provider, text=text, clickable=True))
                except NodeNotReady:
                    pass
            require(len(matches) == 1, 'one actual source-bound provider control required')
            x, y, w, h = matches[0]['rect']
            io.ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h // 2), 'apps579_control_' + action)
            return result(at, selected_node=matches[0], layout=save_json(action + '_layout', layout), original_layout=str(path))
        elif action == 'caller-control':
            require(set(payload) == {'role', 'control'} and payload['control'] in ('touch', 'input'), 'finite caller control')
            role_check(payload['role'])
            identifier = 'apps579-caller-touch' if payload['control'] == 'touch' else 'apps579-input-picker'
            return result(at, selected=io.ui.click(bundle(state['case'], payload['role']), identifier=identifier,
                                                   label='apps579_caller_control'))
        elif action == 'camera-control':
            identifiers = {'photo': 'COMPONENT_ID_SHUTTER_PHOTO_1', 'video': 'COMPONENT_ID_SHUTTER_VIDEO_1',
                'video-stop': 'COMPONENT_ID_SHUTTER_VIDEO_END_1', 'confirm': 'COMPONENT_ID_THIRDPARTYCALL_CONFIRM_1',
                'cancel': 'COMPONENT_ID_THIRDPARTYCALL_BACK_1', 'privacy': 'PICKER_PRIVACY_BANNER_BUTTON'}
            require(state['case'] == 'camera' and set(payload) == {'control'} and payload['control'] in identifiers,
                    'actual common/ComponentIdKeys camera control only')
            deadline = time.monotonic() + 30
            while True:
                try:
                    selected = io.ui.click('com.ohos.camera', identifier=identifiers[payload['control']], label='apps579_camera_control')
                    return result(at, selected=selected)
                except (NodeNotReady, LayoutNotReady):
                    require(time.monotonic() < deadline, 'actual camera provider control did not appear')
                    time.sleep(.25)
        elif action == 'volume-slider':
            require(state['case'] == 'volume' and payload in ({'level': 'low'}, {'level': 'high'}), 'two finite real slider gestures')
            layout, path = io.ui.layout(label='apps579_volume_slider')
            candidates = nodes(layout, {'com.hmos.mediacontroller', bundle('volume', 'grant')}, {'Slider'})
            require(len(candidates) == 1, 'one actual provider Slider required')
            selected = candidates[0]; x, y, w, h = selected['rect']
            quarter = 1 if payload['level'] == 'high' else 3
            # Actual ABC sets Axis.Vertical/reverse=true. Source geometry,
            # actual hierarchy and quarter points bind this physical gesture.
            require(h > w, 'actual reviewed vertical volume slider required')
            io.ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h * quarter // 4), 'apps579_actual_volume_gesture')
            return result(at, selected_node=selected, layout=save_json('volume_slider_layout', layout), original_layout=str(path))
        elif action == 'photos-select-fixture':
            require(state['case'] in ('photos', 'photosform') and payload == {}, 'owned Knowledge nonce image only')
            fixture = json.loads(raw(io.package_inputs['apps579_knowledge_fixture']))
            case = fixture['challenge']['cases'][0]
            raw(case['image'])
            from batch_media_verify_wallpaper_runtime import pixels
            deadline = time.monotonic() + 30
            while True:
                try:
                    layout, path = io.ui.layout(label='apps579_photos_nonce')
                    screen = io.ui.screenshot(label='apps579_photos_nonce')
                    candidates = []
                    for node in nodes(layout, {'com.ohos.photos', bundle(state['case'], 'grant' if state['case'] == 'photosform' else 'normal')}, {'Image', 'GridItem'}):
                        try:
                            metrics = pixels(screen, case['image']['path'], node['rect'], minimum_fraction=.85)
                            candidates.append((node, metrics))
                        except ValueError:
                            pass
                    require(len(candidates) <= 1, 'ambiguous actual nonce thumbnail')
                    if not candidates:
                        raise NodeNotReady('actual nonce thumbnail not painted')
                    break
                except (NodeNotReady, LayoutNotReady):
                    require(time.monotonic() < deadline, 'real Photos nonce thumbnail did not appear')
                    time.sleep(.25)
            node, metrics = candidates[0]
            x, y, w, h = node['rect']
            ams = shell('aa dump -a -u 100', 'photos_actual_provider')['stdout_ref']
            io.ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h // 2), 'apps579_nonce_thumbnail')
            # The already preselected URI normally exposes Complete. A
            # single-select return can close immediately; absence is retained
            # and the caller result, URI and bytes decide that path.
            completed = []
            after, after_path = io.ui.layout(label='apps579_photos_after_nonce')
            for owner in ('com.ohos.photos', bundle(state['case'], 'grant' if state['case'] == 'photosform' else 'normal')):
                try:
                    completed.append(io.ui.click(owner, identifier='Complete', label='apps579_photos_complete'))
                except NodeNotReady:
                    pass
            require(len(completed) <= 1, 'ambiguous real Photos Complete')
            return result(at, selected_node=node, metrics=metrics, layout=save_json('photos_nonce_layout', layout),
                screenshot={'path': str(screen), 'sha256': hashlib.sha256(Path(screen).read_bytes()).hexdigest()},
                original_layout=str(path), provider_ams=ams, case_id=case['case_id'], uri=fixture['uris'][case['case_id']],
                complete=completed, after_layout=save_json('photos_after_layout', after), original_after_layout=str(after_path))
        elif action == 'photoform-select-photo':
            require(state['case'] == 'photosform' and payload == {}, 'actual declared form configuration UI only')
            deadline = time.monotonic() + 30
            while True:
                try:
                    layout, path = io.ui.layout(label='apps579_form_config')
                    matches = []
                    def visit(node, inherited='', ancestors=()):
                        attrs = node['attributes']; owner = attrs.get('bundleName') or inherited
                        chain = ancestors + ((node, owner),)
                        if owner == 'com.ohos.photos' and attrs.get('visible') == 'true' and attrs.get('text') in ('Select a photo', '选择图片'):
                            parents = [(parent, who) for parent, who in reversed(chain) if who == owner and
                                parent['attributes'].get('type') == 'ListItem' and
                                parent['attributes'].get('clickable') == 'true' and
                                parent['attributes'].get('enabled') == 'true' and parent['attributes'].get('visible') == 'true']
                            require(parents, 'source FormEditor ListItem ancestor missing')
                            matches.append({'attributes': parents[0][0]['attributes'], 'bundle': owner,
                                            'rect': list(bounds(parents[0][0]['attributes']['bounds'])), 'text': attrs['text']})
                        for child in node.get('children', []):
                            visit(child, owner, chain)
                    for node in (layout if type(layout) is list else [layout]):
                        visit(node)
                    require(len(matches) <= 1, 'ambiguous actual form editor select-photo ListItem')
                    if not matches:
                        raise NodeNotReady('actual form configuration selector absent')
                    break
                except (NodeNotReady, LayoutNotReady):
                    require(time.monotonic() < deadline, 'real form editor did not appear')
                    time.sleep(.25)
            node = matches[0]; x, y, w, h = node['rect']
            io.ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h // 2), 'apps579_form_select_photo')
            return result(at, selected_node=node, layout=save_json('form_editor_layout', layout), original_layout=str(path))
        elif action == 'photoform-pixels':
            require(state['case'] == 'photosform' and payload in ({'expected': 'visible'}, {'expected': 'absent'}),
                    'finite native form nonce pixel observation only')
            fixture = json.loads(raw(io.package_inputs['apps579_knowledge_fixture']))
            challenge = fixture['challenge']['cases'][0]
            raw(challenge['image'])
            from batch_media_verify_wallpaper_runtime import pixels
            deadline = time.monotonic() + 30
            samples, consecutive = [], 0
            while True:
                try:
                    layout, path = io.ui.layout(label='apps579_native_form')
                    node = select_node(layout, bundle('photosform', 'grant'), identifier='apps579-form-widget')
                    frame = io.frame('apps579_native_form')
                    try:
                        metrics = pixels(frame['path'], challenge['image']['path'], node['rect'], minimum_fraction=.85)
                        match = True
                    except ValueError as error:
                        require(str(error) == 'new challenged wallpaper pixels not independently painted',
                                'invalid capture/geometry is never an absent-image oracle')
                        metrics, match = {'raw_mismatch': str(error)}, False
                    samples.append({'layout': save_json('form_pixel_layout', layout), 'original_layout': str(path),
                        'frame': frame, 'selected_node': node, 'metrics': metrics, 'nonce_matches': match})
                    wanted = payload['expected'] == 'visible'
                    consecutive = consecutive + 1 if match == wanted else 0
                    if consecutive == 2:
                        break
                except (NodeNotReady, LayoutNotReady):
                    consecutive = 0
                require(time.monotonic() < deadline, 'actual native form did not render the required post-mutation nonce state')
                time.sleep(.5)
            return result(at, phase=fixture['phase'], case_id=challenge['case_id'],
                          uri=fixture['uris'][challenge['case_id']], expected=payload['expected'], samples=samples,
                          service_log=shell('hilog -x', 'form_actual_service_log')['stdout_ref'])
        elif action == 'photos-consent':
            require(state['case'] in ('photos', 'camera') and payload in ({'kind': 'save'}, {'kind': 'delete'}) and
                    (state['case'] == 'photos' or payload['kind'] == 'delete'), 'fixed one-image real Photos consent')
            from apps_providers579_dialog import select
            deadline = time.monotonic() + 30
            while True:
                try:
                    layout, path = io.ui.layout(label='apps579_photos_consent')
                    node, contract = select(layout, state['run'], payload['kind'], state['case'])
                    break
                except (NodeNotReady, LayoutNotReady):
                    require(time.monotonic() < deadline, 'actual Photos consent never ready')
                    time.sleep(.25)
            x, y, w, h = node['rect']
            io.ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h // 2), 'apps579_real_photos_consent')
            return result(at, selected_node=node, contract=contract, layout=save_json('photos_consent_layout', layout), original_layout=str(path))
        elif action == 'media-permission':
            require(state['case'] in ('photos', 'camera') and payload == {}, 'owned READ/WRITE cleanup role only')
            label = 'Apps579 ' + state['case'] + ' janitor ' + state['run'][:8]
            deadline = time.monotonic() + 30
            while True:
                _body, values, _files = pull('janitor')
                permissions = [json.loads(row['value']) for row in values if row['event'] == 'permission-result']
                if permissions:
                    return result(at, permission_journal=save('janitor_permission.jsonl', _body))
                try:
                    layout, path = io.ui.layout(label='apps579_media_permission')
                    candidates = []
                    for title, allow in (('允许“' + label + '”访问图片和视频？', '允许'),
                        ('Allow ' + label + ' to access images and videos on your device?', 'Allow')):
                        try:
                            select_node(layout, 'com.ohos.permissionmanager', text=title)
                            candidates.append(io.ui.click('com.ohos.permissionmanager', text=allow, label='apps579_media_allow'))
                        except NodeNotReady:
                            pass
                    if candidates:
                        require(len(candidates) == 1, 'one actual caller-named permission dialog')
                        return result(at, selected=candidates[0], title_layout=save_json('media_permission_layout', layout))
                except LayoutNotReady:
                    pass
                require(time.monotonic() < deadline, 'actual requested media permission did not finish or appear')
                time.sleep(.25)
        else:
            raise ValueError('unimplemented finite input action; no arbitrary coordinates/text fallback')
        return result(at, observation=snapshot(action))

    def network(action, parameters):
        at = begin('network_' + action)
        require(type(parameters) is dict, 'finite network action data required')
        if action == 'cast-native-observations':
            require(state['case'] == 'cast' and parameters == {} and 'grant' in state['installed'],
                    'fixed installed cast grant caller observations only')
            body, journal_rows, journal_files = pull('grant')
            require(body and journal_rows, 'actual cast journal required before native observation')
            pids = sorted(set(row['pid'] for row in journal_rows))
            require(len(pids) <= 8 and all(type(pid) is int and 0 < pid <= 4194304 for pid in pids),
                    'bounded actual journal-owned process set required')
            observations = []

            def capture(name, script):
                receipt = shell(script, 'cast_native_' + name)
                observations.append({'name': name, 'script': script, 'raw': receipt['stdout_ref'],
                                     'command': len(io.receipts) - 1 - at[0]})
                return name

            processes = []
            for pid in pids:
                suffix = str(pid)
                before = 'if test -d /proc/' + suffix + '; then cat /proc/' + suffix + '/stat; else printf "CAST579_ABSENT\\n"; fi'
                status = 'if test -d /proc/' + suffix + '; then cat /proc/' + suffix + '/status; else printf "CAST579_ABSENT\\n"; fi'
                processes.append({'pid': pid, 'observations': {
                    'stat_before': capture('stat_before_' + suffix, before),
                    'status': capture('status_' + suffix, status)}})
            capture('hilog', 'hilog -x')
            capture('ams', 'aa dump -a -u 100')
            capture('bms', shlex.join(['bm', 'dump', '-n', bundle('cast', 'grant'), '-u', '100']))
            capture('ps', 'ps -ef')
            for process in processes:
                suffix = str(process['pid'])
                after = 'if test -d /proc/' + suffix + '; then cat /proc/' + suffix + '/stat; else printf "CAST579_ABSENT\\n"; fi'
                process['observations']['stat_after'] = capture('stat_after_' + suffix, after)
            capture('boot_end', 'cat /proc/sys/kernel/random/boot_id')
            return result(at, schema='actual-cast579-native-observations/v1', run_id=state['run'],
                          bundle=bundle('cast', 'grant'),
                          identity=save_json('cast_native_identity', state['identities']['grant']),
                          journal=save('cast_native_journal.jsonl', body), journal_files=journal_files,
                          observations=observations, processes=processes)
        if action == 'knowledge-fixture':
            require(state['case'] in ('photos', 'photosform') and parameters == {}, 'original Photos fixture only')
            reference = io.package_inputs.get('apps579_knowledge_fixture')
            fixture = json.loads(raw(reference))
            require(fixture['archive_sha256'] == io.archive_sha256 and fixture['boot_id'] == io.boot_id and
                    fixture['phase'] in ('prepare', 'hidden', 'unhidden', 'trashed', 'recovered', 'deleted', 'cleanup') and
                    fixture['cleanup_owner'] == 'original_batch_media_knowledge_suite_Collector' and fixture['uris'],
                    'actual in-process Knowledge phase hook fixture required')
            for reference in (fixture['curator_pid'], fixture['curator_journal'], fixture['phase_journal']):
                raw(reference)
            require(all(type(u) is str and u.startswith('file://media/Photo/') for u in fixture['uris'].values()),
                    'actual PhotoAssets URI required')
            return result(at, fixture=io.package_inputs['apps579_knowledge_fixture'])
        if action == 'photoform-provider':
            require(state['case'] == 'photosform' and parameters == {}, 'actual fixed Photos provider observations only')
            app_types = shell('param get const.bms.supportAppTypes', 'photos_app_types')
            bms = shell('bm dump -n com.ohos.photos -u 100', 'photos_provider_bms')
            services = shell('hidumper -ls', 'photos_form_services')
            return result(at, app_types=app_types['stdout'].strip(), app_types_raw=app_types['stdout_ref'],
                          provider_bms=bms['stdout_ref'], services=services['stdout_ref'])
        if action == 'strict-vpn':
            require(state['case'] == 'vpn' and parameters == {}, 'original Network strict result only')
            # run_on_owner itself belongs to the original NetworkOwner. A
            # narrow OpenVPN cleanup result is never accepted as a TLS peer.
            manifest = io.package_inputs.get('apps579_network_strict_result')
            require(type(manifest) is dict and set(manifest) == {'owner_result', 'peer_steps', 'boot'},
                    'three actual original Network output files required, no synthesized peer schema')
            observed = json.loads(raw(manifest['owner_result']))
            steps = json.loads(raw(manifest['peer_steps']))
            boot = json.loads(raw(manifest['boot']))
            require(observed['scope'] == 'raw_original_peer15_and_strict375_protocol_ONLY' and
                    observed['guest_steps_ok'] is True and observed['protocol']['closed'] is True and
                    observed['protocol']['original_outcomes_verified'] is True, 'actual original protocol verification required')
            require(steps['scope'] == 'actual_raw_peer15_steps_complete_process_GET7_FD_cuts_NOT_aggregate_TLS_TUN_cleanup_pass' and
                    steps['archive']['sha256'] == io.archive_sha256 and steps['boot'] == manifest['boot'] and
                    steps['failures'] == [] and steps['stages'] and steps['fresh_status_has_expected_client'] is True and
                    boot['archive_sha256'] == io.archive_sha256 and boot['test_environment']['boot_id'] == io.boot_id,
                    'actual original peer steps/boot/package differ')
            return result(at, original_strict_peer=manifest,
                          original_manual_aggregate_pending=steps['manual_aggregate_verification_pending'],
                          original_snapshot=shell('ip address\nip route\nps -ef', 'vpn_after_strict')['stdout_ref'])
        if action == 'family-evidence':
            require(state['case'] in ('exports', 'published', 'sysvpn') and parameters == {}, 'finite aggregate source families only')
            families = getattr(io, 'apps579_family_results', None)
            require(type(families) is dict, 'root must attach actual completed original family records')
            allowed = {'apps_ui578', 'live_inputs578', 'audio578', 'rtt578', 'system_services578',
                       'network578', 'knowledge', 'api26_surface', 'apps579_exports', 'apps579_imagegen',
                       'apps579_ethernet', 'apps579_sysvpn', 'apps579_alwaysvpn'}
            require(set(families) <= allowed and families, 'unknown source family')
            verified = {}
            for name, reference in families.items():
                value = json.loads(raw(reference))
                require(value['archive_sha256'] == io.archive_sha256 and value['boot_id'] == io.boot_id,
                        'aggregate family must come from actual same package/boot')
                verified[name] = reference
            return result(at, families=verified)
        if action == 'wifi-radio-prepare':
            require(state['case'] == 'wifi' and parameters == {} and not state['radio_renamed'], 'one owned hwsim fixture')
            # Two real hwsim phys, not an invented WLAN backend. Free wlan1
            # for the actual AP HDI's interface on phy0; leave the second real
            # radio available to a source-bound independent endpoint stage.
            radios = shell('readlink -f /sys/class/net/wlan0/phy80211\nreadlink -f /sys/class/net/wlan1/phy80211\n'
                'cat /sys/class/net/wlan0/operstate\ncat /sys/class/net/wlan1/operstate\n'
                'test ! -e /sys/class/net/s579peer\ntest -x /vendor/bin/hostapd\n'
                'test -x /vendor/bin/wpa_supplicant\ntest -x /vendor/bin/wpa_cli', 'wlan_actual_inventory')
            lines = radios['stdout'].splitlines()
            require(len(lines) >= 4 and lines[0] != lines[1] and '/ieee80211/phy' in lines[0] and
                    '/ieee80211/phy' in lines[1] and lines[2:4] == ['down', 'down'], 'two idle distinct actual hwsim radios required')
            shell('ip link set wlan1 down\nip link set wlan1 name s579peer\n'
                  'readlink -f /sys/class/net/s579peer/phy80211', 'wlan_peer_rename')
            state['radio_renamed'] = True
            return result(at, radio_inventory=radios['stdout_ref'])
        if action == 'wifi-radio-collect':
            require(state['case'] == 'wifi' and parameters == {}, 'actual WLAN service snapshot only')
            records = {}
            for name, script in {'links': 'ip -details link', 'addresses': 'ip address', 'routes': 'ip route',
                                 'wifi': 'hidumper -s 1120', 'netmanager': 'hidumper -s 1151',
                                 'dhcp': 'ps -ef', 'hilog': 'hilog -x'}.items():
                records[name] = shell(script, 'wifi_' + name, allow_failure=True)['stdout_ref']
            return result(at, records=records)
        if action == 'wifi-peer-start':
            require(state['case'] == 'wifi' and state['radio_renamed'] and state['peer_transport'] is None and
                    parameters in ({'mode': 'ap'}, {'mode': 'sta'}), 'one source-bound real independent hwsim radio process')
            mode = parameters['mode']
            remote = '/data/local/tmp/apps579_wifi_' + state['run']
            if state['wifi_dir'] is None:
                shell('test ! -e ' + remote + '\nmkdir -m 700 ' + remote + '\nmkdir -m 700 ' + remote + '/control', 'wifi_owned_directory')
                state['wifi_dir'] = remote
            config = output / ('wifi_' + mode + '_' + state['run'] + '.conf')
            if mode == 'ap':
                body = ('interface=s579peer\ndriver=nl80211\nctrl_interface=' + remote + '/control\n'
                    'ssid=apps579_' + state['run'][:12] + '\nhw_mode=g\nchannel=1\nwpa=2\nwpa_key_mgmt=WPA-PSK\n'
                    'wpa_passphrase=apps579_' + state['run'][:16] + '\nrsn_pairwise=CCMP\n')
                argv = ['/vendor/bin/hostapd', '-d', remote + '/ap.conf']
            else:
                body = ('ctrl_interface=' + remote + '/control\nnetwork={\n ssid="apps579_ap_' + state['run'][:12] + '"\n'
                    ' psk="apps579_' + state['run'][:16] + '"\n key_mgmt=WPA-PSK\n}\n')
                argv = ['/vendor/bin/wpa_supplicant', '-Dnl80211', '-i', 's579peer', '-c', remote + '/sta.conf', '-d']
            config.write_text(body)
            io.send(config, remote + '/' + mode + '.conf', 'apps579_wifi_peer_config')
            state['temporary'].append(remote + '/' + mode + '.conf')
            state['wifi_peer_mode'] = mode
            state['peer_transport'] = io.spawn_guest(shlex.join(argv), 'apps579_wifi_real_' + mode)
            deadline = time.monotonic() + 30
            while True:
                status = shell(shlex.join(['/vendor/bin/wpa_cli', '-p', remote + '/control', '-i', 's579peer', 'raw', 'STATUS']),
                               'wifi_peer_ready', allow_failure=True)
                ready = ('state=ENABLED' if mode == 'ap' else 'wpa_state=') in status['stdout']
                if status['exit_code'] == 0 and ready:
                    break
                require(time.monotonic() < deadline, 'actual private radio control/status not ready; original transport remains held')
                time.sleep(.25)
            return result(at, configuration={'path': str(config), 'sha256': hashlib.sha256(config.read_bytes()).hexdigest()},
                          argv=argv, held_transport=state['peer_transport'], actual_status=status['stdout_ref'])
        if action == 'wifi-peer-collect':
            require(state['case'] == 'wifi' and parameters == {} and state['peer_transport'], 'actual retained radio peer required')
            remote = state['wifi_dir']
            status = shell(shlex.join(['/vendor/bin/wpa_cli', '-p', remote + '/control', '-i', 's579peer', 'raw', 'STATUS']), 'wifi_peer_status')
            station = shell(shlex.join(['/vendor/bin/wpa_cli', '-p', remote + '/control', '-i', 's579peer', 'raw', 'STA-FIRST']),
                            'wifi_peer_station', allow_failure=True) if state['wifi_peer_mode'] == 'ap' else None
            return result(at, mode=state['wifi_peer_mode'], status=status['stdout_ref'],
                          station=station['stdout_ref'] if station else None,
                          mac=shell('cat /sys/class/net/s579peer/address', 'wifi_peer_mac')['stdout_ref'])
        if action == 'wifi-peer-stop':
            require(state['case'] == 'wifi' and parameters == {} and state['peer_transport'], 'actual retained radio peer required')
            remote = state['wifi_dir']
            stopped = shell(shlex.join(['/vendor/bin/wpa_cli', '-p', remote + '/control', '-i', 's579peer', 'raw', 'TERMINATE']),
                            'wifi_peer_protocol_stop')
            require('OK' in stopped['stdout'].splitlines(), 'actual private peer control did not accept TERMINATE')
            completed = io.wait(state['peer_transport'], timeout=30)
            require(completed['boot_id'] == io.boot_id and completed['exit_code'] == 0 and not completed['timed_out'],
                    'actual held radio peer transport did not terminate successfully')
            state['peer_transport'] = None; state['wifi_peer_mode'] = None
            return result(at, transport=io.ref_receipt(completed))
        if action == 'peer-binding':
            require(state['case'] in ('cast', 'dhardware') and parameters == {}, 'original second endpoint only')
            peer = getattr(io, 'apps579_peer_io', None)
            require(peer is not None and peer is not io and peer.archive_sha256 == io.archive_sha256 and
                    peer.boot_id != io.boot_id and peer.udid != io.udid, 'distinct held peer from same representative artifact required')
            peer_boot = peer.shell('cat /proc/sys/kernel/random/boot_id', 'apps579_peer_boot')
            require(peer_boot['stdout'].strip() == peer.boot_id, 'actual peer boot differs')
            return result(at, peer={'boot_id': peer.boot_id, 'udid': peer.udid, 'archive_sha256': peer.archive_sha256,
                'boot_record': peer.ref_receipt(peer_boot),
                'addresses': peer.ref_receipt(peer.shell('ip address', 'apps579_peer_address')),
                'routes': peer.ref_receipt(peer.shell('ip route', 'apps579_peer_route')),
                'services': peer.ref_receipt(peer.shell('ps -ef', 'apps579_peer_services'))})
        raise ValueError('fixed network stage not implemented; cannot replace missing backend with a bool')

    def cleanup():
        if state['closed']:
            return {'boot_id': io.boot_id, 'already_closed': True, 'commands': [], 'qmp_records': []}
        at = begin('cleanup')
        failures = []
        if state['peer_transport']:
            try:
                network('wifi-peer-stop', {})
            except Exception as error:
                return result(at, failures=[{'radio_peer': str(error)}], restored=False)
        if state['owned_media']:
            try:
                require('janitor' in state['installed'], 'actual cleanup consumer must remain installed')
                request_id = 'cleanup_permissions'
                launch('janitor', 'permissions', {'run_id': state['run'], 'request_id': request_id, 'action': 'permissions', 'payload': {}})
                input('media-permission', {})
                collect('janitor', request_id)
                for number, uri in enumerate(sorted(state['owned_media'])):
                    request_id = 'cleanup_media_' + str(number)
                    launch('janitor', 'cleanup-owned', {'run_id': state['run'], 'request_id': request_id, 'action': 'cleanup-owned', 'payload': {'uri': uri}})
                    collect('janitor', request_id)
                    require(uri not in state['owned_media'], 'actual active/TRASH public absence not proven')
            except Exception as error:
                failures.append({'owned_media': str(error), 'uris': sorted(state['owned_media'])})
        if failures:
            return result(at, failures=failures, restored=False)
        cleanup_action = {'location': 'restore', 'volume': 'restore', 'input': 'restore', 'wifi': 'restore',
                          'cast': 'cleanup', 'dhardware': 'stop-discover', 'vpn': 'stop-vpn', 'photos': 'hide-recent',
                          'ethernet': 'restore', 'sysvpn': 'cleanup', 'alwaysvpn': 'cleanup', 'photosform': 'delete-form'}
        for role in sorted(state['installed']):
            try:
                action = cleanup_action.get(state['case'])
                if (role == 'grant' or state['case'] == 'vpn') and action and role not in state['cleaned_roles']:
                    request_id = 'cleanup_' + role
                    launch(role, action, {'run_id': state['run'], 'request_id': request_id, 'action': action, 'payload': {}})
                    collected = collect(role, request_id)
                    values = [json.loads(line) for line in raw(collected['journal']).decode().splitlines()]
                    selected = [r for r in values if r['request_id'] == request_id]
                    require(any(r['event'] == 'done' for r in selected) and not any(r['event'] == 'error' for r in selected),
                            'actual caller restoration failed; retain caller and guest for repair')
                    state['cleaned_roles'].add(role)
                shell(shlex.join(['aa', 'force-stop', bundle(state['case'], role), '-u', '100']), 'cleanup_stop_' + role)
                uninstalled = shell(shlex.join(['bm', 'uninstall', '-n', bundle(state['case'], role), '-u', '100']), 'cleanup_uninstall_' + role)
                require('uninstall bundle successfully.' in uninstalled['stdout'], 'owned caller uninstall failed')
                state['installed'].remove(role)
                if state['case'] == 'imagegen':
                    snapshot('imagegen_removed_' + role)
            except Exception as error:
                failures.append({'role': role, 'error': str(error)})
        if state['radio_renamed'] and not failures:
            try:
                shell('test ! -e /sys/class/net/wlan1\nip link set s579peer down\nip link set s579peer name wlan1\n'
                      'test -e /sys/class/net/wlan1/phy80211', 'restore_second_radio')
                state['radio_renamed'] = False
            except Exception as error:
                failures.append({'radio': str(error)})
        if not failures:
            for remote in list(state['temporary']):
                shell('rm ' + shlex.quote(remote), 'remove_owned_hap')
                state['temporary'].remove(remote)
            if state['wifi_dir']:
                shell('rmdir ' + shlex.quote(state['wifi_dir'] + '/control') + '\nrmdir ' + shlex.quote(state['wifi_dir']), 'remove_wifi_owned_directory')
                state['wifi_dir'] = None
            state['closed'] = True
        return result(at, failures=failures, restored=not failures)

    io.register_cleanup(cleanup)
    return {'prepare_callers': prepare_callers, 'install': install, 'start': start,
            'input': input, 'collect': collect, 'network': network, 'cleanup': cleanup}
