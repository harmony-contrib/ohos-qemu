#!/usr/bin/env python3
"""Pinned source composition; unknown edits fail before mutation."""
from pathlib import Path
import hashlib
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/hap'
REVISION = 'f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
FILES = (('BUILD.gn', '3c9db915d35742864f493c1c3f502314d43ebc85d6e79321e3647db25eb88df4', 'f53e1d7c537ec63ef5c7ebb37b16bcd4a95e1d4a8a17fe68a034b0d65955b9d2'),)
# Patch hunks retain exact CRLF bytes, including original no-final-newline cases.
CRLF_FILES = ()

def validate(root, require_patched=False):
    # Accept only the complete known MMS source-provider successor on replay.
    # Every other byte remains covered by the exact whole-file digest.
    files = FILES
    if hashlib.sha256((Path(root) / PROJECT / 'BUILD.gn').read_bytes()).hexdigest() == 'd35f62e7f04aee85749b3ab9c7ba25261ddf2fa71395d0b829e0e71cef40f18b':
        files = (('BUILD.gn', FILES[0][1], 'd35f62e7f04aee85749b3ab9c7ba25261ddf2fa71395d0b829e0e71cef40f18b'),)
    return validate_component(root, PROJECT, REVISION, files, require_patched)
