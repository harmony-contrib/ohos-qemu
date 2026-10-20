"""Finite Settings NAPI fixture recipe for the original platform helper builder.

Use actual current product object commands, headers, CFI and installed DSOs.
This diagnostic DSO is not claimed as a newly selected product GN target. It is
compiled only to run the actual held guest's real Context/token/IPC boundaries.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = {
    'graph': 'obj/foundation/ability/ability_runtime/interfaces/inner_api/runtime/runtime.ninja',
    'object': 'obj/foundation/ability/ability_runtime/frameworks/native/runtime/runtime/runtime.o',
    'source': 'foundation/ability/ability_runtime/frameworks/native/runtime/runtime.cpp',
    'header': 'foundation/ability/ability_runtime/interfaces/kits/native/appkit/ability_runtime/context/context.h'}
BASE = {
    'graph': 'obj/foundation/ability/ability_runtime/interfaces/inner_api/napi_base_context/napi_base_context.ninja',
    'object': 'obj/foundation/ability/ability_runtime/interfaces/inner_api/napi_base_context/src/napi_base_context/napi_base_context.o',
    'source': 'foundation/ability/ability_runtime/interfaces/inner_api/napi_base_context/src/napi_base_context.cpp',
    'header': 'foundation/ability/ability_runtime/interfaces/inner_api/napi_base_context/include/napi_base_context.h'}
IPC = {
    'graph': 'obj/foundation/communication/ipc/interfaces/innerkits/ipc_napi_common/ipc_napi.ninja',
    'object': 'obj/foundation/communication/ipc/ipc/native/src/napi_common/source/ipc_napi/napi_remote_object.o',
    'source': 'foundation/communication/ipc/ipc/native/src/napi_common/source/napi_remote_object.cpp',
    'header': 'foundation/communication/ipc/interfaces/innerkits/ipc_napi_common/include/napi_remote_object.h'}
TOKEN = {
    'graph': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/libaccesstoken_sdk.ninja',
    'object': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/src/libaccesstoken_sdk/accesstoken_kit.o',
    'source': 'base/security/access_token/interfaces/innerkits/accesstoken/src/accesstoken_kit.cpp',
    'header': 'base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h'}


def helper_recipes():
    return {'settings_idle579_napi': {
        'fixture': '../settings_idle579/native/SettingsIdleNative.cpp',
        'source_file': str(HERE / 'settings_idle579/native/SettingsIdleNative.cpp'),
        'kind': 'shared_napi', 'output_basename': 'libsettings_idle579.so',
        'anchors': [dict(RUNTIME), dict(BASE), dict(IPC), dict(TOKEN)],
        'libraries': [
            'ability/ability_runtime/libnapi_base_context.z.so',
            'communication/ipc/libipc_napi.z.so',
            'communication/ipc/libipc_single.z.so',
            'systemabilitymgr/samgr/libsamgr_proxy.z.so',
            'arkui/napi/libace_napi.z.so',
            'commonlibrary/c_utils/libutils.z.so'],
        'headers': [RUNTIME['header'], BASE['header'], IPC['header'],
            'foundation/systemabilitymgr/samgr/interfaces/innerkits/samgr_proxy/include/iservice_registry.h',
            'foundation/systemabilitymgr/samgr/interfaces/innerkits/samgr_proxy/include/system_ability_definition.h',
            'foundation/communication/ipc/interfaces/innerkits/ipc_core/include/message_parcel.h'],
        'extra_includes': [
            'foundation/ability/ability_runtime/interfaces/kits/native/appkit/ability_runtime/context',
            'foundation/ability/ability_runtime/interfaces/inner_api/napi_base_context/include',
            'foundation/systemabilitymgr/samgr/interfaces/innerkits/samgr_proxy/include']}}


def recipe():
    return {'schema': 'settings-idle579-platform-napi-source/v2',
        'kind': 'diagnostic_shared_napi_from_actual_product_graph',
        'helper': 'settings_idle579_napi', 'actual_GN_anchors': [dict(RUNTIME), dict(BASE), dict(IPC), dict(TOKEN)],
        'output_basename': 'libsettings_idle579.so', 'platform_abi': 'arm64-v8a',
        'hap_destination': 'entry/libs/arm64-v8a/libsettings_idle579.so',
        'new_product_GN_target_selected': False, 'source_only': True}
