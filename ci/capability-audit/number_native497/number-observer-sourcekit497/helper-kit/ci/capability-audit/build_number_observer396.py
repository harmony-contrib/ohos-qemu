"""Fixed inner entry. Root must execute under its owned pinned container.

This file does not acquire or claim resource ownership; it is the finite command
payload for root's actual lease/CID/WNOWAIT driver. No source/out is written.
"""
import argparse
import json
from pathlib import Path
import shutil

import batch_system_build_runtime_helpers as product

NAME = 'number_token_query395'
MOUNT = Path('/number-helper-kit')
BUILD = Path('/number-helper-output/build')
RECHECK = Path('/number-helper-recheck/recheck')
PROFILE = Path('/runtime-profile/runtime-profile.json')


def require(ok, message):
    if not ok: raise ValueError(message)


def export_needed(report):
    target = BUILD.parent / 'product-dsos'; target.mkdir(exist_ok=False)
    row = report['helpers'][NAME]; exported = {}
    require(row['status'] == 'pass_compile_link_ONLY' and row['runtime_validated'] is False,
            'only actual completed compile/link diagnostic may be exported')
    for soname in row['DT_NEEDED']:
        selected, = product.runtime_link_records(row, soname)
        actual = Path(selected['path'])
        product.require_ro(actual)
        require(actual.resolve() == actual and actual.is_relative_to('/ohos') and
                product.sha(actual) == selected['sha256'] and actual.stat().st_size == selected['bytes'] and
                report['inputs'].get(str(actual)) == selected, 'actual installed linker-opened DSO changed')
        require('/' not in soname and soname.endswith('.so'), 'safe exact SONAME required')
        path = target / soname; shutil.copyfile(actual, path)
        require(product.sha(path) == selected['sha256'], 'exported installed DSO bytes changed')
        exported[soname] = dict(path=str(path), sha256=product.sha(path), bytes=path.stat().st_size,
                                original=selected, helpers=[NAME])
    receipt = BUILD / 'build.json'
    value = dict(scope='fresh installed-runtime actual linker-opened DT_NEEDED full-byte export ONLY_NOT_guest',
        build_receipt=dict(path=str(receipt), sha256=product.sha(receipt), bytes=receipt.stat().st_size),
        source_root='/ohos', runtime_profile=report['installed_runtime_profile'], files=exported)
    with (target / 'manifest.json').open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', required=True, choices=('build', 'recheck'))
    p.add_argument('--runtime-profile-sha256')
    p.add_argument('--previous-sha256')
    args = p.parse_args()
    require(product.ROOT == MOUNT and product.HERE == MOUNT / 'ci/capability-audit', 'fixed readonly private helper-kit mount required')
    product.require_ro(Path(__file__)); product.require_ro(product.HERE / 'fixtures' / product.HELPERS[NAME]['fixture'])
    if args.mode == 'build':
        require(args.runtime_profile_sha256 is not None and args.previous_sha256 is None, 'actual profile hash only for fresh build')
        builder = product.Builder('/ohos', BUILD, [NAME], runtime_profile=PROFILE,
                                  runtime_profile_sha256=args.runtime_profile_sha256)
    else:
        require(args.previous_sha256 is not None and args.runtime_profile_sha256 is None, 'actual original report hash only for recheck')
        builder = product.ExistingVerifier('/ohos', RECHECK, [NAME], BUILD / 'build.json', args.previous_sha256)
    report = builder.run()
    require(report['status'] == 'pass_compile_link_ONLY' and set(report['helpers']) == {NAME},
            'fixed actual Number helper build/recheck failed')
    if args.mode == 'build': export_needed(report)
    print(json.dumps(dict(scope='actual product helper compile/recheck ONLY_NOT_guest', mode=args.mode,
                          report=str(builder.output / 'build.json'), status=report['status'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
