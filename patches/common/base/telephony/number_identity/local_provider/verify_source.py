"""Exact public NumberIdentity local-provider source repair, not a cloud provider."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/telephony/number_identity'
REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
FILES = (
 ('BUILD.gn', '8de0e4476dfd172ab9ea355c91785595216cc8c9b95606d922d72cb983750a79', '90c9c001e6981a35e945732ce5439ea69a6b345d89d7420d2fc7eb8516012871'),
 ('number_mark/src/number_mark_ability.cpp', '8b55f6d0c5a2e5951063fad29070c94094f7d181011a89b5df7f307e2cc77a72', '781f7bb3b699ee933d32f1c9c790bcc4c9824a8375c5c5e1ac1472f273d52bb8'),
)
COMPONENT = Path(__file__).resolve().parent
PATCH = '0001-use-repository-profile-and-safe-local-mark-diagnostics.patch'
PATCH_SHA256 = 'e9af243e763df3a567d366ab13fee9f41c002df6c769da33dabf5f93bd0e2116'


def validate(root, require_patched=False):
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches) != 1 or patches[0].name != PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest() != PATCH_SHA256:
        raise ValueError('exact local-provider patch stack required')
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args(argv)
    result = validate(args.source_root, args.require_patched)
    print(json.dumps({'scope':'local-provider exact source only', 'patched':result, 'compiled':False,
                      'cloud_or_aggregate_provider_passed':False, 'guest_pass':False}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
