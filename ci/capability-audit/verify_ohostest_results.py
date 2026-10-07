#!/usr/bin/env python3
"""Require all declared Hypium cases, a consistent summary and clean completion."""
import argparse
import ast
import json
from pathlib import Path
import re


def expected_names(source):
    literals = re.findall(r'^\s*it\s*\(\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\s*,', source, re.MULTILINE)
    names = [ast.literal_eval(literal) for literal in literals]
    if not names or len(names) != len(set(names)):
        raise ValueError("test source must declare unique, literal Hypium case names")
    return names


def verify(text, names):
    count = len(names)
    expected_summary = (count, 0, 0, count, 0)
    summaries = [tuple(map(int, values)) for values in re.findall(
        r'^OHOS_REPORT_RESULT: stream=Tests run: (\d+), Failure: (\d+), Error: (\d+), Pass: (\d+), Ignore: (\d+)\s*$',
        text, re.MULTILINE)]
    if summaries != [expected_summary]:
        raise ValueError("empty, incomplete, failed, ignored or stale Hypium summary")
    if re.findall(r'^TestFinished-ResultCode:\s*(-?\d+)\s*$', text, re.MULTILINE) != ["0"]:
        raise ValueError("test runner did not finish successfully exactly once")
    if re.findall(r'^OHOS_REPORT_CODE:\s*(-?\d+)\s*$', text, re.MULTILINE) != ["0"]:
        raise ValueError("invalid or missing overall Hypium report code")
    fields = {}
    completed = []
    group_size = None
    group_completed = 0
    group_counts = []
    started = None
    for line in text.splitlines():
        group = re.fullmatch(r'OHOS_REPORT_SUM:\s*(\d+)\s*', line.strip())
        if group:
            if fields or started is not None or (group_size is not None and group_completed != group_size):
                raise ValueError("incomplete Hypium group before the next declared suite")
            group_size = int(group[1])
            if group_size <= 0:
                raise ValueError("empty Hypium group")
            group_counts.append(group_size)
            group_completed = 0
        field = re.fullmatch(r'OHOS_REPORT_STATUS: (current|numtests|test)=(.*)', line.strip())
        if field:
            if field[1] in fields:
                raise ValueError("duplicate Hypium case metadata")
            fields[field[1]] = field[2]
        status = re.fullmatch(r'OHOS_REPORT_STATUS_CODE:\s*(-?\d+)', line.strip())
        if status:
            code = int(status[1])
            if code not in (0, 1):
                raise ValueError(f"Hypium case failure/status {code}")
            if (group_size is None or group_completed >= group_size or
                    set(fields) != {"current", "numtests", "test"} or fields["numtests"] != str(count) or
                    not re.fullmatch(r'[1-9][0-9]*', fields["current"])):
                raise ValueError("missing or inconsistent Hypium case metadata")
            current = (int(fields["current"]), fields["test"])
            if code == 1:
                if started is not None or len(completed) >= count or current != (len(completed) + 1, names[len(completed)]):
                    raise ValueError("missing, repeated or stale Hypium case start")
                started = current
            else:
                if started != current:
                    raise ValueError("Hypium pass does not match its actual case start")
                completed.append(current)
                group_completed += 1
                started = None
            fields = {}
    if fields or started is not None or group_size is None or group_completed != group_size or sum(group_counts) != count:
        raise ValueError("runner group case counts differ from the current test source")
    if completed != list(enumerate(names, 1)):
        raise ValueError("passed cases do not exactly match all current source cases")
    return {"scope": "Hypium result completeness only; image identity is recorded by the caller",
            "pass": count, "fail": 0, "cases": names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = verify(args.log.read_text(), expected_names(args.source.read_text()))
    except (ValueError, OSError, SyntaxError) as exc:
        parser.exit(1, f"E2E result validation failed: {exc}\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
