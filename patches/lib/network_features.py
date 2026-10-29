#!/usr/bin/env python3
"""Reject incomplete QEMU network feature pairs before native compilation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(features: dict, device: str) -> None:
    if device not in {"phone", "2in1"}:
        raise ValueError(f"unsupported QEMU network profile: {device}")
    expected = {
        "netmanager_base_enable_feature_sysvpn": True,
        "netmanager_ext_feature_sysvpn": True,
        "netmanager_base_enable_feature_net_firewall": device == "2in1",
        "netmanager_ext_feature_net_firewall": device == "2in1",
    }
    # Require explicit resolved values, not defaults in two separate GNI files.
    failures = [f"{name}: expected {value}, got {features.get(name)!r}"
                for name, value in expected.items() if features.get(name) is not value]
    if failures:
        raise ValueError("incomplete QEMU native network feature configuration: " + "; ".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--device", choices=("phone", "2in1"), required=True)
    args = parser.parse_args()
    validate(json.loads(args.features.read_text())["features"], args.device)
    print(f"QEMU {args.device} native network feature pairs validated")


if __name__ == "__main__":
    main()
