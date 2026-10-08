"""Two actual factory-returned classes; no constructor/provider exemption."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from binding_contract import ROOT, SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh actual binding-factory nonce required')
    rows = [json.loads(line) for line in text.splitlines()]
    expected = []
    for generation in range(2):
        seed = int(run_id[:4], 16) + generation * 100
        for step in range(33):
            value = seed + (step if step % 2 == 0 else -step)
            expected.append(('number.' + str(generation) + '.' + str(step),
                [value, value, -seed, value, step + 1], [True, True, True]))
        expected.append(('object.' + str(generation), [seed + 1, seed + 1, seed], [True] * 4))
    expected += [('getter.exception', [], [True]), ('setter.exception', [17, 17], [True]),
        ('setter.recovery', [31, 31], [True]), ('summary', [68, 3], [True])]
    if len(rows) != len(expected):
        raise ValueError('all two-generation values and original exception/recovery cases required')
    for row, (name, values, checks) in zip(rows, expected):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'checks', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['values'] != values or
                any(type(value) is not int for value in row['values']) or row['checks'] != checks or
                any(type(value) is not bool for value in row['checks']) or row['error'] != ''):
            raise ValueError('actual typed binding values/identity/isolation/errors are missing, stale or wrong')
    return {'closed': ['arkts_export:@ohos.arkui.StateManagement:Binding',
        'arkts_export:@ohos.arkui.StateManagement:MutableBinding'],
        'factory_returned_class_contract': True, 'generations': 2, 'writes_per_generation': 33,
        'same_thrown_error_preserved': True, 'getter_and_setter_recovery': True,
        'not_claimed': 'constructors_ConnectOptions_PersistenceV2_or_UI_redraw'}


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
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


def verify_evidence(document, root, archive_sha, boot_id):
    root = Path(root)
    arch = document.get('arch')
    run_id = document.get('run_id')
    if (document.get('status') != 'pass' or document.get('persona') != 'binding' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            arch not in ('arm64', 'armv7a', 'x86_64')):
        raise ValueError('binding factories were not executed on this actual package and kernel boot')
    paths = {'result': root / 'verified-result.json', 'raw_results': root / 'results.log',
        'ordinary_identity': root / 'application-identity.json',
        'compiled_contract_inputs': root / 'project/binding-probe-inputs.json'}
    for key, path in paths.items():
        if (path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256') or
                key in ('result', 'compiled_contract_inputs') and document.get(key) != str(path)):
            raise ValueError('actual binding caller/results/ordinary identity changed or escaped')
    value = json.loads(paths['result'].read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('run_id') != run_id or
            value.get('arch') != arch or value.get('archive_sha256') != archive_sha or
            value.get('verifier_sha256') != digest(Path(__file__)) or
            value.get('results_sha256') != digest(paths['raw_results']) or
            value.get('application_identity_sha256') != digest(paths['ordinary_identity']) or
            value.get('compiled_inputs_sha256') != digest(paths['compiled_contract_inputs'])):
        raise ValueError('binding verification lacks unchanged original inputs and current verifier')
    inputs = json.loads(paths['compiled_contract_inputs'].read_text())
    if inputs.get('generated_source') != str(root / 'project/entry/src/main/ets/pages/Index.ets'):
        raise ValueError('binding source escaped the actual fresh compiled caller project')
    verify_inputs(inputs, run_id, arch)
    result = verify(paths['raw_results'].read_text(), run_id, paths['ordinary_identity'].read_text())
    if value.get('result') != result:
        raise ValueError('binding closure differs from actual original factory behavior')
    return result


if __name__ == '__main__': raise SystemExit(main())
