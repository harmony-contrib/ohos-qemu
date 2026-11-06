#!/usr/bin/env python3
"""Resolve libGLESv1.so and libGLESv2.so hook tables from libEGL.so instead of private TLS keys."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/graphic/graphic_2d'
REVISION = '81cc9ca9509bccd86c435064136fe45591d29eeb'
FILES = (
    ('frameworks/opengl_wrapper/BUILD.gn',
     '7a20e4183096e08e597c4b5ec6cd8857c8b8b5b0edebbeec9723077bfad4a4be',
     '0684814b2fed5cb439960485a95a02c3d5fe7c3b07582596aa62076876c1e0e5'),
    ('frameworks/opengl_wrapper/src/GLES1/gles1.cpp',
     'b63daff735cce741d238ace6c4b214291751d0c4cc4eb0e2e7179b4f89159c61',
     '998cc93e466f236e4f8cf9f7893486a0d675752cd75e518b966f3d90c3cfe5d9'),
    ('frameworks/opengl_wrapper/src/GLES2/gles2.cpp',
     'ba94754c5c31cd559d8e04bf60eb701019d94534b13fa9081ca7013e7ddb2a3c',
     'fc53cb2bbae62102c7afa6d75e4505a7dc04a128dec1f7322978a90b65b375dd'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
