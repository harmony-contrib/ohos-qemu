"""Replay permission-free compiled/signed native HAP payloads without trusting summaries."""
import json
from pathlib import Path
import zipfile

from build_serial_hap_probe import ARCHITECTURES
from run_root_probe import digest, validate_elf
from qemu_test_hap_archive import canonical_library

ROOT = Path(__file__).resolve().parent


def verify_compiled_payload(document, root, arch, run_id, bundle, source_stem, library_stem, inputs_name):
    files = {'compiled_inputs': root / 'project' / inputs_name,
             'signed_hap': root / 'ordinary-signed.hap'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('changed actual ordinary payload evidence: ' + key)
    inputs = json.loads(files['compiled_inputs'].read_text())
    if (inputs.get('status') != 'pass' or inputs.get('arch') != arch or inputs.get('run_id') != run_id or
            inputs.get('bundle') != bundle or inputs.get('request_permissions') != [] or
            inputs.get('first_artifact_behavior_gate_passed') is not False or
            inputs.get('source_sha256') != digest(ROOT / (source_stem + '_app_probe.cpp')) or
            inputs.get('template_sha256') != digest(ROOT / (source_stem + '_app_probe.ets')) or
            inputs.get('builder_sha256') != digest(ROOT / ('build_' + source_stem + '_app_probe.py'))):
        raise ValueError('actual public caller source, role or ABI changed')
    project = root / 'project'
    abi = ARCHITECTURES[arch][1]
    built = {'module': project / 'entry/src/main/module.json5',
        'generated_source': project / 'entry/src/main/ets/pages/Index.ets',
        'native_library': project / 'entry/libs' / abi / ('lib' + library_stem + 'probe.so'),
        'hap': project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'}
    for key, path in built.items():
        if path.is_symlink() or not path.is_file() or digest(path) != inputs.get(key + '_sha256'):
            raise ValueError('compiled ordinary caller changed: ' + key)
    module = json.loads(built['module'].read_text())['module']
    validate_elf(built['native_library'], arch)
    if module.get('requestPermissions') != []:
        raise ValueError('ordinary caller must not request privileged permissions')
    if built['generated_source'].read_text() != (ROOT / (source_stem + '_app_probe.ets')).read_text().replace('__RUN__', run_id):
        raise ValueError('fresh typed caller does not match its nonce-bearing source')
    # Arkdown strips the packaged .so. Compare the signed payload to the hashed
    # actual build HAP, not to the intentionally unstripped compiler output.
    with zipfile.ZipFile(files['signed_hap']) as signed, zipfile.ZipFile(built['hap']) as unsigned:
        names = unsigned.namelist()
        payload = {}
        for name in names:
            data = unsigned.read(name)
            canonical = canonical_library(name, data) if name.startswith('libs/') else name
            if canonical in payload:
                raise ValueError('duplicate compiled HAP payload')
            payload[canonical] = data
        # Pinned PageInfoGenerator adds only this code-sign executable-page bitmap.
        if (len(signed.namelist()) != len(set(signed.namelist())) or
                set(signed.namelist()) != set(payload) | {'.pages.info'} or
                'libs/' + abi + '/lib' + library_stem + 'probe.so' not in payload or
                any(signed.read(name) != data for name, data in payload.items()) or
                not signed.read('.pages.info') or len(signed.read('.pages.info')) % 8 != 0):
            raise ValueError('signed caller payload differs from the actual build HAP')
    signed_logs = [row for row in document.get('commands', [])
                   if row.get('log') == str(root / 'sign-ordinary-no-permissions.log')]
    if len(signed_logs) != 1 or signed_logs[0].get('exit_code') != 0:
        raise ValueError('actual ordinary code-sign verification required')
    signing_log = root / 'sign-ordinary-no-permissions.log'
    if signing_log.is_symlink() or digest(signing_log) != signed_logs[0].get('sha256'):
        raise ValueError('actual signing transcript changed')
    if not all(marker in signing_log.read_text() for marker in ('verify codesign success',
            'Digest verify result: true', 'verify-app success', 'verify permission sign success')):
        raise ValueError('code signature, digest and ordinary permissions were not verified')
