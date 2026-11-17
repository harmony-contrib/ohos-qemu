#!/usr/bin/env python3
"""Fixed production source adaptation; actual SDK/build/QEMU remain pending."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'base/security/certificate_manager'
REVISION = '57bd41128a07c5289987cf98e04dfc66421029a6'
FILES = (('interfaces/kits/napi/src/dialog/cm_napi_open_uninstall_dialog.cpp', '1931f645c9570fbbcab7730bfa980bdc0be3a30cd0ee5f4dfffa064fcf8304e6', 'a4e0a8cd8395026fe98741fe10fdcb733e55c6a84eddd209a1fdd46cb94de830'),)
CRLF_FILES = ('base/security/certificate_manager/interfaces/kits/napi/src/dialog/cm_napi_open_uninstall_dialog.cpp',)
READONLY = {'interfaces/kits/napi/include/dialog/cm_napi_open_dialog.h': '25e9625ac26b6189a5b4d6db807c5ca3a312b4b09e71085babc0565c4d19a506', 'interfaces/kits/napi/include/dialog/cm_napi_dialog_common.h': '7297636b04994bfc827273c2e9b5f88ab1766b0fb78fa62fa5e1550751f9758d', 'interfaces/kits/common/include/cm_dialog_api_common.h': '67f6d891d0464a3afce303d76357440684dbdccd3e2f0af0305a166b8b63c749', 'interfaces/innerkits/cert_manager_standard/main/include/cm_type.h': 'ff2f54aab6545bea34d9aafd36210e40bbd478ab9dfcfa98bcf508b0d15c3c08'}

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
