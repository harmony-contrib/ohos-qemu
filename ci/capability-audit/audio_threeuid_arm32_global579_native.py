"""Two real original375 C++ recipes, compiled for the actual ARM32 product.

The generic Builder registers these fixed recipes only for armv7a_virt. Nothing
here edits HELPERS, changes a source body or supplies target/float ABI flags.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
NATIVE = HERE / 'fixtures/batch_media/audio_threeuid_global579'
NAMES = ('audio_global579_passive', 'audio_global579_token')
VDI = {'graph': 'obj/vendor/ohemu/virt/hals/vibrator/libhdi_product_vibrator_impl.ninja',
       'object': 'obj/vendor/ohemu/virt/hals/vibrator/libhdi_product_vibrator_impl/qemu_virtual_vibrator.o',
       'source': 'vendor/ohemu/virt/hals/vibrator/qemu_virtual_vibrator.cpp',
       'header': 'drivers/interface/vibrator/v2_0/IVibratorInterface.idl'}
TOKEN = {'graph': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/libaccesstoken_sdk.ninja',
         'object': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/src/libaccesstoken_sdk/accesstoken_kit.o',
         'source': 'base/security/access_token/interfaces/innerkits/accesstoken/src/accesstoken_kit.cpp',
         'header': 'base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h'}


def helper_recipes():
    return {
        NAMES[0]: dict(fixture='batch_media/audio_threeuid_global579/passive375.cpp',
            source_file=NATIVE / 'passive375.cpp', anchors=[dict(VDI), dict(TOKEN)],
            libraries=['hdf/drivers_interface_vibrator/libvibrator_proxy_2.0.z.so'],
            headers=[VDI['header']], extra_includes=[]),
        NAMES[1]: dict(fixture='batch_media/audio_threeuid_global579/token375.cpp',
            source_file=NATIVE / 'token375.cpp', anchors=[dict(TOKEN)],
            libraries=['security/access_token/libaccesstoken_sdk.z.so'],
            headers=[TOKEN['header'], 'base/security/access_token/interfaces/innerkits/accesstoken/include/hap_token_info.h'],
            extra_includes=[]),
    }
