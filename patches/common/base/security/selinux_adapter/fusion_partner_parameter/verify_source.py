#!/usr/bin/env python3
"""Exact new parameter policy with the complete isolated-domain prerequisite."""
import importlib.util
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

spec = importlib.util.spec_from_file_location('fusion_domain_prerequisite',
    Path(__file__).resolve().parent.parent / 'fusion_service_domains/verify_source.py')
prerequisite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prerequisite)
PROJECT = prerequisite.PROJECT
REVISION = prerequisite.REVISION
PREFIX = prerequisite.PREFIX
FILES = prerequisite.FILES + (
    (PREFIX + 'public/parameter.te', None,
     '96521f24187e417b82bc3c72a9c470bcacbcbf8d05b1eb3da1191da60e69e0dc'),
    (PREFIX + 'public/parameter_contexts', None,
     '6378e3b4ccb4ff828d26b36071c666074a1655d7eb092ed0f5a425f390fa612a'),
    (PREFIX + 'system/fusion_partner_parameter.te', None,
     'd4ff9cb6f60531163a2c8765937be758c6a81deac96e7b77cf2dc1877850cd61'),
)


def validate(root, require_patched=False):
    validate_component(root, PROJECT, REVISION, prerequisite.FILES, require_patched=True)
    return validate_component(root, PROJECT, REVISION, FILES[len(prerequisite.FILES):], require_patched)
