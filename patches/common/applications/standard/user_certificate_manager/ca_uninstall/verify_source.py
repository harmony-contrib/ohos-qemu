#!/usr/bin/env python3
"""Fixed production source adaptation; actual SDK/build/QEMU remain pending."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/user_certificate_manager'
REVISION = '0acf067c28bc3957759d288835762ee0209e9fbe'
FILES = (('BUILD.gn', '3bf41bc2c6918d214515c9b6b92a8428aac48bfee7d8584c8e9c8c7545be61a8', '603dae204b42911332ee09d514f01a65cc9aeed5c6b19dd4acfa9bdb415ff8a7'), ('build-profile.json5', '4a91996fda0db90e43e2ac18b655dc4500eea82b5751ae741c4d64cb2c016a46', '011b364335d48a7fb1413aad40419265f040cf34bcd17948076027a42d938a06'), ('certmanager/src/main/ets/MainAbility/CertPickerUiExtAbility.ets', 'cf91f64cf0bf2ea07abe6fb1b606f4b33fcd041462b4092a9ae017629916afbe', 'acb3c31862635adb4288b399f7d1d051db100c04bf8ff9387597daf5b3d160a0'), ('certmanager/src/main/ets/model/CheckUserAuthModel.ets', '1ee6bc26d0eb1302ff50e6aefc54b8314d7e0795c2e5e326ccc209feb602a9aa', 'b67d15190a97973ac1ed32da4388e985785352f7a04650014c974af09a4f39bf'), ('certmanager/src/main/ets/pages/CertificateUninstallPage.ets', None, '3b86ce2e0fbd463f2671abbe6b6189a7dcca5bdfa7caa8700e3d717f782e268f'), ('certmanager/src/main/resources/base/element/ca_uninstall.json', None, '4d72151056dd1504bfac0c62e9243cb37ddd7e64cfbbe656b827c2cb6d99beb6'), ('certmanager/src/main/resources/base/profile/main_pages.json', '7377fa8c1594c0610ce17c8d4c90ad2e15706980773c450bd19c633fb0cbb828', 'e7db52c37eb8c75c2e121aaf0273c628bd40092d684817c898b9f96b090744f6'), ('certmanager/src/main/resources/en_US/element/ca_uninstall.json', None, '6c8cdc785a7e9dc56589357f273e47dff8a461d73b562ee7d671917467fe839e'), ('oh-package.json5', 'b9f69b16251d5d02d63f34289578840bb1d4ee5cfe2e7fcbf9257ec47a2f4932', 'f2d992dc2e19dbec91da5b61dfb73012b83665ac77eb281e59343e46f277fc62'))
CRLF_FILES = ('applications/standard/user_certificate_manager/build-profile.json5', 'applications/standard/user_certificate_manager/certmanager/src/main/ets/model/CheckUserAuthModel.ets', 'applications/standard/user_certificate_manager/oh-package.json5')
READONLY = {'AppScope/app.json5': '7af3ff744b032d6086df0f79db65a75f415fd3dc3f1f8fe7009590ef4b963580', 'certmanager/src/main/module.json5': '957362f7abd60ba86a75c99c9ed25d54cd16764f42262f613720b2328f51424a', 'certmanager/src/main/ets/model/CertMangerModel.ets': 'e0f7a02fb59028d74d68e97c0557e24df2cb390440bca2f9275c54c5a3e29195', 'certmanager/src/main/ets/model/CertManagerVo/CertInfoVo.ets': 'a8c640b5c2beddab784837a7004d54d15c315a74375eee5a1c4a14736663ffa3', 'certmanager/src/main/ets/pages/CertificateInstallPage.ets': '3b2efd4c25c146d5a60a574b0a4e3fd64b07b8ed554ee6221269c36e551158ae', 'hvigor/hvigor-config.json5': 'd40943427756aef7f8b1659d5e261bdf5b6875a44978e68211033987b65008bc', 'bundle.json': '4bca6164c51bb788dacda45168624a22849264cfe186fb44a67b3b7fc2be1e11'}

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
