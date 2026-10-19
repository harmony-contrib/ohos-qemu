"""Exact paired GN source states for the actual OHOS UIExtension carrier."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('frameworks/core/components_ng/components.gni', '40eeb7262448f89e65b18c776ae8ffda7330ed9589898585eabfddb1d63d7f76', 'b845a254530491f05d8a8081a5f329fd6cd24a551c77f6f9c9cfeba0c43e1f8f'),
    ('build/BUILD.gn', 'bd4b450a591a8110ec519ad90b29ea7cc44834a173b7e3de8c0403954f1faae9', '7c3b56fc8c144a184c1328a5400f58f5e1c908c927128a6b10956aaa73f64b14'),
)
PATCH = '0001-enable-real-ui-extension-carrier-cfi-and-final-dso.patch'
PATCH_SHA256 = 'e033023a190cdb38a257c55f16dbcb29da80a5e00018f332829a0d64be305ebb'
COMPONENT = Path(__file__).resolve().parent


def unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate native CFI source metadata')
        result[name] = value
    return result


def metadata():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink() or not path.is_file():
        raise ValueError('actual native CFI source manifest required')
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    expected = dict(schema='native-ui-extension-identity-cfi-source/v1', project=PROJECT, revision=REVISION,
        files=[dict(relative=name, original_sha256=old, final_sha256=new) for name, old, new in FILES],
        patch=PATCH, patch_sha256=PATCH_SHA256,
        scope='actual product GN sanitizer configuration; original query and receipt are unchanged',
        actual_gn_compile_solink_runtime_pending=True, first_artifact_behavior_gate_passed=False)
    if value != expected:
        raise ValueError('native CFI whole-file metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches) != 1 or patches[0].name != PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest() != PATCH_SHA256:
        raise ValueError('native CFI patch stack differs')
    return value


def validate(root, require_patched=False):
    metadata()
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args(argv)
    patched = validate(args.source_root, require_patched=args.require_patched)
    print(json.dumps(dict(scope='exact paired product GN source states only', patched=patched,
                          compiled=False, runtime_passed=False, first_artifact_behavior_gate_passed=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
