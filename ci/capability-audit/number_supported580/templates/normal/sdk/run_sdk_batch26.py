#!/usr/bin/env python3
"""Unexecuted root draft: serial fresh F SDK batch; collect safe failures.

The dispatcher holds no outer flock. Each child acquires the root lock itself,
including the unchanged Apps15 CLI. Abnormal/timeout/cleanup-uncertain stages
halt all subsequent resources; ordinary SDK compile failures are preserved and
other independent roles continue. Never signs, boots, or opens a package gate.
"""
import argparse
import json
from pathlib import Path

import sdk26_common as C
import sdk26_plan as P


def private_sources():
    manifest = C.load(C.HERE / 'source-manifest.json')
    C.require(manifest.get('schema') == 'F-SDK-batch29-source-draft/v1', 'reviewed new29 source manifest required')
    observed = {path.relative_to(C.HERE).as_posix() for path in C.HERE.rglob('*') if path.is_file()}
    C.require(observed == set(manifest['files']) | {'source-manifest.json'}, 'unknown/missing SDK draft source files')
    for name, expected in manifest['files'].items():
        path = C.HERE / name
        C.require(path.is_relative_to(C.HERE) and C.record(path) == expected, 'new SDK draft source changed: ' + name)
    for name, expected in manifest['external_inputs'].items():
        C.require(C.record(expected['path']) == expected, 'reviewed unchanged source helper changed: ' + name)
    return C.record(C.HERE / 'source-manifest.json')


def inspect_stage(stage, commit):
    value = C.load(stage['receipt'])
    C.require(value.get('source_commit') == commit, 'actual stage receipt F commit differs')
    C.require(not value.get('must_resolve_owned_SDK_processes_before_next_resource_stage'),
              'stage has unresolved owned SDK processes')
    if value.get('status') == 'input_admission_rejected':
        C.require(stage['label'] in ('audio-calendar26', 'knowledge26', 'number-local580') and
            type(value.get('exit_code')) is int and value['exit_code'] == 1 and
            value.get('sdk_started') is False and value.get('docker_started') is False and
            value.get('commands') == [], 'typed pre-resource rejection required')
        path = Path(stage['output']) / 'input-admission.json'
        C.require(value.get('input_admission') == C.record(path), 'exact actual pure-input receipt required')
        admission = C.load(path)
        C.require(admission.get('schema') == 'F-SDK-batch29-input-admission/v1' and
            admission.get('source_commit') == commit and admission.get('status') == 'input_rejected' and
            type(admission.get('exit_code')) is int and admission['exit_code'] == 1 and
            admission.get('sdk_started') is False and admission.get('docker_started') is False and
            admission.get('resource_commands_started') is False and admission.get('commands') == [] and
            admission.get('copies') == [] and admission.get('failures'),
            'complete known pre-launch input failure required; no missing journal inference')
        return value
    C.require(value.get('target') == stage['target'], 'actual completed SDK target differs from selected product/profile')
    if stage['label'] == 'number-local580':
        C.require(value.get('schema') == 'number-local580-actual-SDK/v1', 'actual Number SDK receipt schema')
        if stage['target']['device'] == '2in1':
            C.require(value.get('status') == 'not_applicable' and value.get('applicability') == 'phone_only_NO_phone_pass' and
                value.get('roles') == [] and value.get('account_controller') is None and value.get('commands') == [] and
                value.get('sdk_started') is False and value.get('exit_code') == 0,
                'exact 2in1 profile N/A; no phone SDK or runtime result')
        elif value.get('exit_code') == 0:
            C.require(value.get('signed') is False and value.get('guest_executed') is False and
                [r['role'] for r in value['roles']] == ['system-granted','system-readonly','ordinary'] and
                len(value['commands']) == 6 and all(r['exit_code'] == 0 for r in value['roles']),
                'complete three unsigned Number roles and six original SDK commands')
            account = value['account_controller']
            path = Path(account['sdk_evidence']['path'])
            C.require(C.sha(path) == account['sdk_evidence']['sha256'] and path.stat().st_size == account['sdk_evidence']['bytes'],
                'actual independent account SDK receipt')
            document = C.assert_inner_commands_complete(path)
            C.require(document.get('schema') == 'number-local580-account-SDK/v1' and
                document.get('source_commit') == commit and document.get('archive_binding') == value['archive_binding'] and
                document.get('target') == stage['target'] and document.get('exit_code') == 0 and
                document.get('failures') == [] and len(document['commands']) == 2 and
                document.get('signed') is False and document.get('guest_executed') is False and
                document.get('run') == value['run'] and document.get('driver') == value['driver'] and
                document.get('role') == {k:v for k,v in account.items() if k != 'sdk_evidence'} and
                account.get('role') == 'account' and account.get('exit_code') == 0 and
                account.get('permissions') == ['ohos.permission.MANAGE_LOCAL_ACCOUNTS',
                    'ohos.permission.GET_LOCAL_ACCOUNTS', 'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION'] and
                [r['label'] for r in document['commands']] == ['account-dependencies','account-compile'] and
                all(r['project'] == 'account' for r in document['commands']) and
                document.get('source_references') == value['source_references']['account'],
                'independent account role/source/SDK completion; no Number-role privilege merge')
    if stage['label'] in ('live-sdk39-26', 'native-strip26'):
        C.require(value.get('cleanup_verified') is True and value.get('source_freeze_verified') is True,
                  'Linux container identity/removal/source freeze must be proved before next stage')
        if stage['label'] == 'live-sdk39-26':
            C.require(value.get('requested_roles') == ['live-inputs'], 'exact fresh SDK39 role set required')
            C.assert_inner_commands_complete(stage['receipt'])
    else:
        C.assert_inner_commands_complete(stage['receipt'])
        if stage['label'] == 'apps15':
            C.require(all(row.get('owned_process_group_closed') is True and not row.get('cleanup_error')
                for row in value['commands']), 'Apps15 SDK command ownership cleanup is uncertain')
        else:
            C.require(value.get('declared_inner_commands_completed_without_timeout') is True,
                      'new private SDK worker did not complete its declared inner command accounting')
    return value


def inspect_busy(stage, row):
    """Accept only the pinned stage's actual typed LOCK_NB refusal.

    Apps15's unchanged three-field output is deliberately supported separately;
    a naked exit75, missing/unknown sdk_started, banner or foreign lock rejects.
    """
    C.require(type(row.get('exit_code')) is int and row['exit_code'] == 75 and
        not row.get('timed_out') and not row.get('error'), 'actual normal resource refusal required')
    path = Path(row['log'])
    C.require(C.record(path) == {'path': str(path), 'sha256': row['sha256']}, 'actual busy output bytes changed')
    raw = path.read_text()
    C.require(raw.endswith('\n') and '\r' not in raw and len(raw.splitlines()) == 1,
              'single complete typed resource refusal required')
    value = C.load(path)
    expected = {'status', 'sdk_started', 'lock'} if stage['label'] == 'apps15' else {
        'status', 'exit_code', 'sdk_started', 'docker_started', 'lock'}
    C.require(isinstance(value, dict) and set(value) == expected and
        value.get('status') == 'resource_lease_busy' and value.get('sdk_started') is False and
        value.get('lock') == str(C.LOCK), 'actual stage-specific typed busy output required')
    if stage['label'] != 'apps15':
        C.require(stage['label'] in ('audio-calendar26', 'knowledge26', 'live-sdk39-26', 'native-strip26', 'number-local580') and
            type(value.get('exit_code')) is int and value['exit_code'] == 75 and
            value.get('docker_started') is False, 'new wrapper must prove SDK/Docker did not start')
    return value


def declaration_binding(args):
    """Retain the actual normal preparer's new SDK/API and raw Owner receipt."""
    path = Path(args.sdk_declaration_receipt)
    C.require(C.sha(path) == args.sdk_declaration_receipt_sha256,
        'actual selected SDK declaration preparation receipt changed')
    value = C.load(path)
    C.require(value.get('schema') == 'selected-SDK26-real-native-declaration-owner579/v1' and
        value.get('source_commit') == args.commit and type(value.get('exit_code')) is int and value['exit_code'] == 0 and
        value.get('cleanup_verified') is True and value.get('owned_container_absent') is True and
        value.get('source_out_written') is False and value.get('native_source_readonly') is True and
        value.get('native_out_readonly') is True and value.get('sdk_ets_readonly') is False and
        value.get('host_tests_executed') is False and value.get('first_artifact_behavior_gate_passed') is False and
        not value.get('error') and not value.get('must_resolve_owned_resources_before_next_stage'),
        'actual closed normal selected-SDK declaration preparation required')
    ets = (C.SDK / 'ets').resolve(strict=True)
    api = ets / 'api/application/ServiceExtensionContext.d.ts'
    C.require(value['sdk']['sdk_root'] == str(ets) and value['final_sdk_api'] == dict(
        path=str(api),sha256=C.sha(api),bytes=api.stat().st_size) and
        C.sha(api) == 'a436733ec2dc9c393be14e2ac692032be393bf22a6e345d5b6177f0370bac555',
        'actual SDK entry must use the new declaration, never another SDK or old receipt')
    ledger_ref = value['resource_ledger']; ledger_path = Path(ledger_ref['path'])
    C.require(C.sha(ledger_path) == ledger_ref['sha256'], 'actual preparer original Owner raw ledger changed')
    ledger = C.load(ledger_path)
    C.require(ledger.get('schema') == 'owned-resource35/v1' and ledger.get('phase') == 'closed' and
        ledger.get('cleanup_verified') is True and ledger.get('failed') is False and ledger.get('errors') == [] and
        ledger.get('commands') == value['commands'], 'actual original Owner declaration closure/raw journal differs')
    for row in value['commands']:
        for key in ('stdout_record', 'stderr_record'):
            if key not in row:
                C.require(key == 'stderr_record' and row.get('stderr') is None and 'stdout_record' in row,
                    'only original combined stdout may omit a separate stderr record')
                continue
            ref = row[key]
            C.require(C.sha(ref['path']) == ref['sha256'], 'actual declaration command raw stream changed')
    for ref in (value['container_log'], value['sdk_metadata'], value['final_sdk_api'], value['sdk_lock']):
        C.require(C.sha(ref['path']) == ref['sha256'] and
            ('bytes' not in ref or Path(ref['path']).stat().st_size == ref['bytes']),
            'actual declaration preparation data changed')
    return dict(receipt=C.record(path), resource_ledger=ledger_ref, final_sdk_api=value['final_sdk_api'],
        sdk_metadata=value['sdk_metadata'], sdk_lock=value['sdk_lock'])


def execute(args):
    C.pin(args.commit)
    declared = declaration_binding(args)
    source = private_sources()
    out = C.fresh_output(args.output)
    plan = P.plan(args.commit, out, phase=args.phase, width=args.width, height=args.height,
        product=args.product, device=args.device,wallpaper_ui_plan=args.wallpaper_ui_plan,
        wallpaper_ui_plan_sha256=args.wallpaper_ui_plan_sha256,
        number_inputs=args.number_inputs,number_inputs_sha256=args.number_inputs_sha256,
        sdk_declaration_receipt=args.sdk_declaration_receipt,
        sdk_declaration_receipt_sha256=args.sdk_declaration_receipt_sha256)
    C.save(out / 'plan.json', plan)
    report = dict(schema='F-SDK-root-batch26/v1', scope='fresh_unsigned_caller_SDK_ONLY_NOT_product_or_runtime',
        source_commit=args.commit, main_commit=C.MAIN_COMMIT, worktree=str(C.REPO),
        driver=C.record(__file__), source_manifest=source, plan=C.record(out / 'plan.json'), selected_sdk_declaration=declared,
        target=C.target_context(args.product,args.device),
        serial=True, max_sdk_jobs=1, dispatcher_holds_no_outer_flock=True,
        stage_lock=str(C.LOCK), commands=[], stages=[], failures=[], deferred=plan['deferred_postpackage'],
        signed=False, guest_executed=False, first_artifact_behavior_gate_passed=False,
        exit_code=1, started_utc=C.utc())
    receipt = out / 'evidence.json'
    C.save(receipt, report)
    results = {}
    admission = C.input_admission(out, args.commit)
    if admission['exit_code'] != 0:
        print(json.dumps(C.input_rejected(out, report, receipt, admission)))
        return 1
    report['input_admission'] = C.record(out / 'input-admission.json')
    C.save(receipt, report)
    try:
        for stage in plan['stages']:
            dependency = stage.get('depends_on')
            if dependency and results.get(dependency) != 0:
                report['stages'].append(dict(label=stage['label'], status='dependency_failed_NOT_executed', dependency=dependency))
                C.save(receipt, report)
                continue
            C.require(private_sources() == source, 'SDK batch sources changed before stage')
            C.require(declaration_binding(args) == declared, 'actual selected SDK declaration changed before stage')
            C.pin(args.commit)
            row = C.command(stage['argv'], label=stage['label'], cwd=C.REPO, output=out, report=report,
                receipt=receipt, commit=args.commit, timeout=stage['timeout'])
            if row['exit_code'] == 75:
                try:
                    refused = inspect_busy(stage, row)
                except Exception as error:
                    raise C.UnsafeCleanup(stage['label'] + ': unproved exit75 refusal: ' + str(error)) from error
                report['stages'].append(dict(label=stage['label'], status='resource_lease_busy_NOT_accepted',
                    sdk_started=False, actual_refusal=refused, raw=C.record(row['log'])))
                report['resource_admission_deferred'] = True
                break
            try:
                actual = inspect_stage(stage, args.commit)
            except Exception as error:
                raise C.UnsafeCleanup(stage['label'] + ': receipt/cleanup review required: ' + str(error)) from error
            C.require(private_sources() == source, 'SDK batch sources changed after stage')
            C.require(declaration_binding(args) == declared, 'actual selected SDK declaration changed after stage')
            results[stage['label']] = row['exit_code']
            report['stages'].append(dict(label=stage['label'], requested_roles=stage['roles'],
                exit_code=row['exit_code'], actual_receipt=C.record(stage['receipt']),
                ownership_scope='Declared SDK commands returned normally; Linux container cleanup explicit. No absolute descendant-tree claim.'))
            if row['exit_code'] != 0 or actual.get('exit_code') != 0:
                report['failures'].append(stage['label'] + ': actual SDK/binding failure; original logs/receipt preserved')
            C.save(receipt, report)
        C.pin(args.commit)
        C.require(private_sources() == source, 'final SDK batch source freeze differs')
        complete = len(results) == len(plan['stages']) and all(code == 0 for code in results.values())
        report['requested_prepackage_stages_complete'] = complete
        report['exit_code'] = 0 if complete and not report['failures'] else 75 if report.get('resource_admission_deferred') else 1
    except C.UnsafeCleanup as error:
        report.update(must_resolve_owned_SDK_processes_before_next_resource_stage=True,
                      descendants_cleanup_verified=False)
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = C.utc()
        C.save(receipt, report)
    print(json.dumps({'exit_code': report['exit_code'], 'evidence': str(receipt),
        'completed_stages': list(results), 'failures': report['failures'],
        'peer15_roles_deferred_until_new_F_package': 2}))
    return report['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--sdk-declaration-receipt', type=Path, required=True)
    parser.add_argument('--sdk-declaration-receipt-sha256', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=('host', 'prepackage'), default='prepackage')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    parser.add_argument('--product', choices=('arm64_virt','armv7a_virt','x86_64_virt'), default='arm64_virt')
    parser.add_argument('--device', choices=('phone','2in1'), default='phone')
    parser.add_argument('--wallpaper-ui-plan',type=Path)
    parser.add_argument('--wallpaper-ui-plan-sha256')
    parser.add_argument('--number-inputs',type=Path)
    parser.add_argument('--number-inputs-sha256')
    args = parser.parse_args()
    C.commit_shape(args.commit)
    if not args.execute:
        print(json.dumps(P.plan(args.commit, args.output, phase=args.phase, width=args.width, height=args.height,
            product=args.product, device=args.device,wallpaper_ui_plan=args.wallpaper_ui_plan,
        wallpaper_ui_plan_sha256=args.wallpaper_ui_plan_sha256,
        number_inputs=args.number_inputs,number_inputs_sha256=args.number_inputs_sha256,
        sdk_declaration_receipt=args.sdk_declaration_receipt,
        sdk_declaration_receipt_sha256=args.sdk_declaration_receipt_sha256), indent=2))
        return 0
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
