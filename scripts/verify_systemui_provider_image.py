#!/usr/bin/env python3
"""Require actual newly compiled SystemUI modules in the image; QEMU is separate."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
import systemui_provider as provider
from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_photos_provider_image import verify_signature, stage_signature_hap, SIGNER_JAR_SHA
from verify_preinstall_selection import verify_selection


def module_info(hap, source=None):
    with zipfile.ZipFile(hap) as archive:
        rows = archive.infolist(); names = [r.filename for r in rows]
        if len(rows) > 10000 or len(set(names)) != len(names) or sum(r.file_size for r in rows) > 256*1024*1024:
            raise ValueError('invalid SystemUI HAP member closure')
        for row in rows:
            path = PurePosixPath(row.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in row.filename or
                path.as_posix() != row.filename.rstrip('/') or row.flag_bits & 1 or
                row.file_size > 64*1024*1024 or (row.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe SystemUI HAP member')
        if not {'module.json', 'ets/modules.abc', 'resources.index'} <= set(names):
            raise ValueError('actual compiled SystemUI implementation/resources missing')
        abc = archive.read('ets/modules.abc')
        if not abc or not archive.read('resources.index'): raise ValueError('empty compiled SystemUI payload')
        value = json.loads(archive.read('module.json'), object_pairs_hook=provider.unique)
        app, module = value['app'], value['module']
        if (app.get('bundleName'), app.get('versionCode'), app.get('versionName')) != \
                ('com.ohos.systemui', 1000000, '1.0.0'):
            raise ValueError('same-bundle SystemUI module version/name differs')
        if source is not None:
            if app.get('debug') is not False: raise ValueError('source SystemUI must be a release payload')
            for key in ('name', 'type', 'deviceTypes', 'mainElement'):
                if module.get(key) != source.get(key): raise ValueError('compiled SystemUI module differs: ' + key)
            if [r['name'] for r in module.get('requestPermissions', [])] != [r['name'] for r in source.get('requestPermissions', [])]:
                raise ValueError('compiled SystemUI permission surface differs')
            for key in ('abilities', 'extensionAbilities'):
                actual, expected = module.get(key, []), source.get(key, [])
                if [r['name'] for r in actual] != [r['name'] for r in expected]: raise ValueError('SystemUI entrypoint closure differs')
                for a, e in zip(actual, expected):
                    for field in ('permissions', 'skills', 'type', 'visible', 'exported'):
                        if not provider.same_json(a.get(field), e.get(field)): raise ValueError('SystemUI extension boundary differs: ' + field)
        if module['name'] in ('phone_dropdownpanel', 'pc_notificationpanel'):
            if not all(s in abc for s in (b'system-live-view-button-', b'triggerSystemLiveView')):
                raise ValueError('actual compiled live-view renderer/callback absent')
        if module['name'] == 'phone_statusbar' and b'systemui-statusbar-swipe' not in abc:
            raise ValueError('actual compiled status-bar gesture node absent')
        return {'module': module['name'], 'type': module['type'], 'versionCode': app['versionCode'],
                'versionName': app['versionName'], 'compiled_abc_bytes': len(abc), 'sha256': file_sha256(hap)}


def image_names(image, executable):
    observed = []
    for directory in ('/system/app/com.ohos.systemui', '/app/com.ohos.systemui'):
        result = subprocess.run([executable, '-R', 'ls -p ' + directory, str(image)], capture_output=True, text=True, check=True)
        names = set()
        for line in result.stdout.splitlines():
            if not line.startswith('/'): continue
            fields = line.split('/')
            if len(fields) < 7 or not fields[1].isdigit(): raise ValueError('malformed actual SystemUI image listing')
            if fields[5] not in ('.', '..'): names.add(fields[5])
        if names: observed.append(names)
    if not observed or any(s != observed[0] for s in observed): raise ValueError('ambiguous or missing SystemUI image directory')
    return observed[0]


def retained_signature(hap, source, scratch):
    # Only this exact unchanged legacy payload may omit the permission log marker.
    expected_sha = '7e6d99cf44f67a421e20ef2d7a86084d52b45dc1fc4c0ea0902dd4ede47c2cc9'
    if file_sha256(hap) != expected_sha or hap.stat().st_size != 851864:
        raise ValueError('retained ScreenLock exact legacy payload SHA/size differs')
    dist = source / 'developtools/hapsigner/dist'; jar = dist / 'hap-sign-tool.jar'
    if file_sha256(jar) != SIGNER_JAR_SHA:
        raise ValueError('retained ScreenLock signer tool does not match the fixed release')
    signature_hap = stage_signature_hap(hap, scratch)
    if file_sha256(signature_hap) != expected_sha or signature_hap.stat().st_size != 851864:
        raise ValueError('retained ScreenLock staged legacy payload SHA/size differs')
    profile = scratch / 'retained-profile.p7b'; chain = scratch / 'retained-app.cer'
    result = subprocess.run(['java', '-jar', str(jar), 'verify-app', '-inFile', str(signature_hap),
        '-outProfile', str(profile), '-outCertChain', str(chain)], check=True, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    if 'skip code signing verify' in output:
        raise ValueError('retained ScreenLock verifier skipped code signing')
    required = ('verify codesign success', 'Digest verify result: true', 'verify-app success')
    missing_markers = [marker for marker in required if marker not in output]
    if missing_markers:
        raise ValueError('retained ScreenLock verification missing required markers: ' + ', '.join(missing_markers))
    permission_marker = 'verify permission sign success' in output
    leaf = re.split(r'certificate #0\b', output, maxsplit=1)
    match = re.search(r'SHA256:\s*([0-9A-Fa-f:]+)', re.split(r'certificate #1\b', leaf[1], maxsplit=1)[0]) if len(leaf) == 2 else None
    issuer = scratch / 'retained-profile-issuer.pem'
    try:
        document = provider.cms(profile, issuer)
        actual_issuer = provider.certificates(provider.read(issuer))
        expected_issuers = provider.certificates(provider.read(dist / 'OpenHarmonyProfileRelease.pem'))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError('retained ScreenLock profile CMS/export verification failed') from error
    try:
        distribution_fingerprint = provider.certificate_fingerprint(document['bundle-info']['distribution-certificate'].encode())
        actual_fingerprint = provider.certificate_fingerprint(actual_issuer[0]) if len(actual_issuer) == 1 else None
        expected_fingerprint = provider.certificate_fingerprint(expected_issuers[-1]) if len(expected_issuers) == 3 else None
    except (KeyError, TypeError, AttributeError, OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError('retained ScreenLock profile certificate fingerprint extraction failed') from error
    identity_checks = {
        'application_leaf': bool(match and match[1].replace(':', '').upper() == provider.SIGNATURE),
        'certificate_chain_output': chain.is_file(),
        'profile_bundle': document.get('bundle-info', {}).get('bundle-name') == 'com.ohos.systemui',
        'distribution_certificate': distribution_fingerprint == provider.SIGNATURE,
        'profile_CMS_signer_count': len(actual_issuer) == 1,
        'fixed_profile_chain_count': len(expected_issuers) == 3,
        'profile_CMS_signer_identity': actual_fingerprint is not None and expected_fingerprint is not None and actual_fingerprint == expected_fingerprint,
    }
    if not all(identity_checks.values()):
        raise ValueError('retained ScreenLock signing identity/profile mismatch: ' +
                         ', '.join(name for name, passed in identity_checks.items() if not passed))
    return {'application_signer_sha256': provider.SIGNATURE, 'original_payload_retained': True,
            'signature_input_sha256': file_sha256(signature_hap), 'code_signing_skip_rejected': True,
            'legacy_permission_marker_absent': not permission_marker,
            'legacy_exception_payload_sha256': expected_sha, 'legacy_exception_payload_bytes': 851864}


def verify(args):
    provider.verify(args.source_root)
    import json5
    mapping = json.loads(provider.read(provider.PATCH_ROOT / 'common/applications/standard/systemui/source_provider/module_map.json'))
    rows = mapping['modules'][args.device]; retained = mapping['retained_screenlock']
    expected = {r['hap'] for r in rows} | {retained['hap']}
    directory = args.build_hap_dir
    build_target = 'systemui_pc_sources' if args.device == '2in1' else 'systemui_phone_sources'
    if (directory.name != build_target or not directory.is_absolute() or
        directory.resolve() != directory or not directory.is_dir() or
        not directory.is_relative_to(args.source_root / 'out') or any(p.is_symlink() for p in (directory, *directory.parents))):
        raise ValueError('explicit actual SystemUI GN output directory under this source/out required')
    built_names = {p.name for p in directory.glob('*.hap')}
    expected_built_names = {r['hap'] for r in rows}
    if built_names != expected_built_names:
        raise ValueError('actual source build must produce the exact selected modules: ' +
            json.dumps({'directory': str(directory), 'missing': sorted(expected_built_names - built_names),
                        'extra': sorted(built_names - expected_built_names)}, sort_keys=True))
    executable = debugfs_path()
    if image_names(args.system_image, executable) != expected: raise ValueError('image contains stale/missing/extra same-bundle modules')
    result = {'scope': 'actual image/build-byte/signature source proof ONLY; BMS and QEMU UI must still pass',
              'actual_build_target': build_target, 'modules': []}
    with tempfile.TemporaryDirectory(prefix='systemui-source-image-') as temporary:
        scratch = Path(temporary)
        result['install_selection'] = verify_selection(args.source_root, 'com.ohos.systemui', args.system_image, scratch)
        for row in rows + [retained]:
            slot = scratch / row['hap']; slot.mkdir()
            hap, identity = dump_unique_file(args.system_image, tuple(prefix + '/app/com.ohos.systemui/' + row['hap']
                for prefix in ('', '/system')), slot, executable)
            if row is retained:
                if file_sha256(hap) != retained['sha256'] or hap.stat().st_size != retained['bytes']: raise ValueError('retained ScreenLock bytes changed')
                info = module_info(hap)
                if (info['module'], info['type']) != ('phone', 'feature'): raise ValueError('retained ScreenLock module identity changed')
                signature = retained_signature(hap, args.source_root, slot)
            else:
                built = directory / row['hap']
                if file_sha256(hap) != file_sha256(built): raise ValueError('image HAP differs from this actual source build')
                source = json5.loads(provider.read(args.source_root / provider.PROJECT / row['source'] / 'src/main/module.json5').decode(), allow_duplicate_keys=False)['module']
                info = module_info(hap, source)
                signature = verify_signature(hap, args.source_root, slot, provider.PROJECT + '/signature/systemui.p7b')
                info['actual_build_hap'] = str(built)
            result['modules'].append({**identity, **info, **signature})
        for name, expected_row in [('install_list_capability.json', provider.CAPABILITY), ('install_list_permissions.json', provider.GRANTS)]:
            slot = scratch / name; slot.mkdir()
            policy, identity = dump_unique_file(args.system_image, tuple(prefix + '/etc/app/' + name for prefix in ('', '/system')), slot, executable)
            value = json.loads(policy.read_bytes(), object_pairs_hook=provider.unique)
            values = value['install_list'] if isinstance(value, dict) else value
            if not provider.same_json([r for r in values if r.get('bundleName') == 'com.ohos.systemui'], [expected_row]):
                raise ValueError('actual image changed original SystemUI policy')
        result.update(status='pass', system_image_sha256=file_sha256(args.system_image), runtime_validated=False,
                      first_artifact_behavior_gate_passed=False, BMS_mixed_module_installation_still_required=True)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'system-image', 'build-hap-dir', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    result = verify(args)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'runtime_validated': False}))
