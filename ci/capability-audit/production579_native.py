"""Finite explicit recipes for one real first-ARM64 fixture input build batch.

No resource, compiler or default registration runs at import. The original four
core defaults remain unchanged. Extra recipes are resolved only when selected.
Each recipe is the actual existing six-kind configuration or a delivered fixed
communication/Settings/WiFi/virtual-SIM/paired recipe. No fabricated GN target.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADDITIONAL_NAMES = ('audio_haptic_sampler','audio_observation_clock','calendar_runtime_observer',
    'gnss_existing_sa_dump','alsa_inject','audio_capture_token','netlink_snapshot',
    'apn579_modem_peer','apps_paired579_net')
GROUPS = {
    'core': ('contact_picker_observer','wallpaper_default_resolver','wallpaper_token_query','knowledge_token_query'),
    'audio': ('audio_haptic_sampler','audio_observation_clock'),
    'calendar': ('calendar_runtime_observer',), 'gnss': ('gnss_existing_sa_dump',),
    'mic': ('alsa_inject','audio_capture_token'), 'netlink': ('netlink_snapshot',),
    'communications578': ('communications578_permission_controller','communications578_at_peer'),
    'settings_idle579': ('settings_idle579_napi',), 'wifi579': ('apps579_wifi_peer',),
    'apn579': ('apn579_modem_peer',), 'paired579': ('apps_paired579_net',),
}


def selected_names():
    return tuple(name for group in GROUPS.values() for name in group)


def recipe_sources():
    return tuple(HERE / name for name in ('production579_native.py',
        'batch_media_audio_haptic_build_sampler.py','batch_system_calendar_runtime_helper.py',
        'batch_system_gnss_trace_helper.py','build_audio_capture_tools.py',
        'build_network_kernel_snapshot.py','apn579_native.py','apps_paired579_native.py'))


def helper_recipes():
    import batch_system_build_runtime_helpers as product
    import batch_media_audio_haptic_build_sampler as audio
    import batch_system_gnss_trace_helper as gnss
    from build_audio_capture_tools import ALSA, SOURCES
    from build_network_kernel_snapshot import SOURCE as NETLINK_SOURCE
    from apn579_native import helper_recipes as sim_recipes
    from apps_paired579_native import helper_recipes as paired_recipes
    recipes = {
        audio.NAME: {'fixture':'batch_media/' + audio.FIXTURE,'anchors':[audio.VDI,product.TOKEN],
            'libraries':['hdf/drivers_interface_vibrator/libvibrator_proxy_2.0.z.so',
                         'security/access_token/libaccesstoken_sdk.z.so'],
            'headers':[audio.VDI['header'],product.TOKEN['header']],'extra_includes':[]},
        audio.CLOCK_NAME: {'fixture':'batch_media/' + audio.CLOCK_FIXTURE,'anchors':[product.TOKEN,ALSA],
            'libraries':['thirdparty/alsa-lib/libasound.so'],'headers':[ALSA['header'],product.TOKEN['header']],
            'extra_includes':['third_party/alsa-lib/include']},
        'calendar_runtime_observer': {'fixture':'batch_system/calendar_runtime/observer.cpp',
            'anchors':[product.APP,product.TOKEN],
            'libraries':['ability/ability_runtime/libapp_manager.z.so','security/access_token/libaccesstoken_sdk.z.so'],
            'headers':[product.APP['header'],product.TOKEN['header'],'third_party/json/include/nlohmann/json.hpp'],
            'extra_includes':['third_party/json/include/nlohmann']},
        gnss.NAME: {'fixture':'batch_system/gnss_trace/gnss_existing_sa_dump.cpp','anchors':[gnss.GNSS],
            'libraries':['systemabilitymgr/samgr/libsamgr_proxy.z.so','commonlibrary/c_utils/libutils.z.so'],
            'headers':gnss.HEADERS,'extra_includes':[],'production579_elf_contract':'gnss'},
        'alsa_inject': {'fixture':'batch_media_alsa_inject.c','source_file':SOURCES['alsa_inject'],
            'language':'c','anchors':[ALSA],'libraries':['thirdparty/alsa-lib/libasound.so'],
            'headers':[ALSA['header']],'extra_includes':['third_party/alsa-lib/include'],
            'production579_elf_contract':'alsa'},
        'audio_capture_token': {'fixture':'probes/audio_capture_token.cpp','source_file':SOURCES['audio_capture_token'],
            'anchors':[product.TOKEN],'libraries':['security/access_token/libaccesstoken_sdk.z.so'],
            'headers':[product.TOKEN['header']],'extra_includes':[]},
        'netlink_snapshot': {'fixture':'probes/netlink_snapshot.c','source_file':NETLINK_SOURCE,
            'language':'c','anchors':[ALSA],'libraries':[],'headers':[],'extra_includes':[],
            'production579_elf_contract':'netlink'},
    }
    for extra, names in ((sim_recipes(),{'apn579_modem_peer'}),(paired_recipes(),{'apps_paired579_net'})):
        if set(extra) != names or set(extra) & set(recipes):
            raise ValueError('complete disjoint delivered virtual-SIM/paired C recipe required')
        recipes.update(extra)
    if set(recipes) != set(ADDITIONAL_NAMES): raise ValueError('finite production recipe set differs')
    return recipes


def anchor_contract(builder, spec, name, row):
    helper, separator, index = name.rpartition('-')
    if not separator or not index.isdecimal(): raise ValueError('actual helper anchor ordinal required')
    if helper == 'gnss_existing_sa_dump':
        import batch_system_gnss_trace_helper as gnss
        if spec != gnss.GNSS or [flag for flag in row['flags'] if flag.startswith('-DQEMU_GNSS_HDI_RAW_TRACE')] != \
            ['-DQEMU_GNSS_HDI_RAW_TRACE=1'] or '-DFEATURE_GNSS_SUPPORT' not in row['flags']:
            raise ValueError('actual original HDI-enabled QEMU GNSS C++ graph required')
    if helper == 'netlink_snapshot':
        from build_network_kernel_snapshot import ALSA, descriptor
        if spec != ALSA: raise ValueError('actual original netlink ALSA C anchor differs')
        private = builder.output / (name + '.ninja')
        private.write_bytes((builder.build / spec['graph']).read_bytes())
        from batch_system_build_runtime_helpers import sha
        if sha(private) != row['graph']['sha256']: raise ValueError('actual netlink GN graph changed during copy')
        row['private_graph'] = descriptor(private)
    return row


def check_elf(builder, name, binary, direct, row, contract):
    """Invoke original exact per-kind ELF checks; no success replacement."""
    if name == 'gnss_existing_sa_dump' and contract == 'gnss':
        from batch_system_gnss_trace_helper import GnssDumpBuilder
        return GnssDumpBuilder.check_elf(builder,name,binary,direct,row)
    if name == 'alsa_inject' and contract == 'alsa':
        from build_audio_capture_tools import CaptureToolsBuilder
        return CaptureToolsBuilder.check_elf(builder,name,binary,direct,row)
    if name == 'netlink_snapshot' and contract == 'netlink':
        from build_network_kernel_snapshot import KernelSnapshotBuilder
        return KernelSnapshotBuilder.check_elf(builder,name,binary,direct,row)
    raise ValueError('unlisted actual production ELF contract')
