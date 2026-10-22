"""Fixed DATA projection from Root's real new package/source/out production."""
from pathlib import Path
import re
from audio579_common import doc, checked, need, source_guard
from usb579_native import prepared_input

KERNEL_FLAGS = ('USB','USB_GADGET','USB_DUMMY_HCD','USB_LIBCOMPOSITE','USB_CONFIGFS',
    'USB_CONFIGFS_F_FS','USB_CONFIGFS_F_MIDI','SND_USB_AUDIO','SND_RAWMIDI','CONFIGFS_FS')
LIBRARIES = ('libmedia_mtp.z.so', 'libusbfn_mtp_interface_service_1.0.z.so')
SOURCE_FILES = (
    'drivers/peripheral/usb/usb.gni', 'drivers/peripheral/usb/bundle.json',
    'drivers/peripheral/usb/gadget/function/mtp/BUILD.gn',
    'drivers/peripheral/usb/gadget/function/mtp/src/usbfn_mtp_impl.cpp',
    'drivers/peripheral/usb/gadget/function/mtp/src/qemu_mtp_functionfs.cpp',
    'drivers/peripheral/usb/gadget/function/mtp/include/qemu_mtp_functionfs.h',
    'foundation/multimedia/media_library/media_library.gni', 'foundation/multimedia/media_library/bundle.json',
    'foundation/multimedia/media_library/frameworks/innerkitsimpl/medialibrary_data_extension/BUILD.gn',
    'foundation/multimedia/media_library/services/media_mtp/BUILD.gn',
    'foundation/multimedia/media_library/services/media_mtp/src/mtp_driver.cpp',
    'foundation/multimedia/media_library/services/media_mtp/src/mtp_operation_utils.cpp',
    'foundation/multimedia/media_library/services/media_mtp_service/src/media_mtp_manager.cpp',
    'foundation/multimedia/media_library/services/media_mtp_service/include/qemu_mtp_mount_watcher.h',
    'device/qemu/common/virt_full/cfg/init.virt.usb.cfg',
    'base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/ets/pages/UsbDialog.ets',
    'base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/resources/base/element/string.json',
    'base/usb/usb_manager/frameworks/dialog/dialog_ui/AppScope/app.json')


def assemble_usb(export_ref, *, package, target):
    value = doc(export_ref)
    need(set(value) == {'schema','source_commit','archive','product','normal_source_context','source_export',
        'installed_runtime_profile','kernel','init','libraries','native_build','permission_ui'} and
        value['schema'] == 'usb579-actual-product-input-export/v1' and value['source_commit'] == package['source_commit'] and
        value['archive'] == package['archive'] and value['product'] == target['product'],
        'fixed actual USB package DATA; no executable/ID/role/fixture choice')
    context = doc(source_guard(value['normal_source_context']))
    source = doc(value['source_export'])
    need(context['source_commit'] == value['source_commit'] == source['source_commit'] and
        source['archive_sha256'] == value['archive']['sha256'] and source['product'] == target['product'] and
        source['source_kind'] == 'actual_shared_source_and_out_readonly_export' and
        source['resources_executed'] is True and source['cleanup_verified'] is True and source['failures'] == [],
        'normal completed original Owner source/out export of this new package')
    for name in SOURCE_FILES:
        checked(source['files'][name])
    from batch_system_build_runtime_helpers import validate_installed_profile
    profile = doc(value['installed_runtime_profile'])
    validate_installed_profile(profile, archive_sha256=package['archive']['sha256'])
    need(profile['product'] == target['product'] and profile['arch'] == target['arch'] and profile['device'] == target['device'], 'actual installed whole product profile')
    need(set(value['libraries']) == set(LIBRARIES), 'two real existing MTP transport/protocol DSOs')
    for soname in LIBRARIES:
        evidence=doc(value['libraries'][soname])
        need(evidence['schema']=='usb579-whole-product-DSO/v1' and evidence['source_commit']==value['source_commit'] and
            evidence['archive_sha256']==package['archive']['sha256'] and evidence['product']==target['product'] and
            evidence['soname']==soname and evidence['installed_runtime_profile']==value['installed_runtime_profile'] and
            evidence['image_file']==profile['dsos'][soname]['image_file'] and evidence['translation_units'] and evidence['link'],
            'complete real product target/TUs/link/CFI/LTO and installed DSO provenance')
        checked(evidence['image_file']); checked(evidence['complete_compile_commands']); checked(evidence['complete_ninja_log'])
        for query in (evidence['link']['raw_query'],evidence['link']['expanded_compdb_query']):
            need(query in source['commands'] and query['exit_code']==0 and not query['timed_out'], 'actual same original CID link query')
            checked(query['stdout']);need(checked(query['stderr']).read_bytes()==b'', 'actual complete successful native query')
        for logical,unit in evidence['translation_units'].items():
            for key in ('source','object','dependency_file'):checked(unit[key])
            need(unit['dependency_query'] in source['commands'] and unit['dependency_kind']=='original_ninja_deps/v1' and
                unit['dependency_file']==unit['dependency_query']['stdout'] and type(unit['command']) is list and unit['command'],
                'actual full normal TU, exact-object deps query and untouched complete compiler argv')
    config=checked(value['kernel']['config'])
    flags=dict(re.findall(r'^(CONFIG_[A-Z0-9_]+)=(\S+)$',config.read_text(),re.M))
    need(all(flags.get('CONFIG_'+key)=='y' for key in KERNEL_FLAGS), 'real normal selected final kernel config')
    for key in ('image','config','normal_build_log','source_defconfig'):checked(value['kernel'][key])
    need(set(value['init'])=={'source','staged','image_file'} and
        value['init']['source']==source['files']['device/qemu/common/virt_full/cfg/init.virt.usb.cfg'], 'actual new product init input')
    need(checked(value['init']['source']).read_bytes()==checked(value['init']['staged']).read_bytes()==checked(value['init']['image_file']).read_bytes(), 'actual installed normal init bytes')
    ui=value['permission_ui']
    need(set(ui)=={'app','dialog','strings','provider_hap'} and
        ui['app']==source['files']['base/usb/usb_manager/frameworks/dialog/dialog_ui/AppScope/app.json'] and
        ui['dialog']==source['files']['base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/ets/pages/UsbDialog.ets'] and
        ui['strings']==source['files']['base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/resources/base/element/string.json'] and
        doc(ui['app'])['app']['bundleName']=='com.usb.right', 'actual product normal USB permission provider source')
    strings={row['name']:row['value'] for row in doc(ui['strings'])['string']}
    need(strings['allowButton']=='Allow' and strings['notAllowButton']=='Deny', 'exact normal base resource UI selectors')
    checked(ui['provider_hap'])
    peer=prepared_input(value['native_build'],archive=package['archive'],product=target['product'])
    return dict(schema='usb579-shared-device-inputs/v1', product_export=export_ref,
        normal_source_context=value['normal_source_context'],native_peer=peer)
