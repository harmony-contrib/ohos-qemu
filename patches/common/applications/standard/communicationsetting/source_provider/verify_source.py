#!/usr/bin/env python3
"""Exact fixed production source; real build/package/QEMU remain mandatory."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/call'
REVISION = '8383e1930ffb28b512929b913eadf266a4e3a55a'
FILES = (('CommunicationSetting/BUILD.gn', None, '3815c5c8245346dc5a1d0c07495bd6b5f7cf30a85cf35d38702f921dca2bfd6f'), ('CommunicationSetting/build-profile.json5', '3c50a82fc6e1d21eb17794de13500091e82b8afd1380be17bc0dfa79ccbdcd82', '2735d30c2434824f7688bd0c17617d23f4cdbc58756d4498b9ad301b541d74db'), ('CommunicationSetting/entry/src/main/ets/entryability/NetAccessPolicyUIExtension.ets', 'e3fa862f3c0bb08387601d7061aa00669778b502dd9247da46cec4af52c6c2a7', '00f57217294ad37993473e4a90e0993e9d9474825c89e4a89a9e1e8b3a9d2c23'), ('CommunicationSetting/entry/src/main/ets/pages/NetAccessPolicyDiagPage.ets', '961ac8a183f6be2ef2e3f35ee5e4e2072abbb1feb0728c29f3733e8d0fba19e0', '1a61c0d782177150ec684812e1828c15d38a88700aee50112b9642b3272e1576'), ('CommunicationSetting/entry/src/main/module.json5', 'daa669bd49ba526718aaa437a8fd44d80fbf861412f52338c88a10d08409ee72', '205fa3f55be111d36f0be277b9d1ed1b367a218d46eb500e8874bb5ceeb5a759'), ('CommunicationSetting/hvigor/hvigor-config.json5', '2fe952bc1412b5a904f7ffdae94ab9a4989e33fdfb7977ea929bd1a04358aecb', '322eaec60323114fe17400b00062d98b8ad23ca6f6310651ffc9756622d5869f'), ('CommunicationSetting/oh-package.json5', 'd4ae2f8832ae4c301968d96e89227ea52a4e7ad0d28f9b12c5ae559cc825b6ee', '9400f2de5cfe9f1624a8eb9f6f7cb74ec0ee9de2c020a428fe57ab621a6a2d41'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

READONLY = {'CommunicationSetting/AppScope/app.json5': '2f11488fc7d2d30cdd9c12b81c8601d303ad9a6c8942af215a224a4b600ddf54', 'CommunicationSetting/entry/build-profile.json5': '59fbe774864a22ec3b84d7c3b83d802ab103c79541f72a9938a98c7b3ed8c93b', 'CommunicationSetting/entry/oh-package.json5': 'c3ab4a8122311d19a890ceb7d6717fd06e1e2f6ab496aa1fc61e98a95a50a7cc', 'CommunicationSetting/entry/src/main/ets/util/DeviceUtil.ets': 'b5089426592e835486716f8d1b8cdf5f26f2e3647c7a7aa74d8c6bb4b50946b1'}

def prerequisites(root):
    import hashlib
    for relative, expected in READONLY.items():
        path=Path(root)/PROJECT/relative
        if not path.is_file() or any(p.is_symlink() for p in (path,*path.parents)) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('fixed production prerequisite changed: '+relative)
    return READONLY

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    prerequisites(args.source_root.resolve())
