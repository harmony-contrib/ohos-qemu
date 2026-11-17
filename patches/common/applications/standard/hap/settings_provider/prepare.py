#!/usr/bin/env python3
"""Normalize only Settings' equivalent relative/absolute GN target spelling."""
import argparse
from pathlib import Path

BLOCK = '''ohos_prebuilt_etc("settings_hap") {
  source = hap_src_dir + "Settings.hap"
  module_install_dir = "app/com.ohos.settings"
  part_name = "prebuilt_hap"
  subsystem_name = "applications"
}
'''
RELATIVE = '":settings_hap"'
ABSOLUTE = '"//applications/standard/hap:settings_hap"'


def prepare(path, require_patched=False):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('refuse redirected Settings prebuilt graph')
    text = path.read_text()
    counts = text.count(RELATIVE), text.count(ABSOLUTE)
    if text.count('ohos_prebuilt_etc("settings_hap")') == 0:
        if counts != (0, 0) or '"Settings.hap"' in text:
            raise ValueError('partially removed Settings prebuilt graph; preserve it')
        return
    if require_patched:
        raise ValueError('stale Settings prebuilt remains after patch application')
    if text.count(BLOCK) != 1 or counts not in ((2, 0), (0, 2)):
        raise ValueError('unknown Settings prebuilt block/label edits; preserve all HAP wiring')
    canonical = text.replace(ABSOLUTE, RELATIVE)
    if canonical != text:
        path.write_text(canonical)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append')
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    prepare(args.source_root / 'applications/standard/hap/BUILD.gn', args.require_patched)
