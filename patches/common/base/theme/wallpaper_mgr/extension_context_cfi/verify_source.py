#!/usr/bin/env python3
"""Fix com.ohos.wallpaper CFI SIGABRT loop by wrapping std::weak_ptr<Context>."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/theme/wallpaper_mgr'
REVISION = '42256bdeaa504da4ae4d038c24d42a4601e3a6cf'
FILES = (
    ('frameworks/kits/extension/src/js_wallpaper_extension_ability.cpp',
     '1f55200232f9012af90d32c3833655869cf8bd77080d2d250629cba7354d2bfa',
     '7846f4d8ce2bed12ccff8dadb18e1548458781124444f8de7f4e9103534d5af7'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
