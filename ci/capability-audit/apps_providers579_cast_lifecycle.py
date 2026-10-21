"""Fixed real-picker lifecycle driver on the existing seven held callbacks.

No resource, compiler, caller installer or cleanup owner is constructed here.
Only raw observations of the actual guest can satisfy a boundary. This narrow
report never registers a whole ID or the first-artifact gate.
"""
import json
import re
import shlex

from apps_providers579_bindings import bms_json, objects, raw
from apps_providers579_project import require
from guest_ui import command_exit

PROVIDER = 'com.hmos.mediacontroller'
SCHEMA = 'actual-cast579-picker-lifecycle/v1'
# These are source dependencies, not actual runtime evidence or backend claims.
NATIVE_SOURCE = {
    'frozen': '5f802cfd087d57e2c5f0e9c2149848219481b08a508764033b3711a36987e723',
    'picker': '3d492ce67dbba529d42f2feb33bc66dc1b86f950a66a69ebc9204156e6260e6e',
    'callback': 'b40050e529693212a8b3907a835bcab11a0c164dc11e2f3c9f975be5254d30f0',
    'caller': '1d45794ff3ce705dea4ef10167fd53c4552cd82fd101f9b2b80468833c32c5eb'
}
ERRORS = {'error', 'request-error', 'page-error'}
PTR = r'0x[0-9a-fA-F]+'
PATTERNS = {
    'registered': rf'AVPicker registered helper=({PTR}) ref=({PTR}) cell=({PTR})',
    'queue': rf'AVPicker queue helper=({PTR}) generation=([0-9]+) ref=({PTR}) cell=({PTR})',
    'removed': rf'AVPicker removed helper=({PTR}) ref=({PTR}) cell=({PTR}) status=(-?[0-9]+)',
    'checked': rf'AVPicker checked helper=({PTR}) generation=([0-9]+) ref=({PTR}) cell=({PTR}) present=([01])',
    'reject': rf'AVPicker reject helper=({PTR}) generation=([0-9]+) ref=({PTR}) cell=({PTR}) reason=(registration|generation)',
    'generation': rf'AVPicker generation helper=({PTR}) generation=([0-9]+)',
    'state': rf'AVPicker state helper=({PTR}) generation=([0-9]+) state=([01])',
    'lifetime': rf'AVPicker lifetime helper=({PTR}) phase=(construct|destroy)',
    'submit': rf'AVCallback submit event=([0-9]+) ref=({PTR})',
    'submit-result': rf'AVCallback submit-result event=([0-9]+) ref=({PTR}) status=(-?[0-9]+)',
    'begin': rf'AVCallback begin event=([0-9]+) ref=({PTR})',
    'check': r'AVCallback check event=([0-9]+) phase=(before-resolve|before-invoke)',
    'skip': r'AVCallback skip event=([0-9]+) (?:reason=(object-invalid)|phase=(before-resolve|before-invoke))',
    'invoke-result': rf'AVCallback invoke-result event=([0-9]+) ref=({PTR}) status=(-?[0-9]+)',
    'release': rf'AVCallback release event=([0-9]+) ref=({PTR})'
}
# Standard hilog envelope, retaining actual level/domain/tag instead of guessing
# AVSession's unexported log header. Unsupported envelopes fail explicitly.
ENVELOPE = re.compile(r'^(?:[0-9]{4}-)?[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+\s+'
                      r'(?P<pid>[1-9][0-9]*)\s+(?P<tid>[1-9][0-9]*)\s+[DIWEF]\s+[^\s:]+:\s+.*?(?P<body>AV(?:Picker|Callback) .*)$')


def document(ref):
    return json.loads(raw(ref))


def checked_command(record, observation, script):
    """Replay original HDC footer/status, with the literal fixed guest script."""
    require(observation['script'] == script, 'fixed cast observation script changed')
    index = observation['command']
    require(type(index) is int and 0 <= index < len(record['commands']), 'raw command index absent')
    row = record['commands'][index]
    require(row['boot_id'] == record['boot_id'] and row['exit_code'] == 0 and
            row.get('shell_exit_code', 0) == 0 and row['timed_out'] is False, 'cast guest/HDC operation failed')
    argv = row['argv']
    require(len(argv) == 5 and argv[1] == '-t' and argv[3] == 'shell', 'original HDC shell required')
    markers = re.findall(r'__CAP578_EXIT_[a-f0-9]{32}__=', argv[4])
    require(len(markers) == 1, 'original command nonce missing')
    expected = shlex.join(['sh', '-c', 'set -e\n' + script]) + '; cap578_rc=$?; printf "\\n' + markers[0] + '%s\\n" "$cap578_rc"'
    require(argv[4] == expected, 'cast command argv differs from fixed shell/footer')
    body, code = command_exit(raw(row['stdout']).decode(), markers[0])
    require(code == 0 and raw(observation['raw']).decode() == body and not raw(row['stderr']),
            'actual raw footer/body/stderr mismatch')
    if 'shell_stdout' in row:
        require(raw(row['shell_stdout']).decode() == body, 'retained optional shell-body receipt differs')
    return body


def process_identity(pid, stat_body, status_body):
    if stat_body == 'CAST579_ABSENT\n':
        require(status_body == stat_body, 'partial process disappearance requires a fresh observation')
        return None
    match = re.fullmatch(r'([1-9][0-9]*) \((.*)\) ([A-Za-z]) (.*)\n?', stat_body, re.S)
    require(match is not None and int(match[1]) == pid, 'actual proc stat PID missing')
    fields = (match[3] + ' ' + match[4]).split()
    require(len(fields) >= 20 and fields[19].isdigit(), 'kernel starttime field22 absent')
    uid = re.findall(r'^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$', status_body, re.M)
    require(len(uid) == 1 and len(set(uid[0])) == 1, 'complete real/effective/saved/fs UID required')
    return {'pid': pid, 'birth_ticks': int(fields[19]), 'uid': int(uid[0][0])}


def native_lines(text):
    result = []
    for line in text.splitlines():
        if 'AVPicker ' not in line and 'AVCallback ' not in line:
            continue
        envelope = ENVELOPE.fullmatch(line)
        require(envelope is not None, 'unrecognized native hilog envelope; preserve raw and do not infer PID/TID')
        body = envelope['body']
        matches = [(kind, re.fullmatch(pattern, body)) for kind, pattern in PATTERNS.items()]
        matches = [(kind, match) for kind, match in matches if match is not None]
        require(len(matches) == 1, 'unknown or ambiguous cast native log format')
        kind, match = matches[0]
        result.append({'index': len(result), 'pid': int(envelope['pid']), 'tid': int(envelope['tid']),
                       'kind': kind, 'values': list(match.groups()), 'raw_line': line})
    return result


def read_observation(record, run, boot, archive):
    require(record['schema'] == 'actual-cast579-native-observations/v1' and record['run_id'] == run and
            record['boot_id'] == boot and record['archive_sha256'] == archive, 'same run/archive/boot native observation required')
    identity = document(record['identity'])
    require(identity['bundle'] == record['bundle'] and identity['user_id'] == 100 and type(identity['uid']) is int,
            'real installed BMS/self identity required')
    bms = bms_json(raw(identity['bms_raw']).decode())
    require(any(item.get('bundleName') == identity['bundle'] and item.get('uid') == identity['uid'] and
                item.get('fingerprint') == identity['fingerprint'] for item in objects(bms)), 'actual BMS identity/signature join failed')
    self_rows = [json.loads(line) for line in raw(identity['self_query_raw']).decode().splitlines() if line]
    require(any(row['event'] == 'self-identity' and row['run_id'] == run and row['uid'] == identity['uid'] and
                json.loads(row['value'])['fingerprint'] == identity['fingerprint'] and
                json.loads(row['value'])['bundle'] == identity['bundle'] for row in self_rows), 'actual native self identity is absent')
    journal = [json.loads(line) for line in raw(record['journal']).decode().splitlines() if line]
    require(journal and all(row['run_id'] == run and row['kind'] == 'cast' and row['role'] == 'grant' and
            row['bundle'] == identity['bundle'] and row['uid'] == identity['uid'] for row in journal), 'native/typed identity join failed')
    require(b''.join(raw(item['raw']) for item in record['journal_files']) == raw(record['journal']),
            'retained per-PID journal bodies differ from combined raw journal')
    require(len({item['remote'] for item in record['journal_files']}) == len(record['journal_files']), 'duplicate per-PID journal file')
    for item in record['journal_files']:
        file_rows = [json.loads(line) for line in raw(item['raw']).decode().splitlines() if line]
        require(file_rows and all(item['remote'].endswith('-' + str(row['pid']) + '.jsonl') for row in file_rows),
                'journal PID differs from retained actual remote filename')
        require(re.fullmatch(re.escape('/data/app/el2/100/base/' + identity['bundle'] + '/files/apps579-' + run + '-') +
                r'[1-9][0-9]*\.jsonl', item['remote']), 'unexpected actual cast journal path')
    pids = sorted(set(row['pid'] for row in journal))
    require(all(type(pid) is int and 0 < pid <= 4194304 for pid in pids) and
            pids == [p['pid'] for p in record['processes']] and len(pids) <= 8, 'complete bounded caller PID set required')
    for pid in pids:
        selected = [row for row in journal if row['pid'] == pid]
        require([row['seq'] for row in selected] == list(range(len(selected))), 'caller journal sequence is not complete')
    observations = record['observations']
    require(len({row['name'] for row in observations}) == len(observations), 'duplicate raw observation name')
    by_name = {row['name']: row for row in observations}
    expected_names = {'hilog', 'ams', 'bms', 'ps', 'boot_end'} | {kind + '_' + str(pid) for pid in pids
                      for kind in ('stat_before', 'status', 'stat_after')}
    require(set(by_name) == expected_names, 'complete finite raw observation set required')
    for name, script in [('hilog', 'hilog -x'), ('ams', 'aa dump -a -u 100'),
                         ('bms', shlex.join(['bm', 'dump', '-n', identity['bundle'], '-u', '100'])), ('ps', 'ps -ef'), ('boot_end', 'cat /proc/sys/kernel/random/boot_id')]:
        checked_command(record, by_name[name], script)
    require(checked_command(record, by_name['boot_end'], 'cat /proc/sys/kernel/random/boot_id').strip() == boot,
            'actual boot changed during native observation')
    births = {}
    for item in record['processes']:
        pid = item['pid']
        scripts = {
            'stat_before': 'if test -d /proc/' + str(pid) + '; then cat /proc/' + str(pid) + '/stat; else printf "CAST579_ABSENT\\n"; fi',
            'status': 'if test -d /proc/' + str(pid) + '; then cat /proc/' + str(pid) + '/status; else printf "CAST579_ABSENT\\n"; fi',
            'stat_after': 'if test -d /proc/' + str(pid) + '; then cat /proc/' + str(pid) + '/stat; else printf "CAST579_ABSENT\\n"; fi'}
        bodies = {key: checked_command(record, by_name[name], scripts[key]) for key, name in item['observations'].items()}
        require(set(bodies) == set(scripts), 'complete double-stat process sample required')
        before = process_identity(pid, bodies['stat_before'], bodies['status'])
        after = process_identity(pid, bodies['stat_after'], bodies['status'])
        require(before == after and (before is None or before['uid'] == identity['uid']), 'PID birth/UID changed while observing')
        births[pid] = before
    logs = native_lines(checked_command(record, by_name['hilog'], 'hilog -x'))
    return {'journal': journal, 'native': [row for row in logs if row['pid'] in pids], 'births': births,
            'uid': identity['uid'], 'record': record}


def window(before, after, pid):
    require(before['uid'] == after['uid'] and before['births'][pid] == after['births'][pid] and
            after['births'][pid] is not None, 'native window is not one real live process lifetime')
    old = [r for r in before['native'] if r['pid'] == pid]
    new = [r for r in after['native'] if r['pid'] == pid]
    require([r['raw_line'] for r in new[:len(old)]] == [r['raw_line'] for r in old], 'native hilog rollover/reorder; incomplete window')
    old_journal = [r for r in before['journal'] if r['pid'] == pid]
    new_journal = [r for r in after['journal'] if r['pid'] == pid]
    require(new_journal[:len(old_journal)] == old_journal, 'typed journal prefix changed')
    return new[len(old):], new_journal[len(old_journal):]


def parsed(records):
    """Join queue->submit and callback check windows on actual same PID/TID."""
    tasks, queued, states, checks = {}, {}, {}, {}
    for row in records:
        kind, v = row['kind'], row['values']; lane = (row['pid'], row['tid']); position = row['index']
        if kind == 'state':
            states[(row['pid'], v[0], int(v[1]))] = int(v[2])
        elif kind == 'queue':
            require(lane not in queued, 'native queue scope has no matching submission')
            queued[lane] = {'helper': v[0], 'generation': int(v[1]), 'ref': v[2], 'cell': v[3],
                            'state': states.get((row['pid'], v[0], int(v[1]))), 'queue': position}
        elif kind == 'submit':
            if lane not in queued:
                continue  # Other genuine CallWithFunc users are not cast tasks.
            q = queued.pop(lane); key = (row['pid'], int(v[0]))
            require(q['ref'] == v[1] and q['state'] in (0, 1) and key not in tasks, 'ambiguous cast native submission')
            tasks[key] = dict(q, event=key[1], pid=key[0], submit=position, stages=[], decisions=[])
        elif kind in ('submit-result', 'begin', 'check', 'skip', 'invoke-result', 'release'):
            key = (row['pid'], int(v[0]))
            if key not in tasks:
                continue
            task = tasks[key]
            if kind in ('submit-result', 'begin', 'invoke-result', 'release'):
                require(v[1] == task['ref'], 'callback event changed its actual NAPI reference')
            task['stages'].append(row)
            if kind == 'check':
                checks[lane] = key
            elif kind in ('skip', 'invoke-result', 'release'):
                checks.pop(lane, None)
        elif kind in ('checked', 'reject'):
            require(lane in checks, 'picker decision is not within an actual callback check window')
            task = tasks[checks[lane]]
            require((v[0], int(v[1]), v[2], v[3]) ==
                    (task['helper'], task['generation'], task['ref'], task['cell']), 'native check crosses helper/cell/generation')
            task['decisions'].append(row)
    require(not queued, 'cast queue has no actual send_event submission')
    return list(tasks.values())


def stage(task, kind):
    return [row for row in task['stages'] if row['kind'] == kind]


def complete(task, rejected=None):
    submissions, begins, releases = stage(task, 'submit-result'), stage(task, 'begin'), stage(task, 'release')
    require(len(submissions) == len(begins) == len(releases) == 1 and submissions[0]['values'][2] == '0' and
            task['queue'] < task['submit'] < submissions[0]['index'] and
            task['submit'] < begins[0]['index'] < releases[0]['index'],
            'complete actual queue/submission/execution/context-release chain missing')
    invokes, skips = stage(task, 'invoke-result'), stage(task, 'skip')
    if rejected == 'object-invalid':
        require(len(skips) == 1 and skips[0]['values'][1] == 'object-invalid' and not invokes and
                begins[0]['index'] < skips[0]['index'] < releases[0]['index'], 'invalid object task was invoked or not released')
    elif rejected:
        rejects = [r for r in task['decisions'] if r['kind'] == 'reject' and r['values'][4] == rejected]
        check_rows = stage(task, 'check')
        require(len(rejects) == len(skips) == 1 and not invokes and check_rows and
                check_rows[-1]['values'][1] == skips[0]['values'][2] and
                begins[0]['index'] < check_rows[-1]['index'] < rejects[0]['index'] < skips[0]['index'] < releases[0]['index'],
                'retired task lacks actual rejection/skip/release or was invoked')
    else:
        require(len(invokes) == 1 and invokes[0]['values'][2] == '0' and not skips and
                [r['values'][4] for r in task['decisions'] if r['kind'] == 'checked'] == ['1', '1'] and
                [r['values'][1] for r in stage(task, 'check')] == ['before-resolve', 'before-invoke'] and
                begins[0]['index'] < invokes[0]['index'] < releases[0]['index'], 'native exact-once valid callback chain missing')
    return task


def event_rows(rows, name, request=None):
    return [row for row in rows if row['event'] == name and (request is None or row['request_id'] == request)]


def singleton(rows, name, request=None):
    selected = event_rows(rows, name, request)
    require(len(selected) == 1 and selected[0]['code'] == 0, 'one successful actual ' + name + ' required')
    return selected[0]


def panel(record, visible):
    observation = record['observation']
    raw(observation['frame']); raw(observation['windows'])
    layout = document(observation['layout'])
    stack = [(node, '') for node in (layout if type(layout) is list else [layout])]
    found, count = [], 0
    while stack:
        node, inherited = stack.pop(); count += 1
        attrs = node['attributes']; owner = attrs.get('bundleName') or inherited
        if owner == PROVIDER and attrs.get('visible') == 'true':
            found.append(attrs)
        stack.extend((child, owner) for child in node.get('children', []))
    require(count > 0 and bool(found) == visible, 'actual selected provider panel visibility differs')
    return {'provider': PROVIDER, 'visible_nodes': found, 'raw': record}


def normal_oracle(records, journal, registration_request, *, expected=(0, 1), quiet=False):
    generations = [r for r in records if r['kind'] == 'generation']
    require(len(generations) == 1, 'one actual modal generation required')
    helper, generation = generations[0]['values']; generation = int(generation)
    states = [int(r['values'][2]) for r in records if r['kind'] == 'state' and
              r['values'][:2] == [helper, str(generation)]]
    require(states == [0, 1], 'actual provider must appear then terminate once')
    tasks = parsed(records)
    require(not any(row['event'] in ERRORS or row['event'] in ('cast-picker-A-enter', 'cast-picker-B') for row in journal),
            'ordinary/Off-all interval contains an error or an unexpected A/B callback')
    deliveries = event_rows(journal, 'cast-picker-delivery', registration_request)
    require([json.loads(r['value'])['state'] for r in deliveries] == ([] if quiet else list(expected)),
            'actual callback count/state differs; done or quiet is not an oracle')
    if quiet:
        require(not tasks, 'Off-all/Off-only still queued a removed callback')
    else:
        require(len(tasks) == len(expected) and [t['state'] for t in tasks] == list(expected), 'native/JS delivery count differs')
        for task in tasks:
            complete(task)
    return {'helper': helper, 'generation': generation, 'states': states, 'tasks': tasks, 'deliveries': deliveries}


def queue_oracle(records, journal, request, off_on):
    registration = singleton(journal, 'cast-picker-queue-registration', request)
    number = json.loads(registration['value'])['registration']
    registrations = [r for r in records if r['kind'] == 'registered']
    require(len(registrations) == (3 if off_on else 2), 'actual A/B registration and optional new B cell missing')
    a, b = registrations[:2]
    require(a['values'][0] == b['values'][0] and a['values'][2] != b['values'][2], 'A/B must be actual distinct registration cells')
    tasks = parsed(records)
    old = [t for t in tasks if t['cell'] == b['values'][2] and t['state'] == 0]
    active_a = [t for t in tasks if t['cell'] == a['values'][2] and t['state'] == 0]
    require(len(old) == len(active_a) == 1, 'both real A/B state0 tasks must exist')
    old_b, first_a = complete(old[0], 'registration'), complete(active_a[0])
    removed = [r for r in records if r['kind'] == 'removed' and r['values'][:3] == b['values']]
    require(len(removed) == 1 and removed[0]['values'][3] == '0' and
            stage(old_b, 'submit-result')[0]['index'] < removed[0]['index'] < stage(first_a, 'invoke-result')[0]['index'] and
            removed[0]['tid'] == stage(first_a, 'invoke-result')[0]['tid'],
            'B was not actually submitted before synchronous A-Off(B) inside A invocation')
    a_rows = event_rows(journal, 'cast-picker-A-enter', request)
    require([json.loads(r['value']) for r in a_rows] == [{'registration': number, 'state': 0}, {'registration': number, 'state': 1}],
            'actual A state callback sequence missing/duplicated')
    off = singleton(journal, 'cast-picker-A-off-returned', request)
    require(a_rows[0]['seq'] < off['seq'] < a_rows[1]['seq'], 'typed A synchronous Off ordering absent')
    b_rows = event_rows(journal, 'cast-picker-B', request)
    require([json.loads(r['value']) for r in b_rows] == ([{'registration': number, 'state': 1}] if off_on else []),
            'old B state0 delivered or current B state1 missing/duplicated')
    aba = {'covered': False, 'reason': 'off-only has no re-registration'}
    if off_on:
        on = singleton(journal, 'cast-picker-A-on-returned', request)
        newer = registrations[2]
        require(off['seq'] < on['seq'] < a_rows[1]['seq'] and newer['values'][0] == b['values'][0] and
                newer['values'][2] != b['values'][2] and removed[0]['index'] < newer['index'],
                'synchronous On(B) has no genuinely new native cell')
        new_b = [t for t in tasks if t['cell'] == newer['values'][2]]
        require(len(new_b) == 1 and new_b[0]['state'] == 1, 'new B received retired state0 or lacks real terminal state1')
        complete(new_b[0])
        aba = {'covered': newer['values'][1] == b['values'][1], 'old_ref': b['values'][1], 'new_ref': newer['values'][1],
               'old_cell': b['values'][2], 'new_cell': newer['values'][2],
               'reason': 'actual raw reference equal across different cells' if newer['values'][1] == b['values'][1]
                         else 'actual allocator did not reuse reference; handle-ABA remains uncovered'}
    require(len(tasks) == (4 if off_on else 3), 'unexpected native task count in A/B queue boundary')
    for task in tasks:
        if task is not old_b:
            complete(task)
    return {'registrations': registrations, 'retired_B': old_b, 'tasks': tasks, 'handle_ABA': aba}


def run(*, callbacks, start, finish, touch, keep, run_id, boot_id, archive_sha256):
    """Run only within the original cast branch after its real session-create.

    Callables are lexical adapters of runtime.run, never JSON-selected code.
    Semantic failures are retained so independent cases and original discovery
    still execute; resource/transport errors are retained by the original IO.
    """
    require(type(callbacks) is dict and set(callbacks) == {'prepare_callers', 'install', 'start', 'input', 'collect', 'network', 'cleanup'} and
            all(callable(value) for value in callbacks.values()) and all(callable(value) for value in (start, finish, touch, keep)),
            'only the existing seven callbacks and lexical runtime adapters may be used')
    require(re.fullmatch('[a-f0-9]{32}', run_id) and re.fullmatch('[a-f0-9]{64}', archive_sha256) and
            re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', boot_id), 'actual run/archive/boot required')
    report = {'schema': SCHEMA, 'run_id': run_id, 'boot_id': boot_id, 'archive_sha256': archive_sha256,
              'source_dependencies': dict(NATIVE_SOURCE), 'cases': [], 'failures': [], 'uncovered': [],
              'closed_requirement_ids': [], 'first_artifact_behavior_gate_passed': False, 'runtime_pass': False}

    def observe(label):
        receipt = keep('cast_native_' + label, callbacks['network']('cast-native-observations', {}))
        result = read_observation(receipt, run_id, boot_id, archive_sha256)
        for row in result['journal']:
            if row['event'] in ERRORS:
                failure = 'actual asynchronous/typed error PID=' + str(row['pid']) + ' seq=' + str(row['seq']) + ': ' + json.dumps(row, sort_keys=True)
                if failure not in report['failures']:
                    report['failures'].append(failure)
        return result

    def call(action):
        request = start('grant', action)
        values, receipt = finish('grant', request)
        singleton(values, 'request', request)
        require(all(r['action'] == action for r in values), 'typed action changed')
        return request, values, receipt

    def picture(label, visible):
        receipt = touch('snapshot', {'label': 'cast_' + label})
        require(receipt['boot_id'] == boot_id and receipt['archive_sha256'] == archive_sha256, 'UI crossed actual boot/archive')
        return panel(receipt, visible)

    def opened(action, label):
        req, values, receipt = call(action)
        ui = picture(label + '_open', True)
        live = observe(label + '_open')
        selected = singleton(values, 'request', req)
        pid = selected['pid']
        require(live['births'][pid] is not None, 'live caller kernel identity missing')
        return req, pid, ui, live

    def closed(req, label):
        touch('back')
        finish('grant', req)
        ui = picture(label + '_closed', False)
        final = observe(label + '_closed')
        return ui, final

    def seed(label, action='picker'):
        req, _, ui, live = opened(action, label + '_setup')
        after_ui, final = closed(req, label + '_setup')
        return {'request': req, 'ui': [ui, after_ui], 'observations': [live['record'], final['record']]}

    def execute(name, body):
        case = {'name': name, 'observations': [], 'failures': []}
        report['cases'].append(case)
        try:
            body(case)
        except Exception as error:
            failure = type(error).__name__ + ': ' + str(error)
            case['failures'].append(failure); report['failures'].append(name + ': ' + failure)
            # Best-effort public recovery only; no own install/cleanup or VM.
            # Failure to recover is retained and never reclassified as success.
            for action in ('back', 'release'):
                try:
                    if action == 'back':
                        touch('back')
                    else:
                        call('picker-release')
                except Exception as recovery:
                    case['failures'].append('recovery ' + action + ': ' + type(recovery).__name__ + ': ' + str(recovery))

    def initial(case):
        base = observe('normal_before')
        req, pid, ui, opened_raw = opened('picker', 'normal')
        ui_after, final = closed(req, 'normal')
        records, journal = window(base, final, pid)
        reg = singleton(journal, 'cast-picker-registered', req)
        result = normal_oracle(records, journal, req)
        case.update(request=req, pid=pid, identity=final['births'][pid], registered=reg, oracle=result,
                    observations=[base['record'], opened_raw['record'], final['record']], ui=[ui, ui_after])

    execute('ordinary_registered_panel_Back_exact_once', initial)

    def off_and_on(case):
        case['setup'] = seed('off')
        base = observe('off_before'); off_id, _, _ = call('picker-off')
        req, pid, ui, opened_raw = opened('picker-reselect', 'off')
        ui_after, after_off = closed(req, 'off')
        records, journal = window(base, after_off, pid)
        singleton(journal, 'cast-picker-unregistered', off_id)
        removals = [r for r in records if r['kind'] == 'removed']
        require(len(removals) == 1 and removals[0]['values'][3] == '0', 'one actual targeted native Off missing')
        quiet = normal_oracle(records, journal, None, quiet=True)
        call('picker-on')
        base_on = observe('on_before')
        req_on, _, ui_on, live_on = opened('picker-reselect', 'on')
        ui_end, after_on = closed(req_on, 'on')
        records_on, journal_on = window(base_on, after_on, pid)
        recovered = normal_oracle(records_on, journal_on, None)
        case.update(oracle={'off': quiet, 'on': recovered}, observations=[base['record'], opened_raw['record'],
                    after_off['record'], base_on['record'], live_on['record'], after_on['record']], ui=[ui, ui_after, ui_on, ui_end])

    execute('targeted_Off_reselect_quiet_public_On_recovery', off_and_on)

    def replace(case):
        case['setup'] = seed('offon')
        base = observe('offon_before'); call('picker-off-on')
        req, pid, ui, live = opened('picker-reselect', 'offon')
        ui_after, final = closed(req, 'offon')
        records, journal = window(base, final, pid)
        removed = [r for r in records if r['kind'] == 'removed']
        registered = [r for r in records if r['kind'] == 'registered']
        require(len(removed) == len(registered) == 1 and removed[0]['values'][3] == '0' and
                removed[0]['values'][0] == registered[0]['values'][0] and removed[0]['index'] < registered[0]['index'],
                'ordinary OffOn lacks actual successful removal then registration')
        # An idle old cell can already have been freed and its address reused.
        # Distinct live cells are required only in the queued-task ABA case.
        case.update(oracle=normal_oracle(records, journal, None), observations=[base['record'], live['record'], final['record']], ui=[ui, ui_after])

    execute('ordinary_OffOn_reentry', replace)

    for action in ('picker-queue-off', 'picker-queue-off-on'):
        def queued(case, action=action):
            case['setup'] = seed(action.replace('-', '_'))
            call('picker-release')
            base = observe(action.replace('-', '_') + '_before')
            req, pid, ui, live = opened(action, action.replace('-', '_'))
            ui_after, final = closed(req, action.replace('-', '_'))
            records, journal = window(base, final, pid)
            oracle = queue_oracle(records, journal, req, action == 'picker-queue-off-on')
            case.update(oracle=oracle, observations=[base['record'], live['record'], final['record']], ui=[ui, ui_after])
            if action == 'picker-queue-off-on' and not oracle['handle_ABA']['covered']:
                report['uncovered'].append({'case': action, 'boundary': 'same_handle_ABA', 'reason': oracle['handle_ABA']['reason']})
        execute(action, queued)

    def off_all(case):
        case['setup'] = seed('offall', 'picker-queue-off-on')
        base = observe('offall_before'); call('picker-off-all')
        req, pid, ui, live = opened('picker-reselect', 'offall')
        ui_after, final = closed(req, 'offall')
        records, journal = window(base, final, pid)
        removed = [r for r in records if r['kind'] == 'removed']
        require(len(removed) == 2 and len({r['values'][2] for r in removed}) == 2 and
                len({r['values'][0] for r in removed}) == 1 and all(r['values'][3] == '0' for r in removed),
                'Off-all must actually remove both distinct active A/B cells on one helper')
        singleton(journal, 'cast-picker-unregistered')
        case.update(oracle=normal_oracle(records, journal, None, quiet=True), observations=[base['record'], live['record'], final['record']], ui=[ui, ui_after])
        release_before = observe('release_before')
        call('picker-release')
        release_base = observe('released')
        new_req, _, new_ui, new_live = opened('picker', 'released_new')
        closed_ui, after_new = closed(new_req, 'released_new')
        new_records, new_journal = window(release_base, after_new, pid)
        require(len([r for r in new_records if r['kind'] == 'lifetime' and r['values'][1] == 'construct']) == 1,
                'reference release/reentry lacks a real new native helper lifetime')
        case['reentry'] = normal_oracle(new_records, new_journal, new_req)
        case['observations'] += [release_base['record'], new_live['record'], after_new['record']]
        case['ui'] += [new_ui, closed_ui]
        release_records, _ = window(release_before, after_new, pid)
        invalid_tasks = [t for t in parsed(release_records) if any(r['values'][1] == 'object-invalid' for r in stage(t, 'skip'))]
        witnesses = []
        for task in invalid_tasks:
            destroy = [r for r in release_records if r['kind'] == 'lifetime' and r['values'] == [task['helper'], 'destroy'] and
                       task['queue'] < r['index'] < stage(task, 'skip')[0]['index']]
            if destroy:
                witnesses.append({'destroy': destroy, 'task': complete(task, 'object-invalid')})
        case['native_destructor_invalid_tasks'] = witnesses
        case['observations'].append(release_before['record'])
        if not witnesses:
            report['uncovered'].append({'case': 'release', 'boundary': 'native_object_invalid_queued_after_destructor',
                'reason': 'public references released and new helper observed; no actual destructor plus surviving invalid queued task'})

    execute('Off_all_quiet_release_new_helper', off_all)

    def generation(case):
        case['setup'] = seed('generation')
        base = observe('generation_before')
        # No collect/quiet/snapshot is interposed between these real starts.
        # Public APIs still do not guarantee the old task survives replacement.
        req = start('grant', 'picker-reselect')
        req2 = start('grant', 'picker-reselect')
        finish('grant', req)
        finish('grant', req2)
        ui = picture('generation_new_open', True)
        live = observe('generation_new_open')
        pid = singleton(live['journal'], 'request', req)['pid']
        require(singleton(live['journal'], 'request', req2)['pid'] == pid, 'generation starts crossed process lifetime')
        singleton(live['journal'], 'picker-select-returned', req)
        singleton(live['journal'], 'picker-select-returned', req2)
        ui_after, final = closed(req2, 'generation_new')
        records, journal = window(base, final, pid)
        gens = [r for r in records if r['kind'] == 'generation']
        require(len(gens) == 2 and gens[0]['values'][0] == gens[1]['values'][0] and
                int(gens[0]['values'][1]) < int(gens[1]['values'][1]), 'actual modal generation replacement missing')
        helper, newest = gens[1]['values']
        after_new = [r for r in records if r['index'] > gens[1]['index']]
        require(not any(r['kind'] == 'state' and r['values'][:2] == gens[0]['values'] for r in after_new),
                'old generation emitted a state after real replacement')
        require([r['values'][2] for r in after_new if r['kind'] == 'state' and r['values'][:2] == [helper, newest]] == ['0', '1'],
                'new actual generation did not appear/terminate exactly once')
        tasks = parsed(records)
        current = [t for t in tasks if t['generation'] == int(newest)]
        require(len(current) == 2 and [t['state'] for t in current] == [0, 1], 'new generation exact-once callbacks missing')
        for task in current:
            complete(task)
        retired, invoked = [], []
        for task in tasks:
            if task['generation'] == int(newest):
                invoked.append(task)
            elif any(d['kind'] == 'reject' and d['values'][4] == 'generation' for d in task['decisions']):
                retired.append(complete(task, 'generation'))
            else:
                complete(task)
                checks = [decision for decision in task['decisions'] if decision['kind'] == 'checked']
                require(checks and checks[-1]['index'] < gens[1]['index'],
                        'old generation was accepted at its validity check after replacement')
                # The callback may finish after replacement if its final native
                # validity check preceded replacement. That is a legal order.
                invoked.append(task)
        if not retired:
            report['uncovered'].append({'case': 'generation', 'boundary': 'old_queued_generation_rejected',
                'reason': 'real replacement observed, but no old queued task survived to its generation check'})
        deliveries = event_rows(journal, 'cast-picker-delivery')
        expected = [task['state'] for task in sorted(invoked, key=lambda task: stage(task, 'invoke-result')[0]['index'])]
        require([json.loads(r['value'])['state'] for r in deliveries] == expected,
                'typed old/new delivery counts differ from real successful native calls')
        case.update(tasks=tasks, old_rejected_tasks=retired, observations=[base['record'], live['record'], final['record']],
                    ui=[ui, ui_after], requests=[req, req2])

    execute('generation_replacement', generation)

    def death(case):
        case['setup'] = seed('death')
        base = observe('death_before')
        req, old_pid, ui, live = opened('picker-reselect', 'death')
        pending_records, pending_journal = window(base, live, old_pid)
        pending_generations = [r for r in pending_records if r['kind'] == 'generation']
        pending_states = [r for r in pending_records if r['kind'] == 'state']
        pending_tasks = parsed(pending_records)
        require(len(pending_generations) == len(pending_states) == len(pending_tasks) == 1 and
                pending_states[0]['values'][2] == '0' and pending_tasks[0]['state'] == 0 and
                [json.loads(r['value'])['state'] for r in event_rows(pending_journal, 'cast-picker-delivery')] == [0],
                'process death challenge lacks a real currently appeared native modal and callback')
        complete(pending_tasks[0])
        case['pending_before_death'] = {'generation': pending_generations, 'states': pending_states, 'tasks': pending_tasks}
        touch('force-stop', {'role': 'grant'})
        dead_ui = picture('death_stopped', False)
        dead = observe('death_stopped')
        require(live['births'][old_pid] is not None and dead['births'][old_pid] is None, 'actual owned process did not disappear')
        old_rows = [r for r in live['journal'] if r['pid'] == old_pid]
        call('identity'); call('session-create')
        recovery_base = observe('death_recovery_before')
        new_req, new_pid, new_ui, new_live = opened('picker', 'death_recovery')
        end_ui, final = closed(new_req, 'death_recovery')
        require(new_pid != old_pid and recovery_base['births'][new_pid] is not None and
                final['births'][old_pid] is None and final['births'][new_pid] == new_live['births'][new_pid] and
                [r for r in final['journal'] if r['pid'] == old_pid][:len(old_rows)] == old_rows,
                'actual new PID/kernel birth/recovery journal or retired prefix missing')
        records, journal = window(recovery_base, final, new_pid)
        require(not any(r['event'] in ('cast-picker-state', 'cast-picker-delivery', 'cast-picker-A-enter', 'cast-picker-B')
                for r in final['journal'] if r['pid'] == new_pid and r['request_id'] == req), 'new process delivered old request callback')
        case.update(oracle=normal_oracle(records, journal, new_req), old_process=live['births'][old_pid], new_process=final['births'][new_pid],
                    observations=[base['record'], live['record'], dead['record'], recovery_base['record'], new_live['record'], final['record']],
                    ui=[ui, dead_ui, new_ui, end_ui])
        case['not_claimed'] = 'force-stop does not prove C++ destructor execution or object-invalid queued task rejection'

    execute('actual_process_death_new_PID_reentry', death)
    try:
        report['final_observation'] = observe('lifecycle_final')['record']
    except Exception as error:
        report['failures'].append('final raw observation: ' + type(error).__name__ + ': ' + str(error))
    # A natural race/reuse that was not observed remains explicit, never a pass.
    report['supported_observations_complete'] = not report['failures'] and not report['uncovered']
    keep('cast_lifecycle_report', report)
    return report
