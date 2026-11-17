#!/usr/bin/env python3
"""Install the independent manual-settings UI protocol, not the legacy sheet."""
import argparse
import json
from pathlib import Path
import re

ABILITY = "com.ohos.permissionmanager.OpenSettingAbility"
PAGE = "OpenSetting/OpenSettingDialog"
ENTRY = {"name": ABILITY, "srcEntry": "./ets/OpenSetting/OpenSettingAbility.ets",
         "type": "sys/commonUI", "exported": True}


def update(path, content):
    if not path.is_file() or path.read_text() != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root / "applications/standard/permission_manager/permissionmanager/src/main"
    component = Path(__file__).resolve().parent
    for name in ("module.json", "module.json5"):
        path = root / name
        original = path.read_text()
        if ABILITY in original:
            # This component owns one specific entry; do not bless an alias
            # pointing to the old array-result dialog or a non-exported entry.
            match = re.search(r'\{[^{}]*"name"\s*:\s*"' + re.escape(ABILITY) + r'"[^{}]*\}', original)
            if not match or json.loads(match[0]) != ENTRY:
                raise ValueError(f"unexpected existing OpenSettingAbility registration: {path}")
        else:
            original, count = re.subn(r'("extensionAbilities"\s*:\s*\[)',
                lambda match: match[0] + "\n" + json.dumps(ENTRY, indent=4) + ",", original)
            if count != 1:
                raise ValueError(f"expected one extensionAbilities array: {path}")
            update(path, original)
    pages = root / "resources/base/profile/main_pages.json"
    document = json.loads(pages.read_text())
    if PAGE not in document["src"]:
        document["src"].append(PAGE)
        update(pages, json.dumps(document, indent=2) + "\n")
    for candidate in sorted((component / "files").glob("*.ets")):
        update(root / "ets/OpenSetting" / candidate.name, candidate.read_text())
    print("PermissionManager manual-settings UI configured (no implicit grants)")


if __name__ == "__main__":
    main()
