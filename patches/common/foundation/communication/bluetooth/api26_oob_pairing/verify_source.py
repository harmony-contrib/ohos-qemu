"""Exact API26 OOB entrypoint candidate, without claiming adapter support."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/bluetooth'
REVISION = '1727fa05c457f697f7cf80f290c82c663f1c3aab'
FILES = (('frameworks/js/napi/src/connection/napi_bluetooth_connection.cpp', 'f8897e5e26ecd69647a0cd43a736af4110ece8908bee8afbb70c46df61b7b159', '491a97b9d083a197b216965ada159da1824694e025fc0721421469f91fe9a5be'), ('frameworks/js/napi/src/connection/napi_bluetooth_connection.h', 'a053cc245420d5c4bf543275a62293b1f2200e5829ae756c1c45e8456f8d292c', '959e1d74021d9bacf0931b1318873e0cd0d6d3892f36ebd4655a269ca2eb7f6f'))

def validate(root, require_patched=False):
    try:
        return validate_component(root, PROJECT, REVISION, FILES, require_patched)
    except ValueError as original_error:
        import importlib.util
        spec = importlib.util.spec_from_file_location('api26_oob_validation_following',
            Path(__file__).resolve().parent.parent / 'api26_oob_validation/verify_source.py')
        following = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(following)
        try:
            following.validate(root, True)
            replacements = {name: final for name, _, final in following.FILES}
            expected = tuple((name, original, replacements.get(name, final)) for name, original, final in FILES)
            return validate_component(root, PROJECT, REVISION, expected, True)
        except (ValueError, FileNotFoundError):
            raise original_error
