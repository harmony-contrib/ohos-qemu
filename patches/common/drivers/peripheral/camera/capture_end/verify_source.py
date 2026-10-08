#!/usr/bin/env python3
"""Guard the entire online V4L2 capture-end repair, not guest acceptance."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'drivers/peripheral'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
PREFIX = 'camera/vdi_base/v4l2/'
FILES = (
    (PREFIX + 'src/stream_operator/capture_message.cpp',
     '3191ed4ccd444d142107f55b9c0c7db1a7eec46446b96691908de34a755fc568',
     '6d5a254e6c699027adfdeb7fa7b1686be0d9c03e6a16b90f84c485feef2bab55'),
    (PREFIX + 'src/stream_operator/capture_request.cpp',
     '42f9f018b7c883ab188d0222b53b15f0c4eb3fbbf8c1e755d437d5bb8318c772',
     'd7248c10d263e34cc8beec2b160519b6a10b7d092740ab472adc393e5a1b2f27'),
    (PREFIX + 'include/stream_operator/capture_request.h',
     '690894d5f0ce05a2288282d162888219be074d738d8de94fe7faa61dd1d6a243',
     'e22db8bbfec80546c8b57d690f7a44c73df6695a388157e1d6e4fec22064bab7'),
    (PREFIX + 'src/stream_operator/stream_base.cpp',
     '95506e884915e72477e739d7a69037acf7ddec339f871c98fef266a1b8b05d1f',
     '4a4dce6793eadaec4dda7820b61c7d00f3a44daa7847f117f067a7b9dc61f27f'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
