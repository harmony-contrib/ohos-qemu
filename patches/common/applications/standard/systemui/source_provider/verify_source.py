#!/usr/bin/env python3
"""Exact fixed SystemUI build inputs; actual packaged UI is a separate gate."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/systemui'
REVISION = 'd0f84037f1975dd9bf13ccbd279bd2d9b56e8a01'
FILES = (('BUILD.gn', None, '2c4f623b726b7555c8207e562c8c293c3b0281ea1075e1bac7f460ec55325bcd'), ('build-profile.json5', 'fd1608e1a8694d5ffd90fd7cb08c7f8199907f438afbabb2d56b1f80940d1cda', '73d0df791ab3ecc81843585fbc30abd1baf66aa388d276a70ac93c03cc6e6847'), ('oh-package.json5', 'b3c50e8ffdda75fcf6003d7190cc91d170f640d08c8293130510891a1528ab7a', 'e8018bb67b3b5e4fbc2c93e414611c972ce6515ab53474918b8fd5e006f29ef8'), ('hvigor/hvigor-config.json5', 'da6e3d8ecba56149225a1bfdc2609836133f2b9a075a1fef23a4e020a4fe3476', '322eaec60323114fe17400b00062d98b8ad23ca6f6310651ffc9756622d5869f'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
