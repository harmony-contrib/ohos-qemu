#!/usr/bin/env python3
"""Pinned, module-local luminance BusinessError repair; not runtime proof."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
BASE = 'interfaces/napi/kits/luminance_sampler/'
FILES = (
    (BASE + 'js_luminance_sampler.cpp',
     'accf9a2dbb24bf114a7496505fb41d169e5fe06ddf9a5f7651479d744b531b1f',
     '30801f0e921b94877ad1b5e857f1e0addfabf6be120d2daaf55dea0857758f46'),
    (BASE + 'sampler_instance.cpp',
     'a188f7e8d8503a8576f42f85e205b3915583ecfde2d98545dea0cc4cd7ca1226',
     '818b730a511e9ebadaff26abe83be08934710364fad87edf5d91a84ead61d248'),
    (BASE + 'luminance_error.h', None,
     '6156fa134d30fb83bb888adb03260aea07fe179fde452162b8d0ce3ff38aa345'),
)
CRLF_FILES = tuple(PROJECT + '/' + entry[0] for entry in FILES[:2])

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
