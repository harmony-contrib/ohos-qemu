"""Check real ordinary-app statistics deltas, not zero-success API replies."""
import argparse
import json
from pathlib import Path
import re

from storage_stats_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Storage run nonce required')
    rows = [json.loads(line) for line in text.splitlines()]
    expected = [name + '.' + str(generation) for generation in range(2)
                for name in ('before', 'written', 'occupied', 'restored')]
    expected += ['other-bundle-denial', 'summary']
    if len(rows) != len(expected):
        raise ValueError('both actual write/delete generations and permission boundary required')
    for row, name in zip(rows, expected):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or
                any(type(value) is not int or value < 0 or value > 2**53 - 1 for value in row['values'])):
            raise ValueError('Storage observation is malformed, stale, reordered or failed')
    for generation in range(2):
        before, written, occupied, restored = (row['values'] for row in rows[generation * 4:generation * 4 + 4])
        data_bytes, cache_bytes = (generation + 1) * 4 * 1024**2, (generation + 1) * 2 * 1024**2
        if written != [data_bytes, cache_bytes]:
            raise ValueError('actual private file lengths do not match the owned writes')
        if any(len(values) != 3 or values[0] <= 0 for values in (before, occupied, restored)):
            raise ValueError('real installed-app and separate data/cache statistics required')
        # dataSize excludes installation files, not cache files. The pinned
        # Installd GetBundleStats uses UID quota for local data and separately
        # reports cache as a subset; do not double-count or subtract it here.
        for index, byte_count in ((1, cache_bytes), (2, data_bytes + cache_bytes)):
            if not byte_count <= occupied[index] - before[index] <= byte_count + 262144:
                raise ValueError('statistics did not account for the actual file writes')
            if (not byte_count - 65536 <= occupied[index] - restored[index] <= byte_count + 262144 or
                    abs(restored[index] - before[index]) > 262144):
                raise ValueError('statistics did not release the actual deleted file usage')
    if rows[-2]['values'] != [202] or rows[-1]['values'] != [1, 1]:
        raise ValueError('ordinary caller isolation and owned-file cleanup must remain enforced')
    return {'closed': [], 'generations': 2, 'promise_and_callback': True,
        'data_cache_growth_and_release': True, 'cache_is_subset_of_data': True, 'other_bundle_denial': 202,
        'not_claimed': 'kernel_quota_limits_privileged_Storage_APIs_or_complete_gap_closure'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch,
        'archive_sha256': digest(args.archive), 'results_sha256': digest(args.results),
        'application_identity_sha256': digest(args.application_identity),
        'compiled_inputs_sha256': digest(args.inputs), 'verifier_sha256': digest(Path(__file__)),
        'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'failures': report['failures']}))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
