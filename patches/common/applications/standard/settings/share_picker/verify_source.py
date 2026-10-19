#!/usr/bin/env python3
"""Fail closed on partial or unknown system sharing edits."""
from pathlib import Path
import hashlib
import importlib.util
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/settings'
REVISION = '0aba461c750fda71977c2f5186ca0e756ecfc6ca'
FILES = (('product/phone/src/main/module.json5', 'f347664ff4039db0970d58b72ebe28c668d8ab62d950100b8925df68b6351b70', 'fc6383796f603062cd0cba5e5078e28e3b567f95356d09d7014c2c27b52d9a62'), ('product/phone/src/main/resources/base/profile/main_pages.json', '0a3e4a1f4856400dfaef882375159a053caa1f3e45e70cc68570c2e000f70906', '021ce6f5057f629e37236b634dcecc7e963c44ed15d35f9de02a7bbb0d90389d'), ('product/phone/src/main/ets/Setting/SharePicker/SharePickerController.ets', None, '7cbf03a93e1c4877b677c077ba279be7073fcc07996b8b3ac08f551077bf790d'), ('product/phone/src/main/ets/Setting/SharePicker/SharePickerExtension.ets', None, '2b7dc87f39cddb03a6ed9b18172125b717fa5b16fbb3f70f92eddd5dc6b99b61'), ('product/phone/src/main/ets/pages/SharePicker.ets', None, '0b0f93e792995546b831c67980b80717c16067591c3a22b269fdca36c51379dd'))

def validate(root, require_patched=False):
    # The chooser changes module/pages shared with Share and Wallpaper.
    # Accept it only after the entire native/UI/dependency vector is verified.
    chooser_module = Path(root) / PROJECT / 'product/phone/src/main/module.json5'
    if chooser_module.is_file() and hashlib.sha256(chooser_module.read_bytes()).hexdigest() == '8bb80334c6dc6b68c032eedbc14dcd7f79e28d260fcbae0bd2c8965d9a054e3e':
        spec = importlib.util.spec_from_file_location('settings_native_chooser_successor',
            Path(__file__).parent.parent / 'share_picker_choose/verify_source.py')
        chooser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(chooser)
        return chooser.validate(root, require_patched=True)
    files = FILES
    module = Path(root) / PROJECT / FILES[0][0]
    final = 'ec1d3c1525d7298209346cb8f47715f781c1a6cc52b058cadef5e57d211db6bf'
    if module.is_file() and hashlib.sha256(module.read_bytes()).hexdigest() == final:
        spec = importlib.util.spec_from_file_location('settings_wallpaper_successor',
            Path(__file__).parent.parent / 'wallpaper_settings/verify_source.py')
        successor = importlib.util.module_from_spec(spec);spec.loader.exec_module(successor)
        successor.validate(root, require_patched=True)
        files = tuple((name, before, final if name == FILES[0][0] else after) for name, before, after in FILES)
    return validate_component(root, PROJECT, REVISION, files, require_patched)
