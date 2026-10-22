"""Root serial new-package export/profile/helpers; no representative gate claim.

Each resource-owning child takes the existing lease. This dispatcher never
holds an outer lease, changes product inputs, signs, or starts QEMU. A failed
stage with proven cleanup permits independent helpers to finish; uncertain
cleanup stops all subsequent work.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = ROOT / '.tmp/parallel-capability-20261016'
B = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')
PY = '/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python'
COMMIT = None
SOURCE = Path(__file__).resolve().parent
ORIGINAL_RUNNER = SOURCE / 'run_owned_runtime_helper579.py'
ORIGINAL_RUNNER_SHA = 'a6d0bbf3fa64b5ea4c6f8fbc531af25430620ddb3eee98beef6325632fe4c06f'
KINDS = ('core', 'audio', 'calendar', 'gnss', 'mic', 'netlink', 'number', 'number-recheck')


def need(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def record(path):
    p = Path(path)
    need(p.is_absolute() and p.resolve() == p and p.is_file() and not p.is_symlink(), 'actual regular input required')
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return dict(path=str(p), sha256=h.hexdigest(), bytes=p.stat().st_size)


def checked(row):
    actual = record(row['path'])
    need(actual['sha256'] == row['sha256'] and ('bytes' not in row or actual['bytes'] == row['bytes']), 'input bytes changed')
    return Path(actual['path'])


def clean():
    need(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT, 'canonical HEAD differs')
    need(not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True), 'canonical tracked inputs changed')
    for name in ('.representative35-unresolved.json', '.representative48-unresolved.json'):
        p = B / name
        need(not p.exists() and not p.is_symlink(), 'unresolved resource quarantine: ' + name)


def immutable_sources():
    from runtimekit579_contract import read as read_source, checked as source_checked
    pins = read_source(SOURCE.parent / 'PRIVATE_FILES579.json')
    for row in pins['files']:
        source_checked(row)
    need(record(ORIGINAL_RUNNER)['sha256'] == ORIGINAL_RUNNER_SHA, 'original actual six-kind runner changed')
    return record(SOURCE.parent / 'PRIVATE_FILES579.json')


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def authenticated_dependencies(destination):
    original = B / 'r55-helper-python-dependencies-09-01'
    receipt = record(original / 'receipt.json')
    need(receipt['sha256'] == '44cfb62c71d6e4ea7f31e308ec50bcfb8a95f26a2b06c43adea6c9ae8f9f5b13', 'genuine dependency receipt differs')
    data = read(original / 'receipt.json')
    need(data['Pillow'] == '12.3.0', 'actual pinned diagnostic Pillow required')
    need(not destination.exists() and not destination.is_symlink(), 'new diagnostic dependency copy required')
    destination.mkdir()
    # Old __pycache__ files were deliberately outside the authenticated receipt.
    # Mount only full-byte verified receipt members from this fresh derivation.
    copied = {}
    for name, expected in data['files'].items():
        relative = Path(name)
        need(not relative.is_absolute() and '..' not in relative.parts and '__pycache__' not in relative.parts and
             relative.suffix != '.pyc', 'unexpected dependency receipt member')
        source = checked(dict(path=str(original / relative), **expected))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[name] = record(checked(dict(path=str(target), **expected)))
    shutil.copyfile(original / 'receipt.json', destination / 'receipt.json')
    checked(receipt)
    need(record(destination / 'receipt.json')['sha256'] == receipt['sha256'], 'copied authentic receipt changed')
    save(destination / 'copy-proof.json', dict(scope='exact authenticated dependency members copied; original receipt retained verbatim',
         original_root=str(original), original_receipt=receipt, files=copied, excluded_unrecorded_bytecode=True,
         first_artifact_behavior_gate_passed=False))
    return destination, record(destination / 'receipt.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--bindings-sha256', required=True)
    args = parser.parse_args()
    global COMMIT
    bindings = read(checked(dict(path=str(args.bindings), sha256=args.bindings_sha256)))
    need(args.execute and set(bindings) == {'schema','source_commit','source_kit_manifest','canonical_snapshot',
        'snapshot_count','package_receipt','attempt','normal_link_target','scheduling_admission','normal_source'} and bindings['schema'] == 'postpackage-production579-target/v2' and
        re.fullmatch('579-[0-9]{2}',bindings['attempt']), 'explicit current579 production inputs required')
    COMMIT = bindings['source_commit']
    from runtimekit579_contract import verify_kit
    verify_kit(bindings, COMMIT)
    clean()
    immutable_sources()
    receipt_row = bindings['package_receipt']
    package_receipt = read(checked(receipt_row))
    need(type(package_receipt.get('exit_code')) is int and package_receipt['exit_code'] == 0 and
         package_receipt.get('source_commit') == COMMIT and package_receipt.get('cleanup_verified') is True and
         package_receipt.get('owned_container_absent') is True and package_receipt.get('owned_launcher_group_closed') is True and
         package_receipt.get('resource_lease_held') is False and
         package_receipt.get('must_resolve_owned_resources_before_next_stage') is False and
         package_receipt.get('schema') in ('F-representative-source-owner/v18','remaining579-one-target-source-owner/v1') and
         package_receipt.get('host_tests_executed') is False and
         package_receipt.get('capability_acceptance') == 'newly_packaged_QEMU_runtime_only' and
         package_receipt.get('adopted_complete_host_environment',{}).get('PREPARE_ONLY') == '0' and
         package_receipt.get('adopted_complete_host_environment',{}).get('BUILD_ONLY_LOAD') == '0',
         'closed actual full new package required; no host/Linux pass gate or prepare receipt')
    archive = record(checked(package_receipt['package']))
    import sys
    sys.path.insert(0,str(ROOT/'ci/capability-audit'))
    from production579_target import archive_manifest
    target = archive_manifest(Path(archive['path']))['context']
    if target['product'] != 'arm64_virt':
        need(type(bindings['normal_link_target']) is str and bindings['normal_link_target'],
            'actual existing normal Ninja executable target required before nondefault production')
    from production579_receipt import validate as validate_package_receipt
    actual_admission = validate_package_receipt(package_receipt,target,COMMIT)
    admission = bindings['scheduling_admission']
    need(admission == actual_admission,'post input must retain the exact actual normal Owner scheduling Ref')
    if target['product'] == 'arm64_virt' and target['device'] == 'phone':
        need(admission is None,'first representative is not admitted by a remaining-package receipt')
    else:
        need(admission is not None,'actual Root first-artifact scheduling admission required')
        allowed=read(checked(admission))
        need(allowed.get('schema') == 'actual-final579-next-product-scheduling-admission/v1' and
            allowed.get('source_commit') == COMMIT and
            allowed.get('next_target') == dict(product=target['product'],device_type=target['device']),
            'actual fixed first-gate admission differs from this product/profile')
    prefix = 'r67-canonical-runtime-' + bindings['attempt']
    out = B / prefix
    exported = B / (prefix + '-export')
    profile = B / (prefix + '-profile')
    dependency_copy = B / (prefix + '-python-deps')
    outputs = {kind: str(B / (prefix + '-helper-' + kind)) for kind in KINDS}
    extra_output = B / (prefix + '-extra7')
    onset_output = B / (prefix + '-onset-tool')
    au_native_output = B / (prefix + '-au-native')
    au_sdk_output = B / (prefix + '-au-sdk')
    sdk_declaration_output = B / (prefix + '-sdk-declaration')
    for path in [out, exported, profile, dependency_copy, extra_output, extra_output.with_name(extra_output.name+'-profile'),
                 onset_output, onset_output.with_name(onset_output.name+'-profile'), au_native_output, sdk_declaration_output,
                 au_sdk_output, *map(Path, outputs.values())]:
        need(not path.exists() and not path.is_symlink(), 'fresh output required: ' + str(path))
    out.mkdir()
    report = dict(scope=__doc__, source_commit=COMMIT, package_receipt=record(checked(receipt_row)),
                  archive=archive, target=target, scheduling_admission=admission, commands=[], failures=[], exit_code=1,
                  first_artifact_behavior_gate_passed=False, remaining_five_started=False,
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    report_path = out / 'receipt.json'
    save(report_path, report)

    def run(label, argv, result_path, *, profile_stage=False):
        clean()
        immutable_sources()
        checked(receipt_row)
        row = dict(label=label, argv=argv, exit_code=None)
        report['commands'].append(row)
        save(report_path, report)
        log = out / (label + '.log')
        with log.open('xb') as stream:
            result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        row.update(exit_code=result.returncode, log=record(log))
        need(result_path.is_file(), 'actual child receipt absent; stop before next resource')
        data = read(result_path)
        row['receipt'] = record(result_path)
        need(data.get('source_commit') == COMMIT and type(data.get('exit_code')) is int, 'child source/exit differs')
        if not profile_stage:
            need(data.get('cleanup_verified') is True and data.get('owned_container_absent') is True,
                 'actual child resource cleanup unproved')
        need(not data.get('must_resolve_owned_resources_before_next_stage'), 'child resource uncertainty')
        clean()
        immutable_sources()
        if result.returncode or data['exit_code']:
            report['failures'].append(label)
        save(report_path, report)
        print(json.dumps(dict(label=label, exit_code=result.returncode, receipt=str(result_path))), flush=True)
        return not result.returncode and data['exit_code'] == 0

    common = ['--here', str(H), '--qa-root', str(ROOT), '--commit', COMMIT,
              '--package-receipt', receipt_row['path'], '--package-receipt-sha256', receipt_row['sha256']]
    try:
        selected_sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0/ets').resolve(strict=True)
        if not run('selected-sdk-declaration', [PY, '-B', str(SOURCE / 'run_sdk_declaration579.py'),
                   '--execute', *common, '--sdk-ets-root', str(selected_sdk), '--output', str(sdk_declaration_output)],
                   sdk_declaration_output / 'evidence.json'):
            raise ValueError('actual selected SDK declaration preparation failed; do not compile against the old declaration')
        report['selected_sdk_declaration'] = record(sdk_declaration_output / 'evidence.json')
        save(report_path, report)
        if not run('installed-export', [PY, '-B', str(SOURCE / 'export/export_runtime35_installed_dsos.py'),
                   *common, '--output', str(exported)], exported / 'receipt.json'):
            raise ValueError('failed export; profile/helpers depend on actual export')
        report['haptic_source_export'] = read(exported / 'receipt.json')['haptic_source_export']
        checked(report['haptic_source_export'])
        current_export = read(exported / 'receipt.json')
        # A source envelope binds the actual same-package RO producer only.
        # Supported RTT/OOB behavior is still pending actual QEMU execution.
        if current_export.get('rtt_source_facts'):
            source_facts = current_export['rtt_source_facts']
            checked(source_facts)
            source_envelope = out / 'rtt-source-receipt579.json'
            save(source_envelope, dict(schema='api26-rtt-source-receipt579/v1',
                archive_sha256=archive['sha256'], source_commit=COMMIT,
                source={key: source_facts[key] for key in ('path', 'sha256')},
                producer={key: record(exported / 'receipt.json')[key] for key in ('path', 'sha256')}))
            report['rtt_source_receipt'] = record(source_envelope)
            save(report_path, report)
        if not run('installed-profile', [PY, '-B', str(SOURCE / 'prepare_runtime377_installed_profile.py'), *common,
                   '--export-receipt', str(exported / 'receipt.json'), '--export-receipt-sha256', record(exported / 'receipt.json')['sha256'],
                   '--output', str(profile)], profile / 'receipt.json', profile_stage=True):
            raise ValueError('failed installed profile; helpers depend on actual full-byte identity')
        # Pure Media DATA production uses actual closed export/profile and the
        # selected real new Head/Kit/normal SOURCE. It owns no resources.
        try:
            from produce_media579_product import produce as produce_media579_product
            media_output = H / ('media579-product-' + COMMIT + '-' + target['product'] + '-' + target['device'] + '-' + bindings['attempt'])
            media_product = produce_media579_product(export_receipt=record(exported / 'receipt.json'),
                profile_receipt=record(profile / 'receipt.json'), package_receipt=receipt_row,
                normal_source=bindings['normal_source'], kit=bindings['source_kit_manifest'], output=media_output)
            report['media579_product_export'] = media_product['media579_product_export']
            report['media579_source_export'] = media_product['source_export']
            report['media579_provider_facts'] = media_product['provider_facts']
            report['media579_graphics3d'] = media_product['graphics3d']
            report['media579_normal_source_context'] = media_product['normal_source_context']
        except Exception as media_error:
            report['failures'].append('media-product-data')
            report['media579_product_error'] = type(media_error).__name__ + ': ' + str(media_error)
        save(report_path, report)
        dependency, dependency_receipt = authenticated_dependencies(dependency_copy)
        report['audio_onset579_installed_dsos'] = read(profile / 'receipt.json')['audio_onset579_installed_dsos']
        checked(report['audio_onset579_installed_dsos'])
        report['diagnostic_dependency_copy'] = record(dependency / 'copy-proof.json')
        intent = dict(schema_version='helper-build-intent579-target/v2', product_commit=COMMIT, tools_commit=COMMIT,
                      qa_root=str(ROOT), package_receipt=record(checked(receipt_row)), archive=archive,
                      runtime_profile=record(profile / 'runtime-profile.json'), python_dependency_root=str(dependency),
                      python_dependency_receipt=dependency_receipt,
                      profile_producer_source=record(SOURCE / 'prepare_runtime377_installed_profile.py'), outputs=outputs,
                      normal_link_target=bindings['normal_link_target'])
        intent_path = out / 'helper-build-intent.json'
        save(intent_path, intent)
        selected_kinds = KINDS if target['device'] == 'phone' else KINDS[:6]
        for kind in selected_kinds:
            if kind == 'number-recheck' and 'helper-number' in report['failures']:
                report['number580_recheck_skipped'] = 'actual Number build failed; no recheck result claimed'
                continue
            run('helper-' + kind, [PY, '-B', str(ORIGINAL_RUNNER), kind,
                '--here', str(H), '--qa-root', str(ROOT), '--commit', COMMIT,
                '--profile-producer', str(SOURCE / 'prepare_runtime377_installed_profile.py'), '--profile-producer-sha256', record(SOURCE / 'prepare_runtime377_installed_profile.py')['sha256'],
                '--config', str(intent_path), '--config-sha256', record(intent_path)['sha256']], Path(outputs[kind]) / 'evidence.json')
        extra_intent = dict(schema='extra7-production579-target/v2', source_commit=COMMIT,
            package_receipt=record(checked(receipt_row)), archive=archive,
            runtime_profile=record(profile / 'runtime-profile.json'), profile_receipt=record(profile / 'receipt.json'),
            profile_producer=record(SOURCE / 'prepare_runtime377_installed_profile.py'),
            python_dependency_root=str(dependency), python_dependency_receipt=dependency_receipt, output=str(extra_output),
            normal_link_target=bindings['normal_link_target'])
        extra_path = out / 'extra7-intent.json'; save(extra_path, extra_intent)
        run('extra7', [PY, '-B', str(SOURCE / 'run_extra579.py'), '--intent', str(extra_path),
            '--intent-sha256', record(extra_path)['sha256'], '--here', str(H), '--qa-root', str(ROOT)],
            extra_output / 'evidence.json')
        onset_intent = dict(extra_intent, schema='onset-tool-production579-target/v2', output=str(onset_output))
        onset_intent_path = out / 'onset-tool-intent.json'; save(onset_intent_path, onset_intent)
        run('onset-tool', [PY, '-B', str(SOURCE / 'run_onset_tool579.py'), '--intent', str(onset_intent_path),
            '--intent-sha256', record(onset_intent_path)['sha256'], '--here', str(H), '--qa-root', str(ROOT)],
            onset_output / 'evidence.json')
        report['audio_onset579_helper_owner'] = record(onset_output / 'evidence.json')
        au_intent = dict(extra_intent, schema='AU-native-production579-target/v2', output=str(au_native_output))
        au_intent_path = out / 'au-native-intent.json'; save(au_intent_path, au_intent)
        run('au-native', [PY, '-B', str(SOURCE / 'run_au_native579.py'), '--intent', str(au_intent_path),
            '--intent-sha256', record(au_intent_path)['sha256'], '--here', str(H), '--qa-root', str(ROOT)],
            au_native_output / 'evidence.json')
        report['au579_native_owner'] = record(au_native_output / 'evidence.json')
        # This original SDK stage has no Docker owner. Its actual command journal
        # and original UnsafeCleanup accounting remain the resource boundary.
        clean(); immutable_sources()
        haptic = report['haptic_source_export']
        row = dict(label='au-sdk', argv=[PY, '-B', str(SOURCE / 'run_au_sdk579.py'), '--execute',
            '--source-export', haptic['path'], '--source-export-sha256', haptic['sha256'],
            '--output', str(au_sdk_output), '--product',target['product'],'--device',target['device']], exit_code=None)
        report['commands'].append(row); save(report_path, report)
        with (out / 'au-sdk.log').open('xb') as stream:
            result = subprocess.run(row['argv'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        row.update(exit_code=result.returncode, log=record(out / 'au-sdk.log'))
        need((au_sdk_output / 'evidence.json').is_file(), 'actual AU SDK receipt missing; stop')
        sdk = read(au_sdk_output / 'evidence.json')
        row['receipt'] = record(au_sdk_output / 'evidence.json')
        need(sdk.get('source_commit') == COMMIT and type(sdk.get('exit_code')) is int and
            not sdk.get('must_resolve_owned_SDK_processes_before_next_resource_stage'),
            'actual AU SDK completion uncertain; stop resources')
        if result.returncode or sdk['exit_code']:
            report['failures'].append('au-sdk')
        report['au579_sdk_stage'] = row['receipt']
        clean(); immutable_sources(); save(report_path, report)
        report['helpers'] = {kind:dict(root=outputs[kind], launcher=record(Path(outputs[kind])/'evidence.json'))
            for kind in selected_kinds if (Path(outputs[kind])/'evidence.json').is_file()}
        if target['device'] == 'phone' and not {'helper-number', 'helper-number-recheck'} & set(report['failures']):
            number = Path(outputs['number']); recheck = Path(outputs['number-recheck'])
            for directory in (number, recheck):
                actual = read(directory / 'evidence.json')
                need(actual['exit_code'] == 0 and actual['cleanup_verified'] is True and
                     actual['owned_container_absent'] is True and
                     set(read(directory / 'helpers/build.json')['helpers']) == {'number_token_query395'},
                     'both actual normal Number build and independent recheck must finish')
            report['number580_native_observer'] = dict(build=record(number / 'helpers/build.json'),
                recheck=record(recheck / 'helpers/build.json'), dsos=record(number / 'product-dsos/manifest.json'),
                build_owner=record(number / 'evidence.json'), recheck_owner=record(recheck / 'evidence.json'))
        elif target['device'] != 'phone':
            report['number580_native_observer'] = dict(status='not_applicable', device=target['device'], runtime_pass=False)
        report['extra7_owner'] = record(extra_output / 'evidence.json')
        report['profile_receipt'] = record(profile / 'receipt.json')
        report['runtime_profile'] = record(profile / 'runtime-profile.json')
        if not report['failures']:
            actual = read(extra_output / 'evidence.json')
            extra_build = checked(dict(path=actual['build_report'], sha256=actual['build_report_sha256']))
            native_export = dict(schema='actual-root-capability579-native-export/v1', archive=archive,
                source_commit=COMMIT, package_receipt=record(checked(receipt_row)),
                build_inputs=read(profile / 'receipt.json')['build_inputs'], build=record(extra_build),
                supplemental_owner=record(extra_output / 'evidence.json'),
                supplemental_builds={})
            need(set(actual['supplemental_helpers']) == {'networking579', 'owning_services579', 'usb579', 'msdp579'} and
                 actual['exit_code'] == 0 and actual['cleanup_verified'] is True and
                 actual['owned_container_absent'] is True, 'all three actual singleton builds settled')
            for name in ('networking579', 'owning_services579', 'usb579', 'msdp579'):
                observed = actual['supplemental_helpers'][name]
                need(observed['status'] == 'pass_compile_link_ONLY', 'selected native production incomplete')
                native_export['supplemental_builds'][name] = record(checked(observed['build']))
            save(out / 'native-export.json', native_export)
            report['native_export'] = record(out / 'native-export.json')
            from produce_usb579_product import produce as produce_usb579_product
            usb_output = H / ('usb579-product-' + COMMIT + '-' + target['product'] + '-' + target['device'] + '-' + bindings['attempt'])
            usb_product = produce_usb579_product(export_receipt=record(exported / 'receipt.json'),
                profile_receipt=record(profile / 'receipt.json'), package_receipt=receipt_row,
                media_product=report['media579_product_export'], native_export=report['native_export'], output=usb_output)
            report['usb579_product_export'] = usb_product['usb579_product_export']
            from produce_telephony579_product import produce as produce_telephony579_product
            telephony_output = H / ('telephony579-product-' + COMMIT + '-' + target['product'] + '-' + target['device'] + '-' + bindings['attempt'])
            telephony_product = produce_telephony579_product(export_receipt=record(exported / 'receipt.json'),
                profile_receipt=record(profile / 'receipt.json'),package_receipt=receipt_row,
                media_product=report['media579_product_export'],output=telephony_output)
            report['telephony579_product_export'] = telephony_product['telephony579_product_export']
            if target['device'] == 'phone':
                from produce_telephony579_product import produce_number_seeds
                report['number580_local_seeds'] = produce_number_seeds(package_receipt=receipt_row,
                    profile_receipt=record(profile / 'receipt.json'), output=telephony_output / 'number-local-seeds')
                from produce_telephony579_product import produce_number_permission
                report['number580_permission_translation'] = produce_number_permission(
                    export_receipt=record(exported / 'receipt.json'), profile_receipt=record(profile / 'receipt.json'),
                    package_receipt=receipt_row, seed_receipt=report['number580_local_seeds'],
                    output=telephony_output / 'number-permission-translation.json')
            else:
                report['number580_local_seeds'] = dict(status='not_applicable', device=target['device'], runtime_pass=False)
        report['exit_code'] = int(bool(report['failures']))
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(report_path, report)
    print(json.dumps(dict(exit_code=report['exit_code'], receipt=str(report_path), failures=report['failures'], error=report.get('error'))), flush=True)
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
