"""Exact actual-E whole-file carrier states; unknown/partial bytes fail closed."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (('frameworks/core/components_ng/pattern/ui_extension/ui_extension_component/ui_extension_pattern.cpp', '7266f8728437bce6b42043f70733829f548aaf63857cf34a4e38cb536db62b6f', '1e34022836db60588e081edc2fbcc9450cef146bda609365920092d3062e2145'),)
PATCH = '0001-append-real-session-identity-to-existing-native-dump.patch'
PATCH_SHA256 = '67d9b56aa9af38ea267f4c86e0790aea39a18c13d4453344da30a9cae53e9221'
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
        role='arkui', project=PROJECT, revision=REVISION, relative=FILES[0][0],
        source_path=PROJECT+'/'+FILES[0][0], original_sha256=FILES[0][1], final_sha256=FILES[0][2],
        component='patches/common/foundation/arkui/ace_engine/ui_extension_identity_diagnostics', patch=PATCH, patch_sha256=PATCH_SHA256)
    if value != expected: raise ValueError('native identity whole-file metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches) != 1 or patches[0].name != PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest() != PATCH_SHA256:
        raise ValueError('native identity patch stack differs')
    return value


def validate(root, require_patched=False):
    metadata()
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def validate_batch(root, require_patched=False):
    """Root calls before both applies and again before any CFI/package work.

    Single-component apply entries remain independently replayable. This batch
    guard rejects cross-project mixed deployment states; an in-progress apply
    prefix is never accepted as a build-ready native identity carrier.
    """
    other = COMPONENT.parents[2] / 'ability/ability_runtime/ui_extension_identity_diagnostics/verify_source.py'
    if other.is_symlink() or not other.is_file(): raise ValueError('actual paired AMS identity component required')
    spec = importlib.util.spec_from_file_location('actual_paired_ams_native_identity', other)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    left = validate(root); right = module.validate(root)
    if left != right: raise ValueError('mixed ArkUI/AMS native identity batch; preserve source')
    if require_patched and not left: raise ValueError('both native identity carriers must be final before build')
    return left
