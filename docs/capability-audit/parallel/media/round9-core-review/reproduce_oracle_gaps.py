#!/usr/bin/env python3
"""Read-only product review: synthetic mutations are NOT guest acceptance.

Loads the current root oracle and its existing fixture generator without changing
those files. Temporary fixture files stay in the caller-specified docs directory
and are removed on completion. Does not invoke SDK, HDC, Docker, or QEMU.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit = args.root.resolve() / 'ci/capability-audit'
    sys.path.insert(0, str(audit))
    fixtures = load('review_event_fixtures', audit / 'test_batch_media_audio_events.py')
    oracle = fixtures.oracle
    result = {'scope': 'synthetic_oracle_mutations_NOT_guest_acceptance', 'closed_requirements': [],
              'first_artifact_behavior_gate_passed': False, 'sources_sha256': {}, 'observations': []}
    for name in ('batch_media_audio_event_challenge.py', 'test_batch_media_audio_events.py'):
        result['sources_sha256'][name] = hashlib.sha256((audit / name).read_bytes()).hexdigest()
    case = fixtures.Events()
    for mode in (0, 1, 2):
        with tempfile.TemporaryDirectory(prefix='review-oracle-', dir=args.output.parent) as temp:
            directory = Path(temp)
            rows, log, identity, challenge = case.prepare(directory, mode)
            baseline = case.verify(directory, log, identity, challenge, mode)
            assert baseline['status'] == 'candidate_audio_event_PCM_diagnostic_pass'
            mutations = {}
            errored = copy.deepcopy(rows)
            callback_slot = next(i for i, row in enumerate(errored) if row.get('type') == 'event_pcm')
            errored.insert(callback_slot, {'type': 'event_callback', 'run_id': fixtures.RUN,
                               'kind': 2, 'code': 2, 'hint': 0, 'monotonic_ns': 11000000000})
            mutations['unexpected_actual_main_error_callback'] = errored
            wrong_clock = copy.deepcopy(rows)
            for row in wrong_clock:
                if row.get('type') == 'event_snapshot' and row.get('point') in ('baseline', 'primer_baseline'):
                    row['timestamp_ns'] += 3600 * 1000000000
            mutations['baseline_timestamp_one_hour_ahead_of_query'] = wrong_clock
            for name, values in mutations.items():
                log.write_text(''.join(json.dumps(row) + '\n' for row in values))
                actual = case.verify(directory, log, identity, challenge, mode)
                result['observations'].append({'mode': mode, 'mutation': name, 'oracle_status': actual['status'],
                                                'unexpectedly_accepted': actual['status'] == baseline['status']})
    # Keep a small independent control: malformed JSON is observable during CREATE
    # before the native WritePrivate completes. This is not an ArkTS engine test.
    try:
        json.loads('')
    except ValueError:
        result['ready_partial_file_control'] = 'empty CREATE-visible JSON is not parseable; inspect ETS retry contract'
    assert len(result['observations']) == 6 and all(r['unexpectedly_accepted'] for r in result['observations'])
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'synthetic_mutations_unexpectedly_accepted': len(result['observations']),
                      'guest_acceptance': False, 'closed_requirements': []}))


if __name__ == '__main__':
    main()
