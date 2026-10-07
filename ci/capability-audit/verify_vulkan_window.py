#!/usr/bin/env python3
"""Verify two actual compositor screenshots and native surface lifecycle.

This is not a substitute for device submission/readback or resize tests, nor
does it certify the remaining C++/ArkTS APIs. Run against a fresh guest/app log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image


class PixelMismatch(ValueError):
    """A valid current capture has not yet acquired the submitted frame."""


def verify_lifecycle(text: str) -> list[dict]:
    rows = []
    pattern = re.compile(r"^vulkan_window\.(present|destroyed)\|frames=(\d+) width=(\d+) height=(\d+) "
                         r"cleaned=(\d+) destroyed=(\d+) generation=(\d+)$")
    for line in text.splitlines():
        match = pattern.fullmatch(line.strip())
        if not match:
            raise ValueError(f"unexpected or failed Vulkan window result: {line}")
        event = match.group(1)
        frames, width, height, cleaned, destroyed, generation = map(int, match.groups()[1:])
        if frames != 5 or cleaned != 1 or width < 11 or height < 11:
            raise ValueError("Vulkan frames / cleanup / geometry validation failed")
        rows.append(dict(event=event, frames=frames, width=width, height=height,
                         cleaned=cleaned, destroyed=destroyed, generation=generation))
    if [(r["event"], r["destroyed"], r["generation"]) for r in rows] != [
            ("present", 0, 1), ("destroyed", 1, 1), ("present", 0, 2)]:
        raise ValueError("require initial presentation, actual destruction, and fresh surface presentation in order")
    return rows


def verify_pixels(image: Image.Image, rect: tuple[int, int, int, int], geometry: dict) -> int:
    x, y, width, height = rect
    if (min(x, y) < 0 or width != geometry["width"] or height != geometry["height"] or
            x + width > image.width or y + height > image.height or min(width, height) < 11):
        raise ValueError("screenshot rectangle must match the actual native surface geometry")
    # Exclude five pixels of compositor edge filtering; require the entire
    # interior, not a single pixel which might belong to a background widget.
    crop = image.convert("RGBA").crop((x + 5, y + 5, x + width - 5, y + height - 5))
    expected = (51, 102, 153, 255)
    for pixel in crop.get_flattened_data():
        if any(abs(value - wanted) > 1 for value, wanted in zip(pixel, expected)):
            raise PixelMismatch(f"Vulkan compositor RGBA pixel mismatch: {pixel}, expected {expected}")
    return crop.width * crop.height


def rect(value: str) -> tuple[int, int, int, int]:
    values = tuple(map(int, value.split(",")))
    if len(values) != 4:
        raise argparse.ArgumentTypeError("rectangle must be x,y,width,height in screenshot pixels")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--initial-screenshot", type=Path, required=True)
    parser.add_argument("--recreated-screenshot", type=Path, required=True)
    parser.add_argument("--initial-rect", type=rect, required=True)
    parser.add_argument("--recreated-rect", type=rect, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = {"scope": "Vulkan compositor presentation and surface recreation only", "status": "fail",
                "archive": str(args.archive.resolve()), "failures": []}
    # Large archives must not be loaded into RAM just to identify the test.
    with args.archive.open("rb") as archive:
        digest = hashlib.sha256()
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    evidence["archive_sha256"] = digest.hexdigest()
    try:
        rows = verify_lifecycle(args.results.read_text())
        verified = []
        for path, rectangle, geometry in ((args.initial_screenshot, args.initial_rect, rows[0]),
                                          (args.recreated_screenshot, args.recreated_rect, rows[2])):
            with Image.open(path) as screenshot:
                pixels = verify_pixels(screenshot, rectangle, geometry)
            verified.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "rect": rectangle, "verified_rgba_pixels": pixels})
        evidence.update(status="pass", lifecycle=rows, screenshots=verified)
    except (ValueError, OSError) as exc:
        evidence["failures"].append(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
