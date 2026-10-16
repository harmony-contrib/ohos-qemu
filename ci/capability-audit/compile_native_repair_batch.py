#!/usr/bin/env python3
"""Compile complete AVC/child candidates in scratch with real product commands.

Apply every component patch to private fixed-revision source before compiling
all changed TUs. Keep successful objects and all failures. No source/out writes,
link result, package or runtime gate is implied. Explicit new GN feature defines
are labeled diagnostic additions and never prove fresh GN feature selection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

from gn_export_diagnostic import exported_includes

ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    'msdp_sensor': {
        'project': 'base/msdp/device_status',
        'revision': '96335211bea5ca348325d55746e14e102208354f',
        'components': ['sensor_input'],
        'units': ['devicestatus_service', 'devicestatus_static_service', 'intention_stationary_server',
                  'sensor_data_callback'],
        'sources': {**{name: 'services/native/src/devicestatus_msdp_client_impl.cpp' for name in (
            'devicestatus_service', 'devicestatus_static_service', 'intention_stationary_server')},
            'sensor_data_callback': 'libs/src/datahub/sensor_data_callback.cpp'},
        'targets': {**{name: 'obj/base/msdp/device_status/services/native/src/' + name + '/devicestatus_msdp_client_impl.o'
            for name in ('devicestatus_service', 'devicestatus_static_service', 'intention_stationary_server')},
            'sensor_data_callback': 'obj/base/msdp/device_status/libs/src/datahub/devicestatus_algo/sensor_data_callback.o'},
        'diagnostic_feature_defines': ['DEVICE_STATUS_SENSOR_ENABLE', 'DEVICE_STATUS_DISABLE_MOCK_FALLBACK'],
        'required_header': None,
        'supported_products': ['arm64_virt'],
        'scope': 'four_whole_MSDP_product_TUs_with_explicit_new_GN_Sensor_noMock_defines_NOT_fresh_GN_link_runtime',
    },
    'knowledge_content': {
        'project': 'foundation/multimedia/media_library',
        'revision': '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380',
        'components': ['fusion_asset_type', 'api26_photo_enums', 'api26_photo_search_enums',
                       'photos_recent_info', 'business_error', 'result_set_boundaries',
                       'photos_facard', 'public_record_classes',
                       'result_set_export', 'knowledge_content', 'knowledge_holiday_index'],
        'units': ['native_module_ohos_photoaccess_helper', 'knowledge_content_napi', 'knowledge_content_query',
                  'media_asset_rdbstore', 'medialibrary_rdbstore', 'knowledge_holiday_index'],
        'sources': {
            **{name: 'frameworks/js/src/' + name + '.cpp' for name in (
                'native_module_ohos_photoaccess_helper', 'knowledge_content_napi', 'knowledge_content_query')},
            'media_asset_rdbstore': 'frameworks/innerkitsimpl/media_library_helper/src/media_asset_rdbstore.cpp',
            **{name: 'services/media_rdbstore/src/rdbstore/' + name + '.cpp' for name in (
                'medialibrary_rdbstore', 'knowledge_holiday_index')},
        },
        'targets': {
            **{name: 'obj/foundation/multimedia/media_library/frameworks/js/src/photoaccesshelpernative/native_module_ohos_photoaccess_helper.o'
               for name in ('native_module_ohos_photoaccess_helper', 'knowledge_content_napi', 'knowledge_content_query')},
            'media_asset_rdbstore': 'obj/foundation/multimedia/media_library/frameworks/innerkitsimpl/media_library_helper/src/media_library/media_asset_rdbstore.o',
            **{name: 'obj/foundation/multimedia/media_library/services/media_rdbstore/src/rdbstore/medialibrary_data_extension/medialibrary_rdbstore.o'
               for name in ('medialibrary_rdbstore', 'knowledge_holiday_index')},
        },
        'template_sources': {
            **{name: 'frameworks/js/src/native_module_ohos_photoaccess_helper.cpp' for name in (
                'native_module_ohos_photoaccess_helper', 'knowledge_content_napi', 'knowledge_content_query')},
            'media_asset_rdbstore': 'frameworks/innerkitsimpl/media_library_helper/src/media_asset_rdbstore.cpp',
            **{name: 'services/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp' for name in (
                'medialibrary_rdbstore', 'knowledge_holiday_index')},
        },
        'required_header': None,
        'supported_products': ['arm64_virt'],
        'scope': 'six_complete_current_Knowledge_TUs_actual_product_flags_NEW_sources_use_explicit_templates_NOT_fresh_GN_link_runtime',
    },
    'qemu_sensor': {
        'project': 'drivers/peripheral',
        'revision': '69094b77aa2200160207b1b06b3c0b586ae2157c',
        'components': ['sensor/qemu_external'],
        'units': ['qemu_sensor_input', 'qemu_sensor_vdi'],
        'sources': {name: 'sensor/hdi_impl/' + name + '.cpp'
                    for name in ('qemu_sensor_input', 'qemu_sensor_vdi')},
        'extra_owned': ['sensor/hdi_impl/' + name for name in (
            'qemu_sensor_input.cpp', 'qemu_sensor_vdi.cpp', 'qemu_sensor_input.h', 'qemu_sensor_protocol.h')],
        'template_sources': {name: 'sensor/hdi_impl/sensor_impl.cpp'
                             for name in ('qemu_sensor_input', 'qemu_sensor_vdi')},
        'targets': {name: 'obj/drivers/peripheral/sensor/hdi_impl/libhdi_sensor_impl/sensor_impl.o'
                    for name in ('qemu_sensor_input', 'qemu_sensor_vdi')},
        'required_header': 'sensor/hdi_impl/qemu_sensor_input.h',
        'scope': 'whole_new_sensor_TUs_actual_HDI_target_flags_ONLY_NOT_fresh_GN_selection_link_runtime',
    },
    'bluetooth_oob_napi': {
        'project': 'foundation/communication/bluetooth',
        'revision': '1727fa05c457f697f7cf80f290c82c663f1c3aab',
        'components': ['api26_oob_pairing', 'api26_oob_validation'],
        'units': ['napi_bluetooth_connection'],
        'sources': {'napi_bluetooth_connection': 'frameworks/js/napi/src/connection/napi_bluetooth_connection.cpp'},
        'targets': {'napi_bluetooth_connection': 'obj/foundation/communication/bluetooth/frameworks/js/napi/src/connection/connection/napi_bluetooth_connection.o'},
        'required_header': 'frameworks/js/napi/src/connection/napi_bluetooth_connection.h',
    },
    'bluetooth_oob_service': {
        'project': 'foundation/communication/bluetooth_service',
        'revision': 'c489d0aabf77624a4f5ca80ab8b5adefd2d5cfbf',
        'components': ['oob_pairing_backend'],
        'units': ['bluetooth_host_server', 'classic_adapter', 'ble_adapter', 'ble_security', 'gap_if', 'gap_br_sec'],
        'sources': {
            'bluetooth_host_server': 'services/bluetooth/server/src/bluetooth_host_server.cpp',
            'classic_adapter': 'services/bluetooth/service/src/classic/classic_adapter.cpp',
            'ble_adapter': 'services/bluetooth/service/src/ble/ble_adapter.cpp',
            'ble_security': 'services/bluetooth/service/src/ble/ble_security.cpp',
            'gap_if': 'services/bluetooth/stack/src/gap/gap_if.c',
            'gap_br_sec': 'services/bluetooth/stack/src/gap/gap_br_sec.c'},
        'targets': {
            'bluetooth_host_server': 'obj/foundation/communication/bluetooth_service/services/bluetooth/server/src/bluetooth_server/bluetooth_host_server.o',
            'classic_adapter': 'obj/foundation/communication/bluetooth_service/services/bluetooth/service/src/classic/btservice/classic_adapter.o',
            **{name: 'obj/foundation/communication/bluetooth_service/services/bluetooth/service/src/ble/btservice/' + name + '.o'
               for name in ('ble_adapter', 'ble_security')},
            **{name: 'obj/foundation/communication/bluetooth_service/services/bluetooth/stack/src/gap/btstack/' + name + '.o'
               for name in ('gap_if', 'gap_br_sec')}},
        'required_headers': {
            'bluetooth_host_server': 'services/bluetooth/service/include/interface_adapter.h',
            'classic_adapter': 'services/bluetooth/service/src/classic/classic_adapter.h',
            'ble_adapter': 'services/bluetooth/service/src/ble/ble_adapter.h',
            'ble_security': 'services/bluetooth/service/src/ble/ble_security.h',
            'gap_if': 'services/bluetooth/stack/include/gap_if.h',
            'gap_br_sec': 'services/bluetooth/stack/src/gap/gap.h'},
    },
    'calendar_editor': {
        'project': 'applications/standard/calendardata',
        'revision': 'f922427ca0dc20895a0e254ae41382e5b03299a4',
        'components': ['source_provider', 'event_editor', 'editor_callback_dispatch'],
        'extra_checkout': ['build-profile.json5'],
        'units': ['calendar_manager_napi'],
        'sources': {'calendar_manager_napi': 'calendarmanager/napi/src/calendar_manager_napi.cpp'},
        'targets': {'calendar_manager_napi': 'obj/applications/standard/calendardata/calendarmanager/napi/src/calendarmanager/calendar_manager_napi.o'},
        'required_header': 'calendarmanager/napi/include/calendar_manager_napi.h',
    },
    'alsa_capture': {
        'project': 'drivers/peripheral',
        'revision': '69094b77aa2200160207b1b06b3c0b586ae2157c',
        'additional_projects': {
            'device/qemu': 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b',
            'vendor/ohemu': 'b56c5a95ec590543691278b85afe9fe228744163'},
        'components': ['audio', 'audio/capture_loopback'],
        'units': ['alsa_soundcard_capture', 'alsa_soundcard_render', 'alsa_snd_capture', 'qemu_vendor_capture'],
        'source_paths': {
            'alsa_soundcard_capture': 'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_soundcard.c',
            'alsa_soundcard_render': 'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_soundcard.c',
            'alsa_snd_capture': 'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_capture.c',
            'qemu_vendor_capture': 'device/qemu/common/virt_full/audio_alsa/vendor_capture.c'},
        'targets': {
            'alsa_soundcard_capture': 'obj/drivers/peripheral/audio/supportlibs/alsa_adapter/src/audio_capture_adapter/alsa_soundcard.o',
            'alsa_soundcard_render': 'obj/drivers/peripheral/audio/supportlibs/alsa_adapter/src/audio_render_adapter/alsa_soundcard.o',
            'alsa_snd_capture': 'obj/drivers/peripheral/audio/supportlibs/alsa_adapter/src/audio_capture_adapter/alsa_snd_capture.o',
            'qemu_vendor_capture': 'obj/device/qemu/common/virt_full/audio_alsa/audio_capture_adapter/vendor_capture.o'},
        'required_header': 'audio/supportlibs/alsa_adapter/include/alsa_soundcard.h',
        'supported_products': ['arm64_virt'],
    },
    'location': {
        'project': 'base/location/location',
        'revision': '5a0c49c2adb0623fdac73f76e4f98f2e57674c00',
        'components': ['api26_public_enums', 'api26_runtime'],
        'extra_checkout': ['frameworks/native/locator_sdk/type/IDataTypes.idl'],
        'units': ['locator_impl', 'locator_ability', 'request_manager',
                  'locator_required_data_manager', 'location_napi_adapter',
                  'location_napi_entry', 'bluetooth_scan_result_callback_napi',
                  'ohos.geoLocationManager.impl', 'locator_service_proxy', 'locator_service_stub',
                  'request_config', 'report_manager', 'napi_util', 'gnss_ability', 'gnss_event_callback'],
        'sources': {
            'locator_impl': 'frameworks/native/locator_sdk/source/locator_impl.cpp',
            'locator_ability': 'services/location_locator/locator/source/locator_ability.cpp',
            'request_manager': 'services/location_locator/locator/source/request_manager.cpp',
            'locator_required_data_manager': 'services/location_locator/locator/source/locator_required_data_manager.cpp',
            'location_napi_adapter': 'frameworks/js/napi/source/location_napi_adapter.cpp',
            'location_napi_entry': 'frameworks/js/napi/source/location_napi_entry.cpp',
            'bluetooth_scan_result_callback_napi': 'frameworks/js/napi/source/bluetooth_scan_result_callback_napi.cpp',
            'ohos.geoLocationManager.impl': 'frameworks/ets/taihe/locator_sdk/src/ohos.geoLocationManager.impl.cpp'},
        'targets': {
            'locator_impl': 'obj/base/location/location/frameworks/native/locator_sdk/source/locator_sdk/locator_impl.o',
            **{name: 'obj/base/location/location/services/location_locator/locator/source/lbsservice_locator/' + name + '.o'
               for name in ('locator_ability', 'request_manager', 'locator_required_data_manager')},
            **{name: 'obj/base/location/location/frameworks/js/napi/source/geolocationmanager/' + name + '.o'
               for name in ('location_napi_adapter', 'location_napi_entry', 'bluetooth_scan_result_callback_napi')},
            'ohos.geoLocationManager.impl': 'obj/base/location/location/frameworks/ets/taihe/locator_sdk/src/location_framework_taihe_native/ohos.geoLocationManager.impl.o',
            **{'locator_service_' + kind: 'obj/out/arm64_virt/gen/base/location/location/frameworks/native/locator_sdk/liblocator_interface_' + kind + '/locator_service_' + kind + '.o'
               for kind in ('proxy', 'stub')}},
        'generate_idl': True,
        'supported_products': ['arm64_virt'],
    },
    'audio_capture': {
        'project': 'foundation/multimedia/av_codec',
        'revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
        'components': ['audio_capture_integrity'],
        'units': ['audio_capture_filter', 'audio_capture_module'],
        'sources': {
            'audio_capture_filter': 'services/media_engine/filters/audio_capture_filter.cpp',
            'audio_capture_module': 'services/media_engine/modules/source/audio_capture/audio_capture_module.cpp'},
        'targets': {
            'audio_capture_filter': 'obj/foundation/multimedia/av_codec/services/media_engine/filters/av_codec_media_engine_filters/audio_capture_filter.o',
            'audio_capture_module': 'obj/foundation/multimedia/av_codec/services/media_engine/modules/source/audio_capture/av_codec_media_engine_modules/audio_capture_module.o'},
        'required_headers': {
            'audio_capture_filter': 'interfaces/inner_api/native/audio_capture_filter.h',
            'audio_capture_module': 'services/media_engine/modules/source/audio_capture/audio_capture_module.h'},
    },
    'avc': {
        'project': 'foundation/multimedia/av_codec',
        'revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
        'components': ['avc_eos', 'avc_surface_layout'],
        'directory': 'services/engine/codec/video/avcencoder',
        'units': ['avc_encoder', 'avc_encoder_util'],
        'target': 'obj/foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/avc_encoder/{unit}.o',
        'required_header': None,
    },
    'child': {
        'project': 'foundation/ability/ability_runtime',
        'revision': '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8',
        'components': ['native_child_process'],
        'directory': 'frameworks/native/child_process/src',
        'units': ['native_child_process', 'native_child_callback'],
        'target': 'obj/foundation/ability/ability_runtime/frameworks/native/child_process/src/child_process/{unit}.o',
        'required_header': 'frameworks/native/child_process/include/native_child_callback.h',
    },
    'graphics3d': {
        'project': 'foundation/graphic/graphic_3d',
        'revision': 'b2d7af910f2d4b941697630020b0940245d5bd99',
        'components': ['scene_startup'],
        'units': ['scene_adapter', 'RenderContextJS'],
        'sources': {'scene_adapter': '3d_scene_adapter/src/scene_adapter.cpp',
                    'RenderContextJS': 'kits/js/src/RenderContextJS.cpp'},
        'targets': {
            'scene_adapter': 'obj/foundation/graphic/graphic_3d/3d_scene_adapter/src/scene_adapter_source/scene_adapter.o',
            'RenderContextJS': 'obj/foundation/graphic/graphic_3d/kits/js/src/napi_source/RenderContextJS.o'},
        'required_header': None,
    },
}
GROUPS['location']['sources'].update({
    'request_config': 'frameworks/base_module/source/request_config.cpp',
    'report_manager': 'services/location_locator/locator/source/report_manager.cpp',
    'napi_util': 'frameworks/js/napi/source/napi_util.cpp',
    **{name: 'services/location_gnss/gnss/source/' + name + '.cpp' for name in ('gnss_ability', 'gnss_event_callback')},
})
GROUPS['location']['targets'].update({
    'request_config': 'obj/base/location/location/frameworks/base_module/source/lbsbase_module/request_config.o',
    'report_manager': 'obj/base/location/location/services/location_locator/locator/source/lbsservice_locator/report_manager.o',
    'napi_util': 'obj/base/location/location/frameworks/js/napi/source/geolocationmanager/napi_util.o',
    **{name: 'obj/base/location/location/services/location_gnss/gnss/source/lbsservice_gnss/' + name + '.o'
       for name in ('gnss_ability', 'gnss_event_callback')},
})
GROUPS['knowledge_content']['extra_owned'] = [
    str(Path(name).relative_to('foundation/multimedia/media_library')) for name in json.loads(
        (ROOT / 'patches/common/foundation/multimedia/media_library/knowledge_holiday_index/manifest.json').read_text())['files']
]
# These groups preserve original product flags. New dependency exports and
# feature selections are explicitly labeled diagnostics until fresh GN runs.
GROUPS['recorder'] = {
    'project': 'foundation/multimedia/player_framework',
    'revision': '3d3b1231db27561e8978652d7ae867c12f488d9a',
    'components': ['recorder_configuration'], 'units': ['native_avrecorder'],
    'sources': {'native_avrecorder': 'frameworks/native/capi/recorder/native_avrecorder.cpp'},
    'targets': {'native_avrecorder': 'obj/foundation/multimedia/player_framework/frameworks/native/capi/recorder/avrecorder/native_avrecorder.o'},
    'required_header': None, 'supported_products': ['arm64_virt'],
}
NETWORK_BASE = 'foundation/communication/netmanager_base'
NETWORK_EXT = 'foundation/communication/netmanager_ext'
GROUPS['vpn_broker'] = {
    'project': NETWORK_EXT, 'revision': '8c41289750820fb2ddb347b1205cee9a7b527388',
    'additional_projects': {NETWORK_BASE: '9831989d54f490d046a632ab13d309580d2fa710'},
    'components': [],
    'component_paths': [NETWORK_BASE + '/' + name for name in (
        'optional_settings_read', 'qemu_openvpn_control', 'qemu_openvpn_broker')] +
        [NETWORK_EXT + '/' + name for name in ('always_on_vpn', 'vpn_config_arrays', 'vpn_config_store',
         'vpn_openvpn_fields', 'connected_vpn_nullable', 'openvpn_lifecycle', 'openvpn_session',
         'vpn_callback_dispatch', 'netvpn_callback_unused', 'openvpn_broker')],
    'payloads': {NETWORK_EXT + '/qemu_openvpn/' + p.name: str(p.relative_to(ROOT))
        for p in (ROOT / 'patches/common' / NETWORK_EXT / 'openvpn_backend/files').iterdir()
        if p.suffix in ('.h', '.cpp')},
    'units': ['system_vpn_wrapper', 'multi_vpn_manager', 'networkvpn_service',
              'open_vpn_ctl', 'net_vpn_impl', 'multi_vpn_helper',
              'network_vpn_service_proxy', 'network_vpn_service_stub'],
    'source_paths': {
        NETWORK_UNIT: NETWORK_BASE + '/services/netmanagernative/src/' + DIRECTORY + '/' + NETWORK_UNIT + '.cpp'
        for NETWORK_UNIT, DIRECTORY in (('system_vpn_wrapper', 'netsys'), ('multi_vpn_manager', 'manager'))},
    'targets': {
        NETWORK_UNIT: 'obj/' + NETWORK_BASE + '/services/netmanagernative/src/' + DIRECTORY + '/netsys_native_manager/' + NETWORK_UNIT + '.o'
        for NETWORK_UNIT, DIRECTORY in (('system_vpn_wrapper', 'netsys'), ('multi_vpn_manager', 'manager'))},
    'diagnostic_feature_defines': ['OHOS_QEMU_OPENVPN'],
    'generate_vpn_idl': True,
    'required_header': None, 'supported_products': ['arm64_virt'],
    'scope': 'eight_complete_current_VPN_broker_TUs_actual_product_flags_explicit_new_GN_define_NOT_fresh_GN_link_runtime',
}
for name in ('networkvpn_service', 'open_vpn_ctl', 'net_vpn_impl', 'multi_vpn_helper'):
    GROUPS['vpn_broker']['source_paths'][name] = NETWORK_EXT + '/services/vpnmanager/src/' + name + '.cpp'
    GROUPS['vpn_broker']['targets'][name] = 'obj/' + NETWORK_EXT + '/services/vpnmanager/src/net_vpn_manager/' + name + '.o'
for name, target in (('network_vpn_service_proxy', 'net_vpn_manager_if'),
                     ('network_vpn_service_stub', 'networkvpn_interface_stub')):
    GROUPS['vpn_broker']['targets'][name] = ('obj/out/arm64_virt/gen/' + NETWORK_EXT +
        '/interfaces/innerkits/netvpnclient/' + target + '/' + name + '.o')
PRODUCTS = {'arm64_virt': ('aarch64', 183, 2), 'armv7a_virt': ('arm', 40, 1),
            'x86_64_virt': ('x86_64', 62, 2)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_paths(components):
    paths = set()
    for component in components:
        for patch in component.glob('*.patch'):
            for line in patch.read_text().splitlines():
                if line.startswith(('+++ b/', '--- a/')):
                    name = line[6:].split('\t', 1)[0]
                    if Path(name).is_absolute() or '..' in Path(name).parts:
                        raise ValueError('canonical patch path required')
                    paths.add(name)
    return sorted(paths)


def verify_object(obj, disassembler, arch, machine, elf_class):
    data = obj.read_bytes()[:20]
    if data.startswith(b'BC\xc0\xde'):
        ir = obj.with_suffix('.ll')
        subprocess.run([str(disassembler), str(obj), '-o', str(ir)], check=True)
        # CFI can make one product .o contain split-LTO modules. LLVM's real
        # disassembler writes .ll.0/.ll.1 in that case; verify every module.
        modules = [ir] if ir.is_file() else sorted(
            p for p in ir.parent.glob(ir.name + '.*')
            if re.fullmatch(re.escape(ir.name) + r'\.\d+', p.name))
        if not modules:
            raise ValueError('LLVM disassembler produced no actual modules')
        verified = []
        ir_arch = r'arm(?:v7a?)?' if arch == 'arm' else arch
        for module in modules:
            with module.open() as stream:
                triple = next((line.strip() for line in stream if line.startswith('target triple = ')), '')
            if not re.fullmatch('target triple = "' + ir_arch + '(?:-unknown)?-linux-ohos"', triple):
                raise ValueError('actual product LLVM target required for every module')
            verified.append({'file': module.name, 'target_triple': triple, 'sha256': sha(module)})
        return {'object_format': 'LLVM_bitcode', 'llvm_modules': verified}
    if (data[:6] == bytes([127, 69, 76, 70, elf_class, 1]) and
            int.from_bytes(data[18:20], 'little') == machine):
        return {'object_format': 'ELF'}
    raise ValueError('product ELF/LLVM output required')


def generate_location_idl(root, output, staged, product):
    """Use the product's real generator rule, redirecting all generated files."""
    cwd = root / 'out' / product
    suffix = 'base/location/location/frameworks/native/locator_sdk/ILocatorService.idl'
    lines = (cwd / 'toolchain.ninja').read_text().splitlines()
    commands = [line.strip().removeprefix('command = ') for line in lines
                if line.strip().startswith('command = ') and '--src-idl ' in line and suffix in line]
    if len(commands) != 1:
        raise ValueError('one actual product locator IDL rule required')
    original = shlex.split(commands[0])
    argv = original[:]
    old_idl = argv[argv.index('--src-idl') + 1]
    if not old_idl.endswith('/' + suffix):
        raise ValueError('canonical original IDL source required')
    old_root = old_idl[:-len(suffix)]
    gen_relative = 'out/' + product + '/gen/base/location/location/frameworks/native/locator_sdk'
    old_gen = old_root + gen_relative
    if argv[argv.index('--dst-path') + 1] != old_gen:
        raise ValueError('actual locator generator destination differs')
    old_files = argv[argv.index('--dst-file') + 1].split(',')
    names = [str(Path(path).relative_to(old_gen)) for path in old_files]
    expected = {'ilocator_service.h', 'locator_service_proxy.cpp', 'locator_service_stub.cpp',
                'locator_service_proxy.h', 'locator_service_stub.h', 'type/idata_types.h', 'type/idata_types.cpp'}
    if set(names) != expected or len(names) != len(expected):
        raise ValueError('complete real locator generator output set required')
    generated = output / ('generated-' + product)
    generated.mkdir()
    argv[argv.index('--src-idl') + 1] = str(staged / suffix)
    argv[argv.index('--dst-path') + 1] = str(generated)
    argv[argv.index('--dst-file') + 1] = ','.join(str(generated / name) for name in names)
    tool = root / 'out' / product / 'clang_x64/ability/idl_tool'
    argv[argv.index('--idl-tool-path') + 1] = str(tool)
    if (argv[:2] != ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py'] or
            argv[-4:] != ['--log-domainid', '0xD002300', '--log-tag', 'Locator'] or
            argv[argv.index('--language') + 1] != 'cpp'):
        raise ValueError('actual fixed IDL generator options required')
    with (output / ('idl-' + product + '.log')).open('xb') as log:
        subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    for name in names:
        if not (generated / name).is_file():
            raise ValueError('actual IDL generator omitted ' + name)
    interface = (generated / 'ilocator_service.h').read_text()
    if not all(name in interface for name in ('GetLocationIconStatus', 'StartBluetoothSearch', 'StopBluetoothSearch',
                                             'StartDistrictLocating', 'StartLocatingWithSportsType',
                                             'GetPostProcessingTrack', 'CheckDistrictAccess',
                                             'AddFusionFence', 'RemoveFusionFence', 'IsFusionFenceSupported',
                                             'ReleaseFusionFence')):
        raise ValueError('generated interface omits candidate methods')
    return generated, root / gen_relative, {
        'original_argv': original, 'executed_argv': argv,
        'generator_sha256': sha(tool / 'idl'),
        'driver_sha256': sha(root / 'build/config/components/idl_tool/idl.py'),
        'generated_sha256': {name: sha(generated / name) for name in names},
        'prior_generated_sha256': {name: sha(root / gen_relative / name) for name in names}}


def run(args):
    root, output = args.source_root.resolve(), args.output.absolute()
    if any(not os.statvfs(p).f_flag & os.ST_RDONLY for p in [root, root / 'out']):
        raise ValueError('fixed source and product out must be read-only')
    group = GROUPS[args.group]
    if not set(args.product) <= set(group.get('supported_products', PRODUCTS)):
        raise ValueError('this diagnostic group lacks real commands for the requested product')
    project = Path(group['project'])
    projects = {str(project): group['revision'], **group.get('additional_projects', {})}
    for name, revision in projects.items():
        actual = subprocess.check_output(['git', '-C', str(root / name), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != revision:
            raise ValueError('fixed source revision required: ' + name)
    output.mkdir(parents=True, exist_ok=False)
    components = ([ROOT / 'patches/common' / project / name for name in group['components']] +
                  [ROOT / 'patches/common' / name for name in group.get('component_paths', [])])
    owned = sorted(set(patch_paths(components)) |
                   {str(project / name) for name in group.get('extra_checkout', [])} |
                   {str(project / name) for name in group.get('extra_owned', [])} |
                   set(group.get('payloads', {})))
    if any(not any(Path(name).is_relative_to(p) for p in projects) for name in owned):
        raise ValueError('component targets a different project')
    before = {name: sha(root / name) if (root / name).is_file() else None for name in owned}
    recipe = [Path(__file__), ROOT / 'patches/lib/apply_patch.sh',
              ROOT / 'patches/lib/apply_component_stack.py', ROOT / 'patches/lib/exact_source_states.py',
              ROOT / 'patches/lib/apply_exact_component.py',
              *(ROOT / name for name in group.get('payloads', {}).values()),
              ROOT / 'ci/capability-audit/gn_export_diagnostic.py',
              *(p for c in components for p in c.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts)]
    recipe_before = {str(p): sha(p) for p in recipe}
    staged = output / 'candidate'
    private = staged / project
    with (output / 'source-checkout.log').open('xb') as log:
        for name, revision in projects.items():
            checkout = staged / name
            checkout.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root / name), str(checkout)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
            # New files have no HEAD blob; the component creates them itself.
            existing = [str(Path(path).relative_to(name)) for path in owned if Path(path).is_relative_to(name)
                        and subprocess.run(['git', '-C', str(checkout), 'cat-file', '-e',
                            revision + ':' + str(Path(path).relative_to(name))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0]
            if existing:
                subprocess.run(['git', '-C', str(checkout), 'checkout', revision, '--', *existing],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
    for name, payload in group.get('payloads', {}).items():
        destination = staged / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / payload).read_bytes())
    for attempt in (1, 2):
        for component in components:
            with (output / f'apply-{component.name}-{attempt}.log').open('xb') as log:
                subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
    headers = [name for name in owned if Path(name).suffix in ('.h', '.hpp')]
    generated = {}
    generated_report = {}
    if group.get('generate_idl'):
        for product in args.product:
            directory, original_directory, proof = generate_location_idl(root, output, staged, product)
            generated[product] = (directory, original_directory)
            generated_report[product] = proof
    if group.get('generate_vpn_idl'):
        from compile_always_on_vpn import generate, IDL
        for product in args.product:
            directory = output / ('generated-' + product)
            directory.mkdir()
            proof, entries = generate(root, root / 'out' / product, staged, directory)
            generated[product] = (directory / 'generated', root / 'out' / product / 'gen' / IDL)
            generated_report[product] = {**proof,
                'generated_sha256': proof['output_sha256'],
                'prior_generated_sha256': {entry['name'].removeprefix(str(generated[product][1]) + '/'): sha(Path(entry['name']))
                    for entry in entries}}
    overlay = output / 'headers.json'
    overlay.write_text(json.dumps({'version': 0, 'roots': [
        {'type': 'file', 'name': str(root / name), 'external-contents': str(staged / name),
         'use-external-name': True} for name in headers] + [
        {'type': 'file', 'name': str(original_directory / name),
         'external-contents': str(directory / name), 'use-external-name': True}
        for product, (directory, original_directory) in generated.items()
        for name in generated_report[product]['generated_sha256'] if name.endswith('.h')]}) + '\n')
    report = {'status': 'fail', 'group': args.group, 'source_revision': group['revision'],
              'source_revisions': projects,
              'scope': group.get('scope', 'complete_patched_product_TUs_ONLY_NOT_link_package_runtime'),
              'components': [str(c.relative_to(ROOT / 'patches/common')) for c in components], 'source_before_sha256': before,
              'candidate_sha256': {name: sha(staged / name) for name in owned},
              'recipe_sha256': recipe_before, 'objects': [], 'first_artifact_behavior_gate_passed': False}
    if generated_report:
        report['actual_idl_generation'] = generated_report
    for product in args.product:
        cwd = root / 'out' / product
        arch, machine, elf_class = PRODUCTS[product]
        for unit in group['units']:
            row = {'product': product, 'unit': unit, 'status': 'fail'}
            try:
                target = group['targets'][unit] if 'targets' in group else group['target'].format(unit=unit)
                query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                    capture_output=True, text=True, timeout=180, check=True)
                (output / f'{product}-{unit}-query.log').write_text(query.stdout + query.stderr)
                argv = shlex.split(query.stdout.splitlines()[-1])
                if Path(argv[0]).name == 'ccache':
                    argv.pop(0)
                if (group.get('generate_idl') and unit in ('locator_service_proxy', 'locator_service_stub') or
                        group.get('generate_vpn_idl') and unit in ('network_vpn_service_proxy', 'network_vpn_service_stub')):
                    source = generated[product][1] / (unit + '.cpp')
                    candidate_source = generated[product][0] / (unit + '.cpp')
                else:
                    source = (root / group['source_paths'][unit] if 'source_paths' in group else
                              root / project / (group['sources'][unit] if 'sources' in group else
                                                group['directory'] + '/' + unit + '.cpp'))
                    candidate_source = staged / source.relative_to(root)
                compiler = 'clang' if source.suffix == '.c' else 'clang++'
                template = (root / project / group['template_sources'][unit]
                            if 'template_sources' in group else source)
                if (Path(argv[0]).name != compiler or '--target=' + arch + '-linux-ohos' not in argv or
                        argv.count('-c') != 1 or argv.count('-o') != 1 or argv.count('-MF') != 1 or
                        any(v in argv for v in ('&&', ';', '|')) or
                        (cwd / argv[argv.index('-c') + 1]).resolve() != template):
                    raise ValueError('exact real product TU command required')
                row['original_argv'] = argv[:]
                additions = []
                for define in group.get('diagnostic_feature_defines', []):
                    flag = '-D' + define
                    if any(value.startswith(flag + '=') for value in argv):
                        raise ValueError('conflicting product feature define; preserving original command')
                    if flag not in argv:
                        additions.append(flag)
                if args.group == 'knowledge_content' and unit in (
                        'native_module_ohos_photoaccess_helper', 'knowledge_content_napi', 'knowledge_content_query'):
                    export_flags, export_proof = exported_includes(root,
                        'base/security/access_token/interfaces/innerkits/accesstoken/BUILD.gn', 'accesstoken')
                    argv += export_flags
                    row['diagnostic_public_export'] = export_proof
                    row['fresh_GN_dependency_selection_tested'] = False
                if args.group == 'vpn_broker' and unit in ('system_vpn_wrapper', 'multi_vpn_manager'):
                    export_flags, export_proof = exported_includes(root,
                        'base/startup/init/interfaces/innerkits/BUILD.gn', 'exported_header_files')
                    argv += export_flags
                    row['diagnostic_public_export'] = export_proof
                    row['fresh_GN_dependency_selection_tested'] = False
                if additions:
                    argv += additions
                    row['diagnostic_feature_defines_added'] = additions
                    row['fresh_GN_feature_selection_tested'] = False
                if template != source:
                    row['command_template_source'] = str(template)
                    row['fresh_GN_source_selection_tested'] = False
                obj = output / f'{product}-{unit}.o'
                dep = output / f'{product}-{unit}.d'
                argv[argv.index('-c') + 1] = str(candidate_source)
                argv[argv.index('-o') + 1] = str(obj)
                argv[argv.index('-MF') + 1] = str(dep)
                argv += ['-iquote', str(source.parent)]
                if headers or generated:
                    argv += ['-ivfsoverlay', str(overlay)]
                row['executed_argv'] = argv
                with (output / f'{product}-{unit}-compile.log').open('xb') as log:
                    result = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=600)
                row['exit_code'] = result.returncode
                if result.returncode:
                    raise ValueError('product compilation failed; full log retained')
                disassembler = (cwd / argv[0]).resolve().parent / 'llvm-dis'
                row.update(verify_object(obj, disassembler, arch, machine, elf_class))
                dependency = dep.read_text()
                required = group.get('required_headers', {}).get(unit, group.get('required_header'))
                if str(candidate_source) not in dependency or (required and str(private / required) not in dependency):
                    raise ValueError('compiler did not consume actual candidate source/header')
                row.update(status='pass', object_sha256=sha(obj), dependency_sha256=sha(dep))
            except Exception as error:
                row['error'] = type(error).__name__ + ': ' + str(error)
            report['objects'].append(row)
            (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    report['source_inputs_unchanged'] = all(
        (sha(root / name) if (root / name).is_file() else None) == checksum for name, checksum in before.items())
    report['recipe_inputs_unchanged'] = all(sha(Path(name)) == checksum for name, checksum in recipe_before.items())
    report['candidate_inputs_unchanged'] = all(sha(staged / name) == checksum
                                               for name, checksum in report['candidate_sha256'].items())
    report['generated_inputs_unchanged'] = all(
        sha(generated[product][0] / name) == checksum
        for product, proof in generated_report.items()
        for name, checksum in proof['generated_sha256'].items()) and all(
        sha(generated[product][1] / name) == checksum
        for product, proof in generated_report.items()
        for name, checksum in proof['prior_generated_sha256'].items())
    if (report['source_inputs_unchanged'] and report['recipe_inputs_unchanged'] and
            report['candidate_inputs_unchanged'] and report['generated_inputs_unchanged'] and
            report['objects'] and all(x['status'] == 'pass' for x in report['objects'])):
        report['status'] = 'pass'
    (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'group': args.group, 'status': report['status'], 'objects': len(report['objects'])}))
    return report['status'] == 'pass'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group', choices=GROUPS, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append', required=True)
    args = parser.parse_args()
    if len(args.product) != len(set(args.product)):
        parser.error('duplicate products cannot count as separate checks')
    raise SystemExit(0 if run(args) else 1)
