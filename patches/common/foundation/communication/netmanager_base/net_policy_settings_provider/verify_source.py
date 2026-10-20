#!/usr/bin/env python3
"""Exact fixed production source; real build/package/QEMU remain mandatory."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_base'
REVISION = '9831989d54f490d046a632ab13d309580d2fa710'
FILES = (('frameworks/js/napi/netpolicy/src/show_app_net_policy_settings.cpp', '5ddbdd885f0c44935e2d6fb4fca3d7868d07422a841e3a4b7ced63894ca4dce1', 'ee2b6281d017fd1e6f59f61df6ad4b889059a040ca4519bfd190e36d05887142'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
