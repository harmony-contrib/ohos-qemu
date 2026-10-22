"""Fixed Media product DATA selection; no packet-selected executable or policy."""
GFX = 'foundation/graphic/graphic_3d/'
NINJA = 'prebuilts/build-tools/linux-x86/bin/ninja'
TUS = (GFX+'3d_scene_adapter/src/scene_adapter.cpp', GFX+'kits/js/src/RenderContextJS.cpp')
GRAMMAR = ('build/toolchain/gcc_solink_wrapper.py','build/toolchain/gcc_toolchain.gni',
           'build/toolchain/ohos/ohos_toolchain.gni','build/toolchain/wrapper_utils.py')
AUDIO_PERMISSION = 'foundation/multimedia/audio_framework/frameworks/native/audioutils/src/audio_utils.cpp'
AUDIO_SOURCES = (
 'foundation/multimedia/audio_framework/frameworks/js/napi/audiomanager/napi_audio_manager.cpp',
 'foundation/multimedia/audio_framework/services/audio_policy/server/service/service_main/src/audio_policy_server.cpp',
 'foundation/multimedia/audio_framework/services/audio_service/client/src/audio_system_manager.cpp',
 'foundation/multimedia/audio_framework/services/audio_service/client/src/audio_system_client_policy_manager.cpp',
 'foundation/multimedia/audio_framework/services/audio_policy/client/service/src/audio_policy_manager.cpp',
 AUDIO_PERMISSION,
 'foundation/multimedia/audio_framework/frameworks/js/napi/common/napi_audio_error.h',
 'foundation/multimedia/audio_framework/frameworks/native/audioutils/BUILD.gn',
 'foundation/multimedia/audio_framework/frameworks/js/napi/audiomanager/napi_audio_spatialization_manager.cpp',
 'foundation/multimedia/audio_framework/services/audio_policy/server/infra/config/file/audio_effect_config.xml',
 'foundation/multimedia/audio_framework/services/audio_policy/server/infra/config/parser/src/audio_effect_config_parser.cpp',
 'foundation/multimedia/audio_framework/services/audio_policy/server/infra/config/parser/include/audio_effect_config_parser.h',
 'vendor/ohemu/virt/hals/audio/audio_effect.json',
)
MIDI_HEADERS = ('foundation/multimedia/midi_framework/interfaces/kits/c/midi/native_midi.h',
                'foundation/multimedia/midi_framework/interfaces/kits/c/midi/native_midi_base.h')
IV_ROOT = 'drivers/peripheral/intelligent_voice'
IV_ENGINE_ROOT = IV_ROOT+'/passthrough'
SOURCE_TREES = (GFX.rstrip('/'), IV_ROOT, 'foundation/ai/intelligent_voice_framework')
# uid declaration, registration record, actual compiled TU, owning GN, SONAME.
PLUGINS = {
 'UID_CAMERA_PREVIEW_PLUGIN':('camera_preview_plugin/api/cam_preview/implementation_uids.h','camera_preview_plugin/src/component_dll.cpp','camera_preview_plugin/src/component_dll.cpp','camera_preview_plugin/BUILD.gn','libPluginCamPreview.z.so'),
 'UID_SCENE_PLUGIN':('lume/LumeScene/include/scene/base/namespace.h','lume/LumeScene/src/plugin.cpp','lume/LumeScene/src/plugin.cpp','lume/LumeScene/BUILD.gn','libPluginSceneWidget.z.so'),
 'UID_RENDER_PLUGIN':('lume/LumeRender/api/render/implementation_uids.h','lume/LumeRender/src/plugin/registry_data.cpp','lume/LumeRender/src/plugin/dynamic_plugin.cpp','lume/LumeRender/BUILD.gn','libPluginAGPRender.z.so'),
 'UID_3D_PLUGIN':('lume/Lume_3D/api/3d/implementation_uids.h','lume/Lume_3D/src/plugin/registry_data.cpp','lume/Lume_3D/src/plugin/dynamic_plugin.cpp','lume/Lume_3D/BUILD.gn','libPluginAGP3D.z.so'),
 'META_OBJECT_PLUGIN_UID':('lume/LumeMeta/include/meta/base/plugin.h','lume/LumeMeta/src/plugin.cpp','lume/LumeMeta/src/plugin.cpp','lume/LumeMeta/BUILD.gn','libPluginMetaObject.z.so'),
 'UID_SCENE_METADATA_IMPORTER_PLUGIN':('lume/LumeScene/serialization/metadata_importer_plugin/include/scene_metadata_importer/plugin.h','lume/LumeScene/serialization/metadata_importer_plugin/src/plugin.cpp','lume/LumeScene/serialization/metadata_importer_plugin/src/plugin.cpp','lume/LumeScene/BUILD.gn','libPluginLumeSceneMetadataImporter.z.so'),
 'UID_JPG_PLUGIN':('lume/LumeJpg/api/jpg/implementation_uids.h','lume/LumeJpg/src/component_dll.cpp','lume/LumeJpg/src/component_dll.cpp','lume/LumeJpg/BUILD.gn','libPluginAGPJpg.z.so'),
 'UID_PNG_PLUGIN':('lume/LumePng/api/png/implementation_uids.h','lume/LumePng/src/component_dll.cpp','lume/LumePng/src/component_dll.cpp','lume/LumePng/BUILD.gn','libPluginAGPPng.z.so'),
}
MEDIA_NAMES = {'libscene.so','libscene.z.so','libAGPDLL.z.so','libohmidi.so',
 'libPluginLumeSceneImporter.z.so'} | {row[-1] for row in PLUGINS.values()}
IV_NAMES = {'libvendor_intell_voice_engine.z.so'}
PARTITIONS = ('system','vendor','chip_prod','sys_prod','system_ext','product')

# Fixed supplemental USB/MIDI/MTP selection on this same actual RO CID.
USB_NAMES = {'libmedia_mtp.z.so', 'libusbfn_mtp_interface_service_1.0.z.so'}
USB_TREES = ('drivers/peripheral/usb/gadget/function/mtp',
    'foundation/multimedia/media_library/services/media_mtp',
    'foundation/multimedia/media_library/services/media_mtp_service',
    'foundation/multimedia/midi_framework', 'drivers/peripheral/midi', 'drivers/interface/midi',
    'base/usb/usb_manager/frameworks/dialog/dialog_ui')
USB_SOURCES = ('drivers/peripheral/usb/usb.gni', 'drivers/peripheral/usb/bundle.json', 'drivers/peripheral/usb/gadget/function/mtp/BUILD.gn', 'foundation/multimedia/media_library/media_library.gni', 'foundation/multimedia/media_library/bundle.json', 'foundation/multimedia/media_library/frameworks/innerkitsimpl/medialibrary_data_extension/BUILD.gn', 'foundation/multimedia/media_library/frameworks/innerkitsimpl/medialibrary_data_extension/src/media_datashare_ext_ability.cpp', 'device/qemu/common/virt_full/cfg/init.virt.usb.cfg', 'device/qemu/common/virt_full/kernel/build_kernel.sh', 'device/qemu/common/virt_full/kernel/arm64_virt_defconfig', 'device/qemu/common/virt_full/kernel/arm_virt_defconfig', 'device/qemu/common/virt_full/kernel/x86_64_virt_defconfig', 'kernel/linux/linux-6.6/drivers/usb/gadget/udc/dummy_hcd.c', 'kernel/linux/linux-6.6/drivers/usb/gadget/function/f_fs.c', 'kernel/linux/linux-6.6/drivers/usb/gadget/function/f_midi.c')
USB_SOURCES += ('base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/usb/public/file.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/usb/vendor/usb_host.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/multimedia/media_library/system/medialibrary_hap.te', 'base/security/selinux_adapter/sepolicy/base/system/virtfs_contexts', 'base/security/selinux_adapter/sepolicy/ohos_policy/developtools/hdc/system/hdcd.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/developtools/hdc/system/sh.te', 'vendor/ohemu/qemu_arm64_linux_full/config.json', 'vendor/ohemu/qemu_armv7a_linux_full/config.json', 'vendor/ohemu/qemu_x86_64_linux_full/config.json')
MEDIA_NAMES |= USB_NAMES

# Independent normal superset only; original runtime15/USB/SDK sets unchanged.
CPU_PREBUILT_NAMES = {'libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so'}
CPU_ROOT = IV_ENGINE_ROOT+'/cpu'
SPATIAL_ROOT='foundation/multimedia/audio_framework/frameworks/native/audioeffect/qemu_spatial'
TELEPHONY_NATIVE_ROOT='foundation/communication/netmanager_base/services/netmanagernative'
SOURCE_TREES += ('foundation/multimedia/audio_framework','drivers/peripheral/audio/effect','drivers/peripheral/sensor',TELEPHONY_NATIVE_ROOT)
AUDIO_SOURCES += ('base/security/access_token/tools/accesstoken/src/atm_command.cpp',
 'base/security/access_token/tools/accesstoken/include/atm_command.h')
CPU_SOURCE_AUDIO = (CPU_ROOT+'/challenge/3.wav',CPU_ROOT+'/challenge/4.wav')
CPU_IMAGE_ASSETS=('encoder.onnx','decoder.onnx','joiner.onnx','tokens.txt','speaker.onnx','pinyin.txt','NOTICES.txt','INPUTS.json')

# Exact phone Number permission/source/compile supplement. No new resource owner.
NUMBER580_ROOTS = {'libnumber_identity.z.so','libnumberidentity.z.so','libnumberlookup.z.so'}
NUMBER580_SOURCES = {
    'number_napi': 'base/telephony/number_identity/frameworks/js/src/napi_number_identity.cpp',
    'number_errors': 'base/telephony/number_identity/utils/log/include/number_identity_errors.h',
    'mark_ability': 'base/telephony/number_identity/number_mark/src/number_mark_ability.cpp',
    'core_util': 'base/telephony/core_service/frameworks/js/napi/napi_util.cpp',
    'core_errors': 'base/telephony/core_service/interfaces/innerkits/include/telephony_errors.h',
    'js_errors': 'base/telephony/core_service/frameworks/js/napi/js_error_code.h',
}
NUMBER580_TUS = ('number_napi','mark_ability','core_util')
NUMBER580_DEPENDENCIES = {
    'number_napi': ('number_napi','number_errors','core_errors','js_errors'),
    'mark_ability': ('mark_ability','number_errors'),
    'core_util': ('core_util','core_errors','js_errors'),
}
NUMBER580_NAPI_SHA256 = '36a024778c3057f8f3dbe7ad620e5e8446f47cfe718e71c2d0edf65a92a97582'
NUMBER580_PROJECT_REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
