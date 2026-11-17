"""Exact successor of the complete RS async identity/object transport stack."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/graphic/graphic_2d'
REVISION = '81cc9ca9509bccd86c435064136fe45591d29eeb'
FILES = (('rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp',
          '228baf8e2271551f22494fbf1535289fffd77af5da7cdf90f3dfa1ce98d92abb',
          'ab3f257b5afb0e96e485948aeeff89affe3a87fe4f65101d1f259b4c48fea3b6'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
