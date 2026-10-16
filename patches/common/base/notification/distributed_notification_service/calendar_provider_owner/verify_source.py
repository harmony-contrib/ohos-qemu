"""The actual notification consumer must name the installed CalendarData provider."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

COMPONENT = Path(__file__).resolve().parent
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())
PROJECT = MANIFEST['project']
REVISION = MANIFEST['revision']
FILES = tuple((name, row['before_sha256'], row['after_sha256']) for name, row in MANIFEST['files'].items())


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
