#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = "foundation/communication/netmanager_base"
REVISION = "9831989d54f490d046a632ab13d309580d2fa710"
FILES = [
    ("utils/data_share/include/net_datashare_utils.h", "c106f6b8c84ae6dd6e9bb2480d7022f2386da85f7f996d69309e8bd85ffb9ed7", "ce7858878d1351bcb2943ad579a3138b1e50fcd2af9ce0250a9c8482db8ff01b"),
    ("utils/data_share/include/net_datashare_utils_iface.h", "f1a3187061b4b17faaca3d857dc6c02e52809049e1fd375262e34b645efcd6bd", "d4d67c14abe02dfaab376213c55ccc71453088a78d456d81f3665c3bf3201d03"),
    ("utils/data_share/src/net_datashare_utils_iface.cpp", "0af9b85f0b0339fd50ec16f1ffeab8e4f426b104bf5117cd68577602fa9a2915", "426b45e9ced53b12aaa2f3575d446d93dde5062442550f3c0ecbb0430871770f"),
    ("utils/data_share/src/net_datashare_utils.cpp", "93a487361273d9753de7f9c4d1e40991959ab45787cb9a361124e6e8245f003c", "bdc2ff5c30ade6dde346e76a78ad870d032128777fd8da1d1d9ae68abc595a1c"),
]

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
