"""Emit a review-only shared-guard delta; never edit shared files or source."""
import argparse
import difflib
import json
from pathlib import Path

from batch_apps_select375_fixture import COMPONENT, ROOT


def proposed_delta():
    manifest = json.loads((COMPONENT / 'manifest.json').read_bytes())
    prefix = 'applications/standard/settings/'
    module = 'product/phone/src/main/module.json5'
    pages = 'product/phone/src/main/resources/base/profile/main_pages.json'
    final = manifest['files'][prefix + module]['after']
    final_pages = manifest['files'][prefix + pages]['after']
    changes = []
    # Root already integrated the Share and Wallpaper complete-vector branches.
    # Only external_input still needs this separately reviewed shared delta.
    for component in ('external_input',):
        path = COMPONENT.parent / component / 'verify_source.py'
        original = path.read_text()
        marker = 'def validate(root, require_patched=False):\n'
        if original.count(marker) != 1:
            raise ValueError('current shared guard shape differs: ' + str(path))
        block = f'''    # Accept only the complete current native/Settings select successor.
    successor_module = Path(root) / PROJECT / '{module}'
    if successor_module.is_file() and hashlib.sha256(successor_module.read_bytes()).hexdigest() == '{final}':
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location('settings_select375_successor',
            Path(__file__).parent.parent / 'share_picker_choose/verify_source.py')
        successor = module_from_spec(spec)
        spec.loader.exec_module(successor)
        successor.validate(root, require_patched=True)
'''
        if component == 'external_input':
            # Retain verification of this predecessor's two unique ETS files.
            block += f'''        successor_files = tuple((name, before,
            '{final}' if name == '{module}' else
            '{final_pages}' if name == '{pages}' else after)
            for name, before, after in FILES)
        return validate_component(root, PROJECT, REVISION, successor_files, require_patched)
'''
        else:
            # Select successor itself pins all original Share and WP files.
            block += '        return True\n'
        updated = original.replace(marker, marker + block, 1)
        if 'import hashlib' not in original:
            updated = updated.replace('from pathlib import Path\n', 'from pathlib import Path\nimport hashlib\n', 1)
        relative = path.relative_to(ROOT).as_posix()
        changes.append(''.join(difflib.unified_diff(original.splitlines(keepends=True),
            updated.splitlines(keepends=True), fromfile='a/' + relative, tofile='b/' + relative)))
    return ''.join(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(proposed_delta())


if __name__ == '__main__':
    main()
