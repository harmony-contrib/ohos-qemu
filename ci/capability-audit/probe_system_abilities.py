#!/usr/bin/env python3
"""Run a bounded dump probe against every registered System Ability."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=8.0)
    return parser.parse_args()


def hdc(target: str, *command: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["hdc", "-t", target, "shell", *command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.output / "raw"
    raw.mkdir(exist_ok=True)
    listed = hdc(args.target, "hidumper", "-ls", timeout=args.timeout)
    (args.output / "system-abilities.txt").write_text(listed.stdout, encoding="utf-8")
    abilities = listed.stdout.partition(":")[2].split()
    abilities = [name for name in abilities if re.fullmatch(r"[A-Za-z0-9_.-]+", name)]
    rows = []
    for index, ability in enumerate(abilities, 1):
        try:
            result = hdc(args.target, "hidumper", "-s", ability, timeout=args.timeout)
            output = result.stdout
            returncode = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or "") if isinstance(error.stdout, str) else ""
            returncode = None
            timed_out = True
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", ability)
        (raw / f"{index:03d}-{safe_name}.txt").write_text(output, encoding="utf-8")
        lower = output.lower()
        rows.append(
            {
                "system_ability": ability,
                "returncode": returncode,
                "timed_out": timed_out,
                "output_bytes": len(output.encode()),
                "empty_output": not output.strip(),
                "contains_error_word": bool(
                    re.search(r"\b(?:error|failed|failure|not support|not found)\b", lower)
                ),
                "first_line": output.splitlines()[0] if output.splitlines() else "",
            }
        )
        print(f"[{index}/{len(abilities)}] {ability}")
    result = {
        "target": args.target,
        "summary": {
            "registered": len(abilities),
            "timed_out": sum(row["timed_out"] for row in rows),
            "nonzero": sum(row["returncode"] not in (0, None) for row in rows),
            "empty_output": sum(row["empty_output"] for row in rows),
            "contains_error_word": sum(row["contains_error_word"] for row in rows),
        },
        "abilities": rows,
    }
    (args.output / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (args.output / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=rows[0].keys() if rows else [], lineterminator="\n"
        )
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
