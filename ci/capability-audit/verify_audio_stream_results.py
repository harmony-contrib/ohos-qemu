#!/usr/bin/env python3
"""Require fresh normal-app OHAudio lifecycle and actual PCM callback progress."""
import argparse
import hashlib
import json
from pathlib import Path
import re

BOUNDARIES = [('null_start', 1), ('null_pause', 1), ('null_stop', 1)]
CYCLE = [('create', 0), ('invalid_channels', 1), ('rate', 0), ('channels', 0), ('format', 0),
         ('encoding', 0), ('latency', 0), ('usage', 0), ('write_callback', 0), ('error_callback', 0),
         ('generate', 0), ('prepared', 0), ('prepared.value', 1), ('pause_before_start', 2),
         ('start', 0), ('running', 0), ('running.value', 2), ('frames_before', 0), ('@initial', None),
         ('pause', 0), ('paused', 0), ('paused.value', 5), ('flush', 0), ('resume', 0),
         ('resumed', 0), ('resumed.value', 2), ('frames_before', 0), ('@resumed', None),
         ('stop', 0), ('stopped', 0), ('stopped.value', 3), ('release', 0), ('destroy', 0)]


def application_identity(text):
    # bm dump prefixes its JSON with the bundle name, not an arbitrary JSON
    # substring. Reject missing/mixed declarations instead of searching regexes.
    if text.startswith('org.harmonycontrib.capabilityaudit:\n'):
        text = text.split('\n', 1)[1]
    info = json.loads(text)['applicationInfo']
    if (info.get('appPrivilegeLevel') != 'normal' or info.get('isSystemApp') is not False or
            type(info.get('uid')) is not int or info['uid'] < 20000000):
        raise ValueError('audio probe must be a normal, non-system application')
    return info['uid']


def verify(text, run_id, identity_text):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('explicit fresh audio run challenge required')
    uid = application_identity(identity_text)
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    expected_count = 2 + len(BOUNDARIES) + 2 * len(CYCLE)
    if len(rows) != expected_count or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'incomplete audio lifecycle: expected {expected_count} rows, got {len(rows)}')
    if any(row.get('run_id') != run_id for row in rows):
        raise ValueError('stale or mixed audio run challenge')
    first, last = rows[0], rows[-1]
    if (first.get('type') != 'identity' or type(first.get('uid')) is not int or
            type(first.get('euid')) is not int or first['uid'] != uid or first['euid'] != uid):
        raise ValueError('audio native UID does not match the normal HAP')
    if (last.get('type') != 'summary' or last.get('passed') is not True or
            type(last.get('cycles')) is not int or last['cycles'] != 2):
        raise ValueError('audio native summary failed')
    index = 1
    for cycle, sequence in ((0, BOUNDARIES), (1, CYCLE), (2, CYCLE)):
        previous_callbacks, previous_bytes, previous_frames = 0, 0, -1
        for name, expected in sequence:
            row = rows[index]
            index += 1
            if type(row.get('cycle')) is not int or row['cycle'] != cycle or row.get('passed') is not True:
                raise ValueError(f'failed audio cycle/row: {row}')
            if name.startswith('@'):
                fields = ('result', 'before_frames', 'frames', 'before_callbacks', 'callbacks', 'bytes',
                          'invalid_buffers', 'callback_error')
                if (row.get('type') != 'progress' or row.get('phase') != name[1:] or
                        any(type(row.get(field)) is not int for field in fields) or
                        row['result'] != 0 or row['before_frames'] < 0 or
                        row['frames'] <= row['before_frames'] or row['frames'] <= previous_frames or
                        row['before_callbacks'] < previous_callbacks or
                        row['callbacks'] <= row['before_callbacks'] + 2 or
                        row['bytes'] <= previous_bytes or row['bytes'] % 4 != 0 or
                        row['bytes'] < row['callbacks'] * 4 or
                        row['invalid_buffers'] != 0 or row['callback_error'] != 0):
                    raise ValueError(f'no actual PCM frame/callback progression: {row}')
                previous_callbacks, previous_bytes, previous_frames = row['callbacks'], row['bytes'], row['frames']
            elif (row.get('type') != 'step' or row.get('name') != name or
                  type(row.get('actual')) is not int or row['actual'] != expected or
                  type(row.get('expected')) is not int or row['expected'] != expected):
                raise ValueError(f'wrong audio lifecycle/boundary step: {row}')
    return rows


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--application-identity', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'status': 'fail', 'scope': 'normal-app Renderer PCM callbacks/frames and lifecycle only',
                'archive': str(args.archive.resolve()), 'run_id': args.run_id, 'failures': [],
                'first_artifact_behavior_gate_passed': False, 'capturer_tested': False,
                'actual_host_audio_samples_tested': False}
    try:
        evidence['archive_sha256'] = sha256(args.archive)
        evidence['results_sha256'] = sha256(args.results)
        evidence['application_identity_sha256'] = sha256(args.application_identity)
        text = args.results.read_text()
        evidence['observations'] = [json.loads(line) for line in text.splitlines() if line.strip()]
        evidence['results'] = verify(text, args.run_id, args.application_identity.read_text())
        evidence['status'] = 'pass'
    except (OSError, ValueError, TypeError, KeyError) as error:
        evidence['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({key: value for key, value in evidence.items() if key not in ('observations', 'results')}))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
