#!/usr/bin/env python3
"""Require actual I18n data results and the normal-app permission boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import re

NAMES = ("timezone.offsets", "timezone.catalog", "phone.format", "locale.display", "intl.year",
         "permission.boundary", "parameter.type", "parameter.missing")


def verify(text, run_id):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('require explicit fresh I18n run challenge')
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(NAMES) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("require eight fresh I18n results")
    if [row.get("name") for row in rows] != list(NAMES):
        raise ValueError("missing, reordered or stale I18n results")
    for row in rows:
        if (row.get("runId") != run_id or row.get("pass") is not True or not isinstance(row.get("values"), list) or
                not all(isinstance(value, str) for value in row["values"])):
            raise ValueError(f"failed or malformed I18n result: {row}")
    values = {row["name"]: row["values"] for row in rows}
    if values["timezone.offsets"] != ["28800000", "-18000000", "-14400000"]:
        raise ValueError("Shanghai / New York / DST offsets differ")
    catalog = values["timezone.catalog"]
    if len(catalog) != 4 or int(catalog[0]) < 2 or int(catalog[1]) < 1 or not all(catalog[2:]):
        raise ValueError("timezone / city metadata not available")
    if values["phone.format"] != ["true", "false", "+12025550123"]:
        raise ValueError("phone validation / E164 format differs")
    if values["locale.display"] != ["China"] or values["intl.year"] != ["2026"]:
        raise ValueError("locale / ICU format differs")
    boundary = values["permission.boundary"]
    if (len(boundary) != 4 or boundary[0] not in ("201", "202") or boundary[1] != 'number' or not boundary[2] or
            boundary[2] != boundary[3]):
        raise ValueError("normal-app permission not denied or system language changed")
    for name in ('parameter.type', 'parameter.missing'):
        boundary = values[name]
        if (len(boundary) != 4 or boundary[:2] != ['401', 'number'] or not boundary[2] or
                boundary[2] != boundary[3]):
            raise ValueError('invalid I18n parameter not rejected with numeric 401: ' + name)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    evidence = {"scope": "I18n bundled timezone/phone/locale data and permission boundary only",
                "status": "fail", "archive": str(args.archive.resolve()), "failures": [],
                "run_id": args.run_id, "first_artifact_behavior_gate_passed": False}
    try:
        with args.archive.open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        evidence["archive_sha256"] = digest.hexdigest()
        evidence["results_sha256"] = hashlib.sha256(args.results.read_bytes()).hexdigest()
        text = args.results.read_text()
        evidence['observations'] = [json.loads(line) for line in text.splitlines()]
        evidence["results"] = verify(text, args.run_id)
        evidence["status"] = "pass"
    except (ValueError, OSError, TypeError, KeyError) as exc:
        evidence["failures"].append(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
