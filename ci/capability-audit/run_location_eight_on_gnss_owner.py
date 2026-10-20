"""Location8 extension called only inside original GNSS16/393 Owner's live run.

No CLI, Owner, Capture constructor, fport, subprocess or socket constructor.
All commands go through the original bound command object. The only sender is
the original capture.connect and QGN2 encoder, one live stream per profile.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import struct
import sys
import time
import traceback

BUNDLE = 'org.harmonycontrib.capabilityaudit'
PERMISSIONS = ['ohos.permission.APPROXIMATELY_LOCATION', 'ohos.permission.LOCATION']
PROFILES = ('track', 'icon', 'fence')
SDK_SOURCES = ('build_hap_probe.py', 'location_eight_contract.py', 'location_eight/EntryAbility.ets', 'location_eight/Index.ets')

def require(value, message):
    if not value:
        raise ValueError(message)

def descriptor(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def actual(value):
    require(type(value) is dict and set(value) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}), 'Actual artifact descriptor required')
    path = Path(value['path'])
    require(path.is_absolute() and not path.is_symlink() and path.is_file() and
            descriptor(path) == {k: value[k] for k in ('path', 'sha256')} and
            ('bytes' not in value or type(value['bytes']) is int and value['bytes'] == path.stat().st_size), 'Actual artifact changed')
    return path

def preflight(config, *, qa, tool_sources):
    require(type(config) is dict and set(config) == {'schema', 'sdk_evidence', 'profiles'} and
            config['schema'] == 'location-eight-original-gnss/v1' and config['profiles'] == list(PROFILES), 'Exact finite original-Owner Location8 inputs required')
    receipt_path = actual(config['sdk_evidence'])
    receipt = json.loads(receipt_path.read_text())
    require(type(receipt.get('exit_code')) is int and receipt['exit_code'] == 0 and
            receipt.get('persona_flag') == '--location-eight-only' and receipt.get('cleanup_verified') is True and
            receipt.get('owned_container_absent') is True and receipt.get('signals') == [] and
            receipt.get('actual_guest') is None and receipt.get('actual_signed_hap') is None, 'Actual closed unsigned Location8 SDK receipt required')
    actual(receipt['driver']); actual(receipt['sdk'])
    ledger = json.loads(actual(receipt['resource_ledger']).read_text())
    require(ledger.get('schema') == 'owned-resource35/v1' and ledger.get('phase') == 'closed' and
            ledger.get('failed') is False and ledger.get('cleanup_verified') is True and
            ledger.get('errors') == ledger.get('signals') == ledger.get('containers') == [], 'Actual original SDK35 lifecycle not closed')
    qa = Path(qa).resolve(); base = qa / 'ci/capability-audit'
    source_rows = receipt['sources']
    expected = {str(base / relative) for relative in SDK_SOURCES}
    require(len(source_rows) == len(expected) and {r['path'] for r in source_rows} == expected, 'Actual SDK four-source set differs')
    for row in source_rows:
        path = actual(row); relative = str(path.relative_to(qa))
        require(tool_sources.get(relative) == row['sha256'], 'Compiled caller differs from this canonical tools snapshot')
    commands = receipt['commands']
    require(len(commands) == 1 and commands[0].get('exit_code') == 0 and commands[0].get('timed_out') is False, 'One actual completed original SDK command required')
    command = commands[0]; argv = command['argv']
    require(argv.count('--location-eight-only') == 1 and argv.count('--output') == argv.count('--probe-run-id') == 1 and
            str(base / 'build_hap_probe.py') in argv, 'SDK source/nonce/project command differs')
    log = actual(command['stdout_record']).read_text(errors='replace')
    require('BUILD SUCCESSFUL' in log, 'Actual official SDK success stdout missing')
    project = Path(argv[argv.index('--output') + 1])
    run = argv[argv.index('--probe-run-id') + 1]
    require(project.is_absolute() and project.is_dir() and not project.is_symlink() and re.fullmatch('[a-f0-9]{32}', run), 'Actual SDK project/run required')
    for name, relative in [('EntryAbility.ets', 'entry/src/main/ets/entryability/EntryAbility.ets'), ('Index.ets', 'entry/src/main/ets/pages/Index.ets')]:
        expected_text = (base / 'location_eight' / name).read_text().replace('__LOCATION_EIGHT_RUN__', run)
        require((project / relative).read_text() == expected_text, 'Actual compiled caller fixture changed')
    require("case 'permissions':" in (base / 'location_eight/EntryAbility.ets').read_text(), 'Caller must contain the actual consent action; SDK02 predecessor is insufficient')
    hap = actual(receipt['unsigned_hap'])
    require(hap.is_relative_to(project), 'SDK HAP escaped its compiled project')
    # Signature/role/HAP members are checked by the original shared verifier at runtime.
    return {'receipt': descriptor(receipt_path), 'unsigned_hap': descriptor(hap), 'run_id': run, 'project': str(project)}

def native_points(window, sent):
    """Actual HDI raw fields; no altitude/speed/bearing filled from wire expectation."""
    require(window.get('captureWindowComplete') is True, 'Complete original native interval required')
    records = window['records']; require(len(records) == len(sent) >= 2, 'Native input loss/extra report')
    by_source = {r['sourceUtcMs']: r for r in records}
    require(len(by_source) == len(records), 'Repeated native source identity')
    points = []
    def binary(word, code, width):
        require(type(word) is str and re.fullmatch('0x[a-f0-9]{' + str(width) + '}', word), 'Missing new actual native raw word')
        return struct.unpack('>' + code, bytes.fromhex(word[2:]))[0]
    for source in sent:
        row = by_source.get(source['utc_ms']); require(row is not None, 'No native report for sent UTC')
        point = {'latitude': binary(row['latitudeBits'], 'd', 16), 'longitude': binary(row['longitudeBits'], 'd', 16),
                 'accuracy': binary(row['horizontalAccuracyBits'], 'f', 8),
                 'altitude': binary(row.get('altitudeBits'), 'd', 16),
                 'speed': binary(row.get('speedBits'), 'f', 8), 'direction': binary(row.get('bearingBits'), 'f', 8),
                 'timeStamp': row['sourceUtcMs'], 'timeSinceBoot': row['sourceBootNs'], 'sourceType': 1, 'isFromMock': False}
        expected_flags = 1 | 2 | 512 | 1024 | 32 | (4 if 'altitude' in source else 0) | (8 if 'speed' in source else 0) | (16 if 'bearing' in source else 0)
        require(row['fieldValidity'] == expected_flags and point['latitude'] == source['latitude'] and point['longitude'] == source['longitude'] and
                row['horizontalAccuracyBits'] == '0x' + source['horizontal_accuracy_bits'] and
                row['altitudeBits'] == '0x' + struct.pack('>d', source.get('altitude', 0)).hex() and
                row['speedBits'] == '0x' + struct.pack('>f', source.get('speed', 0)).hex() and
                row['bearingBits'] == '0x' + struct.pack('>f', source.get('bearing', 0)).hex() and
                0 < row['sourceBootNs'] <= row['receiptBootNs'], 'Wire/native fields/validity/clock differ')
        points.append(point)
    return points

def run(*, config, settings, spec, qa, env, guest, capture, command, modules,
        snapshot, complete_window, bind_provider, provider_proofs, streams, output):
    """Call after original public stop/quiet review, before original switch/fport cleanup."""
    qa = Path(qa).resolve(); output = Path(output); output.mkdir(exist_ok=False)
    prepared = preflight(config, qa=qa, tool_sources=settings['tool_sources'])
    oracle = modules['verify_location_eight_raw']; factory = modules['location_eight_commands']
    vectors = modules['location_virtual_challenge']; wire = modules['batch_system_gnss_controller']
    shared = modules['batch_apps_contact_picker_coordinator']; identity = modules['hap_identity_binding']
    process_scan = modules['batch_network_openvpn_runtime_collect']
    report = {'schema': 1, 'scope': 'same-original-GNSS-Owner Location8 actual raw collection', 'sdk': prepared,
              'boot_id': env['boot_id'], 'archive': settings['archive'], 'profiles': [], 'failures': [], 'cleanup_errors': [],
              'district': 'pending_actual_reverse_geocoder', 'ble': 'pending_actual_controller_and_peer',
              'capability_ids_closed': [], 'first_artifact_behavior_gate_passed': False}
    sequence = 0
    def save():
        (output / 'location-eight.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    def keep(path, data):
        path = Path(path)
        with path.open('x') as stream:
            stream.write(data if type(data) is str else json.dumps(data, indent=2, allow_nan=False) + '\n')
        return descriptor(path)
    def shell(script, label, accepted_failure=False):
        nonlocal sequence
        sequence += 1; guest.healthy()
        value = capture.shell(script, 'eight-' + str(sequence) + '-' + label, accepted_failure=accepted_failure)
        guest.healthy(); return value
    def absent(label):
        raw = shell('bm dump -a', label)
        require(re.search(r'(?<![A-Za-z0-9_.])com\.ohos\.[A-Za-z0-9_.]+', raw) and
                not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) + r'(?![A-Za-z0-9_.])', raw), 'Fresh caller absent BMS cut missing')
    save(); absent('initial-BMS')
    dist, jar, _ = shared.signer_inputs(spec['signer_dist'], spec['signer_jar'])
    signed = output / 'location-eight-system.hap'
    command([sys.executable, str(qa / 'ci/capability-audit/sign_location_eight_probe.py'), '--signer-dist', str(dist),
             '--jar', str(jar), '--unsigned', prepared['unsigned_hap']['path'], '--output', str(signed),
             '--role', 'system', '--udid', env['udid']], 'sign-location-eight-system')
    shared.verify_signed_payload(Path(prepared['unsigned_hap']['path']), signed)
    report['signed'] = shared.verify_signed_hap_artifacts(signed, BUNDLE, PERMISSIONS, env['udid'], dist, jar,
        output / 'signature-verification', command, apl='system_basic', system_app=True)
    save()
    for profile in PROFILES:
        case = output / profile; case.mkdir()
        item = {'profile': profile, 'requests': [], 'wire_session': None, 'cleanup_errors': []}
        report['profiles'].append(item); installed = False; stream = None; uid = None; pid = None; process_before = None
        remote = '/data/app/el2/100/base/' + BUNDLE + '/haps/entry/files/location-eight-' + prepared['run_id'] + '.jsonl'
        counter = 0; raw_seen = False
        def raw_rows():
            nonlocal counter, raw_seen, pid
            counter += 1
            raw = shell('if test -f ' + shlex.quote(remote) + '; then cat ' + shlex.quote(remote) +
                        '; else printf "__LOCATION_EIGHT_ABSENT__\\n"; fi', profile + '-raw-' + str(counter))
            artifact = keep(case / ('raw-' + str(counter).zfill(4) + '.jsonl'), raw + '\n')
            item.setdefault('raw_captures', []).append(artifact); save()
            if raw == '__LOCATION_EIGHT_ABSENT__' or raw == '':
                require(not raw_seen, 'Caller journal disappeared after first complete row')
                return []
            first = oracle.decode(raw.splitlines()[0])
            require(type(first.get('pid')) is int and first['pid'] > 0, 'Actual journal PID missing')
            if pid is None: pid = first['pid']
            require(pid == first['pid'], 'Singleton caller process changed')
            rows = oracle.rows_from_text(raw + '\n', prepared['run_id'], env['boot_id'], pid, uid)
            raw_seen = True; return rows
        def issue(c):
            item['requests'].append(keep(case / (c['operation_id'] + '.request.json'), c)); save()
            shell('aa start -a EntryAbility -b ' + BUNDLE + ' --ps request ' +
                  shlex.quote(json.dumps(c, separators=(',', ':'), allow_nan=False)), profile + '-' + c['action'])
        def wait(c, timeout=40):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                rows = raw_rows()
                matching = [r for r in rows if r['operation_id'] == c['operation_id'] and r['kind'] == 'end']
                if matching:
                    require(len(matching) == 1, 'Repeated raw end acknowledgement')
                    return rows
                time.sleep(.25)
            raise ValueError('No actual singleton raw end for ' + c['action'])
        try:
            installed = True  # intent precedes constructor/install; cleanup must run even on failure
            capture.command([capture.a.hdc, '-t', env['target'], 'install', str(signed)], 'eight-install-' + profile)
            bms = shell('bm dump -n ' + BUNDLE, profile + '-BMS')
            app_identity = identity.bms_application_identity(bms, BUNDLE)
            bms_doc = oracle.decode(bms[bms.find('{'):])
            require(bms_doc['applicationInfo'].get('isSystemApp') is True and
                    bms_doc['applicationInfo'].get('appPrivilegeLevel') == 'system_basic', 'Actual installed system API role missing')
            uid = app_identity['uid']; item['BMS_identity'] = app_identity
            shell('test ! -e ' + shlex.quote(remote), profile + '-fresh-raw-path')
            source = vectors.challenge(time.time_ns() // 1000000)
            commands = factory.commands(profile, prepared['run_id'], env['boot_id'],
                [secrets.token_hex(16) for _ in oracle.PROFILES[profile]], source)
            consent = dict(commands[0], operation_id=secrets.token_hex(16), action='permissions')
            issue(consent)
            # A genuine system role still uses the existing user-grant dialogue.
            action = capture.ui.click('com.ohos.permissionmanager', text=spec['permission_allow_text'], label='eight-consent-' + profile)
            capture.report['ui_actions'].append(action)
            rows = wait(consent, 90)
            terminal = [r for r in rows if r['operation_id'] == consent['operation_id'] and r['kind'] == 'return']
            require(len(terminal) == 1, 'Actual user consent return missing')
            consent_value = terminal[0]['value']
            require(type(consent_value) is dict and set(consent_value) == {'permissions', 'authResults', 'filesDir', 'journalIno', 'journalUid'} and
                    consent_value['permissions'] == PERMISSIONS and consent_value['authResults'] == [0, 0], 'Actual user consent missing or denied')
            files_dir = consent_value['filesDir']
            require(type(files_dir) is str and files_dir.startswith('/data/storage/') and
                    files_dir.endswith('/haps/entry/files') and str(Path(files_dir)) == files_dir and '..' not in Path(files_dir).parts and
                    type(consent_value['journalIno']) is str and re.fullmatch('[1-9][0-9]*', consent_value['journalIno']) and
                    consent_value['journalUid'] == uid, 'Actual UIAbility module filesDir/inode/UID differs')
            sandbox_file = '/proc/' + str(pid) + '/root' + files_dir + '/' + Path(remote).name
            stat_raw = shell('stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + shlex.quote(remote) + ' ' + shlex.quote(sandbox_file), profile + '-actual-module-files-identity')
            stats = stat_raw.splitlines()
            require(len(stats) == 2 and stats[0] == stats[1] and
                    re.fullmatch('[0-9]+:' + re.escape(consent_value['journalIno']) + ':' + str(uid) + ':regular file', stats[0]), 'App filesDir/root module/proc sandbox file identities differ')
            item['module_files_binding'] = {'caller': consent_value, 'root_path': remote, 'sandbox_path': sandbox_file, 'raw_stat': stat_raw}
            item['consent_operation_id'] = consent['operation_id']
            item['profile_operation_ids'] = [c['operation_id'] for c in commands]
            process_before = capture.mapping_snapshot('eight-' + profile + '-caller-before', pid=pid)
            p = process_before['snapshot']['processes'][pid]
            require(process_before['snapshot']['complete'] and p['complete'] and p['uids'] == [uid] * 4 and p['argv'][0] == BUNDLE, 'Actual caller PID/UID/argv cut differs')
            item['process_before'] = process_before['evidence']
            first_quiet = True; sent = []; before = after = None
            for c in commands:
                if c['action'] == 'quiet': c['wait_ms'] = (5000 if profile == 'icon' else 30000) if first_quiet else 2500
                issue(c)
                if c['action'] == 'quiet' and first_quiet:
                    first_quiet = False
                    before = snapshot('eight-' + profile + '-native-before')
                    stream, nonce, session = capture.connect('gnss', 'location-eight-' + profile); streams.append(stream)
                    item['wire_session'] = session
                    session['capability_ack_hex'] = wire.negotiate_precision(stream, nonce).hex()
                    source = vectors.challenge(time.time_ns() // 1000000)
                    source['measurements'] = source['measurements'][:2] if profile == 'icon' else source['measurements']
                    source['interval_ms'] = 1200
                    for i, row in enumerate(source['measurements']):
                        row['at_ms'] = i * 1200; row['utc_ms'] = source['measurements'][0]['utc_ms'] + i * 1200
                    item['stimulus'] = keep(case / 'controlled-virtual-stimulus.json', source)
                    start = time.monotonic()
                    for i, row in enumerate(source['measurements']):
                        while time.monotonic() < start + row['at_ms'] / 1000:
                            guest.healthy(); time.sleep(min(.1, max(0, start + row['at_ms'] / 1000 - time.monotonic())))
                        packet = wire.encode_precision_sample(nonce, i + 1, row)
                        stream.sendall(packet)
                        session['frames'].append({'hex': packet.hex(), 'host_monotonic_ns': time.monotonic_ns(), 'measurement': row})
                        sent.append(row); save()
                    time.sleep(.75)
                    after = snapshot('eight-' + profile + '-native-after')
                    window = complete_window(before, after)
                    provider = {'gnss': native_points(window, sent)}
                    item['native_window'] = keep(case / 'native-window.json', window)
                    item['provider'] = keep(case / 'provider-native.json', provider)
                    stream.close(); stream = None
                rows = wait(c)
            final = raw_rows()
            # Preserve full raw bytes/sequence. Only the separately checked three
            # permission-control rows are excluded from the fixed behavior body.
            body = [r for r in final if r['operation_id'] != consent['operation_id']]
            item['raw_review'] = oracle.review(body, profile, provider)
            item['reviewed_raw'] = item['raw_captures'][-1]
            process_after = capture.mapping_snapshot('eight-' + profile + '-caller-after', pid=pid)
            p_after = process_after['snapshot']['processes'][pid]
            require(process_after['snapshot']['complete'] and p_after['complete'] and
                    p_after['uids'] == [uid] * 4 and p_after['argv'][0] == BUNDLE and
                    p_after['before']['start_ticks'] == p['before']['start_ticks'], 'Caller process generation changed')
            require(identity.bms_application_identity(shell('bm dump -n ' + BUNDLE, profile + '-BMS-after'), BUNDLE) == app_identity, 'Caller BMS identity changed')
            item['process_after'] = process_after['evidence']
            for index, provider_pid in enumerate(sorted(window['actual_provider_origins']['pids'])):
                proof = bind_provider('eight-' + profile + '-provider-final-' + str(index), provider_pid)
                require(all(proof[k] == provider_proofs[provider_pid][k] for k in ('pid', 'boot_id', 'start_ticks', 'uid', 'role')), 'Native provider process generation changed')
            item['status'] = 'raw_behavior_matched_NOT_capability_closure'
        except Exception as error:
            item['status'] = 'fail_raw_preserved'; item['error'] = type(error).__name__ + ': ' + str(error)
            item['traceback'] = traceback.format_exc(); report['failures'].append(profile + ': ' + item['error'])
        finally:
            if stream is not None: stream.close()
            if installed:
                # Best-effort in-process API release remains observable; process
                # disposal is still the original Owner's final fallback.
                try:
                    if uid is not None:
                        cleanup = dict(commands[0], operation_id=secrets.token_hex(16), action='cleanup')
                        issue(cleanup); release_rows = wait(cleanup)
                        release = [r for r in release_rows if r['operation_id'] == cleanup['operation_id'] and r['kind'] in ('return', 'throw')]
                        require(len(release) == 1 and release[0]['kind'] == 'return' and release[0]['code'] == 0, 'Actual emergency in-process release failed')
                        keep(case / 'final-raw.jsonl', shell('cat ' + shlex.quote(remote), profile + '-preserve-final') + '\n')
                except Exception as error: item['cleanup_errors'].append('caller release/preserve: ' + str(error))
                try:
                    shell('aa force-stop ' + BUNDLE, profile + '-force-stop')
                    shell('bm uninstall -n ' + BUNDLE, profile + '-uninstall')
                    absent(profile + '-BMS-absent')
                    if uid is None: raise ValueError('Installed UID was never independently established')
                    for i in range(2):
                        nonce = secrets.token_hex(16)
                        script = process_scan.snapshot_script(nonce, env['boot_id'], mode='uid', uid=uid, bundle=BUNDLE)
                        raw = shell(script, profile + '-UID-absence-' + str(i))
                        parsed = process_scan.parse_snapshot(raw + '\n', nonce, env['boot_id'], mode='uid', uid=uid, bundle=BUNDLE)
                        require(parsed['processes'] == {}, 'Caller UID/bundle process remains after uninstall')
                        keep(case / ('cleanup-scan-' + str(i) + '.raw'), raw + '\n')
                        if i == 0: time.sleep(.5)
                except Exception as error: item['cleanup_errors'].append('owned app absence: ' + str(error))
            if item['cleanup_errors']:
                report['cleanup_errors'].extend(profile + ': ' + e for e in item['cleanup_errors'])
            save()
        if report['cleanup_errors'] or report['failures']:
            break  # Never run another profile after an unresolved failure/cleanup.
    require(shell('cat /proc/sys/kernel/random/boot_id', 'final-boot').strip() == env['boot_id'], 'Original boot changed')
    report['status'] = 'raw_profiles_matched_NOT_capability_closure' if not report['failures'] and not report['cleanup_errors'] and len(report['profiles']) == 3 else 'fail_raw_preserved'
    save(); return report
