"""Preserve GN-produced NumberIdentity DSO bytes through Hvigor packaging."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/telephony/number_identity'
REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
FILES = (('entry/build-profile.json5', '3ecb8b166df73aa2ff50bdc1d8974d4dc3cc6493aad7d71941d00edd0440c01a', 'bd223a25fb30f98b5772abe2c575e62ff87f20a2fe42b24c8604e2cc64c51ea7'),)
COMPONENT = Path(__file__).resolve().parent
PATCH = '0001-preserve-gn-native-library-bytes-during-hap-packaging.patch'
PATCH_SHA256 = '6dc2c97e3ba16833fd7b7849e7ab37e33e189e1e27e7881fa44daf09b82c6f9d'
SCHEMA = 'number-identity-native-package-identity382/v1'


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
