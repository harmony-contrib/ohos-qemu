#!/usr/bin/env python3
"""Replay the reviewed fixed source patch stacks in this report's scratch only.

No compiler, SDK, container mutation, signer invocation, image or guest is used.
The actual fixed source bytes were read from the RO inspector and are hashed in
fixed-originals.json. All code under review is read from Git e51e3fe.
"""
import argparse
import ast
import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    revision = 'e51e3fed3cabcaf605db46f46eb31962fa4a1150'
    settings = ['source_provider', 'accessibility_service_completion', 'external_input',
                'input_2in1_navigation', 'refresh_rate_page', 'share_picker']
    hap = ['calendar_provider', 'photos_provider', 'settings_provider', 'admin_provider', 'mms_provider']
    prefixes = ['patches/lib', 'ci/capability-audit/fixtures/mms_source_provider',
                'scripts/verify_mms_provider_image.py', 'scripts/package_standard_qemu.sh']
    prefixes += ['patches/common/applications/standard/settings/' + x for x in settings]
    prefixes += ['patches/common/applications/standard/hap/' + x for x in hap]
    prefixes += ['patches/common/applications/standard/mms/' + x for x in ['source_provider', 'send_data_text']]
    archive = subprocess.check_output(['git', '-C', str(args.repository), 'archive', revision, *prefixes])
    originals = json.loads((here / 'fixed-originals.json').read_text())
    report = {'review_commit': revision, 'snapshot_archive_sha256': sha(archive),
              'fixed_originals_sha256': sha((here / 'fixed-originals.json').read_bytes()),
              'scope': 'real_fixed_source_patch_replay_and_read_only_rules_only',
              'products_built': 0, 'haps_signed': 0, 'images_tested': 0,
              'first_artifact_behavior_gate_passed': False, 'commands': []}
    with tempfile.TemporaryDirectory(prefix='.review-scratch-', dir=here) as temp:
        scratch = Path(temp)
        snapshot = scratch / 'repository'
        snapshot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(snapshot, filter='data')
        env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', PYTHONDONTWRITEBYTECODE='1',
                   TMPDIR=str(scratch / 'tmp'), GIT_CEILING_DIRECTORIES=str(scratch))
        (scratch / 'tmp').mkdir()
        source = scratch / 'source'
        source.mkdir()
        for path, row in originals['files'].items():
            raw = gzip.decompress(base64.b64decode(row['gzip_base64']))
            assert sha(raw) == row['sha256']
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

        def run(component, expected=0):
            argv = ['bash', str(snapshot / 'patches/common/applications/standard' / component / 'apply.sh'),
                    '--source-root', str(source)]
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
            row = {'component': component, 'exit_code': result.returncode,
                   'stdout': result.stdout, 'stderr': result.stderr}
            report['commands'].append(row)
            if expected == 0:
                assert result.returncode == 0, row
            else:
                assert result.returncode != 0, row

        for _ in range(3):
            for component in settings:
                run('settings/' + component)
            for component in ['source_provider', 'send_data_text']:
                run('mms/' + component)
            for component in hap:
                run('hap/' + component)
        report['full_stack_cycles'] = 3
        report['final_source_hashes'] = {
            str(p.relative_to(source)): sha(p.read_bytes()) for p in sorted(source.rglob('*'))
            if p.is_file() and '.ohos-qemu-patches' not in p.parts
        }
        target = source / 'applications/standard/settings/product/phone/src/main/ets/pages/SharePicker.ets'
        original = target.read_bytes()

        def snapshot_state():
            return {str(p.relative_to(source)): sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}

        target.unlink()
        before = snapshot_state()
        run('settings/external_input', expected=1)
        assert snapshot_state() == before
        target.write_bytes(original + b'\n// unknown successor\n')
        before = snapshot_state()
        run('settings/external_input', expected=1)
        assert snapshot_state() == before
        target.write_bytes(original)
        report['missing_unknown_share_successor_rejected_without_mutation'] = True

        sys.path.insert(0, str(snapshot / 'patches/lib'))
        spec = importlib.util.spec_from_file_location('review_mms_provider', snapshot / 'patches/lib/mms_provider.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixtures = snapshot / 'ci/capability-audit/fixtures/mms_source_provider'
        profile_raw = gzip.decompress(base64.b64decode((fixtures / 'signature_mms.p7b.gz.b64').read_bytes()))
        assert sha(profile_raw) == module.PROFILE_SHA
        profile = scratch / 'original.p7b'
        profile.write_bytes(profile_raw)
        original_profile = module.cms(profile)  # Real OpenSSL signature verification.
        desired = module.desired_profile(original_profile, (fixtures / 'os-application-leaf.pem').read_bytes())
        restored = copy.deepcopy(desired)
        restored['bundle-info']['distribution-certificate'] = original_profile['bundle-info']['distribution-certificate']
        restored['validity']['not-after'] = original_profile['validity']['not-after']
        assert restored == original_profile
        report['original_cms_profile_verified'] = True
        report['desired_profile_changes_only_leaf_and_finite_expiry'] = True
        for expected in [module.CAPABILITY, module.GRANTS]:
            value = {'install_list': [copy.deepcopy(expected)]}
            changed = module.policy(json.dumps(value).encode(), expected)
            assert json.loads(changed)['install_list'] == [dict(expected, app_signature=[module.SIGNATURE])]
            assert module.policy(changed, expected, require_current=True) == changed
        report['exact_existing_policy_rows_rebound_idempotently'] = True

        image_script = snapshot / 'scripts/verify_mms_provider_image.py'
        image_ast = ast.parse(image_script.read_text())
        literals = {node.value for node in ast.walk(image_ast) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert 'install_list_capability.json' in literals and 'install_list_permissions.json' in literals
        assert 'install_list.json' not in literals
        assert 'install_list.json' in (snapshot / 'patches/lib/mms_provider.py').read_text()
        report['image_preinstall_selection_missing_in_reviewed_guard'] = {
            'status': 'confirmed_read_only_control_flow_gap',
            'image_install_list_read': False,
            'source_install_list_read': True,
            'scope': 'AST/source observation; no synthetic successful image/signature substituted',
        }
        report['reviewed_file_hashes'] = {
            str(p.relative_to(snapshot)): sha(p.read_bytes()) for p in snapshot.rglob('*')
            if p.is_file() and p.suffix in ['.py', '.sh', '.patch']
        }
    report['status'] = 'pass'
    report['scratch_removed'] = True
    (here / 'replay-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'full_stack_cycles',
          'missing_unknown_share_successor_rejected_without_mutation', 'original_cms_profile_verified',
          'desired_profile_changes_only_leaf_and_finite_expiry', 'scratch_removed']}))


if __name__ == '__main__':
    main()
