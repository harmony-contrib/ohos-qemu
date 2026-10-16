#!/usr/bin/env python3
"""Install the QEMU sensor socket's init directory and dedicated SELinux labels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

REVISIONS = {'vendor/ohemu': 'b56c5a95ec590543691278b85afe9fe228744163',
             'base/security/selinux_adapter': 'cfc1d5b31a7438dbc87763f9222f00337221cf21'}
BUILD = 'vendor/ohemu/virt/etc/BUILD.gn'
BUILD_SHA = '3005aaef5824bb27017d2f6374d890663434e894a73391c8fb13ca9c84ee7768'
BLOCK = '''# The virtual sensor host owns only this dedicated input directory.
ohos_prebuilt_etc("qemu_sensor_input_cfg") {
  source = "qemu_sensor_input.cfg"
  output = "qemu_sensor_input.cfg"
  relative_install_dir = "init"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}

'''
DEPENDENCY = '    ":qemu_sensor_input_cfg",\n'
# These two blocks are owned by the parent calendar resource installer. Both
# installers normalize the same pinned GN base, preserving the other's complete
# declarations rather than treating a legitimate second owner as an unknown edit.
KNOWLEDGE_BLOCK = '''# Trusted optional KnowledgeContent configuration, without fabricated dates.
ohos_prebuilt_etc("qemu_knowledge_resource_contract") {
  source = "knowledge_resource.json"
  output = "resource.json"
  relative_install_dir = "knowledge-content"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}

'''
KNOWLEDGE_DEPENDENCY = '    ":qemu_knowledge_resource_contract",\n'
KNOWLEDGE_ASSET_BLOCK = '''ohos_prebuilt_etc("qemu_knowledge_holidays") {
  source = "qemu_holidays.ics"
  output = "holidays.ics"
  relative_install_dir = "knowledge-content"
  subsystem_name = virt_subsystem_name
  part_name = virt_part_name
}

'''
KNOWLEDGE_ASSET_DEPENDENCY = '    ":qemu_knowledge_holidays",\n'
KNOWLEDGE_GN = ((KNOWLEDGE_BLOCK, KNOWLEDGE_DEPENDENCY),
                (KNOWLEDGE_ASSET_BLOCK, KNOWLEDGE_ASSET_DEPENDENCY))
POLICY = 'base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/qemu_sensor/'
FILES = {
    'vendor/ohemu/virt/etc/qemu_sensor_input.cfg': json.dumps({'jobs': [{
        # init jobs precede TriggerServices(START_MODE_BOOT) in PostInitTriggers.
        'name': 'init', 'cmds': [
            'mkdir /dev/unix/socket/qemu_sensor 0700 sensor_host sensor_host',
            'restorecon /dev/unix/socket/qemu_sensor']} ]}, indent=4) + '\n',
    POLICY + 'public/types.te': '''# SPDX-License-Identifier: Apache-2.0
type qemu_sensor_input_dir, dev_attr, file_attr;
type qemu_sensor_input_socket, dev_attr, file_attr;
''',
    POLICY + 'system/file_contexts': '''# SPDX-License-Identifier: Apache-2.0
/dev/unix/socket/qemu_sensor          -d u:object_r:qemu_sensor_input_dir:s0
/dev/unix/socket/qemu_sensor/input    -s u:object_r:qemu_sensor_input_socket:s0
''',
    POLICY + 'system/runtime.te': '''# SPDX-License-Identifier: Apache-2.0
# No permission to bind directly in the shared /dev/unix/socket directory.
type_transition init dev_unix_socket:dir qemu_sensor_input_dir "qemu_sensor";
type_transition sensor_host qemu_sensor_input_dir:sock_file qemu_sensor_input_socket "input";
allow init qemu_sensor_input_dir:dir { create getattr setattr search relabelto };
allow sensor_host qemu_sensor_input_dir:dir { getattr search write add_name remove_name };
allow sensor_host qemu_sensor_input_socket:sock_file { create getattr setattr write unlink };
allow sensor_host self:unix_stream_socket { create bind listen accept read write getattr getopt setopt shutdown connect connectto };
allow sensor_host dev_random_file:chr_file { getattr open read };
# Only a root HDC command (domain su, UID checked again with SO_PEERCRED)
# may feed external measurements. Public Sensor consumers use the HDI service.
debug_only(`
    allow su dev_unix_socket:dir search;
    allow su qemu_sensor_input_dir:dir search;
    allow su qemu_sensor_input_socket:sock_file { getattr write };
    allow su sensor_host:unix_stream_socket connectto;
')
''',
}


def checked(root, name):
    path = root / name
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('linked sensor runtime source rejected: ' + name)
        cursor = cursor.parent
    return path


def optional(path):
    if path.exists():
        if not path.is_file():
            raise ValueError('regular sensor runtime source required: ' + str(path))
        return path.read_bytes()
    return None


def replace(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.qemu-sensor-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def apply(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('materialized sensor runtime source root required')
    for project, revision in REVISIONS.items():
        path = checked(root, project)
        if (path / '.git').exists() and subprocess.check_output(
                ['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip() != revision:
            raise ValueError('fixed sensor runtime source revision required: ' + project)
    before_build = optional(checked(root, BUILD))
    if before_build is None:
        raise ValueError('QEMU product etc GN file required')
    original = before_build.replace(BLOCK.encode(), b'').replace(DEPENDENCY.encode(), b'')
    foreign = []
    for block, dependency in KNOWLEDGE_GN:
        blocks, dependencies = before_build.count(block.encode()), before_build.count(dependency.encode())
        if blocks not in (0, 1) or blocks != dependencies:
            raise ValueError('partial shared KnowledgeContent GN declarations; preserving source')
        if blocks:
            foreign.append((block, dependency))
        original = original.replace(block.encode(), b'').replace(dependency.encode(), b'')
    if hashlib.sha256(original).hexdigest() != BUILD_SHA:
        raise ValueError('unknown QEMU product etc source; preserving edits')
    anchor = b'group("product_etc_conf") {\n  deps = [\n'
    if original.count(anchor) != 1:
        raise ValueError('fixed product etc dependency group required')
    for block, dependency in foreign:
        original = original.replace(anchor, block.encode() + anchor + dependency.encode())
    final_build = original.replace(anchor, BLOCK.encode() + anchor + DEPENDENCY.encode())
    planned = {name: data.encode() for name, data in FILES.items()}
    planned[BUILD] = final_build
    snapshots = {name: optional(checked(root, name)) for name in planned}
    original_state = snapshots[BUILD] == original and all(snapshots[n] is None for n in FILES)
    final_state = (before_build.count(BLOCK.encode()) == 1 and
                   before_build.count(DEPENDENCY.encode()) == 1 and
                   all(snapshots[n] == planned[n] for n in FILES))
    if not original_state and not final_state:
        raise ValueError('unknown or partial sensor runtime source; preserving all files')
    written = []
    try:
        for name, data in planned.items():
            path = checked(root, name)
            if optional(path) != snapshots[name]:
                raise ValueError('sensor runtime source changed after preflight')
            if snapshots[name] != data:
                replace(path, data)
                written.append(name)
    except BaseException:
        for name in reversed(written):
            path = checked(root, name)
            if snapshots[name] is None:
                path.unlink(missing_ok=True)
            else:
                replace(path, snapshots[name])
        raise
    return {'status': 'source_configuration_ONLY_NOT_policy_build_or_guest_sensor',
            'first_artifact_behavior_gate_passed': False,
            'files_sha256': {n: hashlib.sha256(b).hexdigest() for n, b in planned.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root.absolute()), indent=2))
