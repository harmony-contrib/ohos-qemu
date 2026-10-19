"""Exact NumberIdentity native DataShare routing in the Hvigor manifest."""
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
 ('entry/src/main/module.json5', '9b0a2d769cf812b7bd0bc8b1e9e674ccc0fc174762417b138442bfeccc06d8b0', '42ff53888c007c5ba76a4462c05a0b10d196692b484f25897d3db0602d47d1e6'),
)
COMPONENT = Path(__file__).resolve().parent
PATCH = '0001-preserve-native-datashare-routing-in-hvigor-manifest.patch'
PATCH_SHA256 = '3aa075539a75849fc248f83bde5b6aaa2050a4ed98ebc8073154357a81f4db80'


def validate(root, require_patched=False):
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches) != 1 or patches[0].name != PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest() != PATCH_SHA256:
        raise ValueError('exact native-manifest patch stack required')
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args(argv)
    result = validate(args.source_root, args.require_patched)
    print(json.dumps({'scope':'native DataShare manifest exact source only', 'patched':result, 'compiled':False,
                      'cloud_or_aggregate_provider_passed':False, 'guest_pass':False}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
