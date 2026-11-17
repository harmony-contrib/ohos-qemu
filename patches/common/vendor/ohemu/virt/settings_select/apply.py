#!/usr/bin/env python3
"""Bind the complete native Settings select provider to QEMU system parameters."""
import argparse
import importlib.util
import os
from pathlib import Path
import stat
import tempfile

PARAM_FILE = 'vendor/ohemu/virt/etc/param/product_virt.para'
VALUES = {'const.system.sharePicker.bundleName': 'com.ohos.settings',
          'const.system.sharePicker.abilityName': 'PickerDialog'}


def require_chooser(root):
    path = Path(__file__).resolve().parents[4] / 'applications/standard/settings/share_picker_choose/verify_source.py'
    spec = importlib.util.spec_from_file_location('settings_select_complete_guard', path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.validate(root, require_patched=True)


def configure(root, require_patched=False):
    root = Path(root).absolute()
    if root.is_symlink():
        raise ValueError('source root symlink refused')
    root = root.resolve(strict=True)
    target = root / PARAM_FILE
    for cursor in (target, *target.parents):
        if cursor == root:
            break
        if cursor.is_symlink():
            raise ValueError('product parameter path symlink refused')
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('single regular product parameter file required')
    before = target.read_bytes()
    text = before.decode('utf-8')
    seen = {}
    for line in text.splitlines():
        key, separator, value = line.strip().partition('=')
        if separator and key in VALUES:
            if key in seen or value != VALUES[key]:
                raise ValueError('duplicate or conflicting select provider parameter: ' + key)
            seen[key] = value
    if seen and set(seen) != set(VALUES):
        raise ValueError('incomplete select provider parameter pair')
    require_chooser(root)
    if seen:
        return 'already_applied'
    if require_patched:
        raise ValueError('complete Settings select provider parameter pair required')
    if text and not text.endswith('\n'):
        text += '\n'
    text += '\n# Native-bound Settings select provider\n'
    text += ''.join(key + '=' + value + '\n' for key, value in VALUES.items())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.settings-select-', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(info.st_mode))
        current = target.stat()
        if ((current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns, current.st_nlink) !=
                (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink) or
                target.is_symlink() or target.read_bytes() != before):
            raise ValueError('product parameter file changed before publication')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return 'applied'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print(configure(args.source_root, args.require_patched))


if __name__ == '__main__':
    main()
