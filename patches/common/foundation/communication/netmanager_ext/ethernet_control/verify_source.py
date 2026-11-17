"""Exact pinned Ethernet control source; not kernel/IPC/guest acceptance."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('services/ethernetmanager/src/ethernet_management.cpp',
     '43758fac23b2cfedb44588b4e5ecc07fef593ecfa04bf5112c6868cd06e280ef',
     'fb127244d9b536d59c262e7724e885343d281aa5046e0f17d1e5bd4729eaab5f'),
    ('services/ethernetmanager/include/ethernet_management.h',
     'a2dfc7b6f1237178742cc342d94a4f7a2eefb8829c3acd01cd4149b8d4b4d781',
     '3c7bfd98adc288e56e60f9c348f6fc1e184ddeb82cd70dcf35f464573b8f2936'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
