#!/usr/bin/env python3
"""Fail closed on drift or mixed business lifecycle patches."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/contacts'
REVISION = '65de33df8d6d7aaa5797a5625ed0e5938e5cb050'
FILES = (
    ('entry/src/main/ets/uiExtentionAbility/PickerSession.ets', None, '39be22e9c527e940529a0a662013b579f0545e6f23893fbd634c30599eb0cbb4'),
    ('entry/src/main/ets/uiExtentionAbility/ContactUiExtentionAbility.ets', '38bbad6f2b901dc35d9962f9758f04e0fc0c0cf6ff8182196053d68501be05a6', '2ddb5963c0d42929cbc2af9f9676294435d4098fe43e12ae5b817282bb5cf4e4'),
    ('entry/src/main/ets/workers/base/WorkerWrapper.ets', '33393aba92382009b567a98db5d226869e15657a4c0ca95a3b6f439424b525e4', '1b6adb88192ade5cc160098956bd44dd5874fc7ddbe4f780e95d8aa2f58ec3c2'),
    ('entry/src/main/ets/presenter/contact/batchselectcontacts/ContactsPickerPresenter.ets', 'aa317b1b454e5b6a7de1e1cce20209f82679c5945337cae86c95e06fc7ae46ad', 'b1327fb0c6f3872cb16ec84785aad01a9795bb0a4045b9725a4e38d790c25f51'),
    ('entry/src/main/ets/pages/contacts/batchselectcontacts/ContactsPickerPage.ets', '8c2ca9a6d30ddbd76473acdda98f46f135f3b8c5bcb93e0a449a6b2e0c34ff27', '1d5a8c4135ee67e08fc2bf6ad3461ce25db59c19d39fded7ac848182ba1032b8'),
    ('entry/src/main/ets/pages/ContactUiExtentionIndex.ets', '240402171cf74d1782fd6e401e1d52f625df71944f29716d9190a2765e4e8503', '32dc4a208dc5dff759ea68f9d7cf3a853209ee2dfa65d2243d1acd64ad2b525d'),
)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
