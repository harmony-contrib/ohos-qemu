#!/usr/bin/env python3
"""Exact pinned Settings source packaging; not a runtime capability claim."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (
    ('BUILD.gn', None, '6e2870d79724d8a57d8ea1f4c5e5d11a6a674c310a55b7f28c1aa43fbdefd788'),
    ('bundle.json', '7323b381982f8972876312ea7cb6e639968158a9a02d38fbc782c32053a5132b',
     'bb72dba04410b24a381dc716bfd816e1df79d44fc82010c8eb405d70d0361254'),
    ('build-profile.json5', '3cb753081c40409d1011cce590e89b2d2050e728459ac8c0c3686b9049ede2ec',
     'b294f8c2e7cad4132cc59cb7e5d5c58397b614284b80653b47c3c17ad1d3b79b'),
    ('native_api/build-profile.json5', '5d1a34dbf00752cb72bed5c6062a940855b493fb95cc8103ce625238334d25cf',
     '3959a9089919b4c477d605908e868c9e5fbab2bcded0b91fb8b706a38e68d439'),
    ('oh-package.json5', 'bf6da1096f7c8602dce726fcc614a8ec23905ee1751dc75b69b925092ea5b597',
     '1fd2d29e695adf34b8b582aaa76730f24f791ab36f19590e8afafc66dca3971e'),
    ('product/phone/oh-package.json5', 'f61651835ec6b7aa3779e02303944f51554e0fbd44bbfde7d7df407faf779a8d',
     'bc2d2960c1d3aeae31e7e831fea7d986134ba608d347d2fdbf2eb9572c83fdea'),
    ('feature/uikit/oh-package.json5', 'c6db2429eff9597f69bbaa969f2c9c3a36c6e5bfda3eaac79ce92e4239c55dcb',
     '762bd3cc3b98bf41b752f928d9eee9aee7385365a0df4266a17c7122c873d0f6'),
    ('hvigor/hvigor-config.json5', 'a8b31524b98b145e5da698f22119b8436497217022ada82ff2883f2352dac9a8',
     '62bc74f13ae070fc8bd2df03abfe93ba080f552091ef0b18803d100291df07c0'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
