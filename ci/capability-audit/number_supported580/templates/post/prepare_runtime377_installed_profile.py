"""Canonical new-package image/staged full-byte profile; explicit QA and immutable inputs."""
from pathlib import Path
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

import runtime_source377_common as context

COMMIT = None
ROOT = None
inputs = None
BASE = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')
ONSET579_NAMES = {'libaudio_common.z.so', 'libaudio_engine_utils.z.so', 'libaudio_engine_node.z.so',
    'libaudio_process_service.z.so', 'libaudio_effect.z.so', 'libaudio_render_adapter.z.so',
    'libaudio_primary_impl_vendor.z.so'}
PROVENANCE579_NAMES = {'libaudio_haptic.z.so', 'libmedia_engine_histreamer.z.so',
    'libmedia_plugin_AudioServerSink.z.so'}
SUPPLEMENT579_NAMES = ONSET579_NAMES | PROVENANCE579_NAMES
OWNING_SERVICES579_NAMES = {'libhidumper_client.z.so', 'libdata_transit_mgr.z.so',
    'libdslm_sdk.z.so', 'libdeviceauth_sdk.z.so'}
MSDP579_NAMES = {'libintention_cooperate.z.so', 'libdevicestatus_client.z.so'}
EXPORTED_SUPPLEMENT579_NAMES = SUPPLEMENT579_NAMES | OWNING_SERVICES579_NAMES | MSDP579_NAMES
MEDIA579_NAMES = {'libscene.so', 'libscene.z.so', 'libAGPDLL.z.so', 'libohmidi.so',
    'libPluginCamPreview.z.so', 'libPluginSceneWidget.z.so', 'libPluginAGPRender.z.so',
    'libPluginAGP3D.z.so', 'libPluginMetaObject.z.so', 'libPluginLumeSceneMetadataImporter.z.so',
    'libPluginLumeSceneImporter.z.so', 'libPluginAGPJpg.z.so', 'libPluginAGPPng.z.so',
    'libmedia_mtp.z.so', 'libusbfn_mtp_interface_service_1.0.z.so'}


def record(path):
    return dict(path=str(Path(path).resolve()), sha256=inputs.sha(path), bytes=Path(path).stat().st_size)



def source_identity(export, staged, staged_file, manifest, commit, package_descriptor, context579):
    identity = export['source_identity']
    assert identity == staged['source_identity']
    assert identity['schema'] == 'F-source-identity-observation35/v1'
    assert identity['product_commit'] == commit == manifest['source_git_revision']
    assert identity['tree_sha256'] == manifest['tree_sha256']
    assert identity['package_build_receipt'] == package_descriptor
    assert identity['source_ro'] is True and identity['out_ro'] is True
    assert identity['whole_source_tree_verified'] is False and identity['full_rebuild_claimed'] is False
    frozen = inputs.load(inputs.checked(identity['retained_frozen_manifest']))
    assert frozen == manifest, 'actual frozen launcher inputs must equal canonical new package inputs'
    anchor = identity['native_source_recipe_anchor']
    assert anchor['native_source_revision'] == commit
    expected_metadata = '/ohos/' + context579['metadata_relative']
    assert anchor['metadata']['path'] == anchor['metadata']['resolved'] == expected_metadata
    assert anchor['metadata']['symlink'] is False
    relative = Path(anchor['export_relative'])
    assert not relative.is_absolute() and '..' not in relative.parts
    metadata = inputs.regular(staged_file.parent / relative)
    assert inputs.sha(metadata) == anchor['metadata']['sha256'] and metadata.stat().st_size == anchor['metadata']['bytes']
    assert inputs.load(metadata)['privacycenter_provider']['native_source_revision'] == commit
    return identity


def number580_permission_profile(*, output, export, export_file, staged_file, context579,
        archive, images, original_profile, base_profile, debugfs, call, product_file, producer_before):
    """Independent image dumps in the original profile callback; never runtime15."""
    source_ref = export['number_permission_source_export']
    source_file = inputs.checked(source_ref)
    source_before = record(source_file)
    assert source_before == source_ref
    facts = inputs.load(source_file)
    assert facts['schema'] == 'number580-actual-source-compile-export/v1'
    assert facts['source_commit'] == COMMIT and facts['archive_sha256'] == archive['sha256']
    assert facts['product'] == context579['product'] and facts['device'] == context579['device']
    assert facts['source_ro'] is True and facts['out_ro'] is True and facts['source_root'] == '/ohos'
    assert facts['runtime_pass'] is False and facts['first_artifact_behavior_gate_passed'] is False
    assert facts['image_report_attached'] is False and facts['same_archive_image_binding_still_required'] is True
    assert facts['original_primary_export'] == record(staged_file)
    common = dict(schema='number580-actual-permission-installed-profile/v1', source_commit=COMMIT,
        archive=archive, product=context579['product'], device=context579['device'],
        source_export=source_ref, export_receipt=record(export_file), package_receipt=record(product_file),
        build_inputs=record(output / 'build-inputs.json'), original_profile=record(original_profile),
        profile_producer_source=producer_before, images=images, entries={},
        runtime_pass=False, first_artifact_behavior_gate_passed=False)
    destination = output / 'number580-permission-installed-profile.json'
    assert not destination.exists()
    if context579['device'] != 'phone':
        assert context579['device'] == '2in1'
        assert facts['profile_disposition'] == 'not_applicable_to_original_phone_Number_subset'
        assert facts['sources'] == {} and facts['compile_units'] == [] and facts['libraries'] == {}
        assert facts['installed_dependency_closure'] == []
        common['profile_disposition'] = 'not_applicable_to_original_phone_Number_subset'
        assert record(source_file) == source_before
        destination.write_text(json.dumps(common, indent=2) + '\n')
        return {'number580_permission_installed_profile': record(destination)}
    assert facts['profile_disposition'] == 'actual_original_phone_Number_source_compile_dependency_export'
    assert set(facts['sources']) == {'number_napi','number_errors','mark_ability','core_util','core_errors','js_errors'}
    assert facts['sources']['number_napi']['sha256'] == '36a024778c3057f8f3dbe7ad620e5e8446f47cfe718e71c2d0edf65a92a97582'
    roots = {'libnumber_identity.z.so','libnumberidentity.z.so','libnumberlookup.z.so'}
    units = facts['compile_units']
    assert units and {unit['role'] for unit in units} == {'number_napi','mark_ability','core_util'}
    assert all(unit['source_logical'] in {
        'base/telephony/number_identity/frameworks/js/src/napi_number_identity.cpp',
        'base/telephony/number_identity/number_mark/src/number_mark_ability.cpp',
        'base/telephony/core_service/frameworks/js/napi/napi_util.cpp'} for unit in units)
    assert any(unit['role']=='number_napi' and unit['owning_soname']=='libnumberidentity.z.so' for unit in units)
    assert any(unit['role']=='mark_ability' and unit['owning_soname']=='libnumber_identity.z.so' for unit in units)
    core_owners = {unit['owning_soname'] for unit in units if unit['role']=='core_util'}
    wanted = roots | core_owners
    closure = {}
    for row in facts['installed_dependency_closure']:
        assert row['soname'] not in closure
        closure[row['soname']] = row
    assert wanted <= set(closure) and len(closure) <= 256
    for unit in units:
        owner = unit['owning_soname']; library = facts['libraries'][owner]
        assert unit in library['permission_translation_units']
        assert unit['unit']['source'] == facts['sources'][unit['role']]
        assert unit['owning_staged_sha256'] == library['staged']['sha256']
        assert library['linked_output']['sha256'] == library['installed_file']['sha256'] == library['staged']['sha256']
        assert library['linked_output']['bytes'] == library['installed_file']['bytes'] == library['staged']['bytes']
    dump_folder = output / 'number580-image-dumps'
    assert not dump_folder.exists(); dump_folder.mkdir()
    superset = dict(base_profile, kind='installed_number580_permission_dsos', dsos=dict(base_profile['dsos']))
    image_paths = set()
    for name in sorted(wanted):
        assert re.fullmatch(r'[A-Za-z0-9_.+\-]+', name)
        item = closure[name]; staged_row = item['staged']
        source_copy = inputs.checked(item['file'])
        assert inputs.sha(source_copy) == staged_row['sha256'] and source_copy.stat().st_size == staged_row['bytes']
        aliases = item['staged_aliases']
        assert aliases and staged_row in aliases
        proofs = []
        for index, row in enumerate(aliases):
            assert row['soname'] == name and row['symlink'] is False
            assert (row['sha256'],row['bytes']) == (staged_row['sha256'],staged_row['bytes'])
            partition, member = row['partition'], row['image_member']
            assert partition in ('system','vendor') and partition in images
            assert member.startswith(('/lib64/','/lib/')) and '..' not in Path(member).parts
            assert row['path'] == '/ohos/out/' + context579['product'] + '/packages/phone/' + partition + member
            assert (partition,member) not in image_paths; image_paths.add((partition,member))
            image = inputs.checked(images[partition])
            label = 'number580-' + name + '-' + str(index)
            raw = call([debugfs,'-R','stat ' + member,image],label + '-stat')
            inode = re.findall(r'^Inode:\s+([1-9][0-9]*)\s+Type:\s+regular\s',raw,re.M)
            assert len(inode) == 1
            dumped = dump_folder / (name + '-' + str(index) + '.bin')
            assert not dumped.exists()
            call([debugfs,'-R','dump ' + member + ' ' + str(dumped),image],label + '-dump')
            dumped = inputs.regular(dumped)
            assert inputs.sha(dumped) == inputs.sha(source_copy) == row['sha256']
            assert dumped.stat().st_size == source_copy.stat().st_size == row['bytes']
            proofs.append(dict(staged=row,staged_file=record(source_copy),image_file=record(dumped),
                image=images[partition],partition=partition,image_member=member,image_inode=int(inode[0]),
                debugfs_stat_label=label + '-stat',debugfs_dump_label=label + '-dump'))
        canonical = proofs[aliases.index(staged_row)]
        common['entries'][name] = dict(soname=name,staged_file=record(source_copy),
            image_file=canonical['image_file'],image_member=canonical['image_member'],
            partition=canonical['partition'],image=canonical['image'],aliases=proofs,
            compile_roles=sorted({unit['role'] for unit in units if unit['owning_soname']==name}))
        if name in superset['dsos']:
            assert superset['dsos'][name]['staged']['sha256'] == staged_row['sha256']
            assert superset['dsos'][name]['image_file']['sha256'] == staged_row['sha256']
        else:
            superset['dsos'][name] = dict(soname=name,
                staged=dict(path=staged_row['path'],sha256=staged_row['sha256'],bytes=staged_row['bytes']),
                image_file=dict(path='/runtime-profile/number580-image-dumps/' + Path(canonical['image_file']['path']).name,
                    sha256=staged_row['sha256'],bytes=staged_row['bytes']),image_member=canonical['image_member'])
    assert set(common['entries']) == wanted and roots <= set(common['entries'])
    assert set(base_profile['dsos']) <= set(superset['dsos'])
    assert all(superset['dsos'][name] == value for name,value in base_profile['dsos'].items())
    common.update(profile_disposition='actual_same_archive_Number3_and_Coreutil_owner_image_staged_fullbytes',
        required_roots=sorted(roots),core_util_owners=sorted(core_owners),
        profile=superset,original_profile_unchanged=True)
    assert record(source_file) == source_before
    destination.write_text(json.dumps(common, indent=2) + '\n')
    return {'number580_permission_installed_profile': record(destination)}


def main(argv=None):
    global COMMIT, ROOT, inputs
    if not __debug__: raise RuntimeError("strict profile checks cannot run with Python optimization")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--here', type=Path, required=True)
    p.add_argument('--qa-root', type=Path, required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--package-receipt', type=Path, required=True)
    p.add_argument('--package-receipt-sha256', required=True)
    p.add_argument('--export-receipt', type=Path, required=True)
    p.add_argument('--export-receipt-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    here, ROOT = context.directory(args.here), context.directory(args.qa_root)
    inputs = context.descriptor_inputs(here)
    producer_before = context.record(Path(__file__).resolve())
    dependency_before = context.verify_dependencies(here)
    COMMIT = args.commit
    assert re.fullmatch('[a-f0-9]{40}', COMMIT) and COMMIT != 'c14e803c33f96f5fe01e04378c868fce32aa1487'
    lease_path = BASE / '.representative10-resource.lock'
    with os.fdopen(os.open(lease_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'a') as lease:
        current, named = os.fstat(lease.fileno()), lease_path.stat()
        assert current.st_nlink == 1 and (current.st_dev, current.st_ino) == (named.st_dev, named.st_ino)
        assert context.regular(lease_path) == lease_path
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not (BASE / '.representative35-unresolved.json').exists(), 'unresolved Owner35 quarantine requires root recovery'
        return prepare(args, here, producer_before, dependency_before)


def prepare(args, here, producer_before, dependency_before):
    assert inputs.git(ROOT, 'rev-parse', 'HEAD') == COMMIT and not inputs.git(ROOT, 'status', '--short'), 'exact final clean canonical QA commit required'
    product_file = inputs.checked(dict(path=str(args.package_receipt.resolve()), sha256=args.package_receipt_sha256))
    export_file = inputs.checked(dict(path=str(args.export_receipt.resolve()), sha256=args.export_receipt_sha256))
    product, export = inputs.load(product_file), inputs.load(export_file)
    assert type(product['exit_code']) is int and product['exit_code'] == 0 and product['source_commit'] == COMMIT and product['owned_container_absent'] is True and product['owned_launcher_group_closed'] is True
    archive = inputs.checked(product['package'])
    archive_before = archive.stat()
    archive_identity = tuple(getattr(archive_before, k) for k in ('st_dev','st_ino','st_nlink','st_mode','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns'))
    assert type(export['exit_code']) is int and export['exit_code'] == 0 and export['cleanup_verified'] is True and export['source_commit'] == COMMIT
    assert export['package_build_receipt'] == dict(path=str(product_file), sha256=args.package_receipt_sha256)
    assert export['package'] == product['package']
    staged_file = inputs.checked(export['source_export'])
    staged = inputs.load(staged_file)
    assert staged['source_ro'] is True and staged['out_ro'] is True and staged['source_root'] == '/ohos'
    out = args.output.resolve()
    assert out.parent == BASE and not out.is_relative_to(ROOT) and not out.is_relative_to(here) and not out.exists()
    out.mkdir(); (out / 'image-dumps').mkdir(); (out / 'commands').mkdir()
    report = dict(status='fail', scope='same-new-archive actual image/staged full bytes ONLY; no guest acceptance',
                  source_commit=COMMIT, qa_root=str(ROOT), here=str(here),
                  profile_producer_source=producer_before, dependency_sources=dependency_before,
                  package=record(archive), export_receipt=record(export_file),
                  source_export=record(staged_file), commands=[], first_artifact_behavior_gate_passed=False,
                  remaining_five_started=False)

    def save():
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')

    def call(argv, label):
        row = dict(argv=list(map(str, argv)), exit_code=None, timed_out=False)
        report['commands'].append(row); save()
        stdout = stderr = b''
        try:
            result = subprocess.run(row['argv'], capture_output=True, timeout=90)
            stdout, stderr = result.stdout, result.stderr
            row['exit_code'] = result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr = error.stdout or b'', error.stderr or b''
            row.update(timed_out=True, error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            for name, data in (('stdout', stdout), ('stderr', stderr)):
                path = out / 'commands' / (label + '-' + name + '.bin')
                path.write_bytes(data); row[name] = record(path)
            save()
        assert row['exit_code'] == 0
        return stdout.decode()

    save()
    try:
        # Independent copies keep the original package/image inode/link metadata
        # unchanged and form one self-contained read-only compiler mount.
        copied_archive = out / 'F.tar.gz'
        shutil.copyfile(archive, copied_archive)
        assert inputs.sha(copied_archive) == report['package']['sha256']
        prefix = archive.name.removesuffix('.tar.gz') + '/'
        chosen = {prefix + 'images/' + n + '.img': n + '.img' for n in ('system', 'vendor', 'chip_prod')}
        chosen[prefix + 'build-inputs.json'] = 'build-inputs.json'
        chosen[prefix + 'manifest.json'] = 'manifest.json'
        usb_kernel = {'arm64_virt':'Image','armv7a_virt':'zImage','x86_64_virt':'bzImage'}[staged['product']]
        chosen[prefix + 'images/' + usb_kernel] = 'usb579-' + usb_kernel
        # Keep the original mandatory three images and export every additional
        # finite real product partition present in this actual archive.
        optional_images = {}
        seen = set()
        with tarfile.open(archive, 'r:gz') as stream:
            for member in stream:
                for partition in ('sys_prod', 'system_ext', 'product'):
                    if member.name == prefix + 'images/' + partition + '.img':
                        assert partition not in optional_images and member.isfile()
                        optional_images[partition] = partition + '.img'
                        chosen[member.name] = partition + '.img'
                if member.name not in chosen: continue
                assert member.name not in seen and member.isfile() and 0 < member.size <= 16 * 1024**3
                if member.name.endswith(('/build-inputs.json', '/manifest.json')): assert member.size <= 4 * 1024**2
                seen.add(member.name)
                destination = out / chosen[member.name]
                source = stream.extractfile(member)
                assert source is not None
                with source, destination.open('xb') as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                assert destination.stat().st_size == member.size
        assert seen == set(chosen)
        report['usb579_kernel_image'] = record(out / ('usb579-' + usb_kernel))
        manifest = inputs.load(out / 'build-inputs.json')
        sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'ci/capability-audit')]
        from snapshot_build_inputs import digest_files
        from verify_alsa_config_image import debugfs_path
        from batch_system_build_runtime_helpers import validate_installed_profile
        from production579_target import context as package_context
        actual_metadata = inputs.load(out / 'manifest.json')
        context579 = package_context(actual_metadata)
        assert prefix == context579['package_root'] + '/'
        assert staged['product'] == context579['product'] and staged['device'] == context579['device']
        assert staged['actual_package_manifest']['sha256'] == inputs.sha(out / 'manifest.json')
        assert manifest['source_git_revision'] == COMMIT and manifest['files_sha256'] == digest_files(ROOT)
        assert manifest['tree_sha256'] == hashlib.sha256(json.dumps(manifest['files_sha256'], sort_keys=True).encode()).hexdigest()
        report['source_identity'] = source_identity(export, staged, staged_file, manifest, COMMIT,
            dict(path=str(product_file), sha256=args.package_receipt_sha256), context579)
        debugfs = Path(debugfs_path()).resolve()
        report['debugfs'] = record(debugfs)
        report['images'] = {n: record(out / (n + '.img')) for n in ('system', 'vendor', 'chip_prod', *optional_images)}
        profile = dict(schema_version=2, kind='installed_product_runtime', product=context579['product'], arch=context579['arch'],
                       device=context579['device'], source_root='/ohos', archive=dict(path='/runtime-profile/F.tar.gz',
                       sha256=report['package']['sha256'], bytes=archive.stat().st_size), dsos={},
                       package_manifest=dict(path='/runtime-profile/manifest.json', sha256=inputs.sha(out / 'manifest.json'),
                           bytes=(out / 'manifest.json').stat().st_size, archive_member=prefix + 'manifest.json'),
                       package_metadata=actual_metadata)
        if (context579['product'],context579['device']) == ('arm64_virt','phone'):
            # Preserve the original representative runtime contract exactly.
            # Full real manifest observation remains in the export/report.
            profile['schema_version'] = 1
            profile.pop('package_manifest'); profile.pop('package_metadata')
        for n in ('system', 'vendor'):
            profile[n + '_image'] = dict(path='/runtime-profile/' + n + '.img',
                                         sha256=report['images'][n]['sha256'], bytes=report['images'][n]['bytes'],
                                         archive_member=prefix + 'images/' + n + '.img')
        # Number adds separate fixed roots; keep original profile row selection exact.
        number_only_names = set(staged['number580_dependency_closure']) - (
            set(staged['media579_original15']) | EXPORTED_SUPPLEMENT579_NAMES |
            MEDIA579_NAMES | set(staged['media579_dependency_closure']))
        rows = {}
        for row in staged['files']:
            if row['soname'] in number_only_names: continue
            if row['symlink'] or '/module/arkts/' in row['path']: continue
            names = re.findall(r'\(SONAME\)\s+Library soname: \[([^\]]+)\]', row['elf'])
            assert len(names) == 1 and names[0] not in rows
            rows[names[0]] = row
        original15 = set(staged['media579_original15'])
        assert len(original15) == 15 and original15 == {'libaccesstoken_sdk.z.so','libapp_manager.z.so','libc++.so','libc.so','libcjson.z.so','libclang_rt.ubsan_minimal.so','libconfigpolicy_util.z.so','libutils.z.so','libvibrator_proxy_2.0.z.so','libsamgr_proxy.z.so','libasound.so','libnapi_base_context.z.so','libipc_napi.z.so','libipc_single.z.so','libace_napi.z.so'}
        MEDIA579_NAMES.update(set(staged['media579_dependency_closure']) - original15 - EXPORTED_SUPPLEMENT579_NAMES)
        assert EXPORTED_SUPPLEMENT579_NAMES <= set(rows) and len(set(rows) - EXPORTED_SUPPLEMENT579_NAMES - MEDIA579_NAMES) == 15
        assert 'libohmidi.so' in rows and 'libAGPDLL.z.so' in rows and len({'libscene.so', 'libscene.z.so'} & rows.keys()) == 1
        proofs = {}
        for name, row in sorted(rows.items()):
            assert re.fullmatch('[A-Za-z0-9_.+-]+', name)
            image = out / (row['partition'] + '.img')
            member = row['image_member']
            assert (member.startswith(('/lib64/', '/lib/')) and
                    (name != 'libc.so' or row['partition'] == 'system' and
                     re.fullmatch(r'ld-musl-[A-Za-z0-9_+\-]+\.so\.1', Path(member).name) is not None)) and '..' not in Path(member).parts, \
                'unproved installed image path: ' + name + ': ' + member
            raw = call([debugfs, '-R', 'stat ' + member, image], name + '-stat')
            inode = re.findall(r'^Inode:\s+([1-9][0-9]*)\s+Type:\s+regular\s', raw, re.M)
            assert len(inode) == 1
            dest = out / 'image-dumps' / Path(member).name
            assert not dest.exists()
            call([debugfs, '-R', 'dump ' + member + ' ' + str(dest), image], name + '-dump')
            exported = inputs.regular(staged_file.parent / row['export_relative'])
            assert inputs.sha(dest) == inputs.sha(exported) == row['sha256'] and dest.stat().st_size == exported.stat().st_size == row['bytes']
            assert row['path'].startswith('/ohos/out/' + context579['product'] + '/packages/phone/' + row['partition'] + '/')
            if name not in EXPORTED_SUPPLEMENT579_NAMES | MEDIA579_NAMES:
                profile['dsos'][name] = dict(soname=name, staged=dict(path=row['path'], sha256=row['sha256'], bytes=row['bytes']),
                                             image_file=dict(path='/runtime-profile/image-dumps/' + dest.name, sha256=row['sha256'], bytes=row['bytes']),
                                             image_member=member)
            proofs[name] = dict(staged=row, actual_image=record(dest), image_inode=int(inode[0]), partition=row['partition'])
        validate_installed_profile(profile, archive_sha256=report['package']['sha256'])
        path = out / 'runtime-profile.json'; path.write_text(json.dumps(profile, indent=2) + '\n')
        onset_path = out / 'audio-onset579-installed-dsos.json'
        onset_profile = dict(profile, kind='installed_audio_onset_dsos', dsos={})
        supplement_entries = {}
        for name in sorted(SUPPLEMENT579_NAMES):
            proof = proofs[name]; row = proof['staged']
            supplement_entries[name] = dict(soname=name,
                staged=dict(path=row['path'], sha256=row['sha256'], bytes=row['bytes']),
                image_file=dict(path='/runtime-profile/image-dumps/' + Path(proof['actual_image']['path']).name,
                    sha256=row['sha256'], bytes=row['bytes']), image_member=row['image_member'])
        onset_profile['dsos'] = {name: supplement_entries[name] for name in sorted(ONSET579_NAMES)}
        onset = dict(schema='actual-package-audio-onset579-installed-dsos/v1', source_commit=COMMIT,
            archive=report['package'], package_receipt=record(product_file), build_inputs=record(out / 'build-inputs.json'),
            export_receipt=record(export_file), source_export=record(staged_file),
            profile_producer_source=producer_before, original_profile=record(path), images=report['images'],
            profile=onset_profile, proofs={name: proofs[name] for name in sorted(ONSET579_NAMES)},
            provenance_dsos={name: dict(entry=supplement_entries[name], proof=proofs[name])
                for name in sorted(PROVENANCE579_NAMES)},
            libasound=proofs['libasound.so'], runtime_pass=False, first_artifact_behavior_gate_passed=False)
        onset_path.write_text(json.dumps(onset, indent=2) + '\n')
        # Separate actual profile; original15 and onset7/provenance3 are unchanged.
        owning_entries = dict(profile['dsos'])
        for name in sorted(OWNING_SERVICES579_NAMES):
            proof = proofs[name]; row = proof['staged']
            owning_entries[name] = dict(soname=name,
                staged=dict(path=row['path'], sha256=row['sha256'], bytes=row['bytes']),
                image_file=dict(path='/runtime-profile/image-dumps/' + Path(proof['actual_image']['path']).name,
                    sha256=row['sha256'], bytes=row['bytes']), image_member=row['image_member'])
        owning_profile = dict(profile, dsos=owning_entries)
        validate_installed_profile(owning_profile, archive_sha256=report['package']['sha256'])
        owning_path = out / 'owning-services579-installed-profile.json'
        owning_path.write_text(json.dumps(owning_profile, indent=2) + '\n')
        owning_proof = dict(schema='actual-package-owning-services579-installed-dsos/v1', source_commit=COMMIT,
            archive=report['package'], package_receipt=record(product_file), build_inputs=record(out / 'build-inputs.json'),
            export_receipt=record(export_file), source_export=record(staged_file),
            profile_producer_source=producer_before, original_profile=record(path), expanded_profile=record(owning_path),
            images=report['images'], added_dsos={name: proofs[name] for name in sorted(OWNING_SERVICES579_NAMES)},
            runtime_pass=False, first_artifact_behavior_gate_passed=False)
        owning_proof_path = out / 'owning-services579-installed-dsos.json'
        owning_proof_path.write_text(json.dumps(owning_proof, indent=2) + '\n')
        # Distinct single Cooperate DSO sidecar; original15/Own19/onset sets unchanged.
        msdp_entries = {}
        for name in sorted(MSDP579_NAMES):
            proof = proofs[name]; row = proof['staged']
            msdp_entries[name] = dict(soname=name,
                staged=dict(path=row['path'], sha256=row['sha256'], bytes=row['bytes']),
                image_file=dict(path='/runtime-profile/image-dumps/' + Path(proof['actual_image']['path']).name,
                    sha256=row['sha256'], bytes=row['bytes']), image_member=row['image_member'])
        msdp_profile = dict(profile, dsos=dict(profile['dsos'], **{name: msdp_entries[name] for name in sorted(MSDP579_NAMES)}))
        validate_installed_profile(msdp_profile, archive_sha256=report['package']['sha256'])
        msdp_profile_path = out / 'msdp579-installed-profile.json'
        msdp_profile_path.write_text(json.dumps(msdp_profile, indent=2) + '\n')
        msdp_path = out / 'msdp579-installed-dsos.json'
        msdp_path.write_text(json.dumps(dict(schema='actual-package-msdp579-installed-dsos/v1',
            source_commit=COMMIT, archive=report['package'], package_receipt=record(product_file),
            build_inputs=record(out / 'build-inputs.json'), export_receipt=record(export_file),
            source_export=record(staged_file), profile_producer_source=producer_before,
            expanded_profile=record(msdp_profile_path), original_profile=record(path),
            entries=msdp_entries, proofs={name: proofs[name] for name in sorted(MSDP579_NAMES)},
            runtime_pass=False, first_artifact_behavior_gate_passed=False), indent=2) + '\n')
        report.update(number580_permission_profile(output=out,export=export,export_file=export_file,
            staged_file=staged_file,context579=context579,archive=report['package'],images=report['images'],
            original_profile=path,base_profile=profile,debugfs=debugfs,call=call,
            product_file=product_file,producer_before=producer_before))
        # The existing exact image/stat/dump callback remains the only tool
        # runner. Media uses a separate superset; runtime15 stays unchanged.
        try:
            from produce_media579_product import extend_profile
            report.update(extend_profile(base_profile=profile, proofs=proofs, output=out,
                export_receipt=record(export_file), images=report['images'], debugfs=debugfs, call=call))
        except Exception as media_error:
            report['media579_profile_error'] = type(media_error).__name__ + ': ' + str(media_error)
        from produce_telephony579_product import extend_profile as extend_telephony579_profile
        report.update(extend_telephony579_profile(output=out,images=report['images'],debugfs=debugfs,call=call,
            source_commit=COMMIT,archive=report['package'],selected_profile=report['media579_installed_profile']))
        assert inputs.sha(archive) == report['package']['sha256'] and inputs.sha(staged_file) == export['source_export']['sha256']
        assert tuple(getattr(archive.stat(), k) for k in ('st_dev','st_ino','st_nlink','st_mode','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')) == archive_identity
        assert context.record(Path(__file__).resolve()) == producer_before and context.verify_dependencies(here) == dependency_before
        assert inputs.git(ROOT, 'rev-parse', 'HEAD') == COMMIT and not inputs.git(ROOT, 'status', '--short'), 'canonical QA changed during profile production'
        report.update(status='pass_actual_NEW_archive_image_staged_bytes_ONLY', exit_code=0,
                      profile=record(path), dsos={name: proof for name, proof in proofs.items() if name not in EXPORTED_SUPPLEMENT579_NAMES | MEDIA579_NAMES},
                      audio_onset579_installed_dsos=record(onset_path),
                      owning_services579_installed_profile=record(owning_path),
                      msdp579_installed_dsos=record(msdp_path), msdp579_installed_profile=record(msdp_profile_path),
                      owning_services579_installed_dsos=record(owning_proof_path), build_inputs=record(out / 'build-inputs.json'),
                      original_source_package_metadata_unchanged=True)
    except Exception as error:
        report.update(exit_code=1, error=type(error).__name__ + ': ' + str(error))
    report['observed_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat(); save()
    print(json.dumps({k: report.get(k) for k in ('status', 'exit_code', 'error', 'profile')}))
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
