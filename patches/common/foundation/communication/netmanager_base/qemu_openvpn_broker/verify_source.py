"""Exact private broker integration after the reviewed session/callback components."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_base'
REVISION = '9831989d54f490d046a632ab13d309580d2fa710'
FILES = (('services/netmanagernative/include/manager/multi_vpn_manager.h', '9f2e743c2fdcebf6e755ede2680980122afd72aaeb0b103bdbb37dde962561e9', '33f2563d6bdcdf76f1b1bf4c99eb0f088a47a23079a4711c0312c33133a82095'), ('services/netmanagernative/src/manager/multi_vpn_manager.cpp', '3a1e8af91265c7bb8c79279194e174db09dbc04fbf008f41551707f0910a80f1', 'd3de1f59d3de45305d92a605e800e07b8c584e70a7d3800d66c3ee737231346d'), ('services/netmanagernative/src/netsys/system_vpn_wrapper.cpp', 'a9190d3a9fee527a6ff046aa9e54c1f44e0783534caa7830e9eea565a88cd140', '54d3eb71cb6ca158d027d92a4b31ce43802dd0b2a214e9b02f9baac5c4a14943'))
CRLF_FILES = ()

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

def validate_preceding(root, files):
    validate(root, True)
    repaired = {name: final for name, _, final in FILES}
    expected = tuple((name, original, repaired.get(name, final)) for name, original, final in files)
    return validate_component(root, PROJECT, REVISION, expected, True)
