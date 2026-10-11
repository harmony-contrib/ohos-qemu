#!/usr/bin/env python3
"""Require typed and actual native enum members; never attest contact sync."""
import argparse
import json
from pathlib import Path
import re

from contact_sync_mode_contract import CONTRACT, AUDIO_CONTRACT, PHOTO_CONTRACT, RECORD_CLASSES, STATE_RECORD_CLASSES, PHOTO_RECORD_CLASSES, SCOPE, sha256, verify_inputs


def verify(text, run_id, identity):
    from run_normal_hap_probe import require_normal_identity
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh ContactSyncMode challenge required')
    require_normal_identity(identity)
    lines = text.splitlines()
    if len(lines) != 1:
        raise ValueError('one complete actual enum observation required')
    row = json.loads(lines[0])
    if (not isinstance(row, dict) or set(row) != {'runId', 'values', 'native', 'audioValues', 'audioNative',
            'photoValues', 'photoNative', 'attributeValues', 'attributeNative', 'records', 'stateRecords', 'photoRecords'} or row['runId'] != run_id or
            row['values'] != [1, 2] or any(type(value) is not int for value in row['values'])):
        raise ValueError('typed public SDK enum values absent, wrong, malformed or stale')
    if row['audioValues'] != [0, 1] or any(type(value) is not int for value in row['audioValues']):
        raise ValueError('typed SDK DeviceBlockStatus values must be exactly 0/1')
    if row['photoValues'] != [0] or any(type(value) is not int for value in row['photoValues']):
        raise ValueError('typed SDK FusionAssetType value must be exactly numeric zero')
    if row['attributeValues'] != list(range(14)) or any(type(value) is not int for value in row['attributeValues']):
        raise ValueError('all fourteen typed SDK Attribute values must match')
    for key, wanted in (('native', [1, 2]), ('audioNative', [0, 1]), ('photoNative', [0]),
                        ('attributeNative', list(range(14)))):
        native = row[key]
        count = len(wanted)
        if (not isinstance(native, dict) or set(native) != {'values', 'statuses', 'types', 'own', 'exception'} or
            native['values'] != wanted or any(type(value) is not int for value in native['values']) or
            native['statuses'] != [0] * (6 + 4 * count) or
            any(type(value) is not int for value in native['statuses']) or
            native['types'] not in ([6, 6] + [3] * count, [6, 7] + [3] * count,
                                   [7, 6] + [3] * count, [7, 7] + [3] * count) or
            any(type(value) is not int for value in native['types']) or
            native['own'] != [True] * (1 + count) or any(type(value) is not bool for value in native['own']) or
            native['exception'] is not False):
            raise ValueError('actual public NAPI module/enum/own-member reads must succeed with all values: ' + key)
    records = row['records']
    if not isinstance(records, list) or len(records) != len(RECORD_CLASSES):
        raise ValueError('all nine actual contact record classes are required')
    for actual, name in zip(records, RECORD_CLASSES):
        first, second = run_id + '-' + name + '-changed', run_id + '-second-' + name
        if name == 'ContactAttributes':
            first, second = '[1,8]', '[4]'
        elif name == 'Holder':
            first, second = 'com.ohos.contacts:17', 'com.ohos.contacts:29'
        if (not isinstance(actual, dict) or set(actual) != {'name', 'first', 'second', 'flags'} or
                actual['name'] != name or actual['first'] != first or actual['second'] != second or
                actual['flags'] != [True, True, True] or
                any(type(flag) is not bool for flag in actual['flags'])):
            raise ValueError('actual typed contact construction/properties/isolation failed: ' + name)
    state = row['stateRecords']
    if (not isinstance(state, dict) or set(state) != {'flags', 'values'} or
            state['flags'] != [True] * 12 or any(type(flag) is not bool for flag in state['flags']) or
            state['values'] != [run_id + suffix for suffix in ('-first-changed', '-second', '-collection', '-other')]):
        raise ValueError('actual state record construction/inheritance/fields/creator isolation failed')
    photo = row['photoRecords']
    expected = [(run_id + '-cover-changed', run_id + '-cover-second'), ('image/*', 'video/*'), ('17', '29'),
                (run_id + '-info-changed', run_id + '-info-second'),
                (json.dumps([run_id + '-first', run_id + '-second'], separators=(',', ':')), '[]'),
                (run_id + '-context-changed', run_id + '-context-second')]
    if not isinstance(photo, list) or len(photo) != len(PHOTO_RECORD_CLASSES):
        raise ValueError('all six photo record classes required')
    for actual, name, (first, second) in zip(photo, PHOTO_RECORD_CLASSES, expected):
        if (not isinstance(actual, dict) or set(actual) != {'name', 'first', 'second', 'flags'} or
                actual['name'] != name or actual['first'] != first or actual['second'] != second or
                actual['flags'] != [True] * 4 or any(type(flag) is not bool for flag in actual['flags'])):
            raise ValueError('photo record construction/fields/isolation failed: ' + name)
    return {'contract': CONTRACT, 'member_count': 2, 'audio_contract': AUDIO_CONTRACT, 'audio_member_count': 2,
            'photo_contract': PHOTO_CONTRACT, 'photo_member_count': 1, 'record_classes': list(RECORD_CLASSES),
            'state_record_classes': list(STATE_RECORD_CLASSES),
            'photo_record_classes': list(PHOTO_RECORD_CLASSES),
            'not_claimed': 'persistence_cloud_sync_storage_permissions_contacts_or_fusion_provider_or_microphone_blocking_behavior'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from verify_first_artifact_gate import checksum
    report = {'status': 'fail', 'scope': SCOPE,
              'archive_sha256': checksum(args.archive), 'run_id': args.run_id, 'arch': args.arch,
              'compiled_inputs_sha256': sha256(args.inputs), 'results_sha256': sha256(args.results),
              'application_identity_sha256': sha256(args.application_identity), 'failures': [],
              'first_artifact_behavior_gate_passed': False}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scope': report['scope']}))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
