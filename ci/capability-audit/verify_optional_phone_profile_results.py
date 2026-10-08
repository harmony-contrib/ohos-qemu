"""Only outside-official-phone false declarations may close from actual discovery."""
import json
from pathlib import Path
import re
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
sys.path.insert(0, str(ROOT / 'patches/lib'))
sys.path.insert(0, str(ROOT / 'scripts'))
from device_contract import active_official_requirements
from run_normal_hap_probe import require_normal_identity
from verify_native_gap_abi_image import declared_syscaps

OPTIONAL = {
    'SystemCapability.SelectionInput.Selection': 'behavior:selection-input-device-contract-gap',
    'SystemCapability.FileManagement.File.Environment.FolderObtain': 'behavior:folder-obtain-device-contract-failure',
    'SystemCapability.USB.USBManager.Serial': 'behavior:usb-serial-device-query',
    'SystemCapability.Print.PrintFramework': 'behavior:print-framework-missing-runtime-extension',
}
POSITIVE = ('SystemCapability.ArkUI.ArkUI.Full', 'SystemCapability.Multimedia.Camera.Core')
SCOPE = 'actual_phone_image_and_ordinary_dynamic_canIUse_NOT_official_profile_or_provider_exemption'


def verify_runtime(text, run_id, identity):
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh actual capability-discovery challenge required')
    names = [*OPTIONAL, *POSITIVE, 'SystemCapability.QemuOwned.' + run_id, '']
    expected = [False] * 4 + [True] * 2 + [False] * 2
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != 33 * len(names) + 1:
        raise ValueError('complete original discovery, 32 repeated rounds and summary required')
    for index, row in enumerate(rows[:-1]):
        name, wanted = names[index % len(names)], expected[index % len(names)]
        if (set(row) != {'runId', 'syscap', 'observed', 'error'} or row['runId'] != run_id or
            row['syscap'] != name or type(row['observed']) is not bool or
            row['observed'] is not wanted or row['error'] != ''):
            raise ValueError('actual runtime discovery is wrong, stale, missing, reordered or failed')
    if rows[-1] != {'runId': run_id, 'syscap': 'summary', 'observed': True, 'error': ''} or type(
            rows[-1]['observed']) is not bool:
        raise ValueError('actual capability-discovery summary required')
    return {'repeated_rounds': 32, 'actual_dynamic_canIUse_observations': len(rows) - 1}


def verify(text, run_id, identity, profile, syscap):
    runtime = verify_runtime(text, run_id, identity)
    policy = profile['qemu_adaptations']
    protected = (active_official_requirements(policy) |
        set(policy['explicit_qemu_requirements']) | set(policy['enabled_required_syscaps']))
    excluded = set(policy['excluded_unsupported_syscaps'])
    declared = declared_syscaps(syscap)
    if (profile.get('device_type') != 'phone' or set(OPTIONAL) & protected or
        not set(OPTIONAL) <= excluded or set(OPTIONAL) & declared or
        not protected <= declared or not set(POSITIVE) <= declared):
        raise ValueError('cannot exclude official/requested capabilities or retain false declarations')
    return {**runtime, 'closed': list(OPTIONAL.values()),
        'actual_image_and_runtime_discovery_agree': True,
        'not_claimed': 'implementation_of_excluded_optional_features_or_any_official_capability'}


def verify_evidence(document, root, boot, archive_sha, boot_id):
    from optional_phone_profile_contract import verify_inputs
    from optional_phone_profile_image import verify_capture
    from run_root_probe import digest
    root = Path(root)
    arch = document.get('arch')
    if (document.get('status') != 'pass' or document.get('persona') != 'optional-phone-profile' or
            arch not in ('arm64', 'armv7a', 'x86_64') or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id):
        raise ValueError('ordinary profile discovery is not from this archive and owned boot')
    paths = {'result': root / 'verified-result.json', 'raw_results': root / 'results.log',
        'ordinary_identity': root / 'application-identity.json',
        'compiled_contract_inputs': root / 'project/optional-phone-profile-probe-inputs.json'}
    for key, path in paths.items():
        if (path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256') or
                key in ('result', 'compiled_contract_inputs') and document.get(key) != str(path)):
            raise ValueError('original discovery runtime/identity/caller results changed or disappeared')
    verification = json.loads(paths['result'].read_text())
    if (verification.get('status') != 'pass' or verification.get('scope') != SCOPE or
            verification.get('archive_sha256') != archive_sha or verification.get('boot_id') != boot_id or
            verification.get('arch') != arch or verification.get('run_id') != document.get('run_id') or
            verification.get('verifier_sha256') != digest(Path(__file__)) or
            verification.get('results_sha256') != digest(paths['raw_results']) or
            verification.get('application_identity_sha256') != digest(paths['ordinary_identity']) or
            verification.get('compiled_inputs_sha256') != digest(paths['compiled_contract_inputs'])):
        raise ValueError('checked public discovery evidence does not match all original inputs')
    inputs = json.loads(paths['compiled_contract_inputs'].read_text())
    if inputs.get('generated_source') != str(root / 'project/entry/src/main/ets/pages/Index.ets'):
        raise ValueError('discovery source escaped the actual fresh compiled caller project')
    verify_inputs(inputs, arch, document['run_id'])
    profile, syscap = verify_capture(verification, root, boot, archive_sha, arch, boot_id)
    result = verify(paths['raw_results'].read_text(), document['run_id'],
        paths['ordinary_identity'].read_text(), profile, syscap)
    if verification.get('result') != result:
        raise ValueError('reported discovery closure differs from actual image and ordinary app results')
    return result


def main():
    import argparse
    from optional_phone_profile_contract import verify_inputs
    from optional_phone_profile_image import capture
    from run_root_probe import digest
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'boot', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--docker-image', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'archive_sha256': digest(args.archive),
        'run_id': args.run_id, 'boot_id': args.boot_id, 'arch': args.arch,
        'results_sha256': digest(args.results), 'compiled_inputs_sha256': digest(args.inputs),
        'application_identity_sha256': digest(args.application_identity),
        'verifier_sha256': digest(Path(__file__)), 'failures': [],
        'first_artifact_behavior_gate_passed': False}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.arch, args.run_id)
        # Failed public discovery cannot be hidden by a correct JSON profile.
        verify_runtime(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report.update(capture(args.boot, args.archive, args.arch, args.boot_id, args.output.parent,
            args.docker_image))
        files = report['image_contract_files']
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text(),
            json.loads(Path(files['device-profile.json']['file']).read_text()),
            json.loads(Path(files['actual-image-syscap.json']['file']).read_text()))
        if report['actual_syscap_image_entry'] != json.loads(Path(
                files['native-gap-abi-image.json']['file']).read_text()).get('actual_syscap_image_entry'):
            raise ValueError('actual captured SysCap inode/path differs from packaged ABI evidence')
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
