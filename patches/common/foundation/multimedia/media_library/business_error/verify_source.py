"""Exact SDK numeric errors, with first pending validation error preserved."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (
    ('frameworks/js/src/napi_error.cpp',
     '494db603b607f0cc8da8f861f24147141c2cbefe15780b72057e4f49cc45abab',
     '0dd1b17bfbcca6c27c7a0034bf12c1d2e0d60d14f331370a4d8d589300ee80b7'),
    ('frameworks/js/src/medialibrary_napi_utils.cpp',
     '7537d517c8239f30ad0ee6e21c53327b2b4d1c4a66d5bf6418baabe0308a6414',
     'b2bb7472200313e07a162a4b0cfc18d2128733aa5c8b05e5e2cb9396f7177a8a'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
