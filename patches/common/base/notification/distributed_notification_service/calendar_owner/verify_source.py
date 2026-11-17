#!/usr/bin/env python3
"""Pin the real reminder owner; root must require the complete viewer first."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'base/notification/distributed_notification_service'
REVISION = '08a878a934511503bca88d3d69c686cc283c198c'
FILES = (('services/reminder/include/reminder_calendar_share_table.h', 'c6c0f87369b1cf03ec006527fa602cd577be06900b7cd82c2446a4285bef2ff0', 'fe8c90a2d90140018f6c97f49b43e8a5cda47918a3b3f9231cb9d4b0224d1fc5'), ('services/reminder/src/reminder_datashare_helper.cpp', '1dd61955f425eb6ab49b1c59506b9af4f7f64d3adbbe20f17b5deea85389c5cf', '12c4a44b7f3067b0ba776c7b3c14029ef048c7a6e32e11d28dcf07a03f9e24ed'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
