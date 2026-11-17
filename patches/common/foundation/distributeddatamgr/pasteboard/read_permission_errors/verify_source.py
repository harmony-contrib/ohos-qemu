"""Exact public Pasteboard read permission error propagation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/distributeddatamgr/pasteboard'
REVISION = '6909fc2dc334c03afaf1e7c131d0f82639393a4d'
FILES = (('interfaces/kits/napi/src/napi_systempasteboard.cpp', '01332401c8d6116509d89f0d7a08377a490c400e500ff332c0a0ceca103e554f', '3bca4fd436922e8b7ed606592be61364656cd44089591faace552744d38610ad'),)

def validate(root, require_patched=False):
    # The exact later BusinessError repair retains this authorization branch.
    # All three successor files must match before skipping the parent patch.
    successor_files = (
        (FILES[0][0], '8005f2a409e8cf3e33ca1266e847ab94a4c6d050bac6a06915dbb19bbb6ed822',
         '8005f2a409e8cf3e33ca1266e847ab94a4c6d050bac6a06915dbb19bbb6ed822'),
        ('interfaces/kits/napi/src/async_call.cpp',
         '2521fb66dcd0d625ed8e1089913404d663d863e27791766ac05c0c1634f6235b',
         '2521fb66dcd0d625ed8e1089913404d663d863e27791766ac05c0c1634f6235b'),
        ('interfaces/kits/napi/include/async_call.h',
         'ee664a649eaa12a53e0d656b50c04c98c6d93418fe6d7fb5804d41d4156f9048',
         'ee664a649eaa12a53e0d656b50c04c98c6d93418fe6d7fb5804d41d4156f9048'),
    )
    try:
        return validate_component(root, PROJECT, REVISION, successor_files, require_patched=True)
    except ValueError:
        pass
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
