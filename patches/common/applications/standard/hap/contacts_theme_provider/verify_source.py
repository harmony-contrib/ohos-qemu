from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/hap'
REVISION='f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
FILES=(('BUILD.gn','d35f62e7f04aee85749b3ab9c7ba25261ddf2fa71395d0b829e0e71cef40f18b','73940797880d284873c91b2c88eae074aa85beac4fb8a9b5f1b334a31ffbe2f5'),)
def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)
