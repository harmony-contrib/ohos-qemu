#!/usr/bin/env python3
"""Stop an aborted hover cycle without a synthetic cancellation callback."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('frameworks/core/components_ng/manager/drag_drop/drag_drop_spring_loading/drag_drop_spring_loading_state_machine.h',
     '9bee29d44270e60f3b520f5e125b973d18edf2e0518efdad9529b8e3744c75e5',
     '2686cb853430b21e28a76c14b5ab98f44810a757ea67a682bd56822f565ab846'),
    ('frameworks/core/components_ng/manager/drag_drop/drag_drop_spring_loading/drag_drop_spring_loading_state_begin.cpp',
     'a3082749b79cf5378977b4a60ba44f7b90eb017757961054c4223f447f362046',
     '3950ba6eccc43873b553ab2a706134a29dba57134dccf315913a852da9587ddb'),
    ('frameworks/core/components_ng/manager/drag_drop/drag_drop_spring_loading/drag_drop_spring_loading_state_update.cpp',
     '172c800b1740c7d58aa96cd85330a4d88a52b128a985a4466afac241ed667b5a',
     '50c9f4e9a05440ca3a3bbbe0f4b41ef423c277cc5b015c1c69c617acf4bb2d05'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
