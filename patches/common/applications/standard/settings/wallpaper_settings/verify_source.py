#!/usr/bin/env python3
"""Require the complete fixed-source wallpaper component; no runtime claim."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (('feature/theme/src/main/ets/ThemeSettings.ets', '10fdd330cd3958d3e15819d2d62c7ae659a1e4b3293fa059a8c29e9cacfe0dcf', '3bf743568c5dcb454d511c93e96204dd8dce90f80b346dbb4e0bbdf56e857f8a'), ('feature/theme/src/main/ets/WallpaperPicker.ets', '2d848fe7c01a166526ec99bc5ae3f7a461eae84b9f1f04aabb040fa1753e6530', '7b2f8faa71e20ed238c5f9a831fe478362b1b343a7dd21836684d1272557c3be'), ('feature/theme/src/main/ets/utils/WallpaperSelectionController.ets', None, '1bbf47e6f91fd4c3048d1fabbfaa7e374a3e8ca19d72b7ae274eea2dda1a9d6b'), ('feature/theme/src/main/resources/base/element/string.json', '2767b757ebf4bed992d49b7cbf8316dd0a542545eacd15bfda86e213a60e3395', '802ae7d5fc23d4baf2aa7fef33128b18ee0632803705c94d02f4e5309752b4f7'), ('feature/theme/src/main/resources/zh_CN/element/string.json', 'cd8cc6d0a9f9832c070314b7d8d071620d7d44b106b22973c978c5e9cfc497ed', '2c6b1fac6b33ee867750638daece46cc4aa14865295bdc93cd350735b2719198'), ('product/phone/src/main/module.json5', 'fc6383796f603062cd0cba5e5078e28e3b567f95356d09d7014c2c27b52d9a62', 'ec1d3c1525d7298209346cb8f47715f781c1a6cc52b058cadef5e57d211db6bf'))


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
