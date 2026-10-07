#!/usr/bin/env python3
"""Require challenged ordinary-app public AudioSuite DSP PCM and full lifecycle."""
import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from verify_audio_stream_results import application_identity, sha256

FREQUENCIES = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
PREFIX = [('is_supported', 0), ('supported_value', 1), ('engine_create', 0), ('pipeline_create', 0)]
BUILDER = [('builder_create', 0), ('builder_type', 0), ('builder_format', 0)]
NODE_END = [('node_create', 0), ('builder_destroy', 0)]
SUFFIX = [('connect_source', 0), ('connect_destination', 0), ('render_before_start', 2), ('pipeline_start', 0),
          ('@signal', None), ('pipeline_stop', 0), ('disconnect_source', 0), ('disconnect_destination', 0),
          ('destroy_source', 0), ('destroy_effect', 0), ('destroy_destination', 0), ('pipeline_destroy', 0), ('engine_destroy', 0)]


def sequence(test):
    # Effect nodes inherit the pipeline format and forbid an explicit format.
    nodes = (BUILDER + [('input_callback', 0)] + NODE_END +
             BUILDER[:2] + NODE_END + BUILDER + NODE_END)
    if test < 10:
        params = [('eq_set', 0), ('eq_get', 0), ('eq_params', 0), ('eq_invalid_gain', 1),
                  ('eq_get_after_reject', 0), ('eq_reject_preserves_gain', 6)]
    elif test < 14:
        params = [('field_set', 0), ('field_get', 0), ('field_params', test - 9)]
    else:
        params = [('environment_set', 0), ('environment_get', 0), ('environment_params', test - 13)]
    return PREFIX + nodes + params + SUFFIX


@lru_cache(maxsize=128)
def expected_energy(phase, frequency):
    return sum(int(2000 * math.sin(phase + 2 * math.pi * frequency * frame / 48000)) ** 2
               for frame in range(48000, 96000))


def signal(row, run, test):
    expected_phase = (int(run[:8], 16) % 10000) / 10000
    frequency = FREQUENCIES[test] if test < 10 else 1000 if test < 14 else 12000
    numeric = ('frequency', 'phase', 'left_input_energy', 'right_input_energy',
               'left_output_energy', 'right_output_energy', 'left_dB', 'right_dB')
    if (row.get('type') != 'signal' or any(type(row.get(key)) not in (int, float) or
            not math.isfinite(row[key]) for key in numeric) or row['frequency'] != frequency or
            abs(row['phase'] - expected_phase) > 1e-10 or row.get('finished') is not True or
            type(row.get('input_bytes')) is not int or row['input_bytes'] != 384000 or
            type(row.get('consumed_bytes')) is not int or row['consumed_bytes'] != 384000 or
            type(row.get('output_bytes')) is not int or not 384000 <= row['output_bytes'] <= 387840 or
            row['output_bytes'] % 4 != 0 or type(row.get('callbacks')) is not int or
            not 1 <= row['callbacks'] <= 1000 or type(row.get('bad_callbacks')) is not int or row['bad_callbacks'] != 0):
        raise ValueError('bad actual PCM/challenge/lifecycle signal record')
    for channel in ('left', 'right'):
        before, after = row[channel + '_input_energy'], row[channel + '_output_energy']
        # Independent challenged waveform, not a self-reported nominal gain.
        challenged = expected_energy(expected_phase, frequency)
        if before <= 0 or after <= 0 or abs(before - challenged) / challenged > .002:
            raise ValueError('PCM input challenge/energy mismatch')
        actual = 10 * math.log10(after / before)
        if abs(actual - row[channel + '_dB']) > 1e-6:
            raise ValueError('gain does not match actual PCM energy')
        if test < 10 and abs(actual - 6) >= .15:
            raise ValueError('actual equalizer band response failed')
        if 10 <= test < 14 and abs(actual - 20 * math.log10((.5, 2.25, 1, 1.75)[test - 10])) >= .15:
            raise ValueError('actual stereo sound-field response failed')
        if test >= 14 and not -100 < actual < -12:
            raise ValueError('actual environment filter response failed')


def verify(text, run, identity):
    if not isinstance(run, str) or re.fullmatch('[0-9a-f]{32}', run) is None:
        raise ValueError('explicit fresh DSP run challenge required')
    uid = application_identity(identity)
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    count = 3 + 2 * sum(len(sequence(test)) for test in range(18))
    if len(rows) != count or any(not isinstance(row, dict) or row.get('run_id') != run for row in rows):
        raise ValueError('incomplete, stale or mixed DSP evidence')
    first, last = rows[0], rows[-1]
    if (first.get('type') != 'identity' or type(first.get('uid')) is not int or first['uid'] != uid or
            type(first.get('euid')) is not int or first['euid'] != uid):
        raise ValueError('DSP native identity differs from ordinary HAP')
    if (last.get('type') != 'summary' or last.get('passed') is not True or type(last.get('cycles')) is not int or
            last['cycles'] != 2 or type(last.get('pipelines')) is not int or last['pipelines'] != 36 or
            last.get('scope') != 'public_AudioSuite_three_DSP_effects_not_AI_or_download'):
        raise ValueError('DSP summary failed')
    boundary = rows[1]
    if boundary != {'type': 'step', 'run_id': run, 'cycle': 0, 'test': -1, 'name': 'null_create',
                    'actual': 1, 'expected': 1, 'passed': True} or any(type(boundary.get(key)) is not int
                            for key in ('cycle', 'test', 'actual', 'expected')):
        raise ValueError('DSP null boundary failed')
    index = 2
    for cycle in (1, 2):
        for test in range(18):
            for name, expected in sequence(test):
                row = rows[index]
                index += 1
                if (type(row.get('cycle')) is not int or row['cycle'] != cycle or
                        type(row.get('test')) is not int or row['test'] != test or row.get('passed') is not True):
                    raise ValueError('failed or out-of-order DSP cycle')
                if name == '@signal':
                    signal(row, run, test)
                elif (row.get('type') != 'step' or row.get('name') != name or
                      type(row.get('actual')) is not int or row['actual'] != expected or
                      type(row.get('expected')) is not int or row['expected'] != expected):
                    raise ValueError('unexpected DSP public API lifecycle/boundary result')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--application-identity', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'status': 'fail', 'scope': 'normal-app public AudioSuite three DSP effects only',
                'run_id': args.run_id, 'archive': str(args.archive.resolve()), 'failures': [],
                'first_artifact_behavior_gate_passed': False, 'AI_or_download_validated': False}
    try:
        evidence['archive_sha256'] = sha256(args.archive)
        evidence['results_sha256'] = sha256(args.results)
        evidence['identity_sha256'] = sha256(args.application_identity)
        evidence['records'] = len(verify(args.results.read_text(), args.run_id, args.application_identity.read_text()))
        evidence['status'] = 'pass'
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        evidence['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
