#!/usr/bin/env python3
"""Validate packaged init services against accounts, files, and boot evidence.

This catches a class of emulator failures that SysCap declarations, NAPI module
loads, and System Ability profiles cannot see: init may discard a service before
the public API ever reaches it.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any


LINUX_CAPABILITIES = {
    "CHOWN", "DAC_OVERRIDE", "DAC_READ_SEARCH", "FOWNER", "FSETID", "KILL",
    "SETGID", "SETUID", "SETPCAP", "LINUX_IMMUTABLE", "NET_BIND_SERVICE",
    "NET_BROADCAST", "NET_ADMIN", "NET_RAW", "IPC_LOCK", "IPC_OWNER",
    "SYS_MODULE", "SYS_RAWIO", "SYS_CHROOT", "SYS_PTRACE", "SYS_PACCT",
    "SYS_ADMIN", "SYS_BOOT", "SYS_NICE", "SYS_RESOURCE", "SYS_TIME",
    "SYS_TTY_CONFIG", "MKNOD", "LEASE", "AUDIT_WRITE", "AUDIT_CONTROL",
    "SETFCAP", "MAC_OVERRIDE", "MAC_ADMIN", "SYSLOG", "WAKE_ALARM",
    "BLOCK_SUSPEND", "AUDIT_READ", "PERFMON", "BPF", "CHECKPOINT_RESTORE",
}


SYSCAP_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"backup", re.I), ["SystemCapability.FileManagement.StorageService.Backup"]),
    (re.compile(r"fusion|partner_device", re.I), ["SystemCapability.Communication.FusionConnectivity.Core"]),
    (re.compile(r"i18n|timezone|libphonenumber|taboo|icu", re.I), ["SystemCapability.Global.I18n"]),
    (re.compile(r"huks|hks_", re.I), ["SystemCapability.Security.Huks.Core", "SystemCapability.Security.Huks.Extension"]),
    (re.compile(r"pin_auth|pinauth", re.I), ["SystemCapability.UserIAM.UserAuth.PinAuth"]),
    (re.compile(r"thermal", re.I), ["SystemCapability.PowerManager.ThermalManager"]),
    (re.compile(r"ispserver|camera", re.I), ["SystemCapability.Multimedia.Camera.Core"]),
    (re.compile(r"module_update|updater|sys_installer", re.I), ["SystemCapability.Update.UpdateService"]),
    (re.compile(r"usb", re.I), ["SystemCapability.USB.USBManager"]),
    (re.compile(r"device_usage", re.I), ["SystemCapability.ResourceSchedule.UsageStatistics.App"]),
    (re.compile(r"wifi", re.I), ["SystemCapability.Communication.WiFi.Core"]),
    (re.compile(r"netsys|netmanager", re.I), ["SystemCapability.Communication.NetManager.Core"]),
    (re.compile(r"distributedbms|d-bms", re.I), ["SystemCapability.BundleManager.DistributedBundleFramework"]),
    (re.compile(r"resource_schedule", re.I), ["SystemCapability.ResourceSchedule.SystemLoad"]),
    (re.compile(r"faultlogger|hiview", re.I), ["SystemCapability.HiviewDFX.Hiview.FaultLogger"]),
    (re.compile(r"graphic|render_service", re.I), ["SystemCapability.Graphic.Graphic2D.NativeWindow"]),
    (re.compile(r"access.?token", re.I), ["SystemCapability.Security.AccessToken"]),
    (re.compile(r"accountmgr", re.I), ["SystemCapability.Account.OsAccount"]),
]


BOOT_RULES = [
    ("missing_imported_init_config", re.compile(r"Cfg error, ([^ ]+) not found")),
    ("missing_service_account", re.compile(r"failed get uid for service ([A-Za-z0-9_.-]+)")),
    ("missing_service_path", re.compile(r"failed get path for service ([A-Za-z0-9_.-]+)")),
    ("unsupported_capability", re.compile(r"service=([^ ]+) not support caps = ([^ ]+)")),
    ("invalid_job_account", re.compile(r"SetOwner invalid uid : ([A-Za-z0-9_.-]+)")),
    ("missing_job_executable", re.compile(r'DoExec: execute "([^"]+)" failed')),
    ("missing_service_executable", re.compile(r"ServiceStart pathArgs invalid, please check ([^,]+),([^\r\n]+)")),
    ("incomplete_selinux_definition", re.compile(r"No secon item in ([A-Za-z0-9_.-]+)")),
    ("missing_module_update_initializer", re.compile(r"module_update_init\.cpp:.*exec error.*No such file or directory")),
]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, choices=("phone", "2in1"))
    parser.add_argument("--init-root", required=True, type=Path)
    parser.add_argument("--filesystem-manifest", required=True, type=Path)
    parser.add_argument("--passwd", required=True, type=Path)
    parser.add_argument("--group", required=True, type=Path)
    parser.add_argument("--serial-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def identities(path: Path) -> tuple[set[str], set[str]]:
    names: set[str] = set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        fields = line.split(":")
        if len(fields) >= 3:
            names.add(fields[0])
            ids.add(fields[2])
    return names, ids


def values(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def syscaps(text: str) -> list[str]:
    result: set[str] = set()
    for pattern, matches in SYSCAP_RULES:
        if pattern.search(text):
            result.update(matches)
    return sorted(result)


def main() -> int:
    args = arguments()
    files = set(args.filesystem_manifest.read_text(encoding="utf-8", errors="ignore").splitlines())
    users, uids = identities(args.passwd)
    groups, gids = identities(args.group)
    service_definitions: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    issues: list[dict[str, Any]] = []

    def add(kind: str, config: str, subject: str, detail: str) -> None:
        evidence = " ".join((config, subject, detail))
        issues.append({
            "kind": kind,
            "config": config,
            "subject": subject,
            "detail": detail,
            "syscaps": syscaps(evidence),
            "source": "static_init_validation",
        })

    def known(value: Any, names: set[str], numeric_ids: set[str]) -> bool:
        return str(value) in names or str(value) in numeric_ids

    for path in sorted(args.init_root.rglob("*.cfg")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        config = str(path.relative_to(args.init_root))
        for service in data.get("services", []):
            name = service.get("name", "")
            service_definitions[name].append((config, service))
            for uid in values(service.get("uid")):
                if not known(uid, users, uids):
                    add("missing_service_account", config, name, str(uid))
            for gid in values(service.get("gid")):
                if not known(gid, groups, gids):
                    add("missing_supplemental_group", config, name, str(gid))
            for capability in values(service.get("caps")):
                if str(capability).removeprefix("CAP_") not in LINUX_CAPABILITIES:
                    add("unsupported_capability", config, name, str(capability))
            paths = values(service.get("path"))
            if paths and str(paths[0]).startswith("/") and paths[0] not in files:
                add("missing_service_executable", config, name, str(paths[0]))
        for job in data.get("jobs", []):
            for command in job.get("cmds", []):
                tokens = command.split()
                if not tokens:
                    continue
                if tokens[0] == "mkdir" and len(tokens) >= 5:
                    if not known(tokens[3], users, uids):
                        add("invalid_job_account", config, job.get("name", ""), tokens[3])
                    if not known(tokens[4], groups, gids):
                        add("invalid_job_group", config, job.get("name", ""), tokens[4])
                if tokens[0] in {"exec", "exec_nowait"}:
                    executables = [token for token in tokens[1:] if token.startswith("/")]
                    if executables and executables[0] not in files:
                        add("missing_job_executable", config, job.get("name", ""), executables[0])

    for name, definitions in service_definitions.items():
        if len(definitions) == 1 and not definitions[0][1].get("path"):
            add("service_definition_without_path", definitions[0][0], name, "single definition has no path")
        if len(definitions) > 1:
            missing = [config for config, definition in definitions if not definition.get("secon")]
            if missing:
                add("duplicate_incomplete_service_definition", ",".join(missing), name, "duplicate definition lacks secon")

    serial = args.serial_log.read_text(encoding="utf-8", errors="ignore")
    boot_issues: list[dict[str, Any]] = []
    for kind, pattern in BOOT_RULES:
        seen: set[tuple[str, ...]] = set()
        for match in pattern.finditer(serial):
            groups_found = tuple(value.strip() for value in match.groups())
            if groups_found in seen:
                continue
            seen.add(groups_found)
            detail = ":".join(groups_found) if groups_found else match.group(0)
            boot_issues.append({
                "kind": kind,
                "detail": detail,
                "syscaps": syscaps(detail),
                "source": "boot_log",
            })

    result = {
        "schema_version": 1,
        "device": args.device,
        "summary": {
            "init_config_count": len(list(args.init_root.rglob("*.cfg"))),
            "service_definition_count": sum(len(items) for items in service_definitions.values()),
            "static_issue_count": len(issues),
            "boot_issue_count": len(boot_issues),
            "static_issue_kind_counts": dict(sorted(Counter(item["kind"] for item in issues).items())),
            "boot_issue_kind_counts": dict(sorted(Counter(item["kind"] for item in boot_issues).items())),
            "affected_syscaps": sorted({cap for item in issues + boot_issues for cap in item["syscaps"]}),
        },
        "static_issues": issues,
        "boot_issues": boot_issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
