"""Forward the actual Release native ResultSet through the public facade."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (('frameworks/js/src/photoaccesshelperinf.js',
    '7843fe2799ab30bb78aae887196b06bcb96471cdc9c6bb0fb5017aab772bcce2',
    '2b0cbaa4c727061697794e9ade94cb98c6cabe3d68c7aa5a49956ff33f882f26'),)

def validate(root, require_patched=False):
    try:
        return validate_component(root, PROJECT, REVISION,
            ((FILES[0][0], "7108e690526019093c562302afb8d2b41cfefe064bffb555a9da4d0180e32682", "7108e690526019093c562302afb8d2b41cfefe064bffb555a9da4d0180e32682"),), require_patched=True)
    except ValueError:
        pass
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
