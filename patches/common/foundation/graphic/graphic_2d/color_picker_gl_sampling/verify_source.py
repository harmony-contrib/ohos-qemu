"""Exact Release GL sampling source; not runtime acceptance."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/graphic/graphic_2d'
REVISION = '81cc9ca9509bccd86c435064136fe45591d29eeb'
FILES = (('rosen/modules/render_service_base/src/feature/color_picker/rs_color_picker_utils.cpp', '8d6cd40eb9ee25d68d5775b9468aefeed79ed67d2e9238d88d1267c19b5ca32c', 'd9339407358117e6dc50a72837277320566bf32236ed4579be443abd7615a60c'), ('rosen/modules/render_service_base/src/drawable/rs_property_drawable_utils.cpp', '2b7b6878d2724ee340e64994b2473f3a5e730734402c44eefcb7655a8fe3a3c1', '2389495362d4cff91cf6e77b7fe9aea605a2be327c1717d4603cd912abe00649'))


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
