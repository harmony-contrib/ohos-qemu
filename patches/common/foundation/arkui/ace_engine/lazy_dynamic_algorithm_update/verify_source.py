"""Exact pinned LazyDynamicLayout algorithm update without pattern replacement."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (('frameworks/core/components_ng/pattern/dynamiclayout/lazy_dynamic_layout_model_ng.cpp', '3764aa91becc4306695c127e96bb8f8fd596c0f77ddf2e0f9d0c43736f57d8ea', '352ba2fea32c7bf185fdf2fad95605c0e63e94ce2856158967d5b8addf6a88b4'), ('frameworks/core/components_ng/pattern/dynamiclayout/lazy_dynamic_layout_pattern.cpp', '40f8170e4834f6b0d68bf011aa0dec6587f606f651f5c94acf725861ddec2cf1', '3bf088d6e5d676fe5b149817afc6b3c324cc22ad37476d0c12f8ce9040fa87b9'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
