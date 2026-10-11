"""Replay exact typed factory calls plus native scroll/layout/paint, not aliases."""
import argparse
import json
from pathlib import Path
import re

from arkui_components_contract import CONTRACTS, SCOPE, verify_inputs
from arkui_components_ui import verify_actions
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('actual component probe nonce required')
    rows = [json.loads(line) for line in text.splitlines()]
    keys = {'runId', 'name', 'phase', 'chained', 'values', 'error'}
    phase = 0
    events = []
    modifiers = set()
    scroll_requested = scroll_received = False
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or set(row) != keys or row['runId'] != run_id or
                type(row['name']) is not str or type(row['phase']) is not int or
                row['chained'] is not True or row['error'] != '' or not isinstance(row['values'], list) or
                any(type(v) is not int for v in row['values'])):
            raise ValueError('actual component factory failed or returned a malformed/foreign result')
        name, values = row['name'], row['values']
        if index == 0:
            if name != 'ready' or row['phase'] != 0 or values:
                raise ValueError('actual ordinary component caller initial state missing')
            continue
        if name == 'ready.row' and phase == 0:
            phase = 1
            if values: raise ValueError('unexpected row-start payload')
        elif name == 'switch.column' and phase == 1:
            if len(events) != 1 or values != [1] or not scroll_received:
                raise ValueError('real scroll/child click must precede the native layout switch')
            phase = 2
        elif name.startswith('modifier.'):
            if name not in ('modifier.arc-list', 'modifier.arc-item', 'modifier.arc-bar', 'modifier.dynamic') or values:
                raise ValueError('unknown typed native component attribute factory')
            if phase == 1: modifiers.add(name)
        elif name == 'arc.index':
            if (phase == 0 or len(values) != 3 or not 0 <= values[0] <= values[2] <= values[1] <= 7):
                raise ValueError('invalid actual ArcList scroll callback indices')
            if scroll_requested and values[2] == 7: scroll_received = True
        elif name == 'scroll.request':
            if phase != 1 or values or scroll_requested:
                raise ValueError('only one actual foreground ArcList scroll request required')
            scroll_requested = True
        elif name == 'child.clicked':
            expected = len(events) + 1
            if (phase != expected or len(values) != 3 or values[0] != expected or
                    min(values[1:]) <= 0 or values[1] == values[2] or
                    (events and events[0]['values'][1:] != values[1:])):
                raise ValueError('real child state or native frame identities changed across layout switch')
            events.append(row)
        else:
            raise ValueError('unknown/duplicate actual component lifecycle marker')
        if row['phase'] != phase:
            raise ValueError('actual component callback escaped its native phase')
    if (phase != 2 or len(events) != 2 or not scroll_received or modifiers !=
            {'modifier.arc-list', 'modifier.arc-item', 'modifier.arc-bar', 'modifier.dynamic'}):
        raise ValueError('complete actual typed factories/scroll/preserved-child lifecycle missing')
    return dict(closed=CONTRACTS, scope=SCOPE, typed_native_factories=4, actual_Arc_scroll_to_last=True,
        child_state_and_native_frame_ids_preserved=True,
        resolution='SDK_component_factory_returned_attributes_and_Instance_type_NOT_constructor_shims',
        not_claimed='standalone_global_Instance_values_all_ArkUI_components_or_digital_crown_hardware')


def verify_evidence(document, archive_sha, boot_id, arch, device=None, target=None):
    if (document.get('status') != 'pass' or document.get('persona') != 'arkui-components' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False or
            (device is not None and document.get('device') != device) or
            (target is not None and document.get('target') != target)):
        raise ValueError('actual component proof belongs to another archive/boot/profile/ABI')
    result = Path(document.get('result', ''))
    if not result.is_absolute() or result.name != 'verified-result.json':
        raise ValueError('explicit actual component verification required')
    root = result.parent
    files = dict(result=result, raw_results=root / 'results.log',
        ordinary_identity=root / 'application-identity.json', hap=root / 'ordinary-probe-signed.hap',
        compiled_contract_inputs=root / 'project/arkui-components-probe-inputs.json',
        arkui_components_actions=root / 'arkui-components-actions.json')
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual component evidence changed: ' + key)
    value = json.loads(result.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('arch') != arch or
            value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(__file__))):
        raise ValueError('component verifier summary is stale or from another run')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs'), ('actions_sha256', 'arkui_components_actions')):
        if value.get(field) != digest(files[key]):
            raise ValueError('component verifier did not consume exact captured observations')
    verify_inputs(json.loads(files['compiled_contract_inputs'].read_text()), document['run_id'], arch)
    identity = files['ordinary_identity'].read_text()
    actual = verify(files['raw_results'].read_text(), document['run_id'], identity)
    actual['actual_UI'] = verify_actions(json.loads(files['arkui_components_actions'].read_text()),
                                         document['run_id'], files['raw_results'].read_text())
    if actual != value.get('result') or require_normal_identity(identity) != document.get('ordinary_uid'):
        raise ValueError('component summary differs from typed/native/ordinary/UI evidence')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'actions', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch, archive_sha256=digest(args.archive),
        results_sha256=digest(args.results), application_identity_sha256=digest(args.application_identity),
        compiled_inputs_sha256=digest(args.inputs), actions_sha256=digest(args.actions),
        verifier_sha256=digest(Path(__file__)), first_artifact_behavior_gate_passed=False, failures=[])
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['result']['actual_UI'] = verify_actions(json.loads(args.actions.read_text()), args.run_id,
                                                     args.results.read_text())
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], failures=report['failures'])))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__': raise SystemExit(main())
