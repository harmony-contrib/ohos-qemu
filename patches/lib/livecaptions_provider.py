#!/usr/bin/env python3
"""Release OS source/profile preparation; normal platform ohos_app builds/signs HAP.

Root runs this under its existing source builder, without a guest/test UDID.
No Owner, process constructor, fixture signer or app compilation is introduced.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from calendar_provider import SIGNATURE, certificate_fingerprint
from mms_provider import SIGNING_INPUTS, read, replace, unique, cms, certificates
from preinstall_selection import entry, same_json, uninstall_policy

PATCH_ROOT=Path(__file__).resolve().parents[1]
PROJECT='applications/standard/hap/vassistant_livecaptions579'
BUNDLE='com.ohos.vassistant'
LABEL='//applications/standard/hap/vassistant_livecaptions579:vassistant_livecaptions579'
DEVICE_TYPES=['default','tablet','2in1']
PRODUCT_ABIS={'arm64_virt':'arm64-v8a','armv7a_virt':'armeabi-v7a','x86_64_virt':'x86_64'}
LEGACY_PERMISSIONS=['ohos.permission.MANAGE_SETTINGS','ohos.permission.SYSTEM_FLOAT_WINDOW',
                    'ohos.permission.WRITE_ACCESSIBILITY_CONFIG']
PERMISSIONS=LEGACY_PERMISSIONS+['ohos.permission.MANAGE_SECURE_SETTINGS']
LEGACY_CAPABILITY={'bundleName':BUNDLE,'app_signature':[SIGNATURE],'keepAlive':False,'allowAppDesktopIconHide':True}
CAPABILITY=dict(LEGACY_CAPABILITY,allowAppUsePrivilegeExtension=True)


def digest(data): return hashlib.sha256(data).hexdigest()


def capability_policy(data, require_current=True):
    value=json.loads(data,object_pairs_hook=unique)
    rows=value.get('install_list') if isinstance(value,dict) else value
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
        raise ValueError('invalid caption preinstall capability rows')
    matches=[row for row in rows if row.get('bundleName')==BUNDLE]
    allowed=([CAPABILITY],) if require_current else ([LEGACY_CAPABILITY],[CAPABILITY])
    if not any(same_json(matches,expected) for expected in allowed):
        raise ValueError('exact signer-bound caption privilege-extension policy required')
    if same_json(matches,[CAPABILITY]): return data
    matches[0].update(CAPABILITY)
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def target_contract(product, device, abi):
    # Build target context only. Actual selected HAP/BMS/boot remains a guest gate.
    if product not in PRODUCT_ABIS or device not in ('phone','2in1') or PRODUCT_ABIS[product]!=abi:
        raise ValueError('exact three-product by two-device caption ABI context required')
    return {'product':product,'device':device,'abi':abi,
        'sdk_device':'default' if device=='phone' else '2in1','module_device_types':list(DEVICE_TYPES)}


def source_ready(root, require_current=True):
    manifest=json.loads(read(PATCH_ROOT/'common/applications/standard/hap/livecaptions_provider/source_states.json'),
                        object_pairs_hook=unique)
    if manifest['project']!=PROJECT or manifest['parent_project']!='applications/standard/hap':
        raise ValueError('fixed product source identity differs')
    actual=subprocess.check_output(['git','-C',str(root/manifest['parent_project']),'rev-parse','HEAD'],text=True,timeout=30).strip()
    if actual!=manifest['parent_head']: raise ValueError('fixed actual HAP repository HEAD required')
    for relative,sha in manifest['files'].items():
        if digest(read(root/PROJECT/relative))!=sha: raise ValueError('complete production source differs: '+relative)
    actual_sources={p.relative_to(root/PROJECT).as_posix() for p in (root/PROJECT/'entry/src/main/ets').rglob('*.ets')}
    expected_sources={p for p in manifest['files'] if p.startswith('entry/src/main/ets/') and p.endswith('.ets')}
    if actual_sources!=expected_sources: raise ValueError('unexpected/lost production source closure')
    module=json.loads(read(root/PROJECT/'entry/src/main/module.json5'),object_pairs_hook=unique)['module']
    if (module.get('name'),module.get('type'),module.get('deviceTypes'))!=('entry','entry',DEVICE_TYPES):
        raise ValueError('exact SDK26 default/tablet/2in1 source module required')
    hap=read(root/'applications/standard/hap/BUILD.gn').decode()
    if hap.count('"'+LABEL+'"')!=1 or 'ohos_prebuilt_etc("vassistant_livecaptions579")' in hap:
        raise ValueError('select exactly the real source target, never the prototype prebuilt')
    directory=root/'vendor/ohemu/virt/preinstall-config'
    selected=entry(read(directory/'install_list.json'),BUNDLE)
    uninstall_policy(read(directory/'uninstall_list.json'),BUNDLE)
    capability_policy(read(directory/'install_list_capability.json'),require_current)
    grants=json.loads(read(directory/'install_list_permissions.json'),object_pairs_hook=unique)
    grant_rows=grants['install_list'] if isinstance(grants,dict) else grants
    if [r for r in grant_rows if r.get('bundleName')==BUNDLE]:
        raise ValueError('no capture/management/vendor permission bypass grants may be added')
    return {'selection':selected,'capability':CAPABILITY,'label':LABEL}


def desired(root, leaf):
    value=json.loads(read(root/PROJECT/'signature/profile-template.json'),object_pairs_hook=unique)
    bundle=value['bundle-info']
    if value.get('type')!='release' or value.get('app-distribution-type')!='os_integration' or \
        'debug-info' in value or bundle!={'developer-id':'OpenHarmony','distribution-certificate':'',
        'bundle-name':BUNDLE,'apl':'system_basic','app-feature':'hos_system_app'} or \
        value.get('acls')!={'allowed-acls':PERMISSIONS} or value.get('permissions')!={'restricted-permissions':[]} or \
        certificate_fingerprint(leaf)!=SIGNATURE:
        raise ValueError('exact no-UDID release identity/APL/4ACL/OS signer required')
    result=copy.deepcopy(value)
    result['bundle-info']['distribution-certificate']=leaf.decode()+'\n'
    return result


def install(path, data):
    if path.exists():
        if read(path)!=data: raise ValueError('preserve unexpected existing product input: '+str(path))
        return
    if any(p.is_symlink() for p in (path,*path.parents)): raise ValueError('no symlink product destination')
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.caption-product-',dir=path.parent,delete=False) as out:
            pending=Path(out.name);out.write(data);out.flush();os.fchmod(out.fileno(),0o644);os.fsync(out.fileno())
        # Source Owner serializes mutations; an unexpected new file wins and is
        # preserved. Never replace a foreign source/input using last-writer wins.
        os.link(pending,path)
    finally:
        if pending is not None: pending.unlink(missing_ok=True)


def select_assets(root, mapping, inputs, abi):
    """A complete known ABI-data vector may replace another complete known one.

    Normal matrix builds share a source tree. Only HAR/notices differ between
    fixed 64-bit inputs and the sealed actual ARM32 input. Unknown/mixed data is
    rejected, and an ordinary failed transaction restores its exact preimage.
    """
    from livecaptions579_inputs import product_assets, raw
    from livecaptions579_arm32_sources import BASE_HAR_SHA, BASE_NOTICES_SHA
    directory=root/PROJECT; marker=directory/'.assets-selection579.json'
    if any(p.is_symlink() for p in (marker,*marker.parents)): raise ValueError('no symlink ABI-data selection')
    desired_data={relative:raw(value) for relative,value in mapping.items()}
    paths={relative:directory/relative for relative in mapping}
    before={relative:read(path) if path.exists() else None for relative,path in paths.items()}
    marker_before=read(marker) if marker.exists() else None
    if marker_before is not None:
        old=json.loads(marker_before,object_pairs_hook=unique)
        if set(old)!={'schema','abi','inputs','assets'} or old['schema']!='actual-caption579-source-assets/v1':
            raise ValueError('unknown source ABI-data selection marker')
        old_mapping=product_assets(old['inputs'],old['abi'])
        expected={relative:digest(raw(value)) for relative,value in old_mapping.items()}
        if set(old_mapping)!=set(mapping) or old['assets']!=expected or any(
            before[p] is None or digest(before[p])!=checksum for p,checksum in expected.items()):
            raise ValueError('unknown/mixed prior complete caption input vector')
    else:
        har='sherpa_onnx-1.11.2.har'
        notice='entry/src/main/resources/rawfile/LIVE_CAPTIONS_NOTICES.txt'
        if har not in before or notice not in before: raise ValueError('fixed product data destinations changed')
        pair=(before[har],before[notice])
        if (pair[0] is None)!=(pair[1] is None): raise ValueError('partial unmarked ABI-data vector')
        if pair[0] is not None and (digest(pair[0]),digest(pair[1]))!=(BASE_HAR_SHA,BASE_NOTICES_SHA):
            raise ValueError('only the exact historical R66 two-ABI vector can bootstrap an unmarked source')
        for relative,data in before.items():
            if relative not in (har,notice) and data is not None and data!=desired_data[relative]:
                raise ValueError('model/notice source input is not the fixed common vector')
    wanted={'schema':'actual-caption579-source-assets/v1','abi':abi,'inputs':inputs,
        'assets':{relative:digest(data) for relative,data in desired_data.items()}}
    marker_data=(json.dumps(wanted,ensure_ascii=False,indent=2)+'\n').encode()
    written=[]
    def replace(path, expected, data):
        current=read(path) if path.exists() else None
        if current!=expected: raise ValueError('source data changed before atomic replacement: '+str(path))
        if expected==data: return
        path.parent.mkdir(parents=True,exist_ok=True)
        mode=path.stat().st_mode&0o777 if path.exists() else 0o644
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(prefix='.caption-abi-',dir=path.parent,delete=False) as out:
                temporary=Path(out.name);out.write(data);out.flush();os.fchmod(out.fileno(),mode);os.fsync(out.fileno())
            if (read(path) if path.exists() else None)!=expected: raise ValueError('source ABI vector changed during preparation')
            os.replace(temporary,path)
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)
    try:
        for relative,data in desired_data.items():
            path=paths[relative];replace(path,before[relative],data);written.append((path,before[relative],data))
        replace(marker,marker_before,marker_data);written.append((marker,marker_before,marker_data))
        for relative,data in desired_data.items():
            if read(paths[relative])!=data: raise ValueError('complete selected ABI-data vector changed')
    except BaseException:
        for path,previous,data in reversed(written):
            if read(path)!=data: raise ValueError('unknown concurrent source input; preserve it and stop')
            if previous is None:path.unlink()
            else:replace(path,data,previous)
        if any((read(paths[p]) if paths[p].exists() else None)!=data for p,data in before.items()) or \
            (read(marker) if marker.exists() else None)!=marker_before:
            raise ValueError('source ABI-data rollback incomplete')
        raise
    return {relative:{'path':str(paths[relative]),'sha256':digest(data)} for relative,data in desired_data.items()}


def prepare(root, cache, inputs, abi, *, product, device):
    context=target_contract(product,device,abi)
    policies=source_ready(root,require_current=False)
    capability_path=root/'vendor/ohemu/virt/preinstall-config/install_list_capability.json'
    capability_before=read(capability_path)
    capability_after=capability_policy(capability_before,require_current=False)
    # Fixed source module, not a JSON-supplied code path or a live guest factory.
    sys.path.insert(0,str(PATCH_ROOT.parent/'ci/capability-audit'))
    from livecaptions579_inputs import product_assets, raw
    mapping=product_assets(inputs,abi)
    assets=select_assets(root,mapping,inputs,abi)
    dist=root/'developtools/hapsigner/dist'
    for name,sha in SIGNING_INPUTS.items():
        if digest(read(dist/name))!=sha: raise ValueError('fixed public OS signing input changed: '+name)
    app=certificates(read(dist/'OpenHarmonyApplication.pem'))
    issuer=certificates(read(dist/'OpenHarmonyProfileRelease.pem'))
    if len(app)!=3 or len(issuer)!=3: raise ValueError('fixed actual OS certificate chain required')
    expected=desired(root,app[-1]); issuer_sha=certificate_fingerprint(issuer[-1])
    legacy_expected=copy.deepcopy(expected)
    legacy_expected['acls']['allowed-acls']=LEGACY_PERMISSIONS
    path=root/PROJECT/'signature/vassistant.p7b'
    cache.mkdir(parents=True,exist_ok=True)
    commands=[]
    with tempfile.TemporaryDirectory(prefix='vassistant-release-profile-',dir=cache) as directory:
        scratch=Path(directory)
        def verify(profile, allow_legacy=False):
            signer=scratch/'issuer.pem'
            actual=cms(profile,signer)
            chain=certificates(read(signer))
            if (actual!=expected and not (allow_legacy and actual==legacy_expected)) or \
                    len(chain)!=1 or certificate_fingerprint(chain[0])!=issuer_sha or 'debug-info' in actual:
                raise ValueError('signed release profile policy/OS issuer/no-UDID differs')
            return 'current' if actual==expected else 'legacy'
        profile_before=read(path) if path.exists() else None
        profile_state=verify(path,allow_legacy=True) if profile_before is not None else 'absent'
        if profile_before is not None and read(path)!=profile_before:
            raise ValueError('signed caption profile changed during predecessor verification')
        if profile_state!='current':
            template=scratch/'profile.json'; signed=scratch/'release.p7b'
            template.write_text(json.dumps(expected,indent=2)+'\n')
            argv=['java','-jar',str(dist/'hap-sign-tool.jar'),'sign-profile','-keyAlias',
                'openharmony application profile release','-signAlg','SHA256withECDSA','-mode','localSign',
                '-profileCertFile',str(dist/'OpenHarmonyProfileRelease.pem'),'-inFile',str(template),
                '-keystoreFile',str(dist/'OpenHarmony.p12'),'-outFile',str(signed),'-keyPwd','123456','-keystorePwd','123456']
            done=subprocess.run(argv,capture_output=True,timeout=120)
            row={'argv':argv,'exit_code':done.returncode,'stdout':done.stdout.decode(errors='replace'),
                 'stderr':done.stderr.decode(errors='replace'),'timed_out':False}
            commands.append(row)
            if done.returncode: raise ValueError('actual source profile signing failed: '+json.dumps(row))
            verify(signed)
            profile_after=read(signed)
            if profile_before is None:
                install(path,profile_after)
                verify(path)
            else:
                # Upgrade only the authenticated complete three-ACL predecessor.
                # No signing identity, APL, permission grant row or other profile
                # property changes; unknown/concurrent signed bytes are preserved.
                if read(path)!=profile_before:
                    raise ValueError('signed caption profile changed before exact ACL upgrade')
                try:
                    replace(path,profile_after)
                    if read(path)!=profile_after:
                        raise ValueError('signed caption profile changed during exact ACL upgrade')
                    verify(path)
                except BaseException:
                    if read(path)==profile_after: replace(path,profile_before)
                    raise
    if read(capability_path)!=capability_before:
        raise ValueError('caption capability policy changed before exact upgrade')
    if capability_after!=capability_before:
        try:
            replace(capability_path,capability_after)
            if read(capability_path)!=capability_after:
                raise ValueError('caption capability policy changed during exact upgrade')
        except BaseException:
            if read(capability_path)==capability_after: replace(capability_path,capability_before)
            raise
    return {'scope':'release OS source/profile/data preparation only; normal GN builds/signs/packages HAP',
        'project':PROJECT,'label':LABEL,'abi':abi,'target':context,'assets':assets,'profile':{'path':str(path),'sha256':digest(read(path))},
        'signer':SIGNATURE,'policies':policies,'commands':commands,'guest_or_udid_required':False,
        'actual_compilation':False,'runtime_validated':False,'first_artifact_behavior_gate_passed':False}


def payload(hap, root, scratch, inputs, abi, *, product, device):
    """Actual compiled-byte/signature admission; never functional acceptance."""
    context=target_contract(product,device,abi)
    import zipfile
    from pathlib import PurePosixPath
    sys.path.insert(0,str(PATCH_ROOT.parent/'scripts'))
    sys.path.insert(0,str(PATCH_ROOT.parent/'ci/capability-audit'))
    from verify_photos_provider_image import verify_signature
    from livecaptions579_inputs import product_assets, raw
    mapping=product_assets(inputs,abi)
    with zipfile.ZipFile(hap) as archive:
        rows=archive.infolist();names=[r.filename for r in rows]
        if len(names)!=len(set(names)) or len(names)>10000 or sum(r.file_size for r in rows)>256*1024*1024:
            raise ValueError('finite real product HAP closure required')
        for row in rows:
            path=PurePosixPath(row.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in row.filename or row.flag_bits&1 or \
                (row.external_attr>>16)&0o170000==0o120000:
                raise ValueError('unsafe product HAP member')
        document=json.loads(archive.read('module.json'),object_pairs_hook=unique)
        app,module=document['app'],document['module']
        if (app.get('bundleName'),app.get('versionCode'),app.get('versionName'),app.get('debug'))!=(BUNDLE,1000000,'1.0.0',False):
            raise ValueError('real release product app identity differs')
        if (module.get('name'),module.get('type'),module.get('deviceTypes'))!=('entry','entry',DEVICE_TYPES):
            raise ValueError('compiled caption SDK26 device/module contract differs')
        if module.get('abilities',[]) or [p['name'] for p in module.get('requestPermissions',[])]!=PERMISSIONS:
            raise ValueError('compiled provider permission/ability boundary differs')
        extensions=module.get('extensionAbilities',[])
        if len(extensions)!=1 or any(extensions[0].get(k)!=v for k,v in {
            'name':'AiCaptionServiceExtAbility','type':'service','exported':True,
            'permissions':['ohos.permission.WRITE_ACCESSIBILITY_CONFIG']}.items()):
            raise ValueError('real compiled SERVICE entry differs')
        if not archive.read('ets/modules.abc') or not archive.read('resources.index'):
            raise ValueError('real product ABC/resources absent')
        for relative,ref in mapping.items():
            prefix='entry/src/main/resources/'
            if relative.startswith(prefix) and archive.read('resources/'+relative[len(prefix):])!=raw(ref):
                raise ValueError('compiled model/notices bytes differ from actual admitted source: '+relative)
        expected={'libsherpa_onnx.so','libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so'}
        libraries={name:digest(archive.read('libs/'+abi+'/'+name)) for name in expected}
        if abi=='armeabi-v7a':
            from livecaptions579_arm32_contract import admit
            actual=admit(inputs)
            if libraries!={name:row['file']['sha256'] for name,row in actual['libraries'].items()}:
                raise ValueError('actual compiled ARM32 HAP does not contain the admitted native outputs')
    signature=verify_signature(hap,root,scratch,PROJECT+'/signature/vassistant.p7b')
    return {'bundle':BUNDLE,'abi':abi,'target':context,'hap_sha256':digest(read(hap)),'libraries':libraries,**signature,
        'scope':'actual compiled product byte/signature admission only',
        'provider_runtime_validated':False,'first_artifact_behavior_gate_passed':False}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--cache-root',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--inputs-sha256',required=True)
    parser.add_argument('--abi',choices=('arm64-v8a','x86_64','armeabi-v7a'),required=True)
    parser.add_argument('--hap',type=Path)
    parser.add_argument('--product',choices=tuple(PRODUCT_ABIS),required=True)
    parser.add_argument('--device',choices=('phone','2in1'),required=True)
    args=parser.parse_args()
    source=read(args.inputs)
    if digest(source)!=args.inputs_sha256: raise ValueError('actual root dependency descriptor changed')
    inputs=json.loads(source,object_pairs_hook=unique)
    if args.hap is None:
        result=prepare(args.source_root.resolve(),args.cache_root.resolve(),inputs,args.abi,
            product=args.product,device=args.device)
    else:
        source_ready(args.source_root.resolve())
        args.cache_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='caption-product-payload-',dir=args.cache_root) as directory:
            result=payload(args.hap.resolve(),args.source_root.resolve(),Path(directory),inputs,args.abi,
                product=args.product,device=args.device)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
