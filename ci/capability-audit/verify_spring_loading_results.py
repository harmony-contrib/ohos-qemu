"""Strict package-bound real-input class/state proof, never inferred from exports."""
import argparse
import json
import math
from pathlib import Path
import re

from run_normal_hap_probe import require_normal_identity
from spring_loading_contract import SCOPE, verify_inputs
from spring_loading_input import verify_actions
from run_root_probe import digest

CONTRACTS = ['arkts_export:@ohos.arkui.dragController:SpringLoadingContext']


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh spring-loading nonce required')
    rows = [json.loads(line) for line in text.splitlines()]
    keys = {'runId', 'name', 'generation', 'state', 'sequence', 'instance', 'config',
            'summarySize', 'count', 'time', 'error', 'infosOmitted'}
    previous_time = 0
    for row in rows:
        if (not isinstance(row, dict) or set(row) != keys or row['runId'] != run_id or
                type(row['name']) is not str or row['error'] != '' or row['instance'] is not True or
                type(row['infosOmitted']) is not bool or
                any(type(row[k]) is not int for k in ('generation', 'state', 'sequence', 'count', 'time')) or
                row['time'] < previous_time or row['time'] <= 0 or
                type(row['summarySize']) not in (int, float) or not math.isfinite(row['summarySize']) or
                not isinstance(row['config'], list) or
                any(type(v) is not int for v in row['config'])):
            raise ValueError('failed, malformed, stale or out-of-order spring-loading observation')
        previous_time = row['time']
    if (not rows or rows[0]['name'] != 'constructor' or rows[0]['generation'] != 0 or
            any(rows[0][key] != -1 for key in ('state', 'sequence', 'summarySize')) or
            rows[0]['count'] != 0 or rows[0]['config'] or rows[0]['infosOmitted']):
        raise ValueError('actual independent public constructors and native methods missing')
    cursor = 1
    for generation, mode in ((1, 1), (2, 2), (3, 1), (4, 3)):
        selected = []
        while cursor < len(rows) and rows[cursor]['generation'] == generation:
            selected.append(rows[cursor]); cursor += 1
        if not selected or selected[0]['name'] != 'ready.' + str(mode):
            raise ValueError('actual four input generations and abort re-entry are required')
        current_count = 0
        callbacks = []
        actions = []
        quiet = []
        started = ended = False
        quiet_seen = False
        for index, row in enumerate(selected):
            name = row['name']
            if name == 'callback':
                if not started or quiet_seen or (ended and row['state'] != 3):
                    raise ValueError('callback occurred outside an active physical drag')
                current_count += 1
                callbacks.append(row)
            elif name in ('begin.updated', 'outside-begin.ignored', 'abort.called'):
                if not callbacks or index == 0 or selected[index - 1]['name'] != 'callback':
                    raise ValueError('context method result did not follow its real callback')
                actual = callbacks[-1]
                if any(row[key] != actual[key] for key in ('state', 'sequence', 'summarySize', 'infosOmitted')):
                    raise ValueError('context action belongs to another native callback')
                actions.append(row)
            else:
                if (row['state'] != -1 or row['sequence'] != -1 or row['config'] or
                        row['summarySize'] != -1 or row['infosOmitted']):
                    raise ValueError('unexpected payload in spring lifecycle marker')
                if name == 'drag.started':
                    if started or ended or current_count:
                        raise ValueError('duplicate or late real drag start')
                    started = True
                elif name == 'drag.ended':
                    if not started or ended or quiet_seen:
                        raise ValueError('duplicate or invalid drag end')
                    ended = True
                elif name == 'drop':
                    if not started or quiet_seen:
                        raise ValueError('drop outside a real drag')
                elif name in ('quiet.begin', 'quiet.end'):
                    if not ended:
                        raise ValueError('quiet interval started before physical release')
                    quiet_seen = True; quiet.append(row)
                elif index != 0 or name != 'ready.' + str(mode):
                    raise ValueError('unknown or repeated spring-loading marker')
            if row['count'] != current_count:
                raise ValueError('actual callback counter changed outside native dispatch')
        expected_states = [0, 1, 1, 2] if mode == 1 else ([0] if mode == 2 else [0, 3])
        if ([row['state'] for row in callbacks] != expected_states or
                [row['sequence'] for row in callbacks] != list(range(len(expected_states))) or
                not started or not ended or [row['name'] for row in quiet] != ['quiet.begin', 'quiet.end'] or
                quiet[1]['time'] - quiet[0]['time'] < 1500 or selected[-1] is not quiet[1]):
            raise ValueError('normal/aborted/cancelled hover sequence or quiet cleanup did not match SDK')
        initial_config = [150, 10000 if mode == 3 else 100, 2, 100]
        for index, row in enumerate(callbacks):
            expected_config = [] if row['state'] == 3 else (
                [150, 200, 2, 200] if mode == 1 and index > 0 else initial_config)
            if (row['config'] != expected_config or row['infosOmitted'] != (row['state'] == 3) or
                    (row['summarySize'] != -1 if row['state'] == 3 else not row['summarySize'] > 0)):
                raise ValueError('real configuration, drag data, or CANCEL omission violates SDK')
        expected_actions = (['begin.updated'] + ['outside-begin.ignored'] * 3 if mode == 1 else
                            (['abort.called'] if mode == 2 else ['outside-begin.ignored']))
        if [row['name'] for row in actions] != expected_actions:
            raise ValueError('real BEGIN update/other-state no-op/abort action missing')
        for action in actions:
            expected_config = [] if action['state'] == 3 else (
                [150, 200, 2, 200] if mode == 1 else initial_config)
            if action['config'] != expected_config:
                raise ValueError('context method changed configuration outside BEGIN or did not update BEGIN')
    if cursor != len(rows):
        raise ValueError('unexpected extra generation or late spring callback')
    return dict(closed=CONTRACTS, scope=SCOPE, generations=4, native_callbacks=11,
        abort_without_CANCEL=True, reentry_after_abort=True, cancelled_data_omitted=True,
        config_updates_only_BEGIN=True, not_claimed='full_drag_MSDP_or_cross_app_UDMF_backend')


def verify_evidence(document, archive_sha, boot_id, arch, device=None, target=None):
    if (document.get('status') != 'pass' or document.get('persona') != 'spring-loading' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False or
            (device is not None and document.get('device') != device) or
            (target is not None and document.get('target') != target)):
        raise ValueError('spring proof must belong to this actual package/boot/architecture')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit actual spring verification required')
    root = result_path.parent
    files = dict(result=result_path, raw_results=root / 'results.log',
        ordinary_identity=root / 'application-identity.json', hap=root / 'ordinary-probe-signed.hap',
        compiled_contract_inputs=root / 'project/spring-loading-probe-inputs.json',
        spring_loading_actions=root / 'pointer/actions.json')
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual spring evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('boot_id') != boot_id or
            value.get('arch') != arch or value.get('device') != document.get('device') or
            value.get('target') != document.get('target') or value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(__file__))):
        raise ValueError('spring verification is stale or belongs to another ordinary caller')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs'), ('actions_sha256', 'spring_loading_actions')):
        if value.get(field) != digest(files[key]):
            raise ValueError('spring verifier did not consume the captured input/ordinary result')
    verify_inputs(json.loads(files['compiled_contract_inputs'].read_text()), document['run_id'], arch)
    identity, text = files['ordinary_identity'].read_text(), files['raw_results'].read_text()
    actual = verify(text, document['run_id'], identity)
    actual['physical_input'] = verify_actions(json.loads(files['spring_loading_actions'].read_text()), text,
        document['run_id'], archive_sha, boot_id, arch, document['device'], document['target'])
    if actual != value.get('result') or require_normal_identity(identity) != document.get('ordinary_uid'):
        raise ValueError('spring summary differs from actual ordinary/native/physical observations')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'actions', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch, device=args.device,
        target=args.target, boot_id=args.boot_id, archive_sha256=digest(args.archive),
        results_sha256=digest(args.results), application_identity_sha256=digest(args.application_identity),
        compiled_inputs_sha256=digest(args.inputs), actions_sha256=digest(args.actions),
        verifier_sha256=digest(Path(__file__)), first_artifact_behavior_gate_passed=False, failures=[])
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        text = args.results.read_text()
        report['result'] = verify(text, args.run_id, args.application_identity.read_text())
        report['result']['physical_input'] = verify_actions(json.loads(args.actions.read_text()), text,
            args.run_id, report['archive_sha256'], args.boot_id, args.arch, args.device, args.target)
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], failures=report['failures'])))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
