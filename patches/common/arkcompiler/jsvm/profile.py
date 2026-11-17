#!/usr/bin/env python3
"""Add or remove arkcompiler:jsvm in one generated device profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PART = "arkcompiler:jsvm"


def load(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"generated device profile not found: {path}") from exc
    if not isinstance(document, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return document


def write(path: Path, document: dict) -> None:
    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def set_component(document: dict, enabled: bool) -> None:
    subsystems = document.setdefault("subsystems", [])
    arkcompiler = next(
        (item for item in subsystems if item.get("subsystem") == "arkcompiler"),
        None,
    )
    if arkcompiler is None:
        if not enabled:
            return
        arkcompiler = {"subsystem": "arkcompiler", "components": []}
        subsystems.append(arkcompiler)

    components = arkcompiler.setdefault("components", [])
    components[:] = [item for item in components if item.get("component") != "jsvm"]
    if enabled:
        components.append({"component": "jsvm", "features": []})


def update_metadata(path: Path, enabled: bool) -> None:
    if not path.is_file():
        return
    document = load(path)
    required = set(document.get("required_parts", []))
    adaptations = document.setdefault("qemu_adaptations", {})
    if enabled:
        required.add(PART)
        adaptations["jsvm_engine"] = "OpenHarmony-TPC ArkWeb M144 V8 shared library"
    else:
        required.discard(PART)
        adaptations.pop("jsvm_engine", None)
    document["required_parts"] = sorted(required)
    write(path, document)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("action", choices=("enable", "disable"))
    args = parser.parse_args()

    document = load(args.profile)
    enabled = args.action == "enable"
    set_component(document, enabled)
    write(args.profile, document)
    if args.metadata is not None:
        update_metadata(args.metadata, enabled)


if __name__ == "__main__":
    main()
