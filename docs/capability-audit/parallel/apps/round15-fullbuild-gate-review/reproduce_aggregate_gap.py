#!/usr/bin/env python3
"""Run only the retained gate's aggregate branch against missing nested evidence.

This is a synthetic host counterexample, never a QEMU/runtime acceptance.
It reads commit sources and writes only beside this report.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[4]
MAIN = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
COMMIT = '43a4c43991d3a5a9fe60c50c302d10daae592f99'


def retained(name):
    return subprocess.check_output(['git', '-C', str(WORKTREE), 'show', COMMIT + ':' + name])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run():
    gate_name = 'scripts/verify_first_artifact_gate.py'
    source = retained(gate_name)
    for name in ['ci/capability-audit/release_scope.py',
                 'docs/capability-audit/native-arkts11-gap-ledger.json']:
        if (MAIN / name).read_bytes() != retained(name):
            raise ValueError('live read-only import/baseline differs from reviewed commit: ' + name)
    # Execute the actual two functions, with their actual file/ledger/import
    # context. No verification function or closed-row consumer is mocked.
    tree = ast.parse(source)
    selected = [node for node in tree.body if
                (isinstance(node, ast.FunctionDef) and node.name in ('verified_payload', 'checksum')) or
                (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                 target.id == 'REPRESENTATIVE_CHECKS' for target in node.targets))]
    if len(selected) != 3:
        raise ValueError('retained gate functions missing')
    namespace = dict(__file__=str(MAIN / gate_name), json=json, Path=Path,
                     hashlib=hashlib, sys=sys)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(MAIN / gate_name), 'exec'), namespace)
    sys.path.insert(0, str(MAIN / 'ci/capability-audit'))
    from release_scope import SCOPE, exclusion_record
    baseline_path = MAIN / 'docs/capability-audit/native-arkts11-gap-ledger.json'
    baseline = json.loads(baseline_path.read_text())['devices']['phone']
    expected = {'native:' + row['syscap'] + ':' + row['library'] for row in baseline['native_abi_gaps']}
    expected |= {'arkts_load:' + row['module'] for row in baseline['arkts11_module_load_gaps']}
    expected |= {'arkts_export:' + row['module'] + ':' + value['name']
                 for row in baseline['arkts11_runtime_export_gaps'] for value in row['missing']}
    expected |= {'const_enum:' + row['module'] + ':' + value['name']
                 for row in baseline['arkts11_compiled_constant_enum_contracts'] for value in row['contracts']}
    expected |= {'permission:' + row['permission'] for row in baseline['permission_registry_gaps']}
    expected |= {'behavior:' + row['id'] for row in baseline['runtime_behavior_gaps']}
    original_count = len(expected)
    exclusions = exclusion_record('phone', expected)
    expected -= set(exclusions['ids'])
    missing = HERE / 'not-present-old-guest-evidence.json'
    if missing.exists() or missing.is_symlink():
        raise ValueError('counterexample nested evidence must actually be absent')
    environment = dict(device_type='phone', guest_arch='arm64', target='127.0.0.1:47001',
                       boot_id='11111111-1111-1111-1111-111111111111')
    identity = dict(sha256='1' * 64)
    payload = dict(schema_version=2, scope=SCOPE, status='pass',
                   archive_sha256=identity['sha256'], boot_id=environment['boot_id'],
                   original_expected_count=original_count, release_exclusions=exclusions,
                   excluded=['ArkTS Static', 'CloudSync', 'imageGeneration'], unresolved=[],
                   expected_count=len(expected), closed_count=len(expected),
                   audit_baseline_sha256=sha(baseline_path.read_bytes()),
                   closed={identifier: dict(evidence=str(missing), sha256='0' * 64,
                       verifier='intentionally_missing_old_guest_proof') for identifier in sorted(expected)})
    payload_path = HERE / 'synthetic-aggregate.json'
    payload_path.write_text(json.dumps(payload, indent=2) + '\n')
    accepted = namespace['verified_payload']('cxx-arkts11-gaps', payload_path, identity, environment)
    payload_path.unlink()
    cases = ('empty', 'udmf', 'pasteboard', 'avplayer', 'udmf-pasteboard',
             'pasteboard-udmf', 'avplayer-udmf', 'udmf-avplayer')
    library = dict(status='pass', candidate_inputs=[], target=environment['target'], arch='arm64', device='phone',
                   archive_sha256='2' * 64, boot_id='22222222-2222-2222-2222-222222222222',
                   archive_binding='not_attested_by_this_diagnostic_runner',
                   results=[dict(case=case, repeat=repeat, guest_exit_code=0)
                            for case in cases for repeat in range(3)])
    payload_path.write_text(json.dumps(library, indent=2) + '\n')
    library_accepted = namespace['verified_payload']('issue20-library-exit', payload_path, identity, environment)
    payload_path.unlink()
    result = dict(scope='synthetic_host_counterexample_NOT_runtime_NOT_full_gate_bypass',
                  reviewed_commit=COMMIT, gate_source_sha256=sha(source),
                  actual_function='verify_first_artifact_gate.verified_payload',
                  branch='cxx-arkts11-gaps', nested_evidence_exists=missing.exists(),
                  nested_evidence_sha256='0' * 64, aggregate_accepted=accepted == payload,
                  accepted_closed_count=len(accepted['closed']),
                  library_exit_wrong_archive_and_boot_accepted=library_accepted == library,
                  library_exit_expected=dict(archive_sha256=identity['sha256'], boot_id=environment['boot_id']),
                  library_exit_supplied={key: library[key] for key in ('archive_sha256', 'boot_id', 'archive_binding')},
                  limitation='Other required family checks were not exercised or bypassed.')
    (HERE / 'counterexample-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
