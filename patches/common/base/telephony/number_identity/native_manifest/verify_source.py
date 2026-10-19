"""Restore the official schema-valid NumberIdentity Hvigor manifest."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/telephony/number_identity'
REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
FILES = (('entry/src/main/module.json5', '42ff53888c007c5ba76a4462c05a0b10d196692b484f25897d3db0602d47d1e6', '9b0a2d769cf812b7bd0bc8b1e9e674ccc0fc174762417b138442bfeccc06d8b0'),)
COMPONENT = Path(__file__).resolve().parent
PATCH = '0001-restore-schema-valid-native-provider-module.patch'
PATCH_SHA256 = '8131b9830ddad5e762f79a5a949261b7f55837b4225be41dd5f06ef488bb9bb1'
SCHEMA = 'number-identity-hvigor-native-manifest382/v1'


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate NumberIdentity component metadata key')
        value[key] = item
    return value


def metadata():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular NumberIdentity component metadata required')
    value = json.loads(path.read_text(), object_pairs_hook=_unique)
    expected = dict(schema=SCHEMA, project=PROJECT, revision=REVISION,
                    files=[list(item) for item in FILES], patch=PATCH,
                    patch_sha256=PATCH_SHA256, source_only=True, build_or_guest_pass=False)
    if value != expected:
        raise ValueError('NumberIdentity exact component metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if (len(patches) != 1 or patches[0].name != PATCH or patches[0].is_symlink()
            or hashlib.sha256(patches[0].read_bytes()).hexdigest() != PATCH_SHA256):
        raise ValueError('exact NumberIdentity component patch stack required')
    return value


def validate(root, require_patched=False):
    metadata()
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args(argv)
    result = validate(args.source_root, args.require_patched)
    print(json.dumps({'scope': 'NumberIdentity exact source component only',
                      'patched': result, 'compiled': False,
                      'cloud_or_aggregate_provider_passed': False, 'guest_pass': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
