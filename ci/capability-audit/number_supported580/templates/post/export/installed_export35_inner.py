"""UNEXECUTED RO DSO export; honest recipe anchor, not whole-tree rebuild proof."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import re
import sys

p = argparse.ArgumentParser()
p.add_argument('--commit', required=True); p.add_argument('--tree-sha256', required=True)
p.add_argument('--frozen-manifest-sha256', required=True); p.add_argument('--frozen-manifest-host-path', required=True)
p.add_argument('--package-receipt-sha256', required=True); p.add_argument('--package-receipt-host-path', required=True)
p.add_argument('--actual-manifest-sha256', required=True)
a = p.parse_args()
sys.path.insert(0, '/work/ci/capability-audit')
from production579_target import context
import batch_system_build_runtime_helpers as native
manifest_file = Path('/actual-package-manifest.json')
manifest_raw = manifest_file.read_bytes()
assert hashlib.sha256(manifest_raw).hexdigest() == a.actual_manifest_sha256
actual_metadata = json.loads(manifest_raw)
actual_context = context(actual_metadata)
S = Path('/ohos'); O = S / 'out' / actual_context['product']; E = Path('/evidence/native-export'); E.mkdir(exist_ok=False)
NAMES = {'libaccesstoken_sdk.z.so', 'libapp_manager.z.so', 'libc++.so', 'libc.so',
         'libcjson.z.so', 'libclang_rt.ubsan_minimal.so', 'libconfigpolicy_util.z.so', 'libutils.z.so',
         'libvibrator_proxy_2.0.z.so', 'libsamgr_proxy.z.so', 'libasound.so',
         'libnapi_base_context.z.so', 'libipc_napi.z.so', 'libipc_single.z.so', 'libace_napi.z.so'}
ONSET579_NAMES = {'libaudio_common.z.so', 'libaudio_engine_utils.z.so', 'libaudio_engine_node.z.so',
    'libaudio_process_service.z.so', 'libaudio_effect.z.so', 'libaudio_render_adapter.z.so',
    'libaudio_primary_impl_vendor.z.so'}
PROVENANCE579_NAMES = {'libaudio_haptic.z.so', 'libmedia_engine_histreamer.z.so',
    'libmedia_plugin_AudioServerSink.z.so'}
OWNING_SERVICES579_NAMES = {'libhidumper_client.z.so', 'libdata_transit_mgr.z.so',
    'libdslm_sdk.z.so', 'libdeviceauth_sdk.z.so'}
MSDP579_NAMES = {'libintention_cooperate.z.so', 'libdevicestatus_client.z.so'}
NAMES |= ONSET579_NAMES | PROVENANCE579_NAMES | OWNING_SERVICES579_NAMES | MSDP579_NAMES
MEDIA579_NAMES = {'libscene.so', 'libscene.z.so', 'libAGPDLL.z.so', 'libohmidi.so',
    'libPluginCamPreview.z.so', 'libPluginSceneWidget.z.so', 'libPluginAGPRender.z.so',
    'libPluginAGP3D.z.so', 'libPluginMetaObject.z.so', 'libPluginLumeSceneMetadataImporter.z.so',
    'libPluginLumeSceneImporter.z.so', 'libPluginAGPJpg.z.so', 'libPluginAGPPng.z.so',
    'libmedia_mtp.z.so', 'libusbfn_mtp_interface_service_1.0.z.so'}
NAMES |= MEDIA579_NAMES
CPU_PROVIDER579_NAMES = {'libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so','libaudio_qemu_spatial.z.so','libhilog_ndk.z.so','librawfile.z.so','libnetsys_native_manager.z.so','libvendor_intell_voice_engine.z.so','libaudio_policy_service.z.so','libaudio_effect.z.so','libhdi_sensor_impl.z.so'}
ORIGINAL15_NAMES = {'libaccesstoken_sdk.z.so','libapp_manager.z.so','libc++.so','libc.so','libcjson.z.so','libclang_rt.ubsan_minimal.so','libconfigpolicy_util.z.so','libutils.z.so','libvibrator_proxy_2.0.z.so','libsamgr_proxy.z.so','libasound.so','libnapi_base_context.z.so','libipc_napi.z.so','libipc_single.z.so','libace_napi.z.so'}
NAMES |= CPU_PROVIDER579_NAMES
NUMBER580_ROOTS = {'libnumber_identity.z.so','libnumberidentity.z.so','libnumberlookup.z.so'}
HAPTIC_FILES = (
    'base/sensors/miscdevice/utils/tools/haptic_format_converter/converter/schemas/oh_schema.json',
    'base/sensors/miscdevice/utils/tools/haptic_format_converter/tests/test_data/oh_no_curve_sample.json',
)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''): h.update(data)
    return h.hexdigest()


def rec(path, *, source=True):
    path = Path(path); resolved = path.resolve(); info = resolved.stat()
    assert not source or resolved.is_relative_to(S)
    assert stat.S_ISREG(info.st_mode) and info.st_size < 64 * 1024 * 1024
    assert os.statvfs(resolved).f_flag & os.ST_RDONLY
    return dict(path=str(path), resolved=str(resolved), sha256=sha(resolved), bytes=info.st_size,
                mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns, symlink=path.is_symlink())


assert os.statvfs(S).f_flag & os.ST_RDONLY and os.statvfs(O).f_flag & os.ST_RDONLY
frozen_file = Path('/frozen-inputs/build-inputs.json'); frozen_before = rec(frozen_file, source=False)
assert frozen_before['sha256'] == a.frozen_manifest_sha256
frozen = json.loads(frozen_file.read_text())
assert frozen['source_git_revision'] == a.commit and frozen['tree_sha256'] == a.tree_sha256
receipt_file = Path('/package-receipt.json'); receipt_before = rec(receipt_file, source=False)
assert receipt_before['sha256'] == a.package_receipt_sha256
receipt = json.loads(receipt_file.read_text())
assert receipt['source_commit'] == a.commit and receipt['owned_container_absent'] is True and receipt['owned_launcher_group_closed'] is True
manifest_observation = rec(manifest_file, source=False)
assert manifest_observation['sha256'] == a.actual_manifest_sha256
number_archive_file = Path('/evidence/number580-archive-input.json')
number_archive_raw = number_archive_file.read_bytes()
number_archive = json.loads(number_archive_raw)
assert set(number_archive) == {'schema','source_commit','archive','actual_package_manifest_sha256'}
assert number_archive['schema'] == 'number580-original-export-archive-input/v1'
assert number_archive['source_commit'] == a.commit and number_archive['actual_package_manifest_sha256'] == a.actual_manifest_sha256
assert set(number_archive['archive']) == {'path','sha256','bytes'}
assert re.fullmatch('[a-f0-9]{64}',number_archive['archive']['sha256']) and number_archive['archive']['bytes'] > 0
meta = S / actual_context['metadata_relative']; anchor = rec(meta)
revision = json.loads(meta.read_text())['privacycenter_provider']['native_source_revision']
assert revision == a.commit
anchor_copy = E / 'source-identity' / meta.name; anchor_copy.parent.mkdir()
shutil.copyfile(meta, anchor_copy); assert sha(anchor_copy) == anchor['sha256']
source_identity = dict(schema='F-source-identity-observation35/v1', source_root=str(S),
    product_commit=a.commit, tree_sha256=a.tree_sha256,
    package_build_receipt=dict(path=a.package_receipt_host_path, sha256=a.package_receipt_sha256),
    retained_frozen_manifest=dict(path=a.frozen_manifest_host_path, sha256=a.frozen_manifest_sha256, bytes=frozen_before['bytes']),
    native_source_recipe_anchor=dict(native_source_revision=revision, metadata=anchor,
        export_relative=str(anchor_copy.relative_to(E))),
    source_ro=True, out_ro=True, whole_source_tree_verified=False, full_rebuild_claimed=False,
    scope='Actual RO recipe/native revision anchor plus this completed launcher frozen manifest; not proof every source/GN was freshly rebuilt; staged/image full bytes await profile16')
rows = []; graphs = []; readelf = S / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-readelf'
# Resolve the complete actual installed DT_NEEDED closure from fixed normal CPU
# roots. No name/command/function/role comes from the DATA packet.
media_dependency_closure=set(); dependency_candidates={}; metadata={}
for partition in ('system','vendor'):
    root=O/'packages/phone'/partition
    for candidate in sorted(root.rglob('*')):
        if not candidate.is_file() or candidate.is_symlink() or '/module/arkts/' in str(candidate):continue
        if candidate.name in {'libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so'} and partition!='vendor':continue
        if not re.fullmatch(r'(?:lib[A-Za-z0-9_.+\-]+\.so(?:\.[0-9]+)*|ld-musl-[A-Za-z0-9_+\-]+\.so\.1)',candidate.name):continue
        soname=native.elf_soname(candidate,product=actual_context['product'])
        if soname in dependency_candidates:
            assert sha(dependency_candidates[soname])==sha(candidate),'ambiguous installed provider dependency bytes'
            continue
        dependency_candidates[soname]=candidate
pending=sorted(CPU_PROVIDER579_NAMES)
while pending:
    name=pending.pop()
    if name in media_dependency_closure:continue
    assert name in dependency_candidates,'actual installed CPU provider dependency absent: '+name
    path=dependency_candidates[name]
    result=subprocess.run([str(readelf),'-h','-d',str(path)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0
    metadata[name]=result.stdout;media_dependency_closure.add(name)
    assert len(media_dependency_closure)<=256,'complete fixed CPU closure budget; never truncate'
    for needed in re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]',result.stdout):
        assert re.fullmatch(r'[A-Za-z0-9_.+\-]+',needed)
        pending.append(needed)
NAMES |= media_dependency_closure

# Independent exact Number closure. Original CPU/original15 selection is intact.
number_dependency_closure=set();number_dependency_edges={}
number_pending=sorted(NUMBER580_ROOTS) if actual_context['device']=='phone' else []
while number_pending:
    name=number_pending.pop()
    if name in number_dependency_closure:continue
    assert name in dependency_candidates,'actual installed Number dependency absent: '+name
    path=dependency_candidates[name]
    if name not in metadata:
        result=subprocess.run([str(readelf),'-h','-d',str(path)],capture_output=True,text=True,timeout=20)
        assert result.returncode==0 and not result.stderr
        metadata[name]=result.stdout
    needed=re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]',metadata[name])
    assert all(re.fullmatch(r'[A-Za-z0-9_.+\-]+',item) for item in needed)
    number_dependency_edges[name]=needed;number_dependency_closure.add(name)
    assert len(number_dependency_closure)<=256,'complete Number dependency closure budget; never truncate'
    number_pending.extend(needed)
NAMES |= number_dependency_closure

for partition in ('system', 'vendor'):
    for path in sorted((O / 'packages/phone' / partition).rglob('*')):
        if path.name in {'libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so'} and partition!='vendor':continue
        if (path.name not in NAMES and re.fullmatch(r'ld-musl-[A-Za-z0-9_+\-]+\.so\.1', path.name) is None) or not path.is_file(): continue
        native.elf_header(path, product=actual_context['product'])
        soname = native.elf_soname(path, product=actual_context['product'])
        assert soname in NAMES
        if soname == 'libc.so': assert path.name.startswith('ld-musl-')
        row = rec(path)
        result = subprocess.run([str(readelf), '-h', '-d', str(path)], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0
        row.update(elf=result.stdout, soname=soname, partition=partition, image_member='/' + str(path.relative_to(O / 'packages/phone' / partition)))
        destination = E / 'staged' / partition / path.relative_to(O / 'packages/phone' / partition)
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, destination)
        assert sha(destination) == row['sha256']; row['export_relative'] = str(destination.relative_to(E)); rows.append(row)
for path in sorted((O / 'obj/third_party/alsa-lib').rglob('*.ninja')):
    row = rec(path); destination = E / 'graphs' / path.relative_to(O)
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, destination)
    row['export_relative'] = str(destination.relative_to(E)); graphs.append(row)
source_identity['same_RO_ALSA_graphs'] = [{k: row[k] for k in ('path', 'sha256', 'bytes')} for row in graphs]
haptic_sources = []
head_argv = ['git', '-C', str(S / 'base/sensors/miscdevice'), 'rev-parse', 'HEAD']
head = subprocess.run(head_argv, capture_output=True, text=True, timeout=20)
assert head.returncode == 0 and len(head.stdout.strip()) == 40 and not head.stderr
for relative in HAPTIC_FILES:
    path = S / relative; row = rec(path)
    destination = E / 'haptic-source' / relative
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, destination)
    assert sha(destination) == row['sha256'] and rec(path) == row
    row['export_relative'] = str(destination.relative_to(E)); haptic_sources.append(row)
value = dict(scope='RO installed runtime DSOs/ELF and actual ALSA GN anchors ONLY', source_root=str(S), out=str(O),
    product=actual_context['product'], device=actual_context['device'], actual_package_context=actual_context,
    actual_package_manifest=manifest_observation, source_ro=True, out_ro=True, files=rows, alsa_graphs=graphs,
    readelf=rec(readelf), media579_dependency_closure=sorted(media_dependency_closure), media579_original15=sorted(ORIGINAL15_NAMES), number580_dependency_closure=sorted(number_dependency_closure), number580_dependency_edges=number_dependency_edges, number580_roots=sorted(NUMBER580_ROOTS) if actual_context['device']=='phone' else [], number580_archive=number_archive, source_identity=source_identity, haptic_sources=haptic_sources,
    haptic_source_head=dict(argv=head_argv, exit_code=head.returncode, stdout=head.stdout, stderr=head.stderr))
assert rec(meta) == anchor and rec(frozen_file, source=False) == frozen_before and rec(receipt_file, source=False) == receipt_before
assert number_archive_file.read_bytes() == number_archive_raw
assert all(sha(Path(row['resolved'])) == row['sha256'] for row in rows + graphs)
(E / 'installed-runtime-export.json').write_text(json.dumps(value, indent=2) + '\n')
(Path('/evidence') / 'export.json').write_text(json.dumps(dict(scope='actual new staged DSOs and unchanged RO source/out inputs only',
    files=len(rows), export_sha256=sha(E / 'installed-runtime-export.json'), source_out_written=False,
    source_identity=source_identity), indent=2) + '\n')
print(json.dumps(dict(files=len(rows), alsa_graphs=len(graphs), missing=sorted(NAMES - {row['soname'] for row in rows}))))
