"""Exact actual-E whole-file carrier states; unknown/partial bytes fail closed."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
FILES = (('services/abilitymgr/src/extension_record/base_extension_record.cpp', 'f43d3d195b06294314428afe256afe94f5bba71e625ada8f64c9a09016ca81c5', '0486008216b98724f8a5087c0062c696241af4e69639b545f995cd91480714e2'),)
PATCH = '0001-append-real-ui-extension-session-to-existing-ams-dump.patch'
PATCH_SHA256 = '1e131baec4fe39e2b30620083a6ea6722eb4e26228db2220cd6f7ec1892a7bbd'
COMPONENT = Path(__file__).resolve().parent


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate native identity source metadata')
        result[key] = value
    return result


def metadata():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink() or not path.is_file(): raise ValueError('owned native identity source manifest required')
    value = json.loads(path.read_text(), object_pairs_hook=_unique)
    expected = dict(schema='native-ui-extension-identity-source/v1',
        role='ams', project=PROJECT, revision=REVISION, relative=FILES[0][0],
        source_path=PROJECT+'/'+FILES[0][0], original_sha256=FILES[0][1], final_sha256=FILES[0][2],
        component='patches/common/foundation/ability/ability_runtime/ui_extension_identity_diagnostics', patch=PATCH, patch_sha256=PATCH_SHA256)
    if value != expected: raise ValueError('native identity whole-file metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches) != 1 or patches[0].name != PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest() != PATCH_SHA256:
        raise ValueError('native identity patch stack differs')
    return value


def validate(root, require_patched=False):
    metadata()
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
