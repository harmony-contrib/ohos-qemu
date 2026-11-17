"""Exact pinned ResultSet index, empty-result and close boundary repair."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (
    ('frameworks/js/src/result_set_napi.cpp',
     'ba01a69532722f187ba980dcf9458fa29fcbd5a124acfca0b4899f7779587b99',
     '338f1438f457550a9292186ac9d0cf1276250977b5012c26256d19a2255c4ac8'),
)
CRLF_FILES = (PROJECT + '/frameworks/js/src/result_set_napi.cpp',)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
