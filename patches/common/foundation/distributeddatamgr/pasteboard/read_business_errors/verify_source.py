"""Exact current Pasteboard read BusinessError shape, preserving legacy helpers."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/distributeddatamgr/pasteboard'
REVISION = '6909fc2dc334c03afaf1e7c131d0f82639393a4d'
FILES = (('interfaces/kits/napi/src/napi_systempasteboard.cpp', '3bca4fd436922e8b7ed606592be61364656cd44089591faace552744d38610ad', '8005f2a409e8cf3e33ca1266e847ab94a4c6d050bac6a06915dbb19bbb6ed822'), ('interfaces/kits/napi/src/async_call.cpp', '0d1234cfabef38d95716fba3ac105fc70dac97befbd34027f312a35d16544030', '2521fb66dcd0d625ed8e1089913404d663d863e27791766ac05c0c1634f6235b'), ('interfaces/kits/napi/include/async_call.h', 'd730a5caf0cc98c3582f6cde45dc00930d10f31f7bdccdceffcc9feff7c38ac9', 'ee664a649eaa12a53e0d656b50c04c98c6d93418fe6d7fb5804d41d4156f9048'))

def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)
