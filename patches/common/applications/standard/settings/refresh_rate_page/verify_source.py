#!/usr/bin/env python3
"""Exact missing-page candidate, not display-service or guest acceptance."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (
    ('product/phone/src/main/ets/pages/home/controller/PageRouteController.ets',
     '503c4e63b9f4451f47d4308517426af204ea822cc14515c990262a3118342d97',
     '341843b39aade298de963d61345a39d3b39e1001a79132f79d3c553bb4f453b6'),
    ('product/phone/src/main/ets/Setting/Display/controller/QemuRefreshRateController.ets', None,
     '52c5260a1cfd980149b34c130b5d83faff3ffe6dff5d84a36f8533b54bd1b872'),
    ('product/phone/src/main/ets/Setting/Display/QemuRefreshRatePage.ets', None,
     '0f38c5d799ab902180b9d88e50755926f40e2d2b9ea318a06ac00ef001a2ea42'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
