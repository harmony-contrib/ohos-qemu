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
from mms_provider import SIGNING_INPUTS, read, unique, cms, certificates
from preinstall_selection import entry, same_json, uninstall_policy

PATCH_ROOT=Path(__file__).resolve().parents[1]
PROJECT='applications/standard/hap/vassistant_livecaptions579'
BUNDLE='com.ohos.vassistant'
LABEL='//applications/standard/hap/vassistant_livecaptions579:vassistant_livecaptions579'
PERMISSIONS=['ohos.permission.MANAGE_SETTINGS','ohos.permission.SYSTEM_FLOAT_WINDOW',
             'ohos.permission.WRITE_ACCESSIBILITY_CONFIG']
CAPABILITY={'bundleName':BUNDLE,'app_signature':[SIGNATURE],'keepAlive':False,'allowAppDesktopIconHide':True}


def digest(data): return hashlib.sha256(data).hexdigest()


def source_ready(root):
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
    hap=read(root/'applications/standard/hap/BUILD.gn').decode()
    if hap.count('"'+LABEL+'"')!=1 or 'ohos_prebuilt_etc("vassistant_livecaptions579")' in hap:
        raise ValueError('select exactly the real source target, never the prototype prebuilt')
    directory=root/'vendor/ohemu/virt/preinstall-config'
    selected=entry(read(directory/'install_list.json'),BUNDLE)
    uninstall_policy(read(directory/'uninstall_list.json'),BUNDLE)
    policies=json.loads(read(directory/'install_list_capability.json'),object_pairs_hook=unique)
    rows=policies['install_list'] if isinstance(policies,dict) else policies
    if not same_json([r for r in rows if r.get('bundleName')==BUNDLE],[CAPABILITY]):
        raise ValueError('exact signer-bound non-keepalive provider policy required')
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
        raise ValueError('exact no-UDID release identity/APL/3ACL/OS signer required')
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


def prepare(root, cache, inputs, abi):
    policies=source_ready(root)
    # Fixed source module, not a JSON-supplied code path or a live guest factory.
    sys.path.insert(0,str(PATCH_ROOT.parent/'ci/capability-audit'))
    from livecaptions579_inputs import product_assets, raw
    mapping=product_assets(inputs,abi)
    assets={}
    for relative,ref in mapping.items():
        path=root/PROJECT/relative
        data=raw(ref);install(path,data)
        assets[relative]={'path':str(path),'sha256':digest(read(path))}
    dist=root/'developtools/hapsigner/dist'
    for name,sha in SIGNING_INPUTS.items():
        if digest(read(dist/name))!=sha: raise ValueError('fixed public OS signing input changed: '+name)
    app=certificates(read(dist/'OpenHarmonyApplication.pem'))
    issuer=certificates(read(dist/'OpenHarmonyProfileRelease.pem'))
    if len(app)!=3 or len(issuer)!=3: raise ValueError('fixed actual OS certificate chain required')
    expected=desired(root,app[-1]); issuer_sha=certificate_fingerprint(issuer[-1])
    path=root/PROJECT/'signature/vassistant.p7b'
    cache.mkdir(parents=True,exist_ok=True)
    commands=[]
    with tempfile.TemporaryDirectory(prefix='vassistant-release-profile-',dir=cache) as directory:
        scratch=Path(directory)
        def verify(profile):
            signer=scratch/'issuer.pem'
            actual=cms(profile,signer)
            chain=certificates(read(signer))
            if actual!=expected or len(chain)!=1 or certificate_fingerprint(chain[0])!=issuer_sha or 'debug-info' in actual:
                raise ValueError('signed release profile policy/OS issuer/no-UDID differs')
        if path.exists(): verify(path)
        else:
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
            verify(signed);install(path,read(signed));verify(path)
    return {'scope':'release OS source/profile/data preparation only; normal GN builds/signs/packages HAP',
        'project':PROJECT,'label':LABEL,'abi':abi,'assets':assets,'profile':{'path':str(path),'sha256':digest(read(path))},
        'signer':SIGNATURE,'policies':policies,'commands':commands,'guest_or_udid_required':False,
        'actual_compilation':False,'runtime_validated':False,'first_artifact_behavior_gate_passed':False}


def payload(hap, root, scratch, inputs, abi):
    """Actual compiled-byte/signature admission; never functional acceptance."""
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
    signature=verify_signature(hap,root,scratch,PROJECT+'/signature/vassistant.p7b')
    return {'bundle':BUNDLE,'abi':abi,'hap_sha256':digest(read(hap)),'libraries':libraries,**signature,
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
    args=parser.parse_args()
    source=read(args.inputs)
    if digest(source)!=args.inputs_sha256: raise ValueError('actual root dependency descriptor changed')
    inputs=json.loads(source,object_pairs_hook=unique)
    if args.hap is None:
        result=prepare(args.source_root.resolve(),args.cache_root.resolve(),inputs,args.abi)
    else:
        source_ready(args.source_root.resolve())
        args.cache_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='caption-product-payload-',dir=args.cache_root) as directory:
            result=payload(args.hap.resolve(),args.source_root.resolve(),Path(directory),inputs,args.abi)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
