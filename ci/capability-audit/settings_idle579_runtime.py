"""Actual new-package QEMU conditional-idle stage, on the original held IO.

Source candidate only. This file has never been executed by its author. The
parent integrates this finite family and stage into its one representative run.
"""
import json
import re
import time

from capability578_owned_io import require, reference
from hap_identity_binding import strict_json
from settings_idle579_bindings import bind, load_ref
from guest_process_identity import starttime_shell, uids_shell

MALFORMED = {'missing-token', 'missing-id', 'extra', 'zero', 'negative',
             'wrong-descriptor', 'truncated-1', 'truncated-2', 'truncated-3'}
PARAMETERS = {'missing', 'extra', 'string', 'null', 'undefined', 'zero', 'negative',
              'fractional', 'nan', 'infinity', 'overflow'}


def value(row):
    require(row['code'] == 0, 'actual operation returned an error')
    return strict_json(row['value'])


def events(binding, role, operation, event):
    return [r for r in binding.collect(role) if r['operation'] == operation and r['event'] == event]


def one(binding, role, operation, event):
    selected = events(binding, role, operation, event)
    require(len(selected) == 1, 'one actual raw event required: ' + event)
    return selected[0]


def same_live(binding, before, after):
    require(before['pid'] == after['pid'] and before['uid'] == after['uid'] and
        value(before)['generation'] == value(after)['generation'],
        'newer work was not retained by the same real service generation')


def service_records(raw, bundle, service):
    require(re.search(r'^User ID #100\s*$', raw, re.M) and 'AppRunningRecords:' in raw and
            '  ExtensionRecords:' in raw, 'complete live account-100 AMS active/cache dump required')
    records = []
    # These fields come from BaseExtensionRecord::DumpService. The unfiltered
    # dump includes active + cache maps, and does NOT enumerate terminating map.
    chunks = re.split(r'(?=      AbilityRecord ID #)', raw)
    for chunk in chunks[1:]:
        header = re.match(r'      AbilityRecord ID #([1-9][0-9]*)\s+state #([^\s]+)\s+start time \[[^\n]*\]', chunk)
        require(header is not None, 'actual AMS service record header changed')
        names = re.findall(r'^      main name \[([^\n]*)\]\s*$', chunk, re.M)
        bundles = re.findall(r'^      bundle name \[([^\n]*)\]\s*$', chunk, re.M)
        if names and bundles and names[0] == service and bundles[0] == bundle:
            require('      ability type [SERVICE]' in chunk, 'actual fixture is not SERVICE')
            records.append({'record_id': int(header[1]), 'state': header[2]})
    return records


def live_record(binding):
    records = service_records(binding.snapshot(), binding.roles['system']['identity']['bundle'], 'IdleService')
    require(len(records) == 1, 'one actual live fixture service record required')
    return records[0]


def native_identity(binding, role, actual):
    identity = binding.roles[role]['identity']
    require(type(actual) is dict and type(actual['pid']) is int and actual['pid'] > 1 and
        actual['uid'] == identity['uid'] and re.fullmatch('[a-f0-9]{16}', actual['selfTokenHex']) and
        int(actual['selfTokenHex'], 16) & 0xffffffff == identity['token_id'] and
        actual['library'].endswith('/libsettings_idle579.so'),
        'native actual PID/UID/self AccessTokenId or mapped library differs from BMS')
    if 'bundle' in actual:
        require(actual['bundle'] == identity['bundle'], 'native actual Context bundle differs')
    library = actual['library']
    require(library.startswith('/') and '..' not in library.split('/') and '\n' not in library,
            'actual dladdr absolute library path required')
    import shlex
    target = '/proc/' + str(actual['pid']) + '/root' + library
    observed = binding.shell('sha256sum ' + shlex.quote(target), 'native_loaded_hash_' + role)
    require(observed.strip() == binding.native['binary']['sha256'] + '  ' + target,
            'actual loaded native ELF differs from the original platform artifact')
    require(any(k[0] == role and writer['path'].split('/')[-1].startswith(
        'settings-idle579-' + binding.run + '-' + str(actual['pid']) + '-')
        for k, writer in binding.writers.items()), 'native PID is not an independently bound journal writer')


def native_attempt(binding, role, actual):
    native_identity(binding, role, actual)
    require(type(actual['transport']) is int and actual['code'] == 6179 and
        actual['descriptor'] == ('settings_idle579.invalid' if actual['mode'] == 'wrong-descriptor'
                                 else 'ohos.aafwk.AbilityManager') and
        type(actual['requestBytes']) is int and actual['requestBytes'] > 0 and
        type(actual['requestObjects']) is int and actual['requestObjects'] >= 0 and
        re.fullmatch('[a-f0-9]+', actual['clientParcelHex']) and
        len(actual['clientParcelHex']) == actual['requestBytes'] * 2 and
        re.fullmatch('[a-f0-9]*', actual['replyHex']) and len(actual['replyHex']) == actual['replyBytes'] * 2,
        'actual native SendRequest/parcel byte evidence differs')
    return actual


def rejected_reply(binding, actual, error):
    native_attempt(binding, 'system', actual)
    require(actual['mode'] == 'normal' and actual['transport'] == 0 and
        actual['readResult'] is True and actual['readStopped'] is True and actual['remaining'] == 0 and
        actual['result'] == error and actual['stopped'] is False,
        'AMS must reject the genuine live token with its actual native result')


def terminate(binding, operation, record, request):
    call = value(binding.wait('system', operation, 'stop.call'))
    require(call['expectedStartId'] == value(request)['startId'], 'current snapshot did not use real onRequest ID')
    destroyed = binding.wait('system', operation, 'destroy')
    require(destroyed['pid'] == request['pid'] and value(destroyed)['generation'] == value(request)['generation'],
            'actual onDestroy belongs to a different service generation')
    returned = binding.wait('system', operation, 'stop.return')
    require(value(returned)['stopped'] is True and not events(binding, 'system', operation, 'stop.error'),
        'current public Promise must actually resolve true')
    # The fixture caches its actual filesDir while Context is alive, allowing
    # real Promise settlement to be logged after onDestroy without a getter on
    # the destroyed Context. Native decision/destroy remain independent checks.
    process = binding.shell('pidof foundation', 'ams_server_pid').strip()
    require(re.fullmatch('[1-9][0-9]*', process), 'one actual foundation AMS server PID required')
    server_start = binding.shell(starttime_shell(process), 'ams_server_start').strip()
    server_uids = binding.shell(uids_shell(process), 'ams_server_uids').split()
    require(len(server_uids) == 4 and len(set(server_uids)) == 1, 'actual AMS server four-UID identity differs')
    logs = binding.logs()
    log_command = len(binding.commands)-1
    pattern = r'conditional stop accepted, startId=' + str(value(request)['startId']) + \
              ' record=' + str(record['record_id']) + r'\b'
    lines = [line for line in logs.splitlines() if re.search(pattern, line)]
    require(len(lines) == 1, 'actual AMS decision missing/ambiguous for the exact live record/startId')
    logged = re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([1-9][0-9]*)\s+[1-9][0-9]*\s+[DIWEF]\b', lines[0])
    require(logged is not None and logged[1] == process and
        binding.shell(starttime_shell(process), 'ams_server_start_after').strip() == server_start,
        'native decision is not bound to the actual live AMS server process generation')
    absent = []
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        raw = binding.snapshot()
        records = service_records(raw, binding.roles['system']['identity']['bundle'], 'IdleService')
        if not records:
            absent.append(len(binding.commands)-1)
            if len(absent) == 2:
                break
        else:
            absent = []
        time.sleep(.2)
    require(len(absent) == 2, 'destroyed fixture remains in actual active/cache service records')
    return {'record': record, 'request': request, 'destroy': destroyed, 'returned': returned, 'native_decision': lines[0],
            'native_log_command': log_command,
            'native_server': {'pid': int(process), 'start_ticks': int(server_start), 'uids': list(map(int, server_uids))},
            'active_cache_absent_commands': absent,
            'completion_scope': 'real onDestroy and active/cache absence; terminating map is not dumped'}


def settings_actions(io):
    """Replay the Apps owner's real UI/WantAgent/config/flag/lifecycle slice.

    The root supplies immutable snapshots of the actual Apps report AND its
    enclosing original Owner log; arbitrary callbacks or expected booleans are
    not inputs. The parent still owns the wider original-ID/package closure.
    """
    from apps_ui578_verify import commands, role_rows, ui, settings
    descriptor = io.package_inputs['settings_actions579']
    require(type(descriptor) is dict and set(descriptor) == {'report', 'owner'},
            'actual Apps Settings report and original Owner raw-log refs required')
    report = strict_json(load_ref(descriptor['report']).decode())
    owner = strict_json(load_ref(descriptor['owner']).decode())
    require(report['schema'] == 'actual-apps578-runtime/v1' and report['case'] == 'accessibility-settings' and
        report['archive_sha256'] == owner['archive_sha256'] == io.archive_sha256 and
        report['boot_id'] == owner['test_environment']['boot_id'] == io.boot_id and
        report['target'] == io.target and report['failures'] == [] and report['cleanup_verified'] is True and
        report['status'] == 'observed', 'Apps slice is not actual same-package/boot complete raw evidence')
    actual = commands(report, owner, io.hdc, io.target)
    rows = role_rows(report, actual)
    ui(report, actual, rows)
    settings(report, rows, actual)
    return {'report': descriptor['report'], 'owner': descriptor['owner'],
            'cycles': report['settings']['cycles'], 'scope': 'four actual UI notification action/service lifecycles'}


def public_boundary(binding, action):
    baseline = binding.request('system', 'remember')
    first = binding.wait('system', baseline, 'request')
    binding.wait('system', baseline, 'work.end')
    initial = value(first)
    require(initial['startId'] >= initial['initialStartId'] > 0, 'actual positive onRequest IDs required')
    record = live_record(binding)
    op = binding.request('system', action)
    request = binding.wait('system', op, 'request')
    binding.wait('system', op, 'work.end')
    expected = initial['initialStartId'] if action == 'stale' else 2147483647
    call = value(one(binding, 'system', op, 'stop.call'))
    returned = value(one(binding, 'system', op, 'stop.return'))
    same_live(binding, first, request)
    require(value(request)['startId'] > initial['startId'] and call['expectedStartId'] == expected and
        call['latestStartId'] == value(request)['startId'] and returned['stopped'] is False and
        not events(binding, 'system', op, 'stop.error') and
        not events(binding, 'system', op, 'destroy'), 'actual stale/future request was not safely rejected')
    beat = binding.request('system', 'heartbeat')
    work = binding.wait('system', beat, 'work.end'); same_live(binding, first, work)
    require(live_record(binding)['record_id'] == record['record_id'], 'stale/future replaced the live AMS record')
    return {'baseline': first, 'record': record, 'request': request, 'call': call,
            'returned': returned, 'newer_work': work}


def parameters_boundary(binding):
    before = binding.request('system', 'remember')
    first = binding.wait('system', before, 'request'); binding.wait('system', before, 'work.end')
    record = live_record(binding)
    op = binding.request('system', 'parameters')
    binding.wait('system', op, 'work.end')
    calls = events(binding, 'system', op, 'parameter.call')
    require(len(calls) == len(PARAMETERS) and {strict_json(r['value'])['label'] for r in calls} == PARAMETERS,
            'all eleven actual public parameter invocations required')
    errors = events(binding, 'system', op, 'parameter.error')
    require(len(errors) == len(PARAMETERS) and {strict_json(r['value'])['label'] for r in errors} == PARAMETERS and
        all(r['code'] == 401 for r in errors) and not events(binding, 'system', op, 'parameter.return'),
        'all actual public NAPI argument boundaries must reject with 401')
    beat = binding.request('system', 'heartbeat')
    work = binding.wait('system', beat, 'work.end'); same_live(binding, first, work)
    require(live_record(binding)['record_id'] == record['record_id'], 'parameter rejection destroyed/replaced service')
    return {'errors': errors, 'newer_work': work, 'record': record}


def native_boundary(binding, action):
    peer_data, peer_record, peer_work = None, None, None
    if action == 'native-foreign':
        peer_op = binding.request('foreign', 'remember')
        peer = binding.wait('foreign', peer_op, 'peer.work')
        peer_data = value(peer)
        native_identity(binding, 'foreign', strict_json(peer_data['identity']))
        require(peer_data['startId'] > 0, 'foreign token must refer to a real started SERVICE record')
        records = service_records(binding.snapshot(), binding.roles['foreign']['identity']['bundle'], 'PeerService')
        require(len(records) == 1, 'one actual live foreign SERVICE record required')
        peer_record = records[0]
    op = binding.request('system', action)
    binding.wait('system', op, 'native.done')
    event = {'native-ui': 'native.ui', 'native-malformed': 'native.malformed', 'native-foreign': 'native.foreign'}[action]
    observations = events(binding, 'system', op, event)
    require(all(value(row)['pid'] == row['pid'] and value(row)['uid'] == row['uid'] for row in observations),
            'native process identity differs from its actual raw journal writer')
    if action == 'native-ui':
        require(len(observations) == 1, 'one actual UI Context token challenge required')
        rejected_reply(binding, value(observations[0]), 2097202)  # ERR_WRONG_INTERFACE_CALL, fixed actual header.
    elif action == 'native-malformed':
        for control in ('native.malformed.control-before', 'native.malformed.control-after'):
            rejected_reply(binding, value(one(binding, 'system', op, control)), 2097202)
        require(len(observations) == len(MALFORMED), 'all fixed real parcel mutations required')
        actual = [native_attempt(binding, 'system', value(row)) for row in observations]
        require({r['mode'] for r in actual} == MALFORMED and all(r['transport'] != 0 and
            not r['readResult'] and not r['readStopped'] and r['replyBytes'] == 0 for r in actual),
            'malformed IPC must fail in actual stub transport with no manufactured reply')
    else:
        require(len(observations) == 1, 'one genuine foreign SERVICE token challenge required')
        rejected_reply(binding, value(observations[0]), 2097177)  # CHECK_PERMISSION_FAILED, fixed actual header.
        reply = value(one(binding, 'system', op, 'peer.reply'))
        foreign_identity = strict_json(reply['identity']); native_identity(binding, 'foreign', foreign_identity)
        require(reply['startId'] == peer_data['startId'] and
            foreign_identity['uid'] != value(observations[0])['uid'], 'actual peer token provenance differs')
        peer_request = binding.wait('foreign', op, 'peer.token.request')
        p = value(peer_request)
        require(p['callingUid'] == binding.roles['system']['identity']['uid'] and
            p['callingPid'] == observations[0]['pid'] and p['startId'] == reply['startId'],
            'actual cross-HAP RPC caller/token/startId differs')
        beat = binding.request('foreign', 'heartbeat')
        peer_work = binding.wait('foreign', beat, 'peer.work')
        after = service_records(binding.snapshot(), binding.roles['foreign']['identity']['bundle'], 'PeerService')
        require(peer_work['pid'] == peer['pid'] and value(peer_work)['startId'] > peer_data['startId'] and
            len(after) == 1 and after[0]['record_id'] == peer_record['record_id'],
            'denied foreign call destroyed/recreated the actual peer service')
    return {'observations': observations, 'peer': peer_data, 'peer_record': peer_record, 'newer_peer_work': peer_work}


def lifecycle_boundary(binding, output):
    # A new genuine request establishes this independent lifecycle case even if
    # a previous boundary failed. It never converts that earlier failure to pass.
    baseline = binding.request('system', 'remember')
    binding.wait('system', baseline, 'work.end')
    record = live_record(binding)
    retained_op = binding.request('system', 'retain-context')
    retained = binding.wait('system', retained_op, 'old-context.saved')
    binding.wait('system', retained_op, 'work.end')
    op = binding.request('system', 'current')
    request = binding.wait('system', op, 'request')
    output['current'] = terminate(binding, op, record, request)
    recreated_op = binding.request('system', 'remember')
    recreated = binding.wait('system', recreated_op, 'request')
    binding.wait('system', recreated_op, 'work.end')
    replacement = live_record(binding)
    require(replacement['record_id'] != record['record_id'] and recreated['pid'] == retained['pid'] and
        value(recreated)['generation'] > value(retained)['generation'],
        'real separate AMS record and same-process retained old Context required')
    old_op = binding.request('system', 'old-context-attempt')
    binding.wait('system', old_op, 'work.end')
    old_call = value(one(binding, 'system', old_op, 'old-context.call'))
    old_return = events(binding, 'system', old_op, 'old-context.return')
    old_error = events(binding, 'system', old_op, 'old-context.error')
    require(old_call['oldGeneration'] == value(retained)['generation'] and
        old_call['currentGeneration'] == value(recreated)['generation'] and
        len(old_return) + len(old_error) == 1 and
        (not old_return or value(old_return[0])['stopped'] is False) and
        (not old_error or (old_error[0]['code'] > 0 and old_error[0]['code'] != 401)),
        'actual old Context completion was not refused for the replacement')
    beat = binding.request('system', 'heartbeat')
    work = binding.wait('system', beat, 'work.end'); same_live(binding, recreated, work)
    require(live_record(binding)['record_id'] == replacement['record_id'], 'old completion killed replacement record')
    output['old_context'] = {'retained': retained, 'replacement': recreated,
        'call': old_call, 'return': old_return, 'error': old_error, 'newer_work': work}
    op = binding.request('system', 'current')
    request = binding.wait('system', op, 'request')
    output['replacement_current'] = terminate(binding, op, replacement, request)
    return output


def run(root_io):
    binding = bind(root_io)
    report = {'schema': 'actual-settings-idle579-runtime/v1', 'scope': 'conditional-service-boundaries-only',
        'archive_sha256': root_io.archive_sha256, 'boot_id': root_io.boot_id, 'run_id': root_io.run_id,
        'target': root_io.target, 'formally_closed': [], 'first_artifact_behavior_gate_passed': False,
        'status': 'running', 'failures': [], 'observations': {}, 'cleanup_verified': False}
    destination = root_io.output / 'settings-idle579-evidence.json'
    def save():
        report.update(commands=binding.commands, journal_reads=binding.reads,
            roles=binding.roles, writers=[dict(role=role, **writer) for (role, path), writer in binding.writers.items()])
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    def observe(name, fixed_operation):
        try:
            report['observations'][name] = fixed_operation()
        except Exception as error:
            report['failures'].append(name + ': ' + str(error))
        finally:
            save()
    save()
    try:
        try:
            report['prepared'] = binding.prepare()
            binding.install('system'); binding.install('foreign')
        except Exception as error:
            report['failures'].append('prepare/install: ' + str(error))
        if all('identity' in binding.roles.get(role, {}) for role in ('system', 'foreign')):
            observe('stale', lambda: public_boundary(binding, 'stale'))
            observe('future', lambda: public_boundary(binding, 'future'))
            observe('parameters', lambda: parameters_boundary(binding))
            observe('native-ui', lambda: native_boundary(binding, 'native-ui'))
            observe('native-malformed', lambda: native_boundary(binding, 'native-malformed'))
            observe('native-foreign', lambda: native_boundary(binding, 'native-foreign'))
            lifecycle = {}
            # Keep completed current/destroy evidence even if a later old-Context
            # challenge fails; all failures remain fatal in the final result.
            report['observations']['lifecycle_progress'] = lifecycle
            observe('lifecycle', lambda: lifecycle_boundary(binding, lifecycle))
        else:
            report['failures'].append('all mandatory native/public cases lack two actual installed identities')
        # REQUIRED final join, never a prerequisite for independent fixture runs.
        observe('settings_actions', lambda: settings_actions(root_io))
        binding.boot()
    except Exception as error:
        report['failures'].append('stage: ' + str(error))
    finally:
        try:
            binding.cleanup(); report['cleanup_verified'] = True
        except Exception as error:
            report['failures'].append('cleanup: ' + str(error))
        report['status'] = 'observed' if not report['failures'] and report['cleanup_verified'] else 'failed'
        save()
    require(report['status'] == 'observed', 'actual Settings idle stage failed; retain ' + str(destination))
    return {'report': reference(destination), 'archive_sha256': root_io.archive_sha256,
            'boot_id': root_io.boot_id, 'status': report['status'], 'formally_closed': []}
