#!/usr/bin/env python3
"""Pinned public-input UI routing candidate; no preinstall grants or guest claim."""
from pathlib import Path
import hashlib
import importlib.util
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (
    ('product/phone/src/main/module.json5',
     'bfab8c721bfe18dcf640061f93c87684736ac072393863660b441d223a8a7b0f',
     'f347664ff4039db0970d58b72ebe28c668d8ab62d950100b8925df68b6351b70'),
    ('product/phone/src/main/resources/base/profile/main_pages.json',
     'b9093e71b3a95b92237ebab367a2946bb1ca37cf2cc6603e5a4a3ff977d8a446',
     '0a3e4a1f4856400dfaef882375159a053caa1f3e45e70cc68570c2e000f70906'),
    ('product/phone/src/main/ets/MainAbility/ExternalCommonUIExtensionAbility.ets', None,
     'a70db90fcdc0f1338536e1e665d7715de6905e1eb61607d669100e512d92d600'),
    ('product/phone/src/main/ets/pages/input/ExternalInputSettings.ets', None,
     '6a408cc8edb5ee202cd516177fa742d5741271c928e5384064251d3c4b107ce4'),
)


def validate(root, require_patched=False):
    files = FILES
    module = Path(root) / PROJECT / FILES[0][0]
    if module.is_file() and hashlib.sha256(module.read_bytes()).hexdigest() == 'fc6383796f603062cd0cba5e5078e28e3b567f95356d09d7014c2c27b52d9a62':
        # The share successor changes the two shared manifests. Require its
        # entire exact five-file state before accepting either new hash.
        spec = importlib.util.spec_from_file_location('settings_share_successor', Path(__file__).parent.parent / 'share_picker/verify_source.py')
        successor = importlib.util.module_from_spec(spec);spec.loader.exec_module(successor)
        successor.validate(root, require_patched=True)
        hashes = {name: repaired for name, _, repaired in successor.FILES}
        files = tuple((name, original, hashes.get(name, repaired)) for name, original, repaired in FILES)
    return validate_component(root, PROJECT, REVISION, files, require_patched)
