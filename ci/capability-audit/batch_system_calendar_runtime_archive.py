#!/usr/bin/env python3
"""Read-only Calendar HAP derivation from a new archive; no boot or source tree."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

from batch_system_calendar_runtime_project import ROOT, checked, record, require, sha, write
import batch_apps_contact_picker_coordinator as signatures
import batch_system_calendar_runtime_protocol as protocol


def bind(archive, image, signer_jar, output):
    require(not Path(archive).is_symlink() and not Path(image).is_symlink(), 'archive/image alias not accepted')
    archive, image, output = Path(archive).resolve(), Path(image).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    require(not image.is_symlink() and image.is_file() and sha(signer_jar) == signatures.SIGNER_INPUTS['hap-sign-tool.jar'], 'real system image and fixed signer JAR required')
    logs = []
    def command(argv, label):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=120)
        path = output / (label + '.log'); write(path, result.stdout + result.stderr)
        logs.append({'argv': list(map(str, argv)), 'exit_code': result.returncode, **record(path)})
        require(result.returncode == 0, 'actual image/signature inspection failed: ' + label)
        return result.stdout + result.stderr
    with tarfile.open(archive, 'r:gz') as package:
        members = package.getmembers()
        names = [m.name for m in members]
        require(len(names) <= 20000 and len(names) == len(set(names)), 'bounded unique package members required')
        for member in members:
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and '..' not in path.parts and not member.issym() and not member.islnk(), 'unsafe archive alias/path')
        def one(suffix):
            rows = [m for m in members if m.name.endswith(suffix) and m.isfile()]
            require(len(rows) == 1, 'actual unique package member required: ' + suffix)
            return rows[0]
        system = one('/images/system.img')
        require(system.size == image.stat().st_size, 'supplied image length differs from actual archive member')
        digest = hashlib.sha256()
        with package.extractfile(system) as stream:
            for block in iter(lambda: stream.read(1048576), b''):
                digest.update(block)
        require(digest.hexdigest() == sha(image), 'actual archive system.img differs from supplied extraction')
        member = one('/build-inputs.json')
        require(member.size <= 16777216, 'bounded build inputs required')
        inputs_raw = package.extractfile(member).read()
        inputs = protocol.decode(inputs_raw)
        manifest_raw = package.extractfile(one('/manifest.json')).read()
        manifest = protocol.decode(manifest_raw)
    require(manifest.get('guest_arch') == 'arm64' and manifest.get('device_type') == 'phone' and
            manifest.get('device_type_profile') == 'qemu_phone_full_source', 'representative full-source phone package required')
    files = inputs['files_sha256']
    require(inputs['tree_sha256'] == hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), 'frozen build-input tree digest differs')
    prefixes = ('patches/common/applications/standard/calendardata/',
                'patches/common/base/notification/distributed_notification_service/calendar_owner/')
    selected = {name: value for name, value in files.items() if name.startswith(prefixes)}
    require(selected and any('/main_ui/' in n for n in selected) and any('/calendar_owner/' in n for n in selected), 'new reminder UI/consumer frozen inputs missing')
    for name, expected in selected.items():
        require(sha(ROOT / name) == expected, 'current Calendar component differs from packaged frozen input: ' + name)
    write(output / 'build-inputs.json', inputs_raw.decode())
    write(output / 'manifest.json', manifest_raw.decode())
    sys.path.insert(0, str(ROOT / 'scripts'))
    from ext_image_entries import dump_unique_file
    from verify_alsa_config_image import debugfs_path
    hap, inode = dump_unique_file(image, ('/app/com.ohos.calendardata/CalendarData.hap',
        '/system/app/com.ohos.calendardata/CalendarData.hap'), output, debugfs_path())
    module, payload = signatures.hap_contents(hap)
    require(module['app']['bundleName'] == 'com.ohos.calendardata', 'archive provider bundle differs')
    schema = protocol.schema(module)
    embedded, chain = output / 'embedded-profile.p7b', output / 'chain.cer'
    log = command(['java', '-jar', str(signer_jar), 'verify-app', '-inFile', str(hap), '-outCertChain', str(chain), '-outProfile', str(embedded)], 'provider-verify-app')
    require(all(s in log for s in ('verify codesign success', 'Digest verify result: true', 'verify permission sign success', 'verify-app success')), 'actual archive HAP code-sign verification failed')
    signatures.application_leaf(log)
    decoded = output / 'embedded-profile.json'
    require('verify-profile success' in command(['java', '-jar', str(signer_jar), 'verify-profile', '-inFile', str(embedded), '-outFile', str(decoded)], 'provider-verify-profile'), 'actual profile verification failed')
    from check_m144_core_package import verified_profile_content
    profile = verified_profile_content(protocol.decode(decoded.read_text()))
    require(profile['bundle-info']['bundle-name'] == 'com.ohos.calendardata' and
            profile['bundle-info']['apl'] == 'system_core' and profile['bundle-info']['app-feature'] == 'hos_system_app' and
            set(profile['acls']['allowed-acls']) == {'ohos.permission.NOTIFICATION_AGENT_CONTROLLER',
            'ohos.permission.NOTIFICATION_CONTROLLER', 'ohos.permission.PERMISSION_USED_STATS'} and
            len(profile['acls']['allowed-acls']) == 3 and profile['permissions']['restricted-permissions'] == [],
            'archive Calendar original OS profile boundaries differ')
    report = {'schema_version': 1, 'scope': 'actual_archive_system_image_Calendar_HAP_signature_frozen_inputs_ONLY',
        'archive': record(archive), 'system_image': record(image), 'system_member': system.name,
        'build_inputs': record(output / 'build-inputs.json'), 'build_inputs_tree_sha256': inputs['tree_sha256'],
        'manifest': record(output / 'manifest.json'), 'source_component_hashes': selected,
        'signed_hap': record(hap), 'module_payload': payload, 'inode': inode, 'schema': schema,
        'profile': record(decoded), 'commands': logs, 'collector': record(Path(__file__)),
        'not_runtime_validation': True, 'first_artifact_behavior_gate_passed': False}
    write(output / 'archive-provider.json', report)
    return output / 'archive-provider.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'system-image', 'signer-jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(bind(args.archive, args.system_image, args.signer_jar, args.output))
