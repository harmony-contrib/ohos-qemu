"""Finite C recipes for the explicit ARM32 global clock protocol only."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
NATIVE=HERE/'fixtures/batch_media/audio_global_clock579'
NAMES=('audio_global579_control','audio_global579_status','audio_global579_af')
ALSA_C={'graph':'obj/third_party/alsa-lib/libasound.ninja',
        'object':'obj/third_party/alsa-lib/src/libasound/async.o',
        'source':'third_party/alsa-lib/src/async.c',
        'header':'third_party/alsa-lib/include/alsa/asoundlib.h'}
HEADERS=('onset579_clock_domain.h','onset579_kernel_clock_review.h',
         'control_global579_core.h','media598_wire.h','audio_onset580_wire.h')
def helper_recipes():
    files=('control_global579.c','pcm_status_global579.c','audio_onset_global579.c')
    return {name:dict(fixture='batch_media/audio_global_clock579/'+filename,source_file=NATIVE/filename,
        language='c',anchors=[dict(ALSA_C)],libraries=[],headers=[],extra_includes=[],
        private_headers={n:NATIVE/n for n in HEADERS}) for name,filename in zip(NAMES,files)}

# Fixed actual-source implementation prerequisites; generated configs and
# package/held-boot correspondence deliberately are not source-review facts.
KERNEL_PROJECT = 'kernel/linux/linux-6.6'
KERNEL_HEAD = '14c77f1541a53e814d89ad6dea5f7f211f9895a6'
CLOCK_SOURCE_PINS = {'kernel/linux/linux-6.6/arch/arm/Kconfig': {'bytes': 60795,
                                             'sha256': '4793a64bb6fd5fcae3bf18cfa2a1bc733cee6773379c7aea3985f9f631201e1c'},
 'kernel/linux/linux-6.6/arch/arm/vdso/vgettimeofday.c': {'bytes': 929,
                                                          'sha256': 'e5bf23424a0c328bea5bc4027f174b8339fb0f5787e7fa8a395d2a571203b513'},
 'kernel/linux/linux-6.6/fs/proc/namespaces.c': {'bytes': 4323,
                                                 'sha256': 'cc38b0cd358741199f25ecb99487caf46e3794bc8d444dd777791b7c1d49fb45'},
 'kernel/linux/linux-6.6/include/linux/time_namespace.h': {'bytes': 4068,
                                                           'sha256': 'd99650e247b1d4faa704161063a1d7a94e8f9ab56cd28baff2cb4d1095cde81f'},
 'kernel/linux/linux-6.6/init/Kconfig': {'bytes': 67024,
                                         'sha256': '545e3c8fcb6f44dda9f0c91d1dd1705c6b652578646f824745731a0cd2d07e31'},
 'kernel/linux/linux-6.6/kernel/time/posix-timers.c': {'bytes': 42908,
                                                       'sha256': '6918cac7acc14895b03d371b0371b9e25ec5b8239aa11fd0d184acc6d2a97955'},
 'kernel/linux/linux-6.6/kernel/time/timekeeping.c': {'bytes': 72851,
                                                      'sha256': 'd56f6561a288a4e8d87162e81038f82008f0168adbd3d6714b02e154f5074e08'},
 'kernel/linux/linux-6.6/lib/vdso/Kconfig': {'bytes': 674,
                                             'sha256': 'cbf9681abf0e9e41c7ae414cfc7afab0446236e6a09377ca8ced849190e47135'},
 'kernel/linux/linux-6.6/lib/vdso/gettimeofday.c': {'bytes': 10760,
                                                    'sha256': '63881cbf52d1f5d9cb3f5a699720202fac6081827b8b446e138a94dcfa430481'}}


def require_actual_clock_sources(root):
    """Read-only normal producer input admission; no inferred target config."""
    import hashlib
    import os
    import stat
    root=Path(root)
    if root != Path('/ohos') or root.resolve()!=root or root.is_symlink():
        raise ValueError('fixed actual RO source mount required')
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('actual kernel source mount must remain readonly')
    result={}
    for name,expected in CLOCK_SOURCE_PINS.items():
        path=root/name
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('actual clock source alias: '+name)
        st=path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_size!=expected['bytes'] or                 hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:
            raise ValueError('actual reviewed clock implementation differs: '+name)
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('actual implementation input is not readonly')
        result[name]=dict(path=str(path),**expected)
    return result


def main():
    """Finite payload only. The existing original RO35 Owner owns execution."""
    import argparse
    import json
    import batch_system_build_runtime_helpers as product
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=('build','recheck'))
    parser.add_argument('--runtime-profile-sha256')
    parser.add_argument('--normal-link-target')
    parser.add_argument('--previous-sha256')
    args=parser.parse_args()
    mount=Path('/arm32-onset579-kit')
    build=Path('/arm32-onset579-output/build')
    recheck=Path('/arm32-onset579-recheck/recheck')
    profile=Path('/runtime-profile/runtime-profile.json')
    if product.ROOT!=mount or product.HERE!=mount/'ci/capability-audit':
        raise ValueError('fixed readonly source kit required')
    product.require_ro(Path(__file__))
    sources=require_actual_clock_sources(Path('/ohos'))
    head_argv=['git','-c','safe.directory=/ohos/'+KERNEL_PROJECT,
        '-C','/ohos/'+KERNEL_PROJECT,'rev-parse','HEAD']

    class FixedRecheck(product.ExistingVerifier):
        def command(self,argv,label,timeout=60):
            if list(map(str,argv))==head_argv and label=='global-clock-kernel-HEAD':
                # Only one fixed read-only metadata query is added. Original
                # ELF-only recheck command admission remains the fallback.
                return product.Builder.command(self,argv,label,timeout=timeout)
            return super().command(argv,label,timeout=timeout)

    if args.mode=='build':
        if args.runtime_profile_sha256 is None or args.normal_link_target is None or args.previous_sha256 is not None:
            raise ValueError('actual new profile and normal executable target required')
        builder=product.Builder('/ohos',build,list(NAMES),product='armv7a_virt',runtime_profile=profile,
            runtime_profile_sha256=args.runtime_profile_sha256,normal_link_target=args.normal_link_target)
    else:
        if args.previous_sha256 is None or args.runtime_profile_sha256 is not None or args.normal_link_target is not None:
            raise ValueError('actual immutable previous report only for recheck')
        builder=FixedRecheck('/ohos',recheck,list(NAMES),build/'build.json',args.previous_sha256,product='armv7a_virt')
    try:
        actual=builder.command(head_argv,'global-clock-kernel-HEAD',timeout=30)
        if actual!=KERNEL_HEAD+'\n':
            raise ValueError('actual reviewed kernel source HEAD differs')
        rows={name:builder.remember('/ohos/'+name) for name in CLOCK_SOURCE_PINS}
        if rows!=sources:
            raise ValueError('actual fixed source inputs changed before original production')
        builder.report['global_clock579_native_entry']=builder.report['global_clock579_native_recipe']
        builder.report['clock_implementation579']=dict(schema='actual-fixed-clock-implementation579/v1',
            project='/ohos/'+KERNEL_PROJECT,head=KERNEL_HEAD,sources=rows,
            head_command='global-clock-kernel-HEAD',generated_config_admitted=False,
            package_kernel_admitted=False,held_boot_admitted=False)
        report=builder.run()
        if report['status']!='pass_compile_link_ONLY' or set(report['helpers'])!=set(NAMES):
            raise ValueError('actual finite global native build/recheck failed')
        if require_actual_clock_sources(Path('/ohos'))!=sources:
            raise ValueError('readonly clock source changed after original production')
    except BaseException as error:
        builder.report['clock_implementation_error']=type(error).__name__+': '+str(error)
        builder.save()
        raise
    print(json.dumps(dict(schema='actual-fixed-global-native579-result/v1',mode=args.mode,
        report=str(builder.output/'build.json'),status=report['status'],runtime_pass=False)))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
