#!/usr/bin/env python3
"""Guard dedicated non-root QEMU fusion accounts and unchanged service authority."""
import argparse
import hashlib
from pathlib import Path
import subprocess

INIT_REVISION = '475fcc1e48db623ea4a9ee03b5408a21a19b99c4'
FUSION_REVISION = 'dd319c8b946cf6ed1f68867626333945e36424ae'
ACCOUNTS = {'fusion_ranging': 6067, 'partner_device_agent': 6068}
CONFIGS = {
    'fusion_ranging/services/etc/init/fusion_ranging.cfg': '4d016dc83b18509dc76b7e5a9864ca477c79739ff216500b0ce4019f5d583311',
    'partner_agent/services/etc/init/fusion_connectivity.cfg': '9a21373c30834e97d7ad5b57a1bf2882523e20665915a20ad0ad1370e2ed855e',
}


def repaired(original, kind):
    lines = [row.split(':') for row in original.decode('utf-8').splitlines() if row]
    for row in lines:
        if row[0] in ACCOUNTS or int(row[2]) in ACCOUNTS.values():
            raise ValueError('reserved fusion account name/ID already used in the fixed baseline')
        if kind == 'passwd' and int(row[3]) in ACCOUNTS.values():
            raise ValueError('reserved fusion primary GID already used')
    anchor = b'fusion_host:x:3067:3067:::/bin/false\n' if kind == 'passwd' else b'fusion_host:x:3067:\n'
    if original.count(anchor) != 1:
        raise ValueError('unknown fixed fusion account anchor')
    additions = b''.join((f'{name}:x:{uid}:{uid}:::/bin/false\n' if kind == 'passwd' else
                          f'{name}:x:{uid}:\n').encode() for name, uid in ACCOUNTS.items())
    return original.replace(anchor, anchor + additions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    init, fusion = root / 'base/startup/init', root / 'foundation/communication/fusion_connectivity'
    for source, revision in ((init, INIT_REVISION), (fusion, FUSION_REVISION)):
        head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if head != revision:
            raise SystemExit('fusion accounts require fixed 7.0 source ' + revision)
    # Never replace the services' UID with root/system or add permissions/caps.
    for relative, expected in CONFIGS.items():
        if hashlib.sha256((fusion / relative).read_bytes()).hexdigest() != expected:
            raise SystemExit('fusion init authority changed; preserving source')
    for kind in ('passwd', 'group'):
        target = init / 'services/etc' / kind
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise SystemExit('fusion account target contains a source symlink')
            cursor = cursor.parent
        original = subprocess.check_output(['git', '-C', str(init), 'show', 'HEAD:services/etc/' + kind])
        expected = repaired(original, kind)
        accepted = (expected,) if args.require_patched else (original, expected)
        if target.read_bytes() not in accepted:
            raise SystemExit('unknown account table edit; preserving source')
    print('distinct non-root fusion account registration checked (runtime pending)')


if __name__ == '__main__':
    main()
