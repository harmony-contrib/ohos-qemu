"""Strict actual density/breakpoint instances; no other ArkUI closure inferred."""
import argparse
import json
import math
from pathlib import Path
import re

from observer_info_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

CONTRACTS = ['arkts_export:@ohos.arkui.observer:DensityInfo',
             'arkts_export:@ohos.arkui.observer:WindowSizeLayoutBreakpointInfo']


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh observer info run required')
    rows = [json.loads(line) for line in text.splitlines()]
    keys = {'runId', 'name', 'listener', 'generation', 'phase', 'step', 'target', 'density',
            'width', 'height', 'instance', 'contextMatches', 'counts', 'error'}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != keys or row['runId'] != run_id or
                any(type(row[k]) is not str for k in ('name', 'listener', 'error')) or row['error'] != '' or
                any(type(row[k]) is not int for k in ('generation', 'phase', 'step', 'width', 'height')) or
                any(type(row[k]) not in (int, float) or not math.isfinite(row[k])
                    for k in ('target', 'density')) or row['instance'] is not True or
                row['contextMatches'] is not True or not isinstance(row['counts'], list) or
                len(row['counts']) != 4 or any(type(v) is not int or v < 0 for v in row['counts'])):
            raise ValueError('malformed, failed, stale or incomplete observer info record')
    cursor = 0
    counts = [0, 0, 0, 0]
    target = 0
    original_density = 0

    def take(name, generation, phase, step):
        nonlocal cursor
        if cursor >= len(rows):
            raise ValueError('incomplete observer info lifecycle: ' + name)
        row = rows[cursor]
        if (row['name'] != name or row['generation'] != generation or row['phase'] != phase or
                row['step'] != step or row['counts'] != counts or row['listener'] != ''):
            raise ValueError('wrong observer info phase, count or marker: ' + name)
        cursor += 1
        return row

    def marker(name, generation, phase, step, initial=False):
        row = take(name, generation, phase, step)
        if (row['density'] != 0 or row['width'] != -1 or row['height'] != -1 or
                (not initial and row['target'] != target)):
            raise ValueError('wrong observer info marker payload')
        return row

    marker('density.constructor', 0, 0, 0)
    marker('breakpoint.constructor', 0, 0, 0)
    for generation in range(2):
        counts = [0, 0, 0, 0]
        registered = marker('registered', generation, 0, 0, initial=generation == 0)
        if generation == 0:
            target = registered['target']
            original_density = target
            if not 0 < target <= 4:
                raise ValueError('actual initial app-window density missing')
        widths = []
        for step, phase in ((0, 0), (1, 0), (2, 1), (3, 2)):
            if phase == 1:
                marker('first-removed', generation, phase, step)
            if phase == 2:
                marker('all-removed', generation, phase, step)
            target = 4 if target == 0.5 else 0.5
            marker('change', generation, phase, step)
            events = []
            while cursor < len(rows) and rows[cursor]['name'] in ('density', 'breakpoint'):
                row = rows[cursor]
                if (phase == 2 or row['generation'] != generation or row['phase'] != phase or
                        row['step'] != step or row['target'] != target or
                        row['listener'] not in (('a', 'b') if phase == 0 else ('b',))):
                    raise ValueError('observer callback continued after removal or belongs to another change')
                slot = (0 if row['listener'] == 'a' else 1) + (2 if row['name'] == 'breakpoint' else 0)
                counts[slot] += 1
                if row['counts'] != counts:
                    raise ValueError('observer callback counters are inconsistent')
                if row['name'] == 'density':
                    if row['density'] != target or row['width'] != -1 or row['height'] != -1:
                        raise ValueError('density callback did not reflect the real window change')
                elif row['density'] != 0 or row['width'] not in range(6) or row['height'] not in range(3):
                    raise ValueError('invalid actual window breakpoint fields')
                events.append(row)
                cursor += 1
            settled = take('settled', generation, phase, step)
            if (settled['target'] != target or settled['density'] != target or
                    settled['width'] not in range(6) or settled['height'] not in range(3)):
                raise ValueError('actual app window did not settle at the requested density/breakpoint')
            widths.append(settled['width'])
            if phase < 2:
                for kind in ('density', 'breakpoint'):
                    for listener in (('a', 'b') if phase == 0 else ('b',)):
                        selected = [row for row in events if row['name'] == kind and row['listener'] == listener]
                        if not selected:
                            raise ValueError('real density/breakpoint change callback missing')
                        if kind == 'breakpoint' and any(
                                (row['width'], row['height']) != (settled['width'], settled['height'])
                                for row in selected):
                            raise ValueError('breakpoint callback differs from actual UIContext getters')
                    if phase == 0:
                        fields = ('density', 'width', 'height')
                        a = [tuple(row[k] for k in fields) for row in events
                             if row['name'] == kind and row['listener'] == 'a']
                        b = [tuple(row[k] for k in fields) for row in events
                             if row['name'] == kind and row['listener'] == 'b']
                        if a != b:
                            raise ValueError('two observers disagree on real window changes')
            if step and widths[step] == widths[step - 1]:
                raise ValueError('density changes did not exercise an actual width breakpoint boundary')
    restored = take('restored', 2, 2, 3)
    if (restored['target'] != target or restored['density'] != original_density or
            restored['width'] not in range(6) or restored['height'] not in range(3)):
        raise ValueError('own app-window density was not restored after removing observers')
    marker('summary', 2, 2, 3)
    if cursor != len(rows):
        raise ValueError('unexpected observer callbacks after completion')
    return dict(closed=CONTRACTS, scope=SCOPE, generations=2, real_density_changes=8,
        callback_specific_removal=True, all_callbacks_removed=True,
        not_claimed='all_observer_ArkUI_APIs_or_other_windows')


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('persona') != 'observer-info' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('observer info evidence must belong to this actual package/boot/architecture')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit observer info result required')
    root = result_path.parent
    files = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/observer-info-probe-inputs.json'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual observer info evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('arch') != arch or
            value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(__file__))):
        raise ValueError('observer info summary is stale or belongs to another run')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs')):
        if value.get(field) != digest(files[key]):
            raise ValueError('observer info verifier did not consume captured evidence')
    verify_inputs(json.loads(files['compiled_contract_inputs'].read_text()), document['run_id'], arch)
    identity = files['ordinary_identity'].read_text()
    actual = verify(files['raw_results'].read_text(), document['run_id'], identity)
    if actual != value.get('result') or require_normal_identity(identity) != document.get('ordinary_uid'):
        raise ValueError('observer info summary differs from raw ordinary-app observations')
    return actual


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch,
        archive_sha256=digest(args.archive), results_sha256=digest(args.results),
        application_identity_sha256=digest(args.application_identity), compiled_inputs_sha256=digest(args.inputs),
        verifier_sha256=digest(Path(__file__)), first_artifact_behavior_gate_passed=False, failures=[])
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if report['status'] == 'pass' else 1)
