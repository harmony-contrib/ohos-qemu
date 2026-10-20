#!/usr/bin/env python3
"""Fixed production source adaptation; actual SDK/build/QEMU remain pending."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/call'
REVISION = '8383e1930ffb28b512929b913eadf266a4e3a55a'
FILES = (('CallSetting/BUILD.gn', None, '0b6207f41f770ff8300a100d8f39093878ddea77bdae3549927120fbc24ca6b1'), ('CallSetting/build-profile.json5', '44068dd2c57a0e097f87fbe75bcf0a37b1afaf657e5db68e2d313827723c8815', 'bf76539b7b8854b764a10b36dd9d1e26bba0fa9af6797561e9432f44b490b56d'), ('CallSetting/common/src/main/ets/utils/ApnDataStorageCommon.ets', '89ce07d99eb82a8fb82cc107ab6eda71115110297fedc6573ef8595e5bd663e2', '899089572406aed985efac065e026aeaeb688a92e2b961763272d779ccd61b39'), ('CallSetting/common/src/main/ets/utils/ApnDetailsCommon.ets', '96970a53789be51a8876adae018738dd136e53394ec467662ca7e4c917d9432a', '95c8e302611ac53897669abfe1e40b036514e5f2f7cbdac40bddc5706811ef3e'), ('CallSetting/common/src/main/ets/utils/ApnListCommon.ets', '4e758855b075b9606acd9c312583121fa4cf92ea350a3401f882c1f66fb9847c', '19888676bc7a0eb3e4c2f3e0d92789931f99dd2b7f72637c0fc4242a92d14e20'), ('CallSetting/hvigor/hvigor-config.json5', '7373e66e10541c83a72525909753c30f5a8265501a671c18925764e297061287', '1719de0960d58c2513f4968774e5de9be64bcf2797a517f37936df932cfd6029'), ('CallSetting/oh-package.json5', 'fd81940a1464436ce6d284dc474060610a78315f280f23b6c649b1d1b5e15107', '0e121c0863163ef1024c5212eb2ca214648ea21d5b0fea7acdc3092315110693'), ('CallSetting/product/default/oh-package.json5', 'd8fc7350fa2569458af71a636732771ecc15f85a8478e97de7f7b6d930df0d82', 'c9829c95ec250a41d1568fe9ccf1b98a16b1cd52973ef1bf6c83255c3c86fabd'), ('CallSetting/product/default/src/main/ets/CallSettingDialogAbility/GeneralCallSettingDialogAbility.ets', None, '84f9603f9151b47d3f8dc0ef18634c6146611130372a942daf28c9bbcaad6988'), ('CallSetting/product/default/src/main/ets/common/components/ApnDetailDialogContent.ets', 'cfb0d6a79798275e50c39b2f6d878f1a4eaaba275daf4b2a570f57e5a5281f49', 'd9a8d2111c832e96c64208fbadf637ea98cbc5aa3eaece9d4791e3a5e1a8182a'), ('CallSetting/product/default/src/main/ets/pages/ApnDetails.ets', '1aaaf6673c41461081e4ef03d5ed6acd97699b4ffafc21e23893cb02a33728cd', 'c59b68ac2e81d0a45526cba204efdf8d3768abec3e95e6b448c6b7403c1ef322'), ('CallSetting/product/default/src/main/ets/pages/ApnList.ets', '6781a201b281b4c6043bd44ad8b5475971b1d3947aa933f231c463ce63135eb6', 'a67b9b36306600b97e3df3da23eb0fc9fba7d124c05bd4daee0e5dbb17fbc8ca'), ('CallSetting/product/default/src/main/ets/pages/SystemApnDialogPage.ets', None, 'c77d5bd4b5faa84f2c3a3b98aa8211f6fc4d2aa1aba80dcc8e06d2cd8baa76fe'), ('CallSetting/product/default/src/main/module.json5', 'b5f4d21b5b9a4f026a1a85c5f56c0d79707c40f5be231dc48210db1525e7a36a', '69aff4bcb6cab8ee15bd563381d03ca949fdf082d94d3d949fea2457986fec0f'), ('CallSetting/product/default/src/main/resources/base/profile/main_pages.json', '37f5737b619720d733c0ed8afe90f927e06ad6269b59093c8f706bff42172472', 'd5a13f247a4e8b233a2cb44f4363ad332c5d988ac39585715e1d0e1c4e006336'))
CRLF_FILES = ()
READONLY = {'CallSetting/AppScope/app.json5': '3eeb558cd7eb9062ccc0e2950d1e267f8c46e739683abc8ff626598ff150bdf7', 'CallSetting/common/src/main/ets/utils/MobileDataGlobalContextHelper.ets': '17d0781de1279cdf8b41a3c2b2b59755bb2d7f63f9b05357e04896d38a3a1371', 'CallSetting/common/src/main/ets/utils/ReportUtil.ets': '4072d2babdc12a090ee1bb09287d8d2fe4e9fad0cd6442bdb4997d67242d5117', 'CallSetting/product/default/src/main/ets/pages/MdApnDetail.ets': 'e4988f7d3a66caa2a24d24732fa7ce3c87fc845c33e60db23a9e66172ad93f20'}

def validate(root, require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)

def prerequisites(root):
    import hashlib
    for relative,expected in READONLY.items():
        path=Path(root)/PROJECT/relative
        if not path.is_file() or any(x.is_symlink() for x in (path,*path.parents)) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('fixed dialog provider prerequisite changed: '+relative)
    return READONLY

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    prerequisites(args.source_root.resolve())
