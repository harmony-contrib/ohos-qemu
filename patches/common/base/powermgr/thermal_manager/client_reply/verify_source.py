#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/powermgr/thermal_manager'
REVISION = 'dbba4e1d77e4bc2c8ff7e5a0796a36e388277461'
FILES = [
    ('frameworks/native/thermal_mgr_client.cpp',
     '857cf07933cb866d8f569587da55c18d897cbed8dfafb4acba1cacde5304ad2f',
     '4ca722372528c6455eebe229e265c222a04fe9a6acc689b60e5122ec80b52dd6'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
