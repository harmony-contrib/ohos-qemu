#!/usr/bin/env python3
"""Check bounded actual-Dump snapshot shape and the interval between two cuts.

No guest/DSO authenticity is inferred. Synthetic parser counterexamples never
substitute for actual IPC/native/runtime observations.
"""
import argparse
import json
from pathlib import Path
import re

SCHEMA = "qemu-gnss-hdi-trace/v1"
CAPACITY = 128
WORD32 = re.compile(r"0x[0-9a-f]{8}\Z")
WORD64 = re.compile(r"0x[0-9a-f]{16}\Z")
MAX64 = 2**64 - 1
MAX_SNAPSHOT_BYTES = (CAPACITY + 1) * 768

def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid " + name)

def read_snapshot(text):
    if len(text.encode('utf-8')) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot exceeds the actual bounded renderer")
    def non_json(value):
        raise ValueError("non-JSON floating word: " + value)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate trace field: " + key)
            result[key] = value
        return result
    rows = [json.loads(line, parse_constant=non_json, object_pairs_hook=unique_object)
            for line in text.splitlines() if line.strip()]
    if not rows or not isinstance(rows[0], dict):
        raise ValueError("missing actual trace header")
    header, records = rows[0], rows[1:]
    if (header.get("schema"), header.get("kind"), header.get("capacity"), header.get("cachedCaptured")) != (SCHEMA, "snapshot", CAPACITY, False):
        raise ValueError("not an exact diagnostic live-callback snapshot")
    if header.get("cachedCaptured") is not False:
        raise ValueError("cached entry flag must be false")
    for field in ("count", "firstRetainedOrdinal", "lastCapturedOrdinal", "overwrittenTotal", "droppedBeforeStore", "clockErrorsTotal"):
        integer(header.get(field), 0, MAX64, field)
    for field in ("traceEpochBootNs", "snapshotBootNs"):
        integer(header.get(field), -(2**63), 2**63 - 1, field)
    integer(header.get("processPid"), 1, 2**31 - 1, "processPid")
    if type(header.get("ordinalOverflow")) is not bool:
        raise ValueError("invalid overflow flag")
    count, last = header["count"], header["lastCapturedOrdinal"]
    if count != min(last, CAPACITY) or len(records) != count:
        raise ValueError("truncated/extra/broken ring snapshot")
    first = 0 if count == 0 else last - count + 1
    if header["firstRetainedOrdinal"] != first or header["overwrittenTotal"] != max(0, last - CAPACITY):
        raise ValueError("ring retention counters disagree")
    for index, row in enumerate(records):
        if not isinstance(row, dict) or row.get("kind") != "hdi_report_location":
            raise ValueError("cached/other data cannot masquerade as live HDI entry")
        integer(row.get("localOrdinal"), 1, MAX64, "localOrdinal")
        if row.get("localOrdinal") != first + index:
            raise ValueError("missing/reordered/duplicated captured ordinal")
        integer(row.get("fieldValidity"), 0, 2**32 - 1, "fieldValidity")
        for field, pattern in (("horizontalAccuracyBits", WORD32), ("latitudeBits", WORD64), ("longitudeBits", WORD64)):
            if not isinstance(row.get(field), str) or not pattern.fullmatch(row[field]):
                raise ValueError("invalid raw word: " + field)
        for field in ("sourceUtcMs", "sourceBootNs", "receiptBootNs"):
            integer(row.get(field), -(2**63), 2**63 - 1, field)
        for field in ("callbackCallerUid", "callbackCallerPid"):
            integer(row.get(field), -(2**31), 2**31 - 1, field)
    return header, records

def capture_window(before, after):
    b, _ = before
    a, records = after
    reasons = []
    if (b["processPid"], b["traceEpochBootNs"]) != (a["processPid"], a["traceEpochBootNs"]):
        reasons.append("process/trace epoch changed; local ordinals are not cross-boot IDs")
    if a["traceEpochBootNs"] <= 0 or b["snapshotBootNs"] < b["traceEpochBootNs"] or a["snapshotBootNs"] < b["snapshotBootNs"]:
        reasons.append("unavailable/regressed local clock")
    if b["ordinalOverflow"] or a["ordinalOverflow"]:
        reasons.append("captured ordinal overflow")
    if a["droppedBeforeStore"] != b["droppedBeforeStore"]:
        reasons.append("callback was dropped before storage in this interval")
    start, end = b["lastCapturedOrdinal"], a["lastCapturedOrdinal"]
    if end < start:
        reasons.append("captured counter regressed")
    chosen = [row for row in records if start < row["localOrdinal"] <= end]
    if len(chosen) != end - start:
        reasons.append("this capture window was overwritten; older-history overwrites alone do not fail it")
    if a["clockErrorsTotal"] != b["clockErrorsTotal"]:
        reasons.append("a new local clock failure occurred")
    if any(row["receiptBootNs"] < a["traceEpochBootNs"] or row["receiptBootNs"] > a["snapshotBootNs"] for row in chosen):
        reasons.append("receipt clock unavailable/outside actual process trace lifetime")
    return {"status": "INCONCLUSIVE" if reasons else "CAPTURE_WINDOW_COMPLETE_NOT_RUNTIME_PROOF",
            "captureWindowComplete": not reasons, "reasons": reasons,
            "localOrdinalInterval": [start, end], "records": chosen,
            "rawHdiRuntimeProven": False, "capabilityIdsClosed": 0}

def match_expected(window, expected):
    if not window["captureWindowComplete"]:
        raise ValueError("incomplete capture window cannot prove callback presence/absence")
    if not isinstance(expected, list) or not expected:
        raise ValueError("explicit expected source UTC/coordinate/raw precision fields required")
    keys = ("sourceUtcMs", "latitudeBits", "longitudeBits")
    compared = ("fieldValidity", "horizontalAccuracyBits")
    actual = {}
    for row in window["records"]:
        identity = tuple(row[key] for key in keys)
        if identity in actual:
            raise ValueError("ambiguous repeated source identity; local ordinal is not wire sequence")
        actual[identity] = row
    expected_keys = set()
    for row in expected:
        integer(row.get("sourceUtcMs"), -(2**63), 2**63 - 1, "expected sourceUtcMs")
        integer(row.get("fieldValidity"), 0, 2**32 - 1, "expected fieldValidity")
        for field, pattern in (("horizontalAccuracyBits", WORD32), ("latitudeBits", WORD64), ("longitudeBits", WORD64)):
            if not isinstance(row.get(field), str) or not pattern.fullmatch(row[field]):
                raise ValueError("bad expected raw word")
        identity = tuple(row[key] for key in keys)
        if identity in expected_keys or identity not in actual:
            raise ValueError("expected identity repeated/absent")
        expected_keys.add(identity)
        if any(actual[identity][key] != row[key] for key in compared):
            raise ValueError("actual callback fields differ from explicit source measurement")
    if set(actual) != expected_keys:
        raise ValueError("unexpected callback identity in controlled capture window")
    return {"status": "WINDOW_FIELDS_MATCH_NOT_RUNTIME_PROOF", "matched": len(expected_keys),
            "rawHdiRuntimeProven": False, "capabilityIdsClosed": 0}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    window = capture_window(read_snapshot(args.before.read_text()), read_snapshot(args.after.read_text()))
    result = match_expected(window, json.loads(args.expected.read_text())) if args.expected else window
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
