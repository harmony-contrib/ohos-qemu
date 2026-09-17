#!/usr/bin/env python3
"""Verify the packaged Native child-process libraries, not just source markers."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from verify_runtime_elf_contract import read_elf, verify_machine

GET_INSTANCE = '_ZN4OHOS14AbilityRuntime23ChildProcessArgsManager11GetInstanceEv'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--package', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
package = a.package.resolve()
manifest = json.loads((package / 'manifest.json').read_text())
machine = {'armv7a': 40, 'arm64': 183, 'x86_64': 62}[manifest['guest_arch']]
image = package / 'images/system.img'
debugfs = shutil.which('debugfs')
if not debugfs:
    for path in ('/opt/homebrew/opt/e2fsprogs/sbin/debugfs', '/usr/local/opt/e2fsprogs/sbin/debugfs'):
        if Path(path).is_file():
            debugfs = path
            break
if not debugfs:
    raise SystemExit('debugfs is required')
records = {}
with tempfile.TemporaryDirectory(prefix='native-child-elf-') as tmp:
    def extract(name, subdir):
        dest = Path(tmp) / name
        for prefix in ('/system', ''):
            for libdir in ('lib64', 'lib'):
                path = f'{prefix}/{libdir}/{subdir}/{name}'
                subprocess.run([debugfs, '-R', f'dump {path} {dest}', str(image)], capture_output=True, check=False)
                if dest.is_file() and dest.stat().st_size:
                    info = read_elf(dest)
                    verify_machine(info, machine, dest)
                    data = dest.read_bytes()
                    records[name] = {'image_path': path, 'sha256': hashlib.sha256(data).hexdigest()}
                    return info, data
        raise SystemExit(f'missing packaged library: {name}')
    manager, _ = extract('libchild_process_manager.z.so', 'platformsdk')
    api, api_data = extract('libchild_process.so', 'ndk')
    _, app_data = extract('libapp_manager.z.so', 'platformsdk')
    if GET_INSTANCE not in manager.defined:
        raise SystemExit('manager does not export the shared argument singleton')
    if GET_INSTANCE not in api.undefined or GET_INSTANCE in api.defined:
        raise SystemExit('C API does not import the manager singleton')
    if 'OH_Ability_GetCurrentChildProcessArgs' not in api.defined:
        raise SystemExit('C argument query export missing')
    for marker in (b'child args exceed parameter or parcel capacity', b'child info exceeds parameter or parcel capacity'):
        if marker not in app_data:
            raise SystemExit(f'parameter transport fix missing: {marker!r}')
    if b'entry params exceed 150 KiB' not in api_data:
        raise SystemExit('C API argument-size validation missing')
    if manifest['guest_arch'] == 'armv7a':
        _, spawn_data = extract('libappspawn_common.z.so', 'appspawn/common')
        if b'Failed to rmdir in ProcessMgrRemoveApp' in spawn_data:
            raise SystemExit('armv7a native spawn cleanup logging fix missing')
        extract('libappspawn_sandbox.z.so', 'appspawn/common')
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps({'schema_version': 1, 'guest_arch': manifest['guest_arch'], 'elf_contract_verified': True, 'runtime_tested': False, 'libraries': records}, indent=2) + '\n')
print('Native child-process packaged ELF contract verified: ' + manifest['guest_arch'])
