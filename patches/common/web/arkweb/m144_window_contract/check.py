#!/usr/bin/env python3
"""The locked 7.0 ArkWeb already contains the canonical WindowAdapter slot."""
import argparse
from pathlib import Path
import re
import subprocess

REVISION = "f3d904432cc1c57468f2b7fe01979d25e0157581"


def check(root: Path) -> None:
    repository = root / "src/arkweb"
    if subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip() != REVISION:
        raise ValueError("WindowAdapter source is not the locked OHOS 7.0 release")
    path = repository / "ohos_adapter_ndk/interfaces/graphic_adapter.h"
    if path.is_symlink():
        raise ValueError("private WindowAdapter header must not be a symlink")
    text = path.read_text()
    declaration = re.search(r"class WindowAdapter\s*\{(.*?)^\};", text, re.M | re.S)
    required = ("virtual void SetWindowNodeIdAndRSHandle(void* native_window, "
                "uint64_t node_id, uint64_t handle) {}")
    if declaration is None or declaration.group(1).count(required) != 1:
        raise ValueError("release private WindowAdapter slot changed or missing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    check(parser.parse_args().source_root)
