#!/usr/bin/env python3
"""Read-only Calendar HAP derivation from a new archive; no boot or source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

from batch_system_calendar_runtime_project import ROOT, checked, record, require, sha, write
import batch_apps_contact_picker_coordinator as signatures
import batch_system_calendar_runtime_protocol as protocol
from run_root_probe import CheckedPackageInfo, checked_package_members, validate_manifest


def archive_inputs(archive, image):
    """Bind exact package metadata and image after checking the entire archive."""
    with tarfile.open(archive, 'r:gz', tarinfo=CheckedPackageInfo) as package:
        members = dict(checked_package_members(package))
        def one(relative, limit):
            member = members.get(relative)
            require(member is not None and member.isfile() and member.size <= limit,
                    'actual bounded root package member required: ' + relative)
            return member
        system = one('images/system.img', 8 * 1024**3)
        require(system.size == image.stat().st_size, 'supplied image length differs from actual archive member')
        digest = hashlib.sha256()
        with package.extractfile(system) as stream:
            for block in iter(lambda: stream.read(1048576), b''):
                digest.update(block)
        require(digest.hexdigest() == sha(image), 'actual archive system.img differs from supplied extraction')
        inputs_raw = package.extractfile(one('build-inputs.json', 16777216)).read()
        manifest_raw = package.extractfile(one('manifest.json', 1024**2)).read()
        inputs, manifest = protocol.decode(inputs_raw), protocol.decode(manifest_raw)
        validate_manifest(manifest, 'arm64', 'phone')
    return system, inputs_raw, manifest_raw, inputs, manifest


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
    system, inputs_raw, manifest_raw, inputs, manifest = archive_inputs(archive, image)
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
