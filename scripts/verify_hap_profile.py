#!/usr/bin/env python3

import argparse
import json
import re
import sys
import time
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def find_profiles(data: bytes) -> list[dict]:
    text = data.decode("utf-8", errors="ignore")
    decoder = json.JSONDecoder()
    profiles = []
    for match in re.finditer(r'\{\s*"version-name"\s*:', text):
        try:
            document, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if (
            isinstance(document, dict)
            and isinstance(document.get("validity"), dict)
            and isinstance(document.get("bundle-info"), dict)
        ):
            profiles.append(document)
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the signed provisioning profile embedded in a HAP."
    )
    parser.add_argument("hap", type=Path)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--app-feature")
    parser.add_argument("--allowed-acl", action="append", default=[])
    parser.add_argument("--at-time", type=int, default=int(time.time()))
    parser.add_argument("--min-valid-seconds", type=int, default=0)
    args = parser.parse_args()

    if not args.hap.is_file() or args.hap.stat().st_size == 0:
        fail(f"HAP is missing or empty: {args.hap}")

    matching = []
    for profile in find_profiles(args.hap.read_bytes()):
        bundle_info = profile["bundle-info"]
        if bundle_info.get("bundle-name") == args.bundle_name:
            matching.append(profile)
    if not matching:
        fail(
            f"{args.hap} has no embedded profile for bundle "
            f"{args.bundle_name}"
        )

    required_until = args.at_time + args.min_valid_seconds
    for profile in matching:
        bundle_info = profile["bundle-info"]
        if (
            args.app_feature is not None
            and bundle_info.get("app-feature") != args.app_feature
        ):
            continue
        allowed_acls = profile.get("acls", {}).get("allowed-acls", [])
        if not isinstance(allowed_acls, list):
            continue
        missing_acls = sorted(set(args.allowed_acl) - set(allowed_acls))
        if missing_acls:
            continue
        validity = profile["validity"]
        not_before = validity.get("not-before")
        not_after = validity.get("not-after")
        if not isinstance(not_before, int) or not isinstance(not_after, int):
            continue
        if not_before <= args.at_time and not_after >= required_until:
            print(
                json.dumps(
                    {
                        "bundle_name": args.bundle_name,
                        "app_feature": bundle_info.get("app-feature"),
                        "allowed_acls": sorted(allowed_acls),
                        "not_before": not_before,
                        "not_after": not_after,
                        "required_until": required_until,
                    },
                    sort_keys=True,
                )
            )
            return

    fail(
        f"{args.hap} has no profile for {args.bundle_name} with the required "
        f"system feature, ACLs, and validity through epoch {required_until}"
    )


if __name__ == "__main__":
    main()
