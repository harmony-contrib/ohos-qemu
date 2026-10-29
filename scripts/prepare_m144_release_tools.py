#!/usr/bin/env python3
"""Install and attest non-Git M144 build tools from the fixed DEPS.

Do not run upstream gclient sync over OHOS forks. Hash/size/generation are
read from the pinned source. Existing conflicting files are never overwritten.
GN can be built from its exact fixed source when CIPD is inaccessible.
"""
import argparse
import ast
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile

CHROMIUM = 'a8168622b056f25c2e68d5f12fe2759bad2d9a44'
GN_REVISION = '6e0b557db44b3c164094e57687d20ba036a80667'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def literal_entry(tree, assignment, key):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == assignment
                                               for target in node.targets):
            if not isinstance(node.value, ast.Dict):
                raise ValueError('expected a fixed literal DEPS dictionary')
            for candidate, value in zip(node.value.keys, node.value.values):
                if isinstance(candidate, ast.Constant) and candidate.value == key:
                    return ast.literal_eval(value)
    raise ValueError('missing fixed DEPS entry: ' + assignment + '/' + key)


def selected_objects(text):
    tree = ast.parse(text)
    if literal_entry(tree, 'vars', 'gn_version') != 'git_revision:' + GN_REVISION:
        raise ValueError('GN does not match the fixed release DEPS')
    names = {
        'src/third_party/llvm-build/Release+Asserts': ('Linux_x64/clang-llvmorg-', 'Linux_x64/llvmobjdump-'),
        'src/third_party/rust-toolchain': ('Linux_x64/rust-toolchain-',),
        'src/third_party/node/linux': None,
        'src/third_party/node/node_modules': None,
        'src/buildtools/linux64-format': None,
    }
    result = []
    for path, prefixes in names.items():
        entry = literal_entry(tree, 'deps', path)
        if entry['dep_type'] != 'gcs' or not re.fullmatch(r'[a-z0-9-]+', entry['bucket']):
            raise ValueError('unexpected non-Git build-tool source')
        objects = [obj for obj in entry['objects'] if prefixes is None or obj['object_name'].startswith(prefixes)]
        if len(objects) != (len(prefixes) if prefixes else 1):
            raise ValueError('ambiguous/missing Linux build-tool object: ' + path)
        for obj in objects:
            if (not re.fullmatch(r'[0-9a-f]{64}', obj['sha256sum']) or type(obj['size_bytes']) is not int or
                    obj['size_bytes'] <= 0 or type(obj['generation']) is not int):
                raise ValueError('incomplete fixed GCS integrity metadata')
            result.append({'path': path.removeprefix('src/'), 'bucket': entry['bucket'], **obj})
    return result


def fetch(cache, spec, seed_candidates=()):
    if cache.is_symlink():
        raise ValueError('tool-download cache must not be an alias')
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (spec['sha256sum'] + '.payload')
    lock = cache / (spec['sha256sum'] + '.lock')
    if target.is_symlink() or lock.is_symlink():
        raise ValueError('cached payload/lock must not alias another file')
    with lock.open('a+b') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if target.exists():
            if sha(target) != spec['sha256sum'] or ('size_bytes' in spec and target.stat().st_size != spec['size_bytes']):
                raise ValueError('existing cached tool archive differs')
            return target
        scratch = Path(tempfile.mkdtemp(prefix='download-', dir=cache)) / 'payload'
        seed = next((p for p in seed_candidates if p.is_file() and not p.is_symlink() and
                     sha(p) == spec['sha256sum']), None)
        if seed:
            shutil.copy2(seed, scratch)
        else:
            url = spec.get('url') or ('https://storage.googleapis.com/' + spec['bucket'] + '/' +
                                      spec['object_name'] + '?generation=' + str(spec['generation']))
            subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--connect-timeout', '10',
                            '--max-time', '1800', '--output', str(scratch), url], check=True)
        if sha(scratch) != spec['sha256sum'] or ('size_bytes' in spec and scratch.stat().st_size != spec['size_bytes']):
            raise ValueError('downloaded tool archive integrity differs')
        scratch.rename(target)
    return target


def safe_member(member, allow_linux_escaped_names=False):
    path = PurePosixPath(member.name)
    unsafe_backslash = ('\\' in member.name and (not allow_linux_escaped_names or
                         re.search(r'\\(?!x[0-9a-fA-F]{2})', member.name)))
    if (path.is_absolute() or '..' in path.parts or unsafe_backslash or
            not (member.isfile() or member.isdir() or member.issym() or member.islnk())):
        raise ValueError('unsafe tool archive path/type: ' + member.name)
    if member.issym() or member.islnk():
        link = PurePosixPath(member.linkname)
        unsafe_link_backslash = ('\\' in member.linkname and (not allow_linux_escaped_names or
                                  re.search(r'\\(?!x[0-9a-fA-F]{2})', member.linkname)))
        if link.is_absolute() or unsafe_link_backslash:
            raise ValueError('absolute/invalid tool archive link')
        parts = list(path.parent.parts if member.issym() else ())
        for part in link.parts:
            if part == '..':
                if not parts:
                    raise ValueError('escaping tool archive link')
                parts.pop()
            elif part != '.':
                parts.append(part)


def tree_entries(root):
    files = {}
    for current, directories, names in os.walk(root, followlinks=False):
        for name in (*directories, *names):
            path = Path(current) / name
            if path.is_symlink():
                files[path.relative_to(root).as_posix()] = {'link': os.readlink(path)}
            elif path.is_file():
                files[path.relative_to(root).as_posix()] = {'sha256': sha(path), 'executable': bool(path.stat().st_mode & 0o111)}
    return files


def tool_data_filter(member, destination):
    # Some distro backports of PEP 706 incorrectly validate a symlink's
    # target relative to the extraction root, not its parent directory.
    # Validate its root-relative equivalent as a hardlink, which has those
    # semantics on both backported and current Python, then retain the exact
    # original symlink. data_filter still checks actual ancestor symlinks and
    # strips ownership/unsafe modes; this is not a fully_trusted fallback.
    if member.issym():
        rooted = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
        equivalent = copy.copy(member)
        equivalent.type, equivalent.linkname = tarfile.LNKTYPE, rooted
        checked = tarfile.data_filter(equivalent, destination)
        checked.type, checked.linkname, checked.mode = tarfile.SYMTYPE, member.linkname, None
        return checked
    return tarfile.data_filter(member, destination)


def tree_proof(entries):
    # Bound the top-level artifact report while binding every actual installed
    # path/content/mode (including any explicitly preserved LF normalization).
    return {'file_count': len(entries), 'tree_sha256': hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'preserved_normalization': {name: record for name, record in entries.items()
                                   if 'preserved_existing_normalization' in record}}


def install_tree(stage, target, allow_crlf_normalized=False):
    entries = tree_entries(stage)
    if target.is_symlink():
        raise ValueError('tool installation root must not be an alias')
    for name, record in entries.items():
        path = target / name
        if path.exists() or path.is_symlink():
            if 'link' in record:
                if not path.is_symlink() or os.readlink(path) != record['link']:
                    raise ValueError('existing tool link differs: ' + name)
            elif path.is_symlink() or not path.is_file():
                raise ValueError('existing tool file differs: ' + name)
            elif sha(path) != record['sha256']:
                wanted, actual = (stage / name).read_bytes(), path.read_bytes()
                if (not allow_crlf_normalized or b'\0' in wanted or
                        actual != wanted.replace(b'\r\n', b'\n')):
                    raise ValueError('existing tool file differs: ' + name)
                # Existing nohooks caches may have normalized textual module
                # line endings. Preserve, hash and report that exact content;
                # never accept an arbitrary code/license change or binary.
                wanted.decode('utf-8')
                record.update(source_archive_sha256=record['sha256'], sha256=sha(path),
                              preserved_existing_normalization='CRLF_to_LF_only')
        for parent in path.parents:
            if parent == target:
                break
            if parent.is_symlink():
                try:
                    parent.resolve().relative_to(target.resolve())
                except ValueError:
                    raise ValueError('existing tool ancestor escapes owned tree')
    target.mkdir(parents=True, exist_ok=True)
    for name, record in sorted(entries.items(), key=lambda item: (len(Path(item[0]).parts), item[0])):
        path = target / name
        if path.exists() or path.is_symlink():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if 'link' in record:
            path.symlink_to(record['link'])
        else:
            shutil.copy2(stage / name, path)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--tool-source-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('fixed M144 tools require the Linux amd64 build container')
    source = args.source_root.resolve()
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != CHROMIUM:
        raise ValueError('wrong fixed Chromium source')
    deps = (source / 'DEPS').read_bytes()
    if deps != subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:DEPS']):
        raise ValueError('non-Git tool selection must use the unchanged fixed DEPS')
    if args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError('tool preparation evidence already exists')
    work = Path(tempfile.mkdtemp(prefix='m144-tools-', dir=source.parent))
    report = {'scope': 'fixed_non_Git_release_build_tools_NOT_guest_acceptance', 'chromium_revision': CHROMIUM,
              'DEPS_sha256': hashlib.sha256(deps).hexdigest(), 'tools': [],
              'first_artifact_behavior_gate_passed': False}
    for index, spec in enumerate(selected_objects(deps.decode())):
        target = source / spec['path']
        filename = spec.get('output_file', '')
        hidden = '.' + spec['object_name'].replace('/', '_')
        archive = fetch(args.cache_root, spec, (target / filename, target / hidden))
        stage = work / str(index)
        stage.mkdir()
        if tarfile.is_tarfile(archive):
            with tarfile.open(archive) as tar:
                for member in tar.getmembers():
                    safe_member(member)
                tar.extractall(stage, filter=tool_data_filter)
        else:
            if filename != 'clang-format':
                raise ValueError('unexpected non-archive build tool')
            shutil.copy2(archive, stage / filename)
            (stage / filename).chmod(0o755)
        installed = install_tree(stage, target, allow_crlf_normalized=spec['path'] == 'third_party/node/node_modules')
        report['tools'].append({'source': spec, 'archive_sha256': sha(archive), 'installed': tree_proof(installed)})
    # Host snapshot/code-generation tools also require the fixed Linux sysroot.
    sysroots_path = source / 'build/linux/sysroot_scripts/sysroots.json'
    report['sysroots_json_sha256'] = sha(sysroots_path)
    sysroots = json.loads(sysroots_path.read_text())
    for name in ('bullseye_amd64', 'bullseye_i386'):
        spec = sysroots[name]
        if (not re.fullmatch(r'[0-9a-f]{64}', spec['Sha256Sum']) or
                spec['URL'] != 'https://commondatastorage.googleapis.com/chrome-linux-sysroot' or
                spec['SysrootDir'] != 'debian_' + name + '-sysroot'):
            raise ValueError('unexpected fixed host sysroot source')
        request = {'sha256sum': spec['Sha256Sum'],
                   'url': 'https://storage.googleapis.com/chrome-linux-sysroot/' + spec['Sha256Sum']}
        target = source / 'build/linux' / spec['SysrootDir']
        archive = fetch(args.cache_root, request, (target / spec['Tarball'], target / ('.' + spec['Sha256Sum'])))
        stage = work / name
        stage.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                # Debian systemd unit filenames use literal \xNN escapes.
                # Linux does not interpret these as directory separators.
                safe_member(member, allow_linux_escaped_names=True)
            tar.extractall(stage, filter=tool_data_filter)
        report['tools'].append({'source': request, 'archive_sha256': sha(archive),
                                'installed': tree_proof(install_tree(stage, target))})
    gn = source / 'buildtools/linux64/gn'
    if not gn.exists():
        fixed = args.tool_source_root / 'gn'
        if subprocess.check_output(['git', '-C', str(fixed), 'rev-parse', 'HEAD'], text=True).strip() != GN_REVISION:
            raise ValueError('fixed GN source missing')
        output = work / 'gn-build'
        clang = source / 'third_party/llvm-build/Release+Asserts/bin/clang'
        subprocess.run(['python3', str(fixed / 'build/gen.py'), '--out-path=' + str(output)], check=True,
                       env={**os.environ, 'CC': str(clang), 'CXX': str(clang) + '++'})
        subprocess.run(['ninja', '-C', str(output), '-j', '4', 'gn'], check=True)
        gn.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output / 'gn', gn)
    if gn.is_symlink() or subprocess.check_output([str(gn), '--version'], text=True).strip() != '2304 (6e0b557db44b)':
        raise ValueError('GN fixed release version differs')
    report['gn'] = {'revision': GN_REVISION, 'version': '2304 (6e0b557db44b)', 'sha256': sha(gn)}
    for name, executable, expected in (
            ('node', 'third_party/node/linux/node-linux-x64/bin/node', 'v24.11.1'),
            ('clang', 'third_party/llvm-build/Release+Asserts/bin/clang', 'clang version 22.0.0git'),
            ('rust', 'third_party/rust-toolchain/bin/rustc', '11339a0ef5ed586bb7ea4f85a9b7287880caac3a')):
        binary = source / executable
        actual = subprocess.check_output([str(binary), '--version'], text=True).strip()
        if expected not in actual:
            raise ValueError('fixed tool executable version differs: ' + name)
        report[name] = {'version': actual, 'sha256': sha(binary)}
    report['status'] = 'pass'
    args.evidence.write_text(json.dumps(report, indent=2) + '\n')
    print('fixed Chromium build tools and Linux host sysroots installed/verified')


if __name__ == '__main__':
    main()
