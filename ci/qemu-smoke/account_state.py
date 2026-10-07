#!/usr/bin/env python3
"""Parse one current AccountMgr snapshot; never combine unrelated users/states."""
import argparse
from pathlib import Path
import re


def parse_snapshot(text):
    lines = text.replace("\r", "").splitlines()
    parameters = [line.strip() for line in lines
                  if line.strip().startswith("bootevent.account.ready=")]
    ready = parameters in (["bootevent.account.ready=true"],
                           ['bootevent.account.ready="true"'])
    accounts = []
    current = None
    for line in lines:
        line = line.strip()
        match = re.fullmatch(r"ID:\s*(0|[1-9][0-9]*)", line)
        if match:
            current = {"id": int(match[1]), "foreground_values": []}
            accounts.append(current)
        elif line.startswith("ID:"):
            # An invalid record header cannot extend the preceding user 100.
            current = None
        elif current is not None and line.startswith("isForeground:"):
            current["foreground_values"].append(line)
    selected = [account for account in accounts if account["id"] == 100]
    foreground = (len(selected) == 1 and selected[0]["foreground_values"] in (
        ["isForeground: 1"], ["isForeground: true"]))
    return {"param_ready": ready, "user_100": bool(selected), "foreground": foreground}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    state = parse_snapshot(args.snapshot.read_text())
    print(*(int(state[name]) for name in ("param_ready", "user_100", "foreground")))


if __name__ == "__main__":
    main()
