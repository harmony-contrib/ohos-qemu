#!/usr/bin/env python3
"""Read actual ext-image inodes, HAP signatures and unchanged BMS policies only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
import privacycenter_provider as provider
from verify_alsa_config_image import debugfs_path

POLICIES = ('install_list.json', 'install_list_capability.json', 'install_list_permissions.json', 'uninstall_list.json')


def fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_nlink, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def image_identity(path):
    path = Path(path).absolute()
    ancestry = provider.parents(path)
    before = path.lstat()
    provider.require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size > 0,
                     'one real regular nonaliased system image required')
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        provider.require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before), 'image changed before hashing')
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
        provider.require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before), 'image changed while hashing')
    provider.require(fingerprint(path.lstat()) == fingerprint(before) and provider.parents(path) == ancestry,
                     'image path changed while hashing')
    return {'sha256': digest.hexdigest(), 'bytes': before.st_size}, (fingerprint(before), ancestry)


def parse_stat(stdout, stderr, path):
    """debugfs exit0 is not existence. Distinguish an exact absence from errors."""
    errors = [line.strip() for line in stderr.splitlines() if line.strip() and not re.fullmatch(r'debugfs [0-9][^\n]*', line)]
    if not stdout.strip():
        provider.require(errors == [path + ': File not found by ext2_lookup'],
                         'debugfs lookup did not prove exact path absence: ' + path)
        return None
    provider.require(not errors, 'debugfs stat error for ' + path)
    header = re.findall(r'^Inode:\s+([1-9][0-9]*)\s+Type:\s+(\S+)\s+Mode:\s+([0-7]{3,4})\s+Flags:.*$', stdout, re.M)
    owner = re.findall(r'^User:\s+([0-9]+)\s+Group:\s+([0-9]+)\s+(?:Project:\s+[0-9]+\s+)?Size:\s+([0-9]+)\s*$', stdout, re.M)
    links = re.findall(r'^Links:\s+([1-9][0-9]*)\s+Blockcount:\s+[0-9]+\s*$', stdout, re.M)
    provider.require(len(header) == len(owner) == len(links) == 1 and header[0][1] == 'regular' and
                     all(len(re.findall('^' + field + ':', stdout, re.M)) == 1 for field in ('Inode', 'User', 'Links')),
                     'one regular actual image inode/stat required: ' + path)
    inode, _, mode = header[0]; uid, gid, size = map(int, owner[0])
    provider.require(int(mode, 8) in (0o644, 0o444) and int(links[0]) == 1 and 0 < size <= 32 * 1024 * 1024,
                     'unexpected image file mode/link count/size: ' + path)
    return {'inode': int(inode), 'mode': mode, 'uid': uid, 'gid': gid, 'bytes': size, 'links': int(links[0])}


def dump_unique_file(image, candidates, scratch, executable, commands):
    entries = []
    for index, path in enumerate(candidates):
        stdout, stderr = provider.command([executable, '-R', 'stat ' + path, image], 'image-stat-' + str(index), commands)
        identity = parse_stat(stdout, stderr, path)
        if identity is None: continue
        local = scratch / (str(index) + '.extracted')
        provider.require(not local.exists(), 'new actual image extraction path required')
        stdout, stderr = provider.command([executable, '-R', 'dump ' + path + ' ' + str(local), image],
                                           'image-dump-' + str(index), commands)
        provider.require(not stdout.strip() and all(re.fullmatch(r'debugfs [0-9][^\n]*', line) for line in
                         stderr.splitlines() if line.strip()), 'actual debugfs file dump failed')
        actual = provider.Snapshot.read(local)
        provider.require(len(actual.data) == identity['bytes'], 'actual ext inode/file transfer size differs')
        entries.append((actual, path, identity))
    provider.require(entries and len({entry[2]['inode'] for entry in entries}) == 1 and
                     all(entry[2] == entries[0][2] and entry[0].data == entries[0][0].data for entry in entries),
                     'one actual inode required across both image paths; ambiguous alias rejected')
    return entries[0][0], {'image_path': entries[0][1], 'image_path_aliases': [entry[1] for entry in entries],
                           'stat': entries[0][2], 'sha256': provider.digest(entries[0][0].data)}


def verify(image, source, device, revision, *, executable=None, java='java', openssl='openssl', report=None):
    executable = executable or debugfs_path()
    image = Path(image).absolute()
    identity, before = image_identity(image)
    result = {} if report is None else report
    result.update({'status': 'fail', 'scope': 'offline_actual_PrivacyCenter_image_inode_signature_scan_policy_ONLY',
              'image': {'path': str(image), **identity}, 'device': device, 'native_source_revision': revision,
              'source_signature_commands': [], 'signature_commands': [], 'image_commands': [],
              'provider_runtime_validated': False, 'first_artifact_behavior_gate_passed': False})
    state, result['source'] = provider.verify_source(source, device, revision, java=java, openssl=openssl,
                                                    commands=result['source_signature_commands'])
    with tempfile.TemporaryDirectory(prefix='privacycenter-image-') as temporary:
        scratch = Path(temporary).resolve()
        directory = scratch / 'hap'; directory.mkdir()
        relative = '/app/' + provider.BUNDLE + '/' + provider.FILENAME
        hap, result['hap'] = dump_unique_file(image, (relative, '/system' + relative), directory, executable, result['image_commands'])
        result['payload'] = provider.inspect_payload(hap.data, provider.load(state['public']['payload-inventory.json'].data))
        result['signature'] = provider.verify_signature(hap.data, state['jar'], state['public'], java=java, openssl=openssl,
                                                       commands=result['signature_commands'])
        rows = {name: row.data for name, row in state['policies'].items()}
        result['image_policies'] = {}
        for name in POLICIES:
            directory = scratch / name; directory.mkdir()
            relative = '/etc/app/' + name
            actual, result['image_policies'][name] = dump_unique_file(image, (relative, '/system' + relative), directory,
                                                                      executable, result['image_commands'])
            provider.require(actual.data == rows[name], 'PrivacyCenter packaged policy differs from source: ' + name)
            rows[name] = actual.data
        provider.policy_audit(rows, installed=True)
        provider.recheck(state)
        provider.require((fingerprint(image.lstat()), provider.parents(image)) == before,
                         'system image changed during PrivacyCenter validation')
    result['status'] = 'pass'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system-image', 'source-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', required=True, choices=('phone', '2in1'))
    parser.add_argument('--native-source-revision', required=True)
    parser.add_argument('--debugfs'); parser.add_argument('--java', default='java'); parser.add_argument('--openssl', default='openssl')
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline_PrivacyCenter_image_ONLY',
              'provider_runtime_validated': False, 'first_artifact_behavior_gate_passed': False}
    try:
        provider.require(args.output.absolute() != args.system_image.absolute() and
                         not args.output.absolute().is_relative_to(args.source_root.absolute()), 'evidence output must be outside source/image')
        result = verify(args.system_image, args.source_root, args.device, args.native_source_revision,
                        executable=args.debugfs, java=args.java, openssl=args.openssl, report=result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        result['status'] = 'fail'; result['failures'] = [str(error)]
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': result['status'], 'failures': result.get('failures', [])}))
    return result['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
