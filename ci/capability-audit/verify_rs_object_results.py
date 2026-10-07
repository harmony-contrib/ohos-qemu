"""Real packaged-helper boundaries only; not actual cross-process/UI acceptance."""
import json
import re

CASES = tuple(name for mode in ('ordinary', 'ashmem') for name in (
    *(f'{mode}_objects_fd_{size}' for size in (0, 65536, 900000)),
    f'{mode}_null_objects', f'{mode}_fd_zero', f'{mode}_cross_thread_cancel', f'{mode}_128_lifetimes'))
CASES += ('negative_count_rejected', 'oversized_count_rejected', 'wrong_version_rejected', 'trailing_sidecar_rejected')
SCOPE = 'packaged_RS_IPC_real_class_boundaries_NOT_cross_process_or_UI'


def verify(text, arch, run_id, code):
    if type(code) is not int or code != 0 or re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('real RS helper boundaries require a fresh challenge and successful process exit')
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != len(CASES) + 2 or any(not isinstance(row, dict) or row.get('run_id') != run_id for row in rows):
        raise ValueError('incomplete or stale RS helper boundary evidence')
    identity = rows[0]
    bits = {'armv7a': 32, 'arm64': 64, 'x86_64': 64}.get(arch)
    if (set(identity) != {'type', 'run_id', 'uid', 'pointer_bits', 'scope'} or identity.get('type') != 'identity' or
            type(identity.get('uid')) is not int or identity['uid'] != 0 or
            type(identity.get('pointer_bits')) is not int or identity['pointer_bits'] != bits or bits is None or
            identity.get('scope') != SCOPE):
        raise ValueError('real RS helper ABI/root/scope mismatch')
    for name, row in zip(CASES, rows[1:-1]):
        if (set(row) != {'type', 'run_id', 'name', 'passed'} or row.get('type') != 'case' or
                row.get('name') != name or row.get('passed') is not True):
            raise ValueError('failed or reordered RS helper boundary: ' + name)
    summary = rows[-1]
    if (set(summary) != {'type', 'run_id', 'cases', 'passed', 'first_artifact_behavior_gate_passed'} or
            summary.get('type') != 'summary' or type(summary.get('cases')) is not int or
            summary['cases'] != len(CASES) or summary.get('passed') is not True or
            summary.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('incorrect RS helper summary or falsely claimed full package gate')
    return {'cases': len(CASES), 'scope': SCOPE, 'results': rows,
            'cross_process_Binder_or_UI_validated': False, 'first_artifact_behavior_gate_passed': False}
