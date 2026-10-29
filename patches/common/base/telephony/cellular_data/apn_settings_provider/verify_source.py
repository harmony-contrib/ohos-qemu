#!/usr/bin/env python3
"""Fixed production source adaptation; actual SDK/build/QEMU remain pending."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'base/telephony/cellular_data'
REVISION = 'a0a56af15fe15d27494af99546cf3d7da23ac93f'
FILES = (('frameworks/js/napi/src/show_system_apn_settings.cpp', 'c96dd3b3c71bbe11607eecd92f74ba76c7692bfadbd99a9068ebef81b970edb3', '27f390bf4c4e7eac054b7899f7c1637a758eb64c5b9f401d46baad8114eb0090'),)
CRLF_FILES = ()
READONLY = {}

def validate(root, require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)

def prerequisites(root):
    import hashlib
    for relative,expected in READONLY.items():
        path=Path(root)/PROJECT/relative
        if not path.is_file() or any(x.is_symlink() for x in (path,*path.parents)) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('fixed dialog provider prerequisite changed: '+relative)
    return READONLY

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    prerequisites(args.source_root.resolve())
