"""Explicit same-image/test-only updates; production input equality is mandatory."""
import hashlib
import json
from pathlib import Path
import re

# These files only build/run/verify test callers. No image builders, product
# patches, audit expectations or launchers may be substituted by this mechanism.
TEST_ONLY = frozenset('ci/capability-audit/' + name for name in (
    'boot_package.py', 'validation_input_binding.py', 'test_validation_input_binding.py',
    'build_luminance_probe.py', 'build_screen_blink_probe.py', 'luminance_sampler_probe.ets',
    'run_luminance_probe.py', 'run_packaged_qemu_suite.py', 'run_packaged_screen_blink_probe.py',
    'run_screen_blink_probe.py', 'run_wifi_scan_diagnostic.py', 'screen_blink_probe.ets',
    'screen_blink_runtime.py', 'sign_luminance_probe.py', 'test_luminance_results.py',
    'test_packaged_screen_blink.py', 'test_router_observer.py', 'test_screen_blink_results.py',
    'test_screen_blink_runtime.py', 'test_wifi_scan_diagnostic.py', 'verify_gap_closure.py',
    'verify_luminance_results.py', 'verify_router_observer_results.py', 'verify_screen_blink_results.py'))


def tree_digest(files):
    if not isinstance(files, dict) or not files or any(
            not isinstance(name, str) or not isinstance(value, str) or
            re.fullmatch('[a-f0-9]{64}', value) is None for name, value in files.items()):
        raise ValueError('invalid frozen file identity')
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def verify_update(inputs, current, archive_sha256, path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular explicit validation update receipt required')
    raw = path.read_bytes()
    receipt = json.loads(raw)
    original = inputs.get('files_sha256')
    original_tree, current_tree = tree_digest(original), tree_digest(current)
    changed = sorted(name for name in original.keys() | current.keys()
                     if original.get(name) != current.get(name))
    if (inputs.get('tree_sha256') != original_tree or
            set(receipt) != {'schema_version', 'archive_sha256', 'build_tree_sha256',
                             'validation_tree_sha256', 'changed_test_files'} or
            type(receipt['schema_version']) is not int or receipt['schema_version'] != 1 or
            receipt['archive_sha256'] != archive_sha256 or
            receipt['build_tree_sha256'] != original_tree or
            receipt['validation_tree_sha256'] != current_tree or
            receipt['changed_test_files'] != changed or not changed or
            not set(changed).issubset(TEST_ONLY) or not original.keys() <= current.keys()):
        raise ValueError('validation-only update does not match exact archive/build/test identities')
    return dict(scope='explicit_test_only_update_NO_image_or_production_input_change',
                receipt=str(path.resolve()), receipt_sha256=hashlib.sha256(raw).hexdigest(),
                build_tree_sha256=original_tree, validation_tree_sha256=current_tree,
                changed_test_files=changed)
