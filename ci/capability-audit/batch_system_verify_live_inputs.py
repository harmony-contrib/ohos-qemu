#!/usr/bin/env python3
"""Independently recompute public callback/challenge proof, never trust pass flags."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from batch_system_live_inputs import (BUNDLE, FIXTURES, SCOPE, digest, verify_signed_payload, load_rows,
    read_json, trace, verify_project, write_json, f32, require_no_api_errors, switch_observations)
from batch_system_gnss_controller import encode_sample


def require(condition, message):
    if not condition: raise ValueError(message)


def window(rows, pair):
    require(isinstance(pair, list) and len(pair) == 2 and all(type(x) is int for x in pair) and 0 < pair[0] < pair[1] <= len(rows), 'missing actual app-clock interval')
    a, b = rows[pair[0] - 1], rows[pair[1] - 1]
    require(a['kind'] == b['kind'] == 'quiet_marker', 'interval is not bounded by real app records')
    return rows[pair[0]:pair[1] - 1], (int(b['boot_ns']) - int(a['boot_ns'])) / 1e9


def compare_location(rows, samples, generation):
    actual = [r for r in rows if r['kind'] == 'location' and r['generation'] == generation]
    require(actual, 'no actual ordinary location callbacks')
    seen = set(); previous_utc = 0; previous_boot = 0
    for r in actual:
        v = r['values']; require(len(v) == 11 and v[0] == generation, 'old-generation/malformed location callback')
        _, lat, lon, altitude, accuracy, speed, utc, boot, mock, mock_present, source = v
        require(mock_present == 1 and mock == 0 and source == 1, 'public fix must explicitly be nonmock GNSS')
        require(0 < boot <= int(r['boot_ns']) and int(r['boot_ns']) - boot <= 5_000_000_000,
                'public fix is stale or not guest CLOCK_BOOTTIME ns')
        require(utc > previous_utc and boot >= previous_boot, 'public fix order repeated or regressed')
        matched = [i for i, x in enumerate(samples) if x['utc_ms'] == utc and abs(x['latitude'] - lat) <= 1e-8 and
                   abs(x['longitude'] - lon) <= 1e-8 and abs(f32(x['horizontal_accuracy']) - accuracy) <= 1e-4 and
                   ('altitude' not in x or abs(x['altitude'] - altitude) <= 1e-5) and
                   ('speed' not in x or abs(f32(x['speed']) - speed) <= 1e-5)]
        require(len(matched) == 1, 'public fix does not match independent source coordinates/UTC/accuracy')
        seen.add(matched[0]); previous_utc = utc; previous_boot = boot
    require(seen == set(range(len(samples))), 'not every deliberately spaced source GNSS fix was publicly observed')
    return {'callbacks': len(actual), 'distinct_matched_measurements': len(seen), 'source_type': 'GNSS1', 'mock': False}


def compare_sensor(rows, samples, generation):
    actual = [r for r in rows if r['kind'] == 'sensor' and r['generation'] == generation]
    require(actual, 'no actual ordinary accelerometer callbacks')
    expected = [tuple(f32(x[k]) for k in ('x', 'y', 'z')) for x in samples]
    seen = set(); previous_timestamp = 0; previous_index = -1
    for r in actual:
        v = r['values']; require(len(v) == 5 and v[0] == generation, 'old-generation/malformed sensor callback')
        require(0 < v[4] <= int(r['boot_ns']) and int(r['boot_ns']) - v[4] <= 5_000_000_000,
                'sensor timestamp stale/wrong unit')
        require(v[4] > previous_timestamp, 'sensor timestamp repeated/regressed')
        index = previous_index + 1
        require(index < len(expected) and all(abs(expected[index][j] - v[j + 1]) <= 1e-5 for j in range(3)),
                'sensor callback not next independently supplied float32 xyz sample')
        seen.add(index); previous_timestamp = v[4]; previous_index = index
    require(seen == set(range(len(samples))), 'not every deliberately spaced source acceleration was publicly observed')
    return {'callbacks': len(actual), 'matched_samples': len(seen), 'units': 'm/s^2_float32'}


def compare_still(rows, samples, generation):
    """Check real public transitions against externally supplied accelerations.

    A successful Sensor API alone cannot satisfy this. Product source/DSO binding
    is required separately, and physical immobility accuracy is not claimed.
    """
    import math
    sensor_rows = [r for r in rows if r['kind'] == 'sensor' and r['generation'] == generation]
    compare_sensor(rows, samples, generation)
    blocks = []
    for index, sample in enumerate(samples):
        inside = 7 < math.sqrt(sum(f32(sample[k]) ** 2 for k in ('x', 'y', 'z'))) < 11
        if not blocks or blocks[-1]['inside'] != inside:
            blocks.append({'inside': inside, 'indices': []})
        blocks[-1]['indices'].append(index)
    require(len(blocks) >= 3 and [b['inside'] for b in blocks[:3]] == [True, False, True],
            'external source lacks the actual still measurement transitions')
    require(all(len(b['indices']) >= 10 for b in blocks), 'each source phase must outlast the real five-event discriminator')
    actual = [r for r in rows if r['kind'] == 'still' and r['generation'] == generation]
    require(len(actual) == len(blocks), 'missing/extra actual ordinary public still transition callbacks')
    for r, block in zip(actual, blocks):
        state = 1 if block['inside'] else 2
        require(r['values'] == [generation, state], 'public still wrong state/order or retired callback generation')
        first = block['indices'][4 if block['inside'] else 0]
        last = block['indices'][-1]
        earliest = sensor_rows[first]['values'][4]
        latest = sensor_rows[last]['values'][4] + 2_000_000_000
        require(earliest <= int(r['boot_ns']) <= latest,
                'public still arrived before genuine input threshold or outside actual source phase latency')
    return {'callbacks': len(actual), 'states': [r['values'][1] for r in actual],
        'measurement_semantics': 'original five-event 7<magnitude<11 m/s^2 heuristic',
        'physical_immobility_accuracy_verified': False, 'relativeStill_verified': False}


def verify_msdp_inventory(directory, product='arm64_virt'):
    """Check the root-owned actual source/GN/CFI/DSO package contract."""
    directory = Path(directory)
    repository = Path(__file__).resolve().parents[2]
    component = repository / 'patches/common/base/msdp/device_status/public_still'
    manifest = read_json(component / 'manifest.json')
    value = read_json(directory / 'inventory.json')
    expected = {n: row['after'] for n, row in manifest['originals'].items()}
    observed = value.get('source_sha256', {})
    require(all(observed.get(n) == sha for n, sha in expected.items()) and
            value.get('recipe', {}).get('patches/common/base/msdp/device_status/public_still/manifest.json') == digest(component / 'manifest.json'),
            'actual MSDP component/source binding absent/stale')
    sys.path.insert(0, str(repository / 'scripts'))
    import verify_qemu_msdp_image as guard
    guard.check_inventory(value, product, directory)
    require(all(value['graphs'][name]['cross_dso_cfi'] is True for name in ('algo', 'service')),
            'actual product MSDP cross-DSO CFI must be preserved')
    return value


def sessions(report, inputs):
    values = report.get('sessions', []); seen_nonces = set(); old = {}
    for generation in (1, 2):
        for kind in ('gnss', 'sensor'):
            subset = [v for v in values if v.get('kind') == kind and v.get('generation') == generation]
            labels = ['wrong_nonce', 'zero_sequence', 'wrong_version', 'nonfinite']
            if generation == 2: labels.append('old_generation_nonce')
            labels.append('valid-generation-' + str(generation))
            require(sorted(x['label'] for x in subset) == sorted(labels), 'missing/duplicate actual negative or valid socket session')
            for s in subset:
                hello = bytes.fromhex(s['hello_hex']); require(len(hello) == 32, 'missing raw provider hello')
                magic, version, challenge, field, reserved = struct.unpack('<4sI16sII', hello)
                require((magic, version, field, reserved) == ((b'QGN1', 1, 88, 0) if kind == 'gnss' else (b'QSN1', 1, 1, 0)), 'provider raw handshake ABI changed')
                require(challenge != bytes(16) and challenge not in seen_nonces, 'reused/zero provider session nonce')
                seen_nonces.add(challenge)
                frames = s['frames']; samples = inputs[generation][kind]
                def frame(seq, sample):
                    return encode_sample(challenge, seq, sample) if kind == 'gnss' else struct.pack('<4sI16sQfff', b'QSF1', 1, challenge, seq, sample['x'], sample['y'], sample['z'])
                if s['label'].startswith('valid-generation-'):
                    require(len(frames) == len(samples), 'source trace/actual wire frame count differ')
                    require(all(bytes.fromhex(v['hex']) == frame(i, sample) for i, (v, sample) in enumerate(zip(frames, samples), 1)), 'sent wire bytes differ from externally supplied trace')
                    start = s.get('trace_start_monotonic_ns')
                    require(type(start) is int and start >= s['connected_monotonic_ns'], 'actual monotonic send schedule absent')
                    previous = start
                    for record, sample in zip(frames, samples):
                        sent = record['host_monotonic_ns']; due = start + sample['at_ms'] * 1_000_000
                        require(type(sent) is int and sent >= previous and 0 <= sent - due <= 1_000_000_000,
                                'actual input timing differs from deliberate source schedule')
                        previous = sent
                    require(s.get('stop_disconnect') in ('EOF', 'ECONNRESET'), 'stopping observers did not quiesce actual provider stream')
                    old[(generation, kind)] = challenge
                else:
                    require(len(frames) == 1 and s.get('disconnect') in ('EOF', 'ECONNRESET'), 'rejection not proved by actual server disconnect')
                    packet = bytearray(frame(1, samples[0])); name = s['label']
                    if name == 'wrong_nonce': packet[8] ^= 128
                    elif name == 'zero_sequence': packet[24:32] = bytes(8)
                    elif name == 'wrong_version': packet[4:8] = struct.pack('<I', 0xffffffff)
                    elif name == 'nonfinite':
                        if kind == 'gnss': packet[40:48] = struct.pack('<d', float('nan'))
                        else: packet[32:36] = struct.pack('<f', float('nan'))
                    else: packet[8:24] = old[(1, kind)]
                    require(bytes.fromhex(frames[0]['hex']) == bytes(packet), 'negative wire mutation not independently reproducible')
                    require(s['eof_monotonic_ns'] >= frames[0]['host_monotonic_ns'] >= s['connected_monotonic_ns'], 'invalid rejection ordering')
    return {'sessions': len(values), 'unique_provider_nonces': len(seen_nonces), 'old_generation_rejected': True}


def mapped_processes(text):
    result = []
    for block in text.split('PROCESS ')[1:]:
        uid = re.search(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', block, re.M)
        require(uid is not None and len(set(uid.groups())) == 1, 'actual loaded process identity missing')
        require('(deleted)' not in block, 'mapped image library is deleted/replaced')
        result.append((int(uid.group(1)), block))
    require(result, 'no actual driver/service mapped processes')
    return result


def verify_mapping_replays(report, target):
    """Global absence must come from two complete original command observations."""
    from batch_system_live_mappings import verify_evidence
    entries = report.get('mapping_snapshots', [])
    require(isinstance(entries, list) and len(entries) == 2,
            'two complete retained global mappings observations required')
    previous = -1
    nonces = set()
    for generation, entry in enumerate(entries, 1):
        require(entry.get('nonce') not in nonces and entry.get('boot_id') == report.get('boot_id'),
                'fresh distinct mappings observations from the same boot required')
        nonces.add(entry['nonce'])
        index = entry.get('command_index')
        require(type(index) is int and previous < index < len(report['commands']),
                'original mappings command missing, reused or reordered')
        snapshot = verify_evidence(entry, report['commands'][index], target=target)
        require(snapshot['complete'] is True and snapshot['global_absence_eligible'] is True and entry.get('pid') is None,
                'unread or partial process enumeration cannot prove global absence')
        require(entry.get('legacy_view', {}).get('path') == report.get('mappings_' + str(generation)),
                'ordinary positive check uses another or reordered mappings view')
        previous = index


def verify(root, archive, boot_path, sdk):
    from run_normal_hap_probe import require_normal_identity
    root, archive, boot_path, sdk = map(Path, (root, archive, boot_path, sdk))
    report = read_json(root / 'capture.json'); boot = read_json(boot_path); env = boot['test_environment']
    require(report.get('scope') == SCOPE and report.get('capture_complete') is True and not report['failures'], 'capture incomplete/failed; raw logs must be retained')
    require(report['archive_sha256'] == digest(archive) == boot['archive_sha256'] and
        report['enclosing_boot_sha256'] == digest(boot_path) and report['boot_id'] == env['boot_id'] and
        boot.get('purpose') == 'acceptance' and boot.get('status') == 'pass' and env.get('external_keepalive') is False and
        env['device_type'] in ('phone','2in1') and report['arch'] == env['guest_arch'] and
        {'arm64':'arm64_virt','armv7a':'armv7a_virt','x86_64':'x86_64_virt'}.get(env['guest_arch']) == env['product'],
        'not same new actual product/profile archive/acceptance boot')
    for rel, value in report['files_sha256'].items():
        path = root / rel
        require(not Path(rel).is_absolute() and '..' not in Path(rel).parts and path.is_file() and not path.is_symlink() and digest(path) == value, 'captured evidence changed: ' + rel)
    for c in report['commands']:
        require(c.get('log') and digest(c['log']) == c['sha256'], 'actual command evidence changed')
    require(report['runner_sha256'] == digest(Path(__file__).with_name('batch_system_run_live_inputs.py')), 'capture runner source changed')
    verify_mapping_replays(report, env['target'])
    project = Path(report['project']); verify_project(project, sdk, report['run_id'], report['arch'])
    require(digest(project / 'live-inputs-contract.json') == report['contract_sha256'] and
        digest(project / 'live-inputs-build.json') == report['build_sha256'], 'actual SDK contract/build changed')
    build = read_json(project / 'live-inputs-build.json')
    require(build['status'] == 'pass' and digest(build['unsigned_hap']) == build['unsigned_hap_sha256'] and
        all(c['exit_code'] == 0 and digest(c['log']) == c['sha256'] for c in build['commands']), 'SDK source/build proof incomplete')
    require(digest(report['signed_hap']) == report['signed_hap_sha256'], 'signed HAP bytes changed')
    verify_signed_payload(build['unsigned_hap'], report['signed_hap'])
    require(digest(report['signer_jar']) == report['signer_jar_sha256'], 'actual signature verifier changed')
    signatures = [c for c in report['commands'] if c['label'] == 'actual-hap-signature']
    require(len(signatures) == 1 and signatures[0]['exit_code'] == 0, 'actual HAP signature verification absent')
    text = Path(signatures[0]['log']).read_text()
    require(all(s in text for s in ['verify codesign success', 'Digest verify result: true', 'verify-app success', 'verify permission sign success']), 'incomplete actual code/profile signature verification')
    cms = subprocess.run(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(root / 'verified-profile.p7b'), '-noverify'], capture_output=True, check=True, timeout=30)
    profile = json.loads(cms.stdout); bundle = profile['bundle-info']
    require(bundle['bundle-name'] == BUNDLE and bundle['apl'] == 'normal' and bundle['app-feature'] == 'hos_normal_app' and
        not profile['acls']['allowed-acls'] and not profile['permissions']['restricted-permissions'], 'nonordinary profile/ACL bypass')
    identity = (root / 'application-identity.json').read_text(); uid = require_normal_identity(identity, BUNDLE)
    require(uid == report['ordinary_uid'], 'actual ordinary UID mismatch')
    rows = load_rows(root / 'raw-results.jsonl', report['run_id'])
    require_no_api_errors(rows, 'independent ordinary API/lifecycle verification')
    public_switch = switch_observations(rows, require_complete=True)
    require(rows[0]['kind'] == 'ready' and rows[-1]['kind'] == 'finished', 'missing full actual app lifecycle')
    perms = [r for r in rows if r['kind'] == 'permissions']
    require(len(perms) == 1 and perms[0]['text'].split(',') == ['ohos.permission.APPROXIMATELY_LOCATION', 'ohos.permission.LOCATION'] and
        perms[0]['values'] == [0, 0], 'actual fine/approx ordinary consent not granted')
    denials = [r for r in rows if r['kind'] == 'socket_denials']
    require({r['generation'] for r in denials} == {0, 1, 2}, 'actual UID denials missing at active provider generations')
    for r in denials:
        value = json.loads(r['text'])
        require(value['uid'] == uid and type(value['pid']) is int and value['pid'] > 0 and value['gnss_errno'] in (1, 13) and value['sensor_errno'] in (1, 13),
            'ordinary UID was not denied by actual socket boundary (ENOENT/refusal is not permission proof)')
    inputs = {}
    for generation in (1, 2):
        if rows[0]['schema'] == 2:
            starts = [r for r in rows if r['generation'] == generation and r['kind'] == 'start']
            previous_stop = max((r['seq'] for r in rows if r['generation'] == generation - 1 and r['kind'] == 'stopped'), default=0)
            require(len(starts) == 1, 'missing/duplicate actual start before switch observation binding')
            observations = [r for r in public_switch if previous_stop < r['before_seq'] < r['after_seq'] < starts[0]['seq']]
            require(observations and observations[-1]['location_enabled'] is True,
                    'actual read-only public switch state was not true before ordinary subscription')
        base = root / ('input-' + str(generation)); m = read_json(base / 'manifest.json')
        require(m['run_id'] == report['run_id'] and m['generation'] == generation and bool(m['source'].strip()), 'root external trace provenance absent')
        inputs[generation] = {kind: trace(base / (kind + '.json'), kind) for kind in ('gnss', 'sensor')}
        require([r['kind'] for r in rows if r['generation'] == generation].count('start') == 1 and
                len([r for r in rows if r['generation'] == generation and r['kind'] == 'stopped']) == 1, 'missing/duplicate real subscribe lifecycle')
        bad, _ = window(rows, report['attack_window_' + str(generation)])
        require(not any(r['kind'] in ('location', 'sensor', 'still') for r in bad), 'rejected/no-source session generated public callbacks')
        stopped = next(r['seq'] for r in rows if r['generation'] == generation and r['kind'] == 'stopped')
        next_start = next((r['seq'] for r in rows if r['generation'] == generation + 1 and r['kind'] == 'start'), len(rows) + 1)
        require(not any(stopped < r['seq'] < next_start and r['kind'] in ('location', 'sensor', 'still') for r in rows),
                'queued callback arrived after actual off() completed')
        quiet, elapsed = window(rows, report['quiet_window_' + str(generation)])
        require(elapsed >= 3.9 and not any(r['kind'] in ('location', 'sensor', 'still') for r in quiet), 'actual post-stop quiet interval missing or old callback delivered')
    require(all(digest(root / 'input-1' / (kind + '.json')) != digest(root / 'input-2' / (kind + '.json')) for kind in ('gnss', 'sensor')),
            'reused source trace between newly challenged generations')
    wire = sessions(report, inputs)
    # Bind source/feature/build inventories to the very package used for this boot.
    package = Path(env['freshly_extracted_directory']); repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository / 'scripts'))
    import verify_qemu_gnss_image as gnss_guard
    import verify_qemu_runtime_assets_image as sensor_guard
    gi = read_json(package / 'gnss-source/inventory.json'); si = read_json(package / 'runtime-assets-source/inventory.json')
    gnss_guard.check_inventory(gi, env['product'], package / 'gnss-source')
    sensor_guard.check_inventory(si, env['product'], package / 'runtime-assets-source')
    for name in ['gnss-source/inventory.json', 'runtime-assets-source/inventory.json']:
        require(boot['initial_package_file_sha256'].get(name) == digest(package / name), 'boot did not bind this source/feature inventory')
    libdir579 = 'lib' if env['guest_arch'] == 'armv7a' else 'lib64'
    results = {'wire_rejections': wire, 'ordinary_uid_socket_boundary': uid}
    for component, compare in [('gnss', compare_location), ('sensor', compare_sensor)]:
        try:
            for generation in (1, 2):
                maps = mapped_processes(Path(report['mappings_' + str(generation)]).read_text())
                if component == 'gnss':
                    require(any(u == 1022 and 'vendorGnssAdapter.so' in b and 'libgnss_interface_service_2.0.z.so' in b and 'location_host' in b for u, b in maps), 'real GNSS provider/bridge not mapped in location_host1022')
                    require(any('liblbsservice_gnss.z.so' in b for _, b in maps), 'real third GNSS business service not mapped')
                else:
                    require(any(u == 3033 and 'libhdi_sensor_impl.z.so' in b and 'sensor_host' in b for u, b in maps), 'actual Sensor VDI not mapped in sensor_host3033')
                record = next(c for c in report['commands'] if c['label'] == 'actual-image-libraries-' + str(generation))
                observed = dict(re.findall(r'^([a-f0-9]{64})\s+(\S+)\s*$', Path(record['log']).read_text(), re.M))
                expected = {'/vendor/lib64/vendorGnssAdapter.so': gi['files_sha256']['provider.so'],
                    '/vendor/lib64/libgnss_interface_service_2.0.z.so': gi['files_sha256']['bridge.so'],
                    '/system/lib64/liblbsservice_gnss.z.so': gi['files_sha256']['service.so'],
                    '/vendor/lib64/libhdi_sensor_impl.z.so': si['files_sha256']['sensor.so']}
                expected = {name.replace('/lib64/','/' + libdir579 + '/'):value for name,value in expected.items()}
                require(all(observed.get(value) == name for name, value in expected.items()), 'actual guest DSO bytes differ from this new package')
                results[component + '_generation' + str(generation)] = compare(rows, inputs[generation][component], generation)
            results[component] = {'status': 'pass'}
        except Exception as e: results[component] = {'status': 'fail', 'reason': str(e)}
    try:
        inventory = verify_msdp_inventory(package / 'msdp-source', env['product'])
        require(boot['initial_package_file_sha256'].get('msdp-source/inventory.json') == digest(package / 'msdp-source/inventory.json'),
                'boot did not bind current actual MSDP source/build inventory')
        for generation in (1, 2):
            maps = mapped_processes(Path(report['mappings_' + str(generation)]).read_text())
            require(any(u < 10000 and 'libdevicestatus_algo.z.so' in b and 'libdevicestatus_service.z.so' in b for u, b in maps),
                    'actual real algorithm and service not loaded together in native process')
            require(not any('libdevicestatus_mock.z.so' in b for _, b in maps), 'mock MSDP library mapped during real challenge')
            record = next(c for c in report['commands'] if c['label'] == 'actual-image-libraries-' + str(generation))
            observed = dict(re.findall(r'^([a-f0-9]{64})\s+(\S+)\s*$', Path(record['log']).read_text(), re.M))
            require(observed.get(inventory['files_sha256']['libdevicestatus_algo.z.so']) == '/system/' + libdir579 + '/libdevicestatus_algo.z.so' and
                    observed.get(inventory['files_sha256']['libdevicestatus_service.z.so']) == '/system/' + libdir579 + '/libdevicestatus_service.z.so',
                    'real mapped MSDP DSO differs from source-bound package')
            results['msdp_public_still_generation' + str(generation)] = compare_still(rows, inputs[generation]['sensor'], generation)
        results['msdp_public_still'] = {'status': 'pass', 'physical_immobility_accuracy_verified': False, 'relativeStill_verified': False}
    except Exception as e:
        results['msdp_public_still'] = {'status': 'fail', 'reason': str(e)}
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['capture-directory', 'archive', 'boot', 'sdk', 'output']: p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args(); report = {'schema_version': 1, 'scope': SCOPE, 'status': 'fail', 'first_artifact_behavior_gate_passed': False,
        'verifier_sha256': digest(Path(__file__)), 'capture_sha256': digest(a.capture_directory / 'capture.json'), 'failures': []}
    try:
        report['results'] = verify(a.capture_directory, a.archive, a.boot, a.sdk)
        if all(report['results'].get(c, {}).get('status') == 'pass' for c in ('gnss', 'sensor', 'msdp_public_still')):
            report['status'] = 'pass'
    except Exception as e: report['failures'].append(type(e).__name__ + ': ' + str(e))
    write_json(a.output, report); print(json.dumps({'status': report['status'], 'failures': report['failures']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__': raise SystemExit(main())
