"""Verify real ordinary-app metadata calls, never infer positive asset closure."""
import argparse
import json
import math
from pathlib import Path
import re

from photos_recent_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Photos nonce required')
    rows = [json.loads(line) for line in text.splitlines()]
    expected = [name + '.' + str(cycle) + suffix for cycle in (1, 2)
                for name, suffix in [('default-album', ''), ('recent', '.0'), ('recent', '.1'),
                                     ('options-unmodified', ''), ('picker.invalid-count', '')]] + ['summary']
    if len(rows) != len(expected):
        raise ValueError('both full metadata generations are required')
    for index, (row, name) in enumerate(zip(rows, expected)):
        if (set(row) != {'runId', 'sequence', 'name', 'pass', 'value'} or
                row['runId'] != run_id or type(row['sequence']) is not int or row['sequence'] != index + 1 or
                row['name'] != name or row['pass'] is not True or not isinstance(row['value'], str)):
            raise ValueError('missing, failed or stale Photos observation')
        value = row['value']
        if name.startswith('recent.'):
            info = json.loads(value)
            stamp = info.get('dateTaken')
            if (type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 or
                    not isinstance(info.get('identifier'), str) or not info['identifier']):
                raise ValueError('Photos provider returned failure sentinel or invalid metadata')
        elif name.startswith('default-album.') and not value.strip():
            raise ValueError('actual localized default album name required')
        elif name.startswith('options-unmodified.') and value != '{}':
            raise ValueError('caller-owned reused options changed')
        elif name.startswith('picker.invalid-count.') and json.loads(value).get('code') != 401:
            raise ValueError('actual public parameter error code required')
        elif name == 'summary' and value != 'metadata-defaults-reused-options-and-parameter-rejection-only':
            raise ValueError('metadata scope changed')
    return {'generations': 2, 'observations': len(rows), 'closed': [],
        'not_claimed': ['positive recent asset retrieval', 'picker selection or cancellation', 'FA card', 'cloud provider']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'archive_sha256': digest(args.archive),
        'arch': args.arch, 'run_id': args.run_id, 'results_sha256': digest(args.results),
        'application_identity_sha256': digest(args.application_identity),
        'compiled_inputs_sha256': digest(args.inputs), 'verifier_sha256': digest(Path(__file__)),
        'failures': [], 'first_artifact_behavior_gate_passed': False}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
