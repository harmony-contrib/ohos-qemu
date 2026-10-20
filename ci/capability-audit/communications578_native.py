"""Pure fixed native recipes for the root's existing product helper-builder.

No query, compiler, subprocess or resource action occurs here. Native artifacts
are built once after the new archive's actual installed-profile export, before
starting its VM. These are diagnostic helpers using existing actual GN flags;
the BUILD.gn declarations do not claim fresh product graph selection.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = {
    'graph': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/libaccesstoken_sdk.ninja',
    'object': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/src/libaccesstoken_sdk/accesstoken_kit.o',
    'source': 'base/security/access_token/interfaces/innerkits/accesstoken/src/accesstoken_kit.cpp',
    'header': 'base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h'}
RIL_C = {
    'graph': 'obj/base/telephony/ril_adapter/services/vendor/ril_vendor.ninja',
    'object': 'obj/base/telephony/ril_adapter/services/vendor/src/ril_vendor/vendor_adapter.o',
    'source': 'base/telephony/ril_adapter/services/vendor/src/vendor_adapter.c',
    'header': 'base/telephony/ril_adapter/services/vendor/include/vendor_adapter.h'}


def helper_recipes():
    """Exact original Builder.HELPERS shape; root adds these two fixed entries."""
    return {
        'communications578_permission_controller': {
            'fixture': '../communications578/PermissionController.cpp',
            'source_file': str(HERE / 'communications578/PermissionController.cpp'),
            'anchors': [dict(TOKEN)], 'libraries': ['security/access_token/libaccesstoken_sdk.z.so'],
            'headers': [TOKEN['header'],
                'base/security/access_token/interfaces/innerkits/accesstoken/include/access_token.h',
                'base/security/access_token/interfaces/innerkits/accesstoken/include/hap_token_info.h'],
            'extra_includes': []},
        'communications578_at_peer': {
            'fixture': '../communications578_at_peer.c',
            'source_file': str(HERE / 'communications578_at_peer.c'),
            'language': 'c', 'anchors': [dict(RIL_C)], 'libraries': [],
            'headers': [], 'extra_includes': []}}


def gn_contract():
    """Source declarations and actual product anchor dependency identities."""
    return {
        'permission_controller': {
            'diagnostic_target': 'communications578_permission_controller',
            'diagnostic_build': str(HERE / 'communications578/BUILD.gn'),
            'source_file': str(HERE / 'communications578/PermissionController.cpp'),
            'deps': ['//base/security/access_token/interfaces/innerkits/accesstoken:libaccesstoken_sdk'],
            'external_deps': [], 'actual_anchor': dict(TOKEN),
            'actual_anchor_GN_target': '//base/security/access_token/interfaces/innerkits/accesstoken:libaccesstoken_sdk',
            'actual_anchor_external_deps': ['c_utils:utils', 'hilog:libhilog', 'init:libbegetutil',
                                           'ipc:ipc_single', 'samgr:samgr_proxy'],
            'required_helper_DT_NEEDED': ['libaccesstoken_sdk.z.so'],
            'elf_contract': 'actual system __h C++ ABI, cross-DSO CFI, LTO, product CRT and installed runtime'},
        'at_peer': {
            'diagnostic_target': 'communications578_at_peer',
            'diagnostic_build': str(HERE / 'communications578/BUILD.gn'),
            'source_file': str(HERE / 'communications578_at_peer.c'),
            'deps': [], 'external_deps': [], 'actual_anchor': dict(RIL_C),
            'actual_anchor_GN_target': '//base/telephony/ril_adapter/services/vendor:ril_vendor',
            'actual_anchor_deps': ['//base/telephony/ril_adapter/interfaces/innerkits:hril_innerkits'],
            'actual_anchor_external_deps': ['bounds_checking_function:libsec_shared', 'c_utils:utils',
                                           'hilog:libhilog', 'init:libbegetutil'],
            'actual_exported_BUILD_sha256': '49a42221271edfbb07763d866b67182e84ff4918b83a36f0a026893250f98492',
            'actual_exported_anchor_source_sha256': 'ef04e99ece9ac924b4961de367e7a570481c9a52e9955f84bf62c1e23805883c',
            'required_helper_DT_NEEDED': ['libc.so'],
            'elf_contract': 'actual C GN flags, musl product CRT/runtime, LTO and selected CFI; no C++ symbol assertion'}}
