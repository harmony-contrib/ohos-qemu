#!/usr/bin/env python3
"""Exact source packaging metadata; not SDK, signature or guest acceptance."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/contacts'
REVISION = '65de33df8d6d7aaa5797a5625ed0e5938e5cb050'
FILES = (
    ('BUILD.gn', None, 'acf6f0814077df6e45864c46787c99241a17336af8eaf53657a4c6e73b9e6bb4'),
    ('build-profile.json5', 'd104e7b39d0dede9116a90ee191d2dbcac59af78398fe0d05afc89d7319d5196', '4c690458a9d6f14ee1401698fbcb9fa1faabf44a253c1da1b3d9f53bccb18249'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
