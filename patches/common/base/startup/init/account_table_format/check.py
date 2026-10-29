#!/usr/bin/env python3
"""Guard the exact fixed 7.0 account-table and known Fusion composition."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from init_account_tables import repair_cloud, validate

FUSION_CHECK = Path(__file__).resolve().parent.parent / 'fusion_accounts/check.py'
spec = importlib.util.spec_from_file_location('fixed_fusion_accounts', FUSION_CHECK)
fusion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fusion)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    init = root / 'base/startup/init'
    if subprocess.check_output(['git', '-C', str(init), 'rev-parse', 'HEAD'], text=True).strip() != fusion.INIT_REVISION:
        raise SystemExit('account repair requires the fixed 7.0 init revision')
    for kind in ('passwd', 'group'):
        target = init / 'services/etc' / kind
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise SystemExit('account-table target contains a source symlink')
            cursor = cursor.parent
        original = subprocess.check_output(['git', '-C', str(init), 'show', 'HEAD:services/etc/' + kind])
        combined = fusion.repaired(original, kind)
        repaired = [repair_cloud(value) if kind == 'passwd' else value for value in (original, combined)]
        accepted = repaired if args.require_patched else [original, combined, *repaired]
        if target.read_bytes() not in accepted:
            raise SystemExit('unknown account-table edit; preserving source')
        if args.require_patched:
            validate(target.read_bytes(), kind)
    print('exact cloud passwd field repair and dedicated identity checked (guest pending)')


if __name__ == '__main__':
    main()
