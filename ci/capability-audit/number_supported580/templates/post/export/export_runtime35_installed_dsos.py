"""UNEXECUTED successor of export_runtime15_installed_dsos; same original CLI."""
from pathlib import Path
import argparse
import shutil
import sys
from support_common35 import *


def main():
    parser = argparse.ArgumentParser(description=__doc__); common_arguments(parser)
    args = parser.parse_args(); here, root = configure(args.here, args.qa_root)
    receipt_row = dict(path=str(regular(args.package_receipt)), sha256=args.package_receipt_sha256)
    body = regular(Path(__file__).resolve().parent / 'installed_export35_inner.py')
    body_before = record(body)
    owner = Owner(args.output)
    with owner:
        report = dict(source_commit=args.commit, exit_code=1, commands=owner.commands,
                      scope='actual new F installed DSO/ELF/GN RO export ONLY; no runtime acceptance',
                      cleanup_verified=False, first_artifact_behavior_gate_passed=False,
                      here=str(here), private_source=record(Path(__file__).resolve()),
                      resource_helper=record(Path(__file__).resolve().parent / 'owned_resource35.py'))
        path = owner.output / 'receipt.json'
        owner.callbacks.append(lambda: write_json(path, report)); write_json(path, report)
        try:
            receipt_file, product, package, inputs = package_inputs(owner, root, args.commit, receipt_row)
            report.update(metadata(args.commit, receipt_file, product, package, inputs)); report['commands'] = owner.commands
            from production579_target import archive_manifest
            package_manifest = archive_manifest(package)
            manifest_copy = owner.output / 'actual-package-manifest.json'
            manifest_copy.write_bytes(package_manifest['raw'])
            require(sha(manifest_copy) == package_manifest['sha256'], 'actual archive manifest copy changed')
            report['actual_package_context'] = package_manifest['context']
            report['actual_package_manifest'] = record(manifest_copy)
            archive_input = owner.output / 'number580-archive-input.json'
            archive_binding = dict(schema='number580-original-export-archive-input/v1',
                source_commit=args.commit, archive=record(regular(package)),
                actual_package_manifest_sha256=package_manifest['sha256'])
            write_json(archive_input, archive_binding)
            report['number_permission_input'] = record(archive_input)
            frozen, frozen_manifest = frozen_snapshot(product, inputs)
            report['retained_launcher_snapshot'] = frozen_manifest
            inner = owner.output / 'inner.py'; shutil.copyfile(body, inner)
            require(record(body) == body_before and sha(inner) == body_before['sha256'], 'fixed RO export body changed')
            report['inner_source'] = record(inner)
            dispatcher_source = regular(Path(__file__).resolve().parent / 'export_with_facts579_inner.py')
            dispatcher = owner.output / 'export-with-facts579.py'
            shutil.copyfile(dispatcher_source, dispatcher)
            optional_sources = Path(__file__).resolve().parent / 'six-source'
            copied_sources = owner.output / 'six-source-payload579'; copied_sources.mkdir()
            report['six_source_fixed_inputs'] = []
            for name in ('six_source_export579.py', 'six_source_request579.py'):
                source = regular(optional_sources / name); target = copied_sources / name
                shutil.copyfile(source, target)
                require(sha(source) == sha(target), 'fixed optional source copy changed')
                report['six_source_fixed_inputs'].append(dict(source=record(source), copied=record(target)))
            report['six_source_dispatcher'] = dict(source=record(dispatcher_source), copied=record(dispatcher))
            rtt_source = regular(Path(__file__).resolve().parent / 'rtt-source/append_rtt579_source_facts.py')
            rtt_target = owner.output / 'rtt-source-payload579/append_rtt579_source_facts.py'
            rtt_target.parent.mkdir()
            shutil.copyfile(rtt_source, rtt_target)
            require(sha(rtt_source) == sha(rtt_target), 'fixed RTT source copy changed')
            report['rtt_source_fixed_input'] = dict(source=record(rtt_source), copied=record(rtt_target))
            # Fixed extra DATA producer copied into the same original RO CID.
            # No second Owner/create/start or source/out mount is introduced.
            media_sources = Path(__file__).resolve().parent / 'media-source'
            media_targets = owner.output / 'media-source-payload579'; media_targets.mkdir()
            report['media_source_fixed_inputs'] = []
            for name in ('media579_source_request.py', 'export_media579_source.py'):
                source = regular(media_sources / name); target = media_targets / name
                shutil.copyfile(source, target)
                require(sha(source) == sha(target), 'fixed Media source copy changed')
                report['media_source_fixed_inputs'].append(dict(source=record(source), copied=record(target)))
            mounts = {'/ohos': volume_mount(SOURCE_VOLUME), '/ohos/out': volume_mount(OUT_VOLUME),
                      '/work': bind_mount(root), '/evidence': bind_mount(owner.output, True),
                      '/frozen-inputs': bind_mount(frozen), '/package-receipt.json': bind_mount(receipt_file),
                      '/actual-package-manifest.json': bind_mount(manifest_copy)}
            command = ['python3', '/evidence/export-with-facts579.py', '--commit', args.commit, '--tree-sha256', inputs['tree_sha256'],
                       '--frozen-manifest-sha256', frozen_manifest['sha256'], '--frozen-manifest-host-path', frozen_manifest['path'],
                       '--package-receipt-sha256', sha(receipt_file), '--package-receipt-host-path', str(receipt_file),
                       '--actual-manifest-sha256', package_manifest['sha256']]
            entry = owner.plan(name='ohos-F-runtime-export35-' + owner.owner, commit=args.commit,
                               image=IMAGE, mounts=mounts, command=command)
            entry['cidfile'] = str(owner.output / 'container.cid'); owner.save()
            owner.create(entry, mount_options(mounts))
            report['container_id'] = entry['id']; write_json(path, report)
            owner.start(entry, timeout=480)
            report['media_source_stage'] = record(owner.output / 'media-source-stage579.json')
            media_facts = owner.output / 'media-source-facts579/RAW.json'
            if media_facts.is_file() and not media_facts.is_symlink():
                report['media_source_facts'] = record(media_facts)
            report['six_source_stage'] = record(owner.output / 'six-source-stage579.json')
            optional = owner.output / 'six-source-facts579/FACTS579.json'
            if optional.is_file() and not optional.is_symlink():
                report['six_source_facts'] = record(optional)
            report['rtt_source_stage'] = record(owner.output / 'rtt-source-stage579.json')
            rtt_facts = owner.output / 'rtt-source-facts579/SOURCE.json'
            if rtt_facts.is_file() and not rtt_facts.is_symlink():
                report['rtt_source_facts'] = record(rtt_facts)
            exported = regular(owner.output / 'native-export/installed-runtime-export.json')
            actual = load(exported)
            require(actual['source_ro'] is True and actual['out_ro'] is True and actual['source_root'] == '/ohos' and
                    actual['product'] == package_manifest['context']['product'] and
                    actual['device'] == package_manifest['context']['device'] and
                    actual['actual_package_manifest']['sha256'] == package_manifest['sha256'],
                    'actual RO installed export required')
            identity = actual['source_identity']
            require(identity['product_commit'] == args.commit and identity['tree_sha256'] == inputs['tree_sha256'] and
                    identity['package_build_receipt'] == report['package_build_receipt'] and
                    identity['retained_frozen_manifest'] == frozen_manifest and
                    identity['native_source_recipe_anchor']['native_source_revision'] == args.commit and
                    identity['whole_source_tree_verified'] is False, 'actual recipe/frozen source identity differs')
            anchor = identity['native_source_recipe_anchor']
            require(sha(regular(exported.parent / anchor['export_relative'])) == anchor['metadata']['sha256'],
                    'actual copied recipe metadata differs')
            report['source_identity'] = identity
            require(len(actual['files']) >= 15 and actual['alsa_graphs'], 'actual installed DSOs and ALSA GN graphs required')
            source_names = {
                'base/sensors/miscdevice/utils/tools/haptic_format_converter/converter/schemas/oh_schema.json',
                'base/sensors/miscdevice/utils/tools/haptic_format_converter/tests/test_data/oh_no_curve_sample.json'}
            haptic_files = {}
            for row in actual['haptic_sources']:
                name = str(Path(row['path']).relative_to('/ohos'))
                require(name in source_names and name not in haptic_files and not row['symlink'],
                        'exact actual haptic format sources required')
                copied = regular(exported.parent / row['export_relative'])
                require(sha(copied) == row['sha256'] and copied.stat().st_size == row['bytes'],
                        'actual haptic source copy changed')
                haptic_files[name] = dict(path=str(copied), sha256=sha(copied))
            require(set(haptic_files) == source_names, 'both actual current haptic format inputs required')
            haptic_export = owner.output / 'haptic-source-export.json'
            write_json(haptic_export, dict(exit_code=0,
                scope='actual read-only prepared product source export for same new archive haptic format inputs',
                files=haptic_files, source_commit=args.commit, package_build_receipt=report['package_build_receipt'],
                source_export=record(exported), source_identity=identity,
                actual_project_head=actual['haptic_source_head'], original_ro_rows=actual['haptic_sources'],
                runtime_pass=False, first_artifact_behavior_gate_passed=False))
            report['haptic_source_export'] = record(haptic_export)
            require(record(body) == body_before and sha(inner) == body_before['sha256'], 'export sources changed')
            require(record(dispatcher_source) == report['six_source_dispatcher']['source'] and
                record(dispatcher) == report['six_source_dispatcher']['copied'] and all(
                    record(regular(row[key]['path'])) == row[key] for row in report['six_source_fixed_inputs']
                    for key in ('source','copied')), 'fixed optional source input changed during export')
            require(record(rtt_source) == report['rtt_source_fixed_input']['source'] and
                record(rtt_target) == report['rtt_source_fixed_input']['copied'],
                'fixed RTT source input changed during export')
            require(all(record(regular(row[key]['path'])) == row[key] for row in report['media_source_fixed_inputs']
                for key in ('source', 'copied')), 'fixed Media source inputs changed during same-CID export')
            # Number DATA comes from this completed same-CID export, never a
            # future fabricated Ref or a replacement compile-success summary.
            number_raw = load(media_facts)['number_permission580']
            require(number_raw['source_commit'] == args.commit and
                    number_raw['archive_sha256'] == archive_binding['archive']['sha256'] and
                    number_raw['device'] == package_manifest['context']['device'],
                    'actual Number source export belongs to another archive/product')
            def number_host_refs(value):
                if type(value) is dict:
                    if set(value) == {'path','sha256','bytes'}:
                        location = Path(value['path'])
                        require(location.is_absolute() and '..' not in location.parts and
                                location.is_relative_to('/evidence'), 'fixed Number evidence Ref3 only')
                        relative = location.relative_to('/evidence')
                        require(relative.parts and relative.parts[0] in ('media-source-facts579','native-export'),
                                'Number source Ref leaves original export evidence')
                        host = owner.output / relative
                        require(host.resolve() == host, 'Number evidence alias refused')
                        actual_ref = record(regular(host))
                        require(actual_ref['sha256'] == value['sha256'] and actual_ref['bytes'] == value['bytes'],
                                'same-CID Number evidence full bytes changed')
                        return actual_ref
                    return {key:number_host_refs(item) for key,item in value.items()}
                if type(value) is list:
                    return [number_host_refs(item) for item in value]
                return value
            number_host = number_host_refs(number_raw)
            number_host['original_media_raw'] = record(media_facts)
            number_host['original_primary_export'] = record(exported)
            number_path = owner.output / 'number-permission-source580.json'
            write_json(number_path, number_host)
            report['number_permission_source_export'] = record(number_path)
            require(record(archive_input) == report['number_permission_input'] and
                    actual['number580_archive'] == archive_binding,
                    'actual Number archive input changed during original export')
            clean(owner, root, args.commit); checked(receipt_row); checked(product['package'])
            report.update(source_export=record(exported), export_sha256=sha(owner.output / 'export.json'), exit_code=0, run_id=owner.owner)
        except BaseException as error:
            report.update(exit_code=1, error=type(error).__name__ + ': ' + str(error)); owner.note_failure(error)
        finally:
            finish_report(owner, report, path)
    print(__import__('json').dumps({k: report.get(k) for k in ('exit_code', 'error', 'cleanup_verified', 'export_sha256')}))
    return report['exit_code']


if __name__ == '__main__': raise SystemExit(main())
