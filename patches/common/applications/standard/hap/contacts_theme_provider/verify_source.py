from pathlib import Path
import hashlib
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/hap'
REVISION='f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
FILES=(('BUILD.gn','d35f62e7f04aee85749b3ab9c7ba25261ddf2fa71395d0b829e0e71cef40f18b','73940797880d284873c91b2c88eae074aa85beac4fb8a9b5f1b334a31ffbe2f5'),)
def validate(root,require_patched=False):
    files=FILES
    if hashlib.sha256((Path(root)/PROJECT/'BUILD.gn').read_bytes()).hexdigest()=='d25f524ae8b82607c04ddd86b485b3940b40af14376cbf9c3d23f15d6655a83c':
        files=(('BUILD.gn',FILES[0][1],'d25f524ae8b82607c04ddd86b485b3940b40af14376cbf9c3d23f15d6655a83c'),)
    return validate_component(root,PROJECT,REVISION,files,require_patched)
