from pathlib import Path
import hashlib
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/hap'
REVISION='f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
FILES=(('BUILD.gn','d35f62e7f04aee85749b3ab9c7ba25261ddf2fa71395d0b829e0e71cef40f18b','73940797880d284873c91b2c88eae074aa85beac4fb8a9b5f1b334a31ffbe2f5'),)
def _validate_original(root,require_patched=False):
    files=FILES
    if hashlib.sha256((Path(root)/PROJECT/'BUILD.gn').read_bytes()).hexdigest()=='d25f524ae8b82607c04ddd86b485b3940b40af14376cbf9c3d23f15d6655a83c':
        files=(('BUILD.gn',FILES[0][1],'d25f524ae8b82607c04ddd86b485b3940b40af14376cbf9c3d23f15d6655a83c'),)
    return validate_component(root,PROJECT,REVISION,files,require_patched)


# Read-only exact one-file QEMU-provider ancestry. The original guard below
# remains the only authority for the projected predecessor; no live write.
import json
import os
import re
import stat
import subprocess
import tempfile

_QEMU580_BEFORE = 'd25f524ae8b82607c04ddd86b485b3940b40af14376cbf9c3d23f15d6655a83c'
_QEMU580_AFTER = 'a95ff1daedefc3cd597e4b389d93a9ca0d824b4876e74d1f20d3c3e92881b547'
_QEMU580_ASSETS = {'source_states.json': {'sha256': '20db9b6d0791a3073f0f3d3626f0111788db043fa3a3fa7f3570a18c3df95132', 'bytes': 525}, '0001-compose-product-provider-source.patch': {'sha256': '8c061094ee4455794770387b4a1ae6e5f0b28cac12230fac9ef81105282ab6a8', 'bytes': 3935}, 'before/BUILD.gn': {'sha256': 'd25f524ae8b82607c04ddd86b485b3940b40af14376cbf9c3d23f15d6655a83c', 'bytes': 18470}, 'verify_source.py': {'sha256': 'a5b3083f367a9146e27da3d7eb0df48149c87cb3de459820c0cae7bfb4803338', 'bytes': 2885}, 'apply_runtime.py': {'sha256': 'e6815a24e66e7fed6a24f8711ef79b5ba969a4443ad2566977d019b0fea8382e', 'bytes': 6119}, 'apply.sh': {'sha256': '4173a3b014b66d34ea38209d51d667370ca09a965aaf15add8aeac778d5ef48b', 'bytes': 91}}


def _qemu580_capture(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path or
            any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError('unaliased exact QEMU-provider source required')
    first = path.stat()
    if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or
            first.st_size > 4 * 1024 * 1024):
        raise ValueError('bounded one-link QEMU-provider source required')
    data = path.read_bytes()
    last = path.stat()
    fields = ('st_dev', 'st_ino', 'st_nlink', 'st_mode', 'st_uid', 'st_gid',
              'st_size', 'st_mtime_ns', 'st_ctime_ns')
    identity = tuple(getattr(first, name) for name in fields)
    if len(data) != first.st_size or identity != tuple(getattr(last, name) for name in fields):
        raise ValueError('QEMU-provider source changed during read')
    return data, identity


def _qemu580_head(root):
    project = root / PROJECT
    actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse',
                                      '--verify', 'HEAD^{commit}'], text=True).strip()
    top = subprocess.check_output(['git', '-C', str(project), 'rev-parse',
                                   '--show-toplevel'], text=True).strip()
    if actual != REVISION or Path(top).resolve() != project:
        raise ValueError('exact actual QEMU-provider project HEAD/toplevel required')


def _qemu580_cuts(patch):
    lines = patch.splitlines(keepends=True)
    name = (PROJECT + '/BUILD.gn').encode()
    if lines[:2] != [b'--- a/' + name + b'\n', b'+++ b/' + name + b'\n']:
        raise ValueError('exact one-file QEMU-provider patch headers required')
    cuts = []
    cursor = 2
    while cursor < len(lines):
        match = re.fullmatch(rb'@@ -([0-9]+),([0-9]+) \+([0-9]+),([0-9]+) @@\n', lines[cursor])
        if match is None:
            raise ValueError('fixed complete QEMU-provider hunk required')
        cursor += 1
        before, after = [], []
        while cursor < len(lines) and not lines[cursor].startswith(b'@@ '):
            line = lines[cursor]
            if line[:1] not in (b' ', b'-', b'+'):
                raise ValueError('unknown QEMU-provider patch body')
            if line[:1] in (b' ', b'-'):
                before.append(line[1:])
            if line[:1] in (b' ', b'+'):
                after.append(line[1:])
            cursor += 1
        a, b = b''.join(before), b''.join(after)
        if (len(before) != int(match[2]) or len(after) != int(match[4]) or
                not a or not b or a == b):
            raise ValueError('complete QEMU-provider hunk counts differ')
        cuts.append((a, b))
    if len(cuts) != 4:
        raise ValueError('exact four complete QEMU-provider hunks required')
    return cuts


def _qemu580_preceding(root, require_patched):
    root = Path(root)
    if (not root.is_absolute() or root.resolve() != root or
            any(p.is_symlink() for p in (root, *root.parents))):
        raise ValueError('actual canonical QEMU-provider root required')
    path = root / PROJECT / 'BUILD.gn'
    actual = _qemu580_capture(path)
    assets_root = Path(__file__).resolve().parent.parent / 'qemu_provider_sources'
    saved = {}
    for name, expected in _QEMU580_ASSETS.items():
        asset = assets_root / name
        observed = _qemu580_capture(asset)
        if (len(observed[0]) != expected['bytes'] or
                hashlib.sha256(observed[0]).hexdigest() != expected['sha256']):
            raise ValueError('fixed complete QEMU-provider asset differs: ' + name)
        saved[asset] = observed
    manifest = json.loads(saved[assets_root / 'source_states.json'][0])
    if (manifest['schema'] != 'qemu579-hap-source-vector/v1' or
            manifest['projects'] != {PROJECT: REVISION} or
            manifest['files'] != {PROJECT + '/BUILD.gn': [_QEMU580_BEFORE, _QEMU580_AFTER]}):
        raise ValueError('exact whole one-file QEMU-provider vector required')
    prefix = saved[assets_root / 'before/BUILD.gn'][0]
    if (hashlib.sha256(prefix).hexdigest() != _QEMU580_BEFORE or
            hashlib.sha256(actual[0]).hexdigest() != _QEMU580_AFTER):
        raise ValueError('exact actual QEMU-provider final and predecessor required')
    _qemu580_head(root)
    cuts = _qemu580_cuts(saved[assets_root / '0001-compose-product-provider-source.patch'][0])
    current = prefix
    for before, after in cuts:
        if current.count(before) != 1:
            raise ValueError('unique whole QEMU-provider forward hunk required')
        current = current.replace(before, after, 1)
        if current.count(after) != 1:
            raise ValueError('unique whole QEMU-provider postimage required')
    if current != actual[0]:
        raise ValueError('complete actual QEMU-provider postimage differs')
    for before, after in reversed(cuts):
        if current.count(after) != 1:
            raise ValueError('unique whole QEMU-provider inverse hunk required')
        current = current.replace(after, before, 1)
    if current != prefix:
        raise ValueError('complete QEMU-provider ancestor inverse differs')
    with tempfile.TemporaryDirectory(prefix='contacts_theme_provider-qemu-provider-ancestor-') as directory:
        view = Path(directory).resolve()
        ancestor = view / PROJECT / 'BUILD.gn'
        ancestor.parent.mkdir(parents=True)
        ancestor.write_bytes(prefix)
        os.chmod(ancestor, stat.S_IMODE(actual[1][3]))
        if _validate_original(view, require_patched=True) is not True:
            raise ValueError('complete original HAP guard must accept exact ancestor')
    _qemu580_head(root)
    if _qemu580_capture(path) != actual or any(_qemu580_capture(p) != value for p, value in saved.items()):
        raise ValueError('actual QEMU-provider source or fixed assets changed during readonly proof')
    return True


def validate(root, require_patched=False):
    # Unknown and all older states retain the original exact rejection rules.
    path = Path(root) / PROJECT / 'BUILD.gn'
    if hashlib.sha256(path.read_bytes()).hexdigest() != _QEMU580_AFTER:
        return _validate_original(root, require_patched)
    return _qemu580_preceding(root, require_patched)
