#!/usr/bin/env python3
"""Install the explicit QEMU GNSS target and private input directory/policy.

Source preparation only; actual loading and public fixes need new-image tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_qemu_sensor_runtime import checked, optional, replace

REVISIONS = {'device/qemu': 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b',
             'base/security/selinux_adapter': 'cfc1d5b31a7438dbc87763f9222f00337221cf21'}
BUILD = 'device/qemu/common/virt_full/BUILD.gn'
BUILD_SHA256 = 'b263fd6a8686efd2597a02b2db13b2e413e62ff598c757a368b828c3229452e6'
DIRECTORY = 'device/qemu/common/virt_full/qemu_gnss_runtime/'
POLICY = 'base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/qemu_gnss/'
DEPENDENCY = '    "//device/qemu/common/virt_full/qemu_gnss_runtime:qemu_gnss_runtime",\n'
FILES = {
    DIRECTORY + 'BUILD.gn': '''# SPDX-License-Identifier: Apache-2.0
import("//build/ohos.gni")
import("//device/qemu/common/virt_full/device.gni")
ohos_prebuilt_etc("qemu_gnss_input_cfg") {
  source = "qemu_gnss_input.cfg"
  output = "qemu_gnss_input.cfg"
  relative_install_dir = "init"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}
group("qemu_gnss_runtime") {
  deps = [
    ":qemu_gnss_input_cfg",
    ":qemu_gnss_standalone_param",
    "//device/qemu/common/virt_full/external_gnss:qemu_external_gnss",
  ]
}
ohos_prebuilt_etc("qemu_gnss_standalone_param") {
  source = "qemu_gnss.para"
  output = "qemu_gnss.para"
  relative_install_dir = "param"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}
''',
    # Actual LocationConfigManager uses this parameter and MODE_STANDALONE=1.
    # The virtual provider implements this mode without assistance services.
    DIRECTORY + 'qemu_gnss.para': 'const.location.supl_mode=1\n',
    DIRECTORY + 'qemu_gnss_input.cfg': json.dumps({'jobs': [{
        'name': 'init', 'cmds': [
            'mkdir /dev/unix/socket/qemu_gnss 0700 location_host location_host',
            'restorecon /dev/unix/socket/qemu_gnss']} ]}, indent=4) + '\n',
    POLICY + 'public/types.te': '''# SPDX-License-Identifier: Apache-2.0
type qemu_gnss_input_dir, dev_attr, file_attr;
type qemu_gnss_input_socket, dev_attr, file_attr;
''',
    POLICY + 'vendor/file_contexts': '''# SPDX-License-Identifier: Apache-2.0
/dev/unix/socket/qemu_gnss          -d u:object_r:qemu_gnss_input_dir:s0
/dev/unix/socket/qemu_gnss/input    -s u:object_r:qemu_gnss_input_socket:s0
''',
    POLICY + 'vendor/runtime.te': '''# SPDX-License-Identifier: Apache-2.0
type_transition init dev_unix_socket:dir qemu_gnss_input_dir "qemu_gnss";
type_transition location_host qemu_gnss_input_dir:sock_file qemu_gnss_input_socket "input";
allow init qemu_gnss_input_dir:dir { create getattr setattr search relabelto };
allow location_host qemu_gnss_input_dir:dir { getattr search write add_name remove_name };
allow location_host qemu_gnss_input_socket:sock_file { create getattr setattr write unlink };
allow location_host self:unix_stream_socket { create bind listen accept read write getattr getopt setopt shutdown connect connectto };
allow location_host dev_random_file:chr_file { getattr open read };
# Debug HDC writer additionally authenticates real UID zero in the provider.
debug_only(`
    allow su dev_unix_socket:dir search;
    allow su qemu_gnss_input_dir:dir search;
    allow su qemu_gnss_input_socket:sock_file { getattr write };
    allow su location_host:unix_stream_socket connectto;
')
''',
}


def apply(root):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('materialized QEMU GNSS runtime source root required')
    for project, revision in REVISIONS.items():
        path = checked(root, project)
        if (path / '.git').exists() and subprocess.check_output(
                ['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip() != revision:
            raise ValueError('fixed QEMU GNSS runtime source revision required: ' + project)
    current = optional(checked(root, BUILD))
    if current is None or current.count(DEPENDENCY.encode()) not in (0, 1):
        raise ValueError('fixed device GN dependency group required')
    original = current.replace(DEPENDENCY.encode(), b'')
    if hashlib.sha256(original).hexdigest() != BUILD_SHA256:
        raise ValueError('unknown QEMU device GN source; preserving caller edits')
    anchor = b'group("virt_group") {\n  deps = [\n'
    if original.count(anchor) != 1:
        raise ValueError('one fixed virt_group GN block required')
    planned = {name: value.encode() for name, value in FILES.items()}
    planned[BUILD] = original.replace(anchor, anchor + DEPENDENCY.encode())
    snapshots = {name: optional(checked(root, name)) for name in planned}
    first = current == original and all(snapshots[name] is None for name in FILES)
    final = all(snapshots[name] == value for name, value in planned.items())
    if not first and not final:
        raise ValueError('unknown or partial QEMU GNSS runtime files; preserving source')
    written = []
    try:
        for name, value in planned.items():
            path = checked(root, name)
            if optional(path) != snapshots[name]:
                raise ValueError('GNSS runtime source changed after preflight')
            if snapshots[name] != value:
                replace(path, value)
                written.append(name)
    except BaseException:
        for name in reversed(written):
            path = checked(root, name)
            if snapshots[name] is None:
                path.unlink(missing_ok=True)
            else:
                replace(path, snapshots[name])
        raise
    return {'status': 'source_runtime_installed_ONLY_NOT_device_loading_or_public_GNSS',
        'source_revisions': REVISIONS,
        'files_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in planned.items()},
        'first_artifact_behavior_gate_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root), indent=2))
