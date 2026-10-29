"""Load the NumberIdentity bundle native provider before DataShare extension creation."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
FILES = (('frameworks/native/appkit/app/main_thread.cpp', 'ea42b93089e536e6ac8fea3dacadea9f3c93ca5fe0edd67f39cdc83a5bef2b2c', '3680fd9fb200b103a87bc01d530e0c68deadfac843825354adb4182763618c1e'),)
COMPONENT = Path(__file__).resolve().parent
PATCH = '0001-load-numberidentity-bundle-native-provider-library.patch'
PATCH_SHA256 = '23f53c5c4b2fa9ac840edd0140ee06790c46f388853f87d8d101be1f57f7c154'
SCHEMA = 'number-identity-native-loader382/v1'


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
