#!/usr/bin/env python3
"""Audit whether preinstalled HAP payloads can become usable system bundles.

The package verifier historically checked only that selected files existed in
system.img.  This audit also compares the preinstall list, the bundle registry,
the HAP module profile, and the signing certificate allowed by
install_list_capability.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, choices=("phone", "2in1"))
    parser.add_argument(
        "--system-app-root",
        required=True,
        type=Path,
        help="Local copy of guest /system/app (for example from hdc file recv)",
    )
    parser.add_argument("--install-list", required=True, type=Path)
    parser.add_argument("--capability-list", required=True, type=Path)
    parser.add_argument("--bundles", required=True, type=Path)
    parser.add_argument("--hap-sign", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enabled_bundles(path: Path) -> set[str]:
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        value = line.strip()
        if value and not value.startswith(("#", "ID:")):
            result.add(value)
    return result


def hap_profile(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        with zipfile.ZipFile(path) as archive:
            for name in ("module.json", "config.json"):
                if name in archive.namelist():
                    data = json.loads(archive.read(name))
                    return data, name
            if "pack.info" in archive.namelist():
                return json.loads(archive.read("pack.info")), "pack.info"
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
        pass
    return {}, None


def profile_fields(data: dict[str, Any], profile_name: str | None) -> dict[str, Any]:
    if profile_name == "module.json":
        app = data.get("app", {})
        module = data.get("module", {})
        abilities = [
            {
                "name": item.get("name"),
                "exported": item.get("exported"),
                "permissions": item.get("permissions", []),
                "skills": item.get("skills", []),
            }
            for item in module.get("abilities", [])
            if isinstance(item, dict)
        ]
        extensions = [
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "exported": item.get("exported"),
                "process": item.get("process"),
                "permissions": item.get("permissions", []),
                "uri": item.get("uri"),
                "read_permission": item.get("readPermission"),
                "write_permission": item.get("writePermission"),
                "skills": item.get("skills", []),
            }
            for item in module.get("extensionAbilities", [])
            if isinstance(item, dict)
        ]
        return {
            "bundle": app.get("bundleName"),
            "module": module.get("name"),
            "device_types": module.get("deviceTypes", []),
            "extension_types": sorted(
                {
                    item.get("type")
                    for item in extensions
                    if isinstance(item, dict) and item.get("type")
                }
            ),
            "abilities": abilities,
            "extensions": extensions,
        }
    if profile_name == "config.json":
        app = data.get("app", {})
        module = data.get("module", {})
        return {
            "bundle": app.get("bundleName"),
            "module": module.get("name") or module.get("package"),
            "device_types": module.get("deviceType", module.get("deviceTypes", [])),
            "extension_types": [],
            "abilities": [],
            "extensions": [],
        }
    if profile_name == "pack.info":
        packages = data.get("packages", [])
        package = packages[0] if packages else {}
        summary = package.get("summary", {})
        return {
            "bundle": summary.get("bundleName") or package.get("bundleName"),
            "module": package.get("name"),
            "device_types": [],
            "extension_types": [],
            "abilities": [],
            "extensions": [],
        }
    return {
        "bundle": None,
        "module": None,
        "device_types": [],
        "extension_types": [],
        "abilities": [],
        "extensions": [],
    }


def signing_fingerprint(hap_sign: Path, path: Path) -> tuple[str | None, str | None]:
    proc = subprocess.run(
        [str(hap_sign), "inspect", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None, (proc.stderr.strip() or "hap-sign inspect failed")
    start = proc.stdout.find("{")
    if start < 0:
        return None, "embedded provisioning profile was not printed"
    try:
        profile = json.loads(proc.stdout[start:])
        pem = profile["bundle-info"]["distribution-certificate"]
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return None, f"cannot parse distribution certificate: {error}"
    return hashlib.sha256(der).hexdigest().upper(), None


def normalise_root(path: Path) -> Path:
    path = path.resolve()
    nested = path / "app"
    return nested if nested.is_dir() else path


def uri_authority(uri: Any) -> str | None:
    """Return the authority used to resolve an extension URI."""
    if not isinstance(uri, str) or "://" not in uri:
        return None
    parsed = urlsplit(uri)
    authority = parsed.netloc.strip()
    if not authority:
        # DataShare accepts both ``scheme://authority`` and
        # ``scheme:///authority/path`` spellings.
        authority = parsed.path.lstrip("/").split("/", 1)[0].strip()
    return authority or None


def main() -> int:
    args = arguments()
    root = normalise_root(args.system_app_root)
    install_entries = read_json(args.install_list).get("install_list", [])
    capability_entries = read_json(args.capability_list).get("install_list", [])
    enabled = enabled_bundles(args.bundles)

    capability_by_bundle: dict[str, dict[str, Any]] = {}
    for entry in capability_entries:
        bundle = entry.get("bundleName")
        if bundle:
            capability_by_bundle[bundle] = entry

    install_dirs = {
        entry.get("app_dir") for entry in install_entries if isinstance(entry.get("app_dir"), str)
    }
    hap_rows: list[dict[str, Any]] = []
    haps_by_dir: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(root.rglob("*.hap")):
        relative = path.relative_to(root).as_posix()
        data, profile_name = hap_profile(path)
        fields = profile_fields(data, profile_name)
        fingerprint, inspect_error = signing_fingerprint(args.hap_sign, path)
        expected_raw = capability_by_bundle.get(fields["bundle"], {}).get("app_signature", [])
        expected_fingerprints = sorted(
            value.upper() for value in expected_raw if isinstance(value, str) and SHA256_RE.fullmatch(value)
        )
        fingerprint_match: bool | None = None
        if expected_fingerprints and fingerprint:
            fingerprint_match = fingerprint in expected_fingerprints
        row = {
            "path": f"/system/app/{relative}",
            "directory": f"/system/app/{Path(relative).parent.as_posix()}",
            "profile": profile_name,
            **fields,
            "listed_for_preinstall": f"/system/app/{Path(relative).parent.as_posix()}" in install_dirs,
            "enabled_for_user_100": fields["bundle"] in enabled,
            "configured_in_capability_list": fields["bundle"] in capability_by_bundle,
            "signing_certificate_sha256": fingerprint,
            "configured_certificate_sha256": expected_fingerprints,
            "configured_signature_values": expected_raw,
            "certificate_matches_capability_list": fingerprint_match,
            "inspect_error": inspect_error,
        }
        hap_rows.append(row)
        haps_by_dir[row["directory"]].append(row)

    directories_by_bundle: dict[str, set[str]] = defaultdict(set)
    for row in hap_rows:
        if row["bundle"]:
            directories_by_bundle[row["bundle"]].add(row["directory"])

    preinstall_rows: list[dict[str, Any]] = []
    for entry in install_entries:
        app_dir = entry.get("app_dir", "")
        relative = app_dir.removeprefix("/system/app/")
        directory = root / relative
        haps = haps_by_dir.get(app_dir, [])
        bundles = sorted({row["bundle"] for row in haps if row["bundle"]})
        enabled_here = sorted(set(bundles) & enabled)
        if not directory.exists():
            status = "payload_path_missing"
        elif not haps:
            status = "hap_payload_missing"
        elif enabled_here:
            status = "enabled"
        else:
            status = "present_but_not_enabled"
        preinstall_rows.append(
            {
                "app_dir": app_dir,
                "removable": entry.get("removable"),
                "path_exists": directory.exists(),
                "hap_count": len(haps),
                "bundles": bundles,
                "enabled_bundles": enabled_here,
                "path_mismatch_candidates": sorted(
                    directories_by_bundle.get(Path(app_dir).name, set()) - {app_dir}
                ),
                "status": status,
            }
        )

    signature_mismatches = [
        row for row in hap_rows if row["certificate_matches_capability_list"] is False
    ]
    not_enabled = [row for row in preinstall_rows if row["status"] != "enabled"]
    unlisted_haps = [row for row in hap_rows if not row["listed_for_preinstall"]]
    unlisted_bundles = sorted({row["bundle"] for row in unlisted_haps if row["bundle"]})
    path_mismatches = [row for row in preinstall_rows if row["path_mismatch_candidates"]]
    uri_providers: list[dict[str, Any]] = []
    for row in hap_rows:
        for extension in row.get("extensions", []):
            authority = uri_authority(extension.get("uri"))
            if not authority:
                continue
            uri_providers.append(
                {
                    "authority": authority,
                    "scheme": extension["uri"].split(":", 1)[0],
                    "uri": extension["uri"],
                    "bundle": row.get("bundle"),
                    "entrypoint": extension.get("name"),
                    "extension_type": extension.get("type"),
                    "read_permission": extension.get("read_permission"),
                    "write_permission": extension.get("write_permission"),
                    "path": row["path"],
                    "enabled_for_user_100": row["enabled_for_user_100"],
                }
            )
    uri_providers.sort(
        key=lambda item: (
            item["authority"].lower(), item.get("bundle") or "", item.get("entrypoint") or ""
        )
    )
    output = {
        "schema_version": 3,
        "device": args.device,
        "logical_system_app_root": "/system/app",
        "summary": {
            "hap_count": len(hap_rows),
            "hap_bundle_count": len({row["bundle"] for row in hap_rows if row["bundle"]}),
            "enabled_bundle_count": len(enabled),
            "preinstall_entry_count": len(preinstall_rows),
            "preinstall_enabled_count": sum(row["status"] == "enabled" for row in preinstall_rows),
            "preinstall_present_but_not_enabled_count": sum(
                row["status"] == "present_but_not_enabled" for row in preinstall_rows
            ),
            "preinstall_missing_payload_count": sum(
                row["status"] in {"payload_path_missing", "hap_payload_missing"}
                for row in preinstall_rows
            ),
            "certificate_mismatch_hap_count": len(signature_mismatches),
            "inspect_error_count": sum(row["inspect_error"] is not None for row in hap_rows),
            "unlisted_hap_count": len(unlisted_haps),
            "unlisted_bundle_count": len(unlisted_bundles),
            "unlisted_enabled_bundle_count": len(set(unlisted_bundles) & enabled),
            "preinstall_path_mismatch_candidate_count": len(path_mismatches),
            "declared_extension_uri_count": len(uri_providers),
            "declared_extension_authority_count": len(
                {row["authority"].lower() for row in uri_providers}
            ),
        },
        "preinstall_entries": preinstall_rows,
        "preinstall_path_mismatch_candidates": path_mismatches,
        "unlisted_bundles": unlisted_bundles,
        "unlisted_haps": unlisted_haps,
        "certificate_mismatches": signature_mismatches,
        "extension_uri_providers": uri_providers,
        "haps": hap_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2, sort_keys=True))
    for row in not_enabled:
        print(f"{row['status']}: {row['app_dir']} ({', '.join(row['bundles']) or 'no bundle'})")
    for row in signature_mismatches:
        print(
            f"certificate mismatch: {row['bundle']} {row['path']} "
            f"actual={row['signing_certificate_sha256']} "
            f"expected={','.join(row['configured_certificate_sha256'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
