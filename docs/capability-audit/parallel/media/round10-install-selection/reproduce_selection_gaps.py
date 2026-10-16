#!/usr/bin/env python3
"""Isolated read-only checker tests. No actual image/HAP/guest acceptance."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def load(name, path, root=None, revision=None):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    if revision is None:
        spec.loader.exec_module(value)
    else:
        raw = subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path.relative_to(root).as_posix()])
        exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = args.root.resolve()
    baseline = json.loads((args.output.parent / 'review-inputs.json').read_text())['main_head']
    sys.path.insert(0, str(root / 'scripts'))
    sys.path.insert(0, str(root / 'patches/lib'))
    observation = json.loads((args.output.parent / 'source-observations.json').read_text())
    original = json.loads(observation['source_files']['vendor/ohemu/virt/preinstall-config/install_list.json']['content'])
    report = {'scope': 'isolated_policy_and_source_type_checks_with_controlled_dependencies_NOT_image_or_guest_acceptance',
              'baseline_commit': baseline, 'image_policy_checks': [], 'admin_source_type_checks': [], 'closed_requirements': [],
              'first_artifact_behavior_gate_passed': False}
    for role, class_name in [('settings', 'SettingsImageBoundary'), ('photos', 'PhotosImageBoundary')]:
        fixtures = load('review_' + role + '_fixture', root / 'ci/capability-audit' / ('test_' + role + '_provider_image.py'))
        verifier = load('review_old_' + role, root / 'scripts' / ('verify_' + role + '_provider_image.py'), root, baseline)
        fixtures.provider = verifier
        bundle = 'com.ohos.' + role
        for fault in ('missing_target', 'wrong_directory', 'removable_true', 'uninstall_veto'):
            with tempfile.TemporaryDirectory(prefix='selection-review-', dir=args.output.parent) as temporary:
                base = Path(temporary)
                fixture = getattr(fixtures, class_name)()
                fixture.temporary = SimpleNamespace(name=str(base))
                source, directory, _ = fixture.policy_fixture()
                # Existing policy fixtures have no source install_list at all.
                source_check = verifier.verify_preinstall_policies(source)
                image = {name: (directory / name).read_bytes() for name in source_check}
                installs = copy.deepcopy(original)
                rows = installs['install_list']
                target = next(r for r in rows if r['app_dir'] == '/system/app/' + bundle)
                uninstalls = {'uninstall_list': [], 'recover_list': []}
                if fault == 'missing_target': rows.remove(target)
                elif fault == 'wrong_directory': target['app_dir'] += '.wrong'
                elif fault == 'removable_true': target['removable'] = True
                else: uninstalls['uninstall_list'].append(target['app_dir'])
                image['install_list.json'] = json.dumps(installs).encode()
                image['uninstall_list.json'] = json.dumps(uninstalls).encode()
                requested = []
                def extract(_image, candidates, destination, _executable):
                    name = Path(candidates[0]).name
                    requested.append(name)
                    path = destination / 'controlled-extracted-file'
                    path.write_bytes(image[name])
                    return path, {'image_path': candidates[0], 'image_inode': 5}
                scratch = base / 'scratch';scratch.mkdir()
                with patch.object(verifier, 'dump_unique_file', side_effect=extract), \
                        patch.object(verifier, 'debugfs_path', return_value='/controlled/debugfs'):
                    verifier.verify_preinstall_policies(source, base / 'NOT-real-system.img', scratch)
                assert requested == ['install_list_capability.json', 'install_list_permissions.json']
                report['image_policy_checks'].append({'provider': role, 'fault': fault,
                    'source_install_list_absent': not (directory / 'install_list.json').exists(),
                    'requested_image_files': requested, 'isolated_policy_check_accepted': True})
    # Exercise the actual Admin verify() selection branch. Only unrelated crypto,
    # manifest validation, and certificate parsing dependencies are controlled.
    admin = load('review_admin_guard', root / 'patches/lib/admin_provider.py', root, baseline)
    with tempfile.TemporaryDirectory(prefix='admin-selection-review-', dir=args.output.parent) as temporary:
        base = Path(temporary)
        project = base / 'applications/standard/admin_provisioning'
        (project / 'entry/src/main').mkdir(parents=True)
        (project / 'entry/src/main/module.json5').write_text('{"module":{}}')
        (project / 'BUILD.gn').write_text('ohos_app("adminprovisioning_hap")\ncertificate_profile = "signature/adminprovisioning.p7b"\nmodule_install_dir = "app/com.ohos.adminprovisioning"\nassemble_type = "assembleHap"\n')
        cert = base / 'developtools/hapsigner/dist/OpenHarmonyApplication.pem'
        cert.parent.mkdir(parents=True);cert.write_bytes(b'controlled certificate dependency')
        directory = base / 'vendor/ohemu/virt/preinstall-config';directory.mkdir(parents=True)
        for name, row in admin.POLICIES.items():
            (directory / name).write_text(json.dumps({'install_list': [row]} if 'capability' in name else [row]))
        decoded = SimpleNamespace(stdout=b'{"bundle-info":{"distribution-certificate":"controlled"}}')
        for removable, expected in [(False, True), (0, True), (0.0, True), (True, False)]:
            (directory / 'install_list.json').write_text(json.dumps({'install_list': [
                {'app_dir': '/system/app/' + admin.BUNDLE, 'removable': removable}]}))
            with patch.object(admin.subprocess, 'run', return_value=decoded), \
                    patch.object(admin, 'validate', return_value=None), \
                    patch.object(admin, 'certificate_fingerprint', return_value=admin.SIGNATURE), \
                    patch.object(admin, 'platform_leaf_fingerprint', return_value=admin.SIGNATURE):
                try:
                    admin.verify(base)
                    accepted = True
                except ValueError as error:
                    accepted = False
                    failure = str(error)
            assert accepted is expected, (removable, accepted, failure if not accepted else '')
            report['admin_source_type_checks'].append({'removable': removable, 'python_type': type(removable).__name__,
                                                        'actual_selection_branch_accepted': accepted})
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'isolated_image_policy_omissions': len(report['image_policy_checks']),
                      'admin_invalid_numeric_false_accepted': 2, 'guest_or_image_acceptance': False}))


if __name__ == '__main__':
    main()
