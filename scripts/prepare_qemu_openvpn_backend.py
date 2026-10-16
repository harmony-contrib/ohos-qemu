#!/usr/bin/env python3
"""Install the complete locked QEMU OpenVPN source/GN/init/policy inputs.

This prepares sources only. It does not build a binary, activate a service,
or provide any runtime/representative-package acceptance result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from openvpn_source_archive import validate as validate_archive

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'foundation/communication/netmanager_ext'
POLICY = 'base/security/selinux_adapter'
BASE = 'foundation/communication/netmanager_base'
NATIVE_CFG = BASE + '/services/etc/init/netsysnative.cfg'
NATIVE_CFG_SHA256 = 'e9dd94da52893eeeec00e0988bf9cbc1c46bb66289106e3b8643a310fd5f4419'
REVISIONS = {PROJECT: '8c41289750820fb2ddb347b1205cee9a7b527388',
             BASE: '9831989d54f490d046a632ab13d309580d2fa710',
             POLICY: 'cfc1d5b31a7438dbc87763f9222f00337221cf21'}
BUILD = PROJECT + '/BUILD.gn'
BUILD_SHA256 = '982285f8a99a4eadd4ea272fd718ce618e49dccad0f9a1975ac6c8ba036e4b4c'
COMPONENT = ROOT / 'patches/common' / PROJECT / 'openvpn_backend/files'
MARKER = '.ohos-qemu-openvpn-backend.json'
POLICY_BASE = POLICY + '/sepolicy/ohos_policy/communication/qemu_openvpn/'
POLICY_FILES = {'qemu_openvpn_types.te': 'public/types.te',
                'qemu_openvpn_policy.te': 'system/qemu_openvpn.te',
                'qemu_openvpn_file_contexts': 'system/file_contexts',
                'qemu_openvpn_parameter_contexts': 'system/parameter_contexts'}
RECIPE_FILES = ('scripts/build_openvpn_ohos.py', 'scripts/build_product_openvpn.py',
    'scripts/build_openvpn_ohos_in_docker.sh', 'scripts/openvpn_source_lock.json',
    'scripts/openvpn_source_archive.py', 'scripts/openharmony_release_source_lock.py',
    'scripts/openharmony_7_0_release_source_lock.json',
    'patches/common/third_party/openvpn/ohos_backend/0001-recognize-OHOS-and-isolate-duplicate-UAPI-socket-type.patch')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(root, relative):
    name = Path(relative)
    if name.is_absolute() or '..' in name.parts or not name.parts:
        raise ValueError('relative owned source path required')
    target = root / name
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('linked source path rejected: ' + str(name))
        cursor = cursor.parent
    return target


def read_optional(path):
    if path.exists():
        if not path.is_file():
            raise ValueError('regular source file required: ' + str(path))
        return path.read_bytes()
    return None


def transform_build(original):
    anchor = '''    if (!netmanager_ext_fpga_mode_enable) {
      deps += [
        "$NETMANAGER_EXT_ROOT/services/vpnmanager:net_vpn_manager",
      ]
    }
'''
    addition = '''    if (netmanager_ext_feature_sysvpn && !netmanager_ext_fpga_mode_enable &&
        (product_name == "armv7a_virt" || product_name == "arm64_virt" ||
         product_name == "x86_64_virt")) {
      deps += [ "$NETMANAGER_EXT_ROOT/qemu_openvpn:qemu_openvpn_backend" ]
    }
'''
    text = original.decode()
    if text.count(anchor) != 1:
        raise ValueError('exact fixed vpn_packages GN block required')
    return text.replace(anchor, anchor + addition).encode()


def payloads(archive):
    lock = json.loads((ROOT / 'scripts/openvpn_source_lock.json').read_text())
    validate_archive(archive, lock)
    destination = PROJECT + '/qemu_openvpn/'
    result = {destination + path.name: path.read_bytes()
              for path in sorted(COMPONENT.iterdir())
              if path.is_file() and path.name not in POLICY_FILES and path.name != 'netsysnative.cfg'}
    result[NATIVE_CFG] = (COMPONENT / 'netsysnative.cfg').read_bytes()
    result.update({POLICY_BASE + target: (COMPONENT / source).read_bytes()
                   for source, target in POLICY_FILES.items()})
    result.update({destination + 'recipe/' + name: (ROOT / name).read_bytes()
                   for name in RECIPE_FILES})
    result[destination + 'upstream/openvpn-' + lock['commit'] + '.tar.gz'] = archive.read_bytes()
    return result


def replace_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.qemu-openvpn-install-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install(root, archive):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('materialized source root required')
    for project, revision in REVISIONS.items():
        path = checked(root, project)
        if (path / '.git').exists():
            actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != revision:
                raise ValueError('fixed source revision required: ' + project)
    marker = checked(root, MARKER)
    previous_bytes = read_optional(marker)
    previous = json.loads(previous_bytes) if previous_bytes is not None else {}
    if previous and (previous.get('schema_version') != 1 or
                     previous.get('component') != 'qemu_openvpn_complete_source_inputs'):
        raise ValueError('unknown OpenVPN source inventory; preserving source')
    build_path = checked(root, BUILD)
    current_build = read_optional(build_path)
    if current_build is None:
        raise ValueError('fixed netmanager_ext GN file required')
    # Keep the pristine GN bytes in the owned inventory so that a future recipe
    # can replace its own hook without accepting arbitrary caller modifications.
    original = bytes.fromhex(previous['original_build_hex']) if previous else current_build
    if digest(original) != BUILD_SHA256:
        raise ValueError('unknown netmanager_ext GN source; preserving edits')
    planned = payloads(Path(archive))
    planned[BUILD] = transform_build(original)
    previous_files = previous.get('files_sha256', {})
    snapshots = {}
    for name, data in planned.items():
        path = checked(root, name)
        actual = read_optional(path)
        if name == NATIVE_CFG and actual is None:
            raise ValueError('fixed netsysnative init file required')
        if (actual is not None and actual != data and
                not (name == BUILD and actual == original) and
                not (name == NATIVE_CFG and digest(actual) == NATIVE_CFG_SHA256) and
                previous_files.get(name) != digest(actual)):
            raise ValueError('unknown or modified OpenVPN input; preserving edits: ' + name)
        snapshots[name] = actual
    inventory = {'schema_version': 1, 'component': 'qemu_openvpn_complete_source_inputs',
                 'source_revisions': REVISIONS, 'original_build_hex': original.hex(),
                 'files_sha256': {name: digest(data) for name, data in sorted(planned.items())},
                 'runtime_gate_passed': False, 'first_artifact_behavior_gate_passed': False}
    planned[MARKER] = (json.dumps(inventory, indent=2) + '\n').encode()
    snapshots[MARKER] = previous_bytes
    # Validate every input before publishing any file, then reject concurrent
    # modifications. A write failure restores only this attempt's own changes.
    if any(read_optional(checked(root, name)) != old for name, old in snapshots.items()):
        raise ValueError('source changed during OpenVPN preparation')
    written = []
    try:
        for name, data in planned.items():
            if snapshots[name] == data:
                continue
            replace_bytes(checked(root, name), data)
            written.append(name)
    except BaseException:
        for name in reversed(written):
            path = checked(root, name)
            if snapshots[name] is None:
                path.unlink(missing_ok=True)
            else:
                replace_bytes(path, snapshots[name])
        raise
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    result = install(args.source_root, args.archive)
    print(json.dumps({'status': 'source_inputs_installed_only', 'files': len(result['files_sha256']),
                      'first_artifact_behavior_gate_passed': False}))
