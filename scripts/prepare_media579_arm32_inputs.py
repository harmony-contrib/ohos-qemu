#!/usr/bin/env python3
"""Ordinary fixed file/DATA preparation in the original normal build flow.

No resource constructors, imports of candidates, business decoder or acceptance
execution. The passed actual global gate is a prerequisite, not a new verdict.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, stat

REPO = Path(__file__).resolve().parents[1]
BASE = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')


def need(value, message):
    if not value: raise ValueError(message)


def canonical(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)) and
         not any(c in str(path) for c in ('\n', '\r', '\x00', ',')), 'canonical fixed mount input')
    return path


def ref(path):
    path = canonical(path); before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'one regular immutable input')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    after = path.stat()
    names = ('st_dev','st_ino','st_size','st_mode','st_uid','st_gid','st_mtime_ns','st_ctime_ns')
    need(tuple(getattr(before,k) for k in names) == tuple(getattr(after,k) for k in names), 'input changed during source capture')
    return dict(path=str(path), sha256=digest.hexdigest(), bytes=after.st_size)


def checked(row):
    need(type(row) is dict and set(row) in ({'path','sha256'},{'path','sha256','bytes'}) and
         re.fullmatch('[a-f0-9]{64}', row['sha256']), 'fixed Ref2/Ref3 input')
    actual = ref(row['path'])
    need(actual['sha256'] == row['sha256'] and ('bytes' not in row or actual['bytes'] == row['bytes']), 'actual source/evidence identity differs')
    return actual


def load(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            need(k not in result,'duplicate DATA key');result[k]=v
        return result
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite DATA')))


def two(row):return {k:row[k] for k in ('path','sha256')}


def gate_inputs(gate_ref, commit):
    """Enumerate only published, fixed global-gate/source-vector slots."""
    files={};roots=set()
    def take(row):
        actual=checked(row);files[actual['path']]=actual;return load(actual['path'])
    gate=take(gate_ref)
    need(gate['schema']=='actual-final579-global-raw-gate/v1' and gate['status']=='pass' and
         gate['first_artifact_behavior_gate_passed'] is True and gate['failures']==[], 'actual complete global QEMU gate required')
    packet=take(gate['packet'])
    need(packet['schema']=='actual-final579-root-packet/v1' and packet['source_commit']==commit and
         gate['original_main_suite']==packet['main_suite'] and gate['original_main_attempt']==packet['main_attempt'], 'same actual source commit and original Main binding')
    for key in ('original_main_suite','original_main_attempt','raw_actor_attempt','raw_actor_result','source_vector','final_au_owner'):
        take(gate[key])
    attempt=load(gate['raw_actor_attempt']['path']);result=load(gate['raw_actor_result']['path'])
    need(attempt['schema']=='actual-final579-original-owner-actor-attempt/v1' and attempt['packet']==gate['packet'] and
         attempt['result']==gate['raw_actor_result'] and attempt['source_vector']==gate['source_vector'] and
         attempt['command']['exit_code']==0 and not attempt['command'].get('timed_out',False), 'actual completed raw actor command')
    checked_log=checked(dict(path=attempt['command']['log'],sha256=attempt['command']['sha256']));files[checked_log['path']]=checked_log
    need(result['packet']==gate['packet'] and result['source_vector']==gate['source_vector'] and result['failures']==[] and
         result['status']=='raw_union_complete_pending_original_owner_finish' and result['owner_finish_still_required'] is True and
         result['first_artifact_behavior_gate_passed'] is False and result['fullledger']==gate['fullledger'], 'raw result alone is not a gate')
    ledger=gate['fullledger'];need(ledger['obligation_complete'] is True and ledger['effective_unresolved']==[] and ledger['failures']==[], 'complete supported whole ledger')
    settlements=[gate['main_settlement'],gate['audio_settlement']]
    for name in ('network','gnss'):
        independent=gate['independent_owner_settlement'][name]
        need(independent['business_failures']==[] and independent['actual_api'] is not None, 'independent original business completed')
        for key in ('report','dedicated','actual_api','case_boot','final_boot'):take(independent[key])
        settlements.append(independent['settlement'])
    need(len({r['root'] for r in settlements})==4, 'four distinct original closures')
    for row in settlements:
        root=canonical(row['root']);need(root.is_dir() and root.is_relative_to(BASE) and
            row['original_authority_settled'] is True and row['original_constructor_tree_settled'] is True, 'original actual Owner closed')
        for key in ('held','constructors'):
            need(Path(row[key]['path']).is_relative_to(root), 'settlement references belong to the same original root');take(row[key])
        roots.add(root)
    au=load(gate['final_au_owner']['path'])
    need(au['schema']=='actual-dedicated-AU579-owner-result/v1' and au['cleanup_verified'] is True and
         au['audio_runtime_verified'] is True and au['failures']==[], 'actual AU final closure')
    take(packet['main_boot']);boot=load(packet['main_boot']['path']);env=boot['test_environment']
    need(boot['status']=='pass' and boot['purpose']=='acceptance' and boot['archive_sha256']==packet['archive']['sha256'] and
         env['external_keepalive'] is False and (env['product'],env['device_type'],env['guest_arch'])==('arm64_virt','phone','arm64'), 'actual first representative boot')
    archive=checked(packet['archive']);files[archive['path']]=archive
    vector=load(gate['source_vector']['path'])
    need(vector['source_commit']==commit and vector['pending_dependencies']==[] and type(vector['files']) is list and
         0<len(vector['files'])<=32768, 'complete finalized source vector')
    take(vector['original_kit'])
    for row in vector['files']:actual=checked(row);files[actual['path']]=actual
    need(set(vector['frozen_dependencies'])<= {'gap','calendar','paired','system','network','api','gnss','msdp'}, 'fixed source dependency families')
    for row in vector['frozen_dependencies'].values():actual=checked(row);files[actual['path']]=actual
    # These known input/source roots are mounted, never arbitrary JSON parents.
    for row in (gate_ref,gate['packet'],gate['raw_actor_attempt'],gate['raw_actor_result'],gate['source_vector'],gate['final_au_owner']):
        parent=canonical(Path(row['path']).parent)
        need(parent.is_relative_to(BASE) or parent.is_relative_to(REPO), 'known gate source/evidence root')
        if parent!=BASE:roots.add(parent)
    roots.add(REPO)
    return files,roots


def sdk_inventory(root, metadata_sha):
    """Capture the complete selected Linux SDK bytes, including internal links."""
    root=canonical(root);need(root.is_dir(), 'actual selected Linux native SDK directory')
    metadata=checked(dict(path=str(root/'oh-uni-package.json'),sha256=metadata_sha));value=load(metadata['path'])
    need(value['apiVersion']=='26' and value['path']=='native' and value['displayName']=='Native' and
         value['platformVersion']=='26.0.0' and value['releaseType']=='Release', 'actual explicit API26 native SDK metadata')
    compiler=(root/'llvm/bin/clang').resolve(strict=True)
    need(compiler.is_relative_to(root) and compiler.is_file(), 'same SDK Linux compiler')
    header=compiler.open('rb').read(20)
    need(header[:6]==b'\x7fELF\x02\x01' and int.from_bytes(header[18:20],'little')==62, 'Linux amd64 SDK compiler, never host Darwin tools')
    files={};links={};count=0;total=0
    for path in sorted(root.rglob('*')):
        count+=1;need(count<=250000,'bounded complete SDK source inventory')
        relative=str(path.relative_to(root));s=path.lstat()
        if path.is_symlink():
            target=path.resolve(strict=True);need(target.is_relative_to(root), 'SDK symlink escapes selected SDK')
            links[relative]=dict(target=os.readlink(path),resolved_relative=str(target.relative_to(root)))
        elif path.is_file():
            actual=ref(path);total+=actual['bytes'];need(total<=32*1024**3, 'bounded selected complete SDK')
            files[relative]=dict(sha256=actual['sha256'],bytes=actual['bytes'],mode=stat.S_IMODE(s.st_mode))
        else:need(path.is_dir(),'unknown SDK input type')
    need('build/cmake/ohos.toolchain.cmake' in files and files and links is not None,'complete native SDK source closure')
    return dict(schema='media579-observed-linux-native-sdk-inputs/v1',root=str(root),metadata=metadata,compiler=ref(compiler),files=files,links=links,bytes=total,source_only=True,runtime_pass=False)


def save_new(path,value):
    canonical(path.parent);need(not path.exists(),'fresh ordinary normal DATA output')
    temporary=path.with_name(path.name+'.tmp')
    with temporary.open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gate-only',action='store_true');p.add_argument('--print-mounts',type=Path);p.add_argument('--mounts-sha256')
    for key in ('representative-gate','normal-source','sdk-native','output'):p.add_argument('--'+key,type=Path)
    for key in ('representative-gate-sha256','normal-source-sha256','sdk-metadata-sha256','source-commit','source-root','product','device','normal-build-run-id'):p.add_argument('--'+key)
    a=p.parse_args()
    if a.print_mounts:
        receipt=checked(dict(path=str(a.print_mounts),sha256=a.mounts_sha256));value=load(receipt['path'])
        need(value['schema']=='media579-arm32-normal-data-mounts/v1','fixed normal mount receipt')
        for row in value['files']:checked(row)
        inputs=load(checked(value['inputs'])['path']);sdk=load(checked(value['sdk_closure'])['path'])
        need(inputs['sdk_native']==sdk['root'] and sdk_inventory(Path(sdk['root']),sdk['metadata']['sha256'])==sdk,
             'complete actual selected SDK changed before/after normal production')
        for path in value['readonly_paths']:print(canonical(path))
        return 0
    need(a.representative_gate is not None and re.fullmatch('[a-f0-9]{40}',a.source_commit or ''),'actual selected source/gate required')
    gate_ref=dict(path=str(a.representative_gate),sha256=a.representative_gate_sha256)
    files,roots=gate_inputs(gate_ref,a.source_commit)
    if a.gate_only:
        print(json.dumps(dict(representative_gate=checked(gate_ref),source_commit=a.source_commit,normal_production_prerequisite_only=True,runtime_pass=False)));return 0
    need(a.normal_source and a.sdk_native and a.output and a.product=='armv7a_virt' and a.device in ('phone','2in1') and
         re.fullmatch('[a-f0-9]{32}',a.normal_build_run_id or ''),'fixed actual ARM32 normal DATA selection')
    normal_ref=dict(path=str(a.normal_source),sha256=a.normal_source_sha256);normal=load(checked(normal_ref)['path'])
    need(normal['schema']=='postpackage-source579-output/v1' and normal['source_commit']==a.source_commit,'same actual normal SOURCE')
    for row in (normal_ref,normal['source_kit_manifest'],normal['canonical_snapshot']):actual=checked(row);files[actual['path']]=actual
    roots.update((canonical(a.normal_source.parent),canonical(Path(normal['source_kit_manifest']['path']).parent)))
    sdk=sdk_inventory(a.sdk_native,a.sdk_metadata_sha256);roots.add(canonical(a.sdk_native))
    source_root=Path(a.source_root or '')
    need(source_root.is_absolute() and '..' not in source_root.parts and str(source_root) not in ('/',''),'selected container source root string only; never host mirror source bytes')
    output=canonical(a.output);need(output.is_dir() and output.is_relative_to(BASE),'existing original Owner normal log output')
    paths=set(roots)
    for name in files:
        path=Path(name)
        if not any(path.is_relative_to(root) for root in roots):paths.add(path)
    paths={path for path in paths if not any(path!=other and path.is_relative_to(other) for other in paths)}
    need(not any(output.is_relative_to(path) for path in paths),'read-only source/evidence mount would cover live normal output')
    sdk_file=output/'normal-media579-arm32-sdk.json';input_file=output/'normal-media579-arm32-inputs.json';mount_file=output/'normal-media579-arm32-mounts.json'
    save_new(sdk_file,sdk)
    inputs=dict(schema='media579-arm32-held-normal-build-inputs/v1',normal_source=two(normal_ref),representative_gate=two(gate_ref),sdk_native=str(canonical(a.sdk_native)),source_root=str(source_root),product=a.product,device=a.device,normal_build_run_id=a.normal_build_run_id)
    save_new(input_file,inputs)
    paths.update((input_file,sdk_file))
    receipt=dict(schema='media579-arm32-normal-data-mounts/v1',inputs=ref(input_file),sdk_closure=ref(sdk_file),source_commit=a.source_commit,normal_build_run_id=a.normal_build_run_id,
        product=a.product,device=a.device,files=list(files.values()),readonly_paths=sorted(str(p) for p in paths),source_only=True,normal_production_prerequisite_only=True,runtime_pass=False,first_artifact_behavior_gate_passed=False)
    save_new(mount_file,receipt)
    print(json.dumps(dict(inputs=ref(input_file),mounts=ref(mount_file),sdk_closure=ref(sdk_file))))
    return 0


if __name__=='__main__':raise SystemExit(main())
