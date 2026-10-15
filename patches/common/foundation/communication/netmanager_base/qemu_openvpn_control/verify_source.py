"""Exact fixed-source QEMU OpenVPN control candidate; runtime acceptance pending."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_base'
REVISION = '9831989d54f490d046a632ab13d309580d2fa710'
FILES = (('services/netmanagernative/BUILD.gn', '76487f617bc760c021d974a69ec35a7d37f8241a4bd83a6485e55185ccbccab8', '7358e7778ead53edeab9834f9288e5b9b873dddf01fd44ce3730d3ed7c744531'), ('services/netmanagernative/src/netsys/system_vpn_wrapper.cpp', 'ad840342174e05ccbbb9e2d73a49c97314ac4241ca3428c854f48eb0ab07ed1b', 'a9190d3a9fee527a6ff046aa9e54c1f44e0783534caa7830e9eea565a88cd140'))
CRLF_FILES = ()

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
