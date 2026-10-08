#!/usr/bin/env python3
"""Pin both image-model callback sources and the actual Rollup action inputs.

This repairs custom-model callback lifecycle only. It does not supply a default
AI model, restore missing dialog exports, or attest any guest UI behavior.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
PREFIX = 'advanced_ui_component/imageGeneratorDialog/'
FILES = (
    (PREFIX + 'interfaces/image_generator_dialog_project/general/utils/AIGenerateImpl.js',
     '1d9f54bfa7472dc435a2e3cd71fbfc61ceb63f1a5ee818172da07c79df03fb25',
     'd8160a43e12eeb6dc92a292e946379098aca1146ed60b7a397975e8c345964c2'),
    (PREFIX + 'source/image_generator_dialog_project/image_generator_dialog/src/main/ets/general/utils/AIGenerateImpl.ets',
     'dea90470b92a1d905b911a049a7172d3bcdff271b059e37807d890990cf94018',
     'a5f2df850909b705c84b661d8e91d3636a089e3ea29d0027fb5b0b69d4f7f061'),
    (PREFIX + 'interfaces/BUILD.gn',
     'd26beb09572fdd15a2d62447132225ee28df2dbf375ebca302cfb2c539ad2970',
     '6ff7ed9d628b01a987e8ab4d65d3974de03b51a0b565dad5005403b61a44c8a8'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
