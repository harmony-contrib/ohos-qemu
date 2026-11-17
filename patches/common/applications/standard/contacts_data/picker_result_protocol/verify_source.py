#!/usr/bin/env python3
"""Require the exact sync_mode predecessor or complete picker protocol final state."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/contacts_data'
REVISION = 'c73bd27daa3fcd8ed6099b17cbffbd7021e3873e'
FILES = (
    ('contacts/src/contact.js', '37a2627df3602a73c71b0568c0b163333f6db404a7aa9dd2ffa3015353f434f2', 'ae22907681082d8f7ccdaeaa81ee80d3da31114353bf2b167a060c2cf946b759'),
    ('contacts/src/contacts_api.cpp', '1e695abbda171e24ba756d670f635ff5ee3cad748b5cdfe05a29f14002d85303', 'e4d8a123de6ba2e943c6fda5e0258960376998f54fd61565e81e8b224beeb4d8'),
    ('contacts/src/contacts_napi_utils.cpp', '813b4d673a83344373fb69d70139d3f196ace321b8b67b2802e78d9ac65dd32c', 'ffd0180bf9632f6adc7fff2721d865446f27c65a3013f5b09b01433b484d4358'),
    ('contacts/include/contacts_napi_utils.h', '80bb097276ecbf229a5601c41587d1bfb0d01f52763c07db5edfce21e881c657', '3066f698312815e0bbfba4d71fb54e49d589641cd4947ba98859092dc8b1efc8'),
    ('contacts/include/contact_picker_protocol.h', None, '722ead111840a4ecdc0336eec4511fa43790228f9decb2155bee08a5a2fa60c1'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
