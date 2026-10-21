"""Fixed inner entry. Root must execute under its owned pinned container.

This file does not acquire or claim resource ownership; it is the finite command
payload for root's actual lease/CID/WNOWAIT driver. No source/out is written.
"""
import argparse
import json
from pathlib import Path
import shutil

import batch_system_build_runtime_helpers as product

NAMES = ('audio_global579_passive', 'audio_global579_token')
FIXTURES = {'audio_global579_passive':'batch_media/audio_threeuid_global579/passive375.cpp','audio_global579_token':'batch_media/audio_threeuid_global579/token375.cpp'}
MOUNT = Path('/audio-threeuid-global579-helper-kit')
BUILD = Path('/audio-threeuid-global579-output/build')
RECHECK = Path('/audio-threeuid-global579-recheck/recheck')
PROFILE = Path('/runtime-profile/runtime-profile.json')


def require(ok, message):
    if not ok: raise ValueError(message)


def export_needed(report):
    target = BUILD.parent / 'product-dsos'; target.mkdir(exist_ok=False)
    exported = {}
    for name in NAMES:
        row=report['helpers'][name]
        require(row['status']=='pass_compile_link_ONLY' and row['runtime_validated'] is False,'actual fixed C++ compile/link only')
        for soname in row['DT_NEEDED']:
            selected,=product.runtime_link_records(row,soname);actual=Path(selected['path']);product.require_ro(actual)
            require(actual.resolve()==actual and actual.is_relative_to('/ohos') and product.sha(actual)==selected['sha256'] and actual.stat().st_size==selected['bytes'] and report['inputs'].get(str(actual))==selected,'actual installed linker-opened DSO changed')
            require('/' not in soname and soname.endswith('.so'),'exact safe SONAME')
            if soname in exported:
                require(exported[soname]['original']==selected,'shared actual DSO differs');exported[soname]['helpers'].append(name)
            else:
                path=target/soname;shutil.copyfile(actual,path);require(product.sha(path)==selected['sha256'],'copied actual DSO changed')
                exported[soname]=dict(path=str(path),sha256=product.sha(path),bytes=path.stat().st_size,original=selected,helpers=[name])
    receipt = BUILD / 'build.json'
    value = dict(scope='fresh installed-runtime actual linker-opened DT_NEEDED full-byte export ONLY_NOT_guest',
        build_receipt=dict(path=str(receipt), sha256=product.sha(receipt), bytes=receipt.stat().st_size),
        source_root='/ohos', runtime_profile=report['installed_runtime_profile'], files=exported)
    with (target / 'manifest.json').open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def raw_trace_recheck(verifier,name):
    require(name in NAMES,'fixed two C++ helper only');old=verifier.previous['helpers'][name]
    command=verifier.prior_command(name+'-link');raw=Path(verifier.bound_artifact(command['log'],command['sha256'])['path']).read_text()
    actual=product.trace_link_inputs(raw,verifier.build);obj=Path(product.argument(old['compile_command'],'-o')).resolve()
    require(obj==Path(verifier.artifact_origin/name/(name+'.o')).resolve() and obj in actual,'actual sole fixed object must be linker-opened')
    require([str(p) for p in actual if product.within(p,verifier.root)]==[r['path'] for r in old['actual_link_inputs']] and all(product.within(p,verifier.root) or p==obj for p in actual),'complete real raw link input set differs')
    for r in old['actual_link_inputs']:
        require(verifier.previous['inputs'].get(r['path'])==r and product.sha(r['path'])==r['sha256'] and Path(r['path']).stat().st_size==r['bytes'],'actual opened input bytes differ')
class FixedExistingVerifier(product.ExistingVerifier):
    def helper(self,name):
        raw_trace_recheck(self,name)
        return super().helper(name)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', required=True, choices=('build', 'recheck'))
    p.add_argument('--runtime-profile-sha256')
    p.add_argument('--previous-sha256')
    p.add_argument('--normal-link-target')
    args = p.parse_args()
    require(product.ROOT == MOUNT and product.HERE == MOUNT / 'ci/capability-audit', 'fixed readonly private helper-kit mount required')
    product.require_ro(Path(__file__))
    from audio_threeuid_arm32_global579_native import helper_recipes
    expected = helper_recipes()
    require(set(expected)==set(NAMES) and all(product.helper_spec(name)==expected[name] for name in NAMES), 'fixed registered ARM32 recipes required')
    for name in NAMES:product.require_ro(product.HERE/'fixtures'/FIXTURES[name])
    if args.mode == 'build':
        require(args.runtime_profile_sha256 is not None and args.previous_sha256 is None and args.normal_link_target is not None, 'actual profile hash only for fresh build')
        builder = product.Builder('/ohos', BUILD, list(NAMES), runtime_profile=PROFILE,
                                  runtime_profile_sha256=args.runtime_profile_sha256, product='armv7a_virt',
                                  normal_link_target=args.normal_link_target)
    else:
        require(args.previous_sha256 is not None and args.runtime_profile_sha256 is None and args.normal_link_target is None, 'actual original report hash only for recheck')
        builder = FixedExistingVerifier('/ohos', RECHECK, list(NAMES), BUILD / 'build.json', args.previous_sha256, product='armv7a_virt')
    builder.report['audio_threeuid_arm32_global579_extension']=product.input_record(Path(__file__))
    report = builder.run()
    require(report['status'] == 'pass_compile_link_ONLY' and set(report['helpers']) == set(NAMES),
            'fixed actual 375 helpers build/recheck failed')
    if args.mode == 'build': export_needed(report)
    print(json.dumps(dict(scope='actual product helper compile/recheck ONLY_NOT_guest', mode=args.mode,
                          report=str(builder.output / 'build.json'), status=report['status'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
