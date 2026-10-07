#!/usr/bin/env python3
"""Record and validate source-built unlock files; never patch image binaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile


def extract(tool: str, image: Path, paths: tuple[str, ...], output: Path) -> None:
    for path in paths:
        result = subprocess.run([tool, "-R", f"dump -p {path} {output}", str(image)],
                                capture_output=True, text=True)
        if result.returncode == 0 and output.is_file() and output.stat().st_size:
            return
    raise RuntimeError(f"required source-built SceneBoard file missing: {paths}")


def validate(cem: bytes, config: dict, machine: int) -> None:
    if cem[:4] != b"\x7fELF" or int.from_bytes(cem[18:20], "little") != machine or b"userId" not in cem:
        raise ValueError("source-built CEM architecture / userId Want support is missing")
    expected_paths = {
        "qemu_sceneboard_user_unlock": ["/system/bin/cem", "publish", "-e", "usual.event.USER_UNLOCKED", "-c", "100"],
        "qemu_sceneboard_unlock": ["/system/bin/cem", "publish", "-e", "usual.event.SCREEN_UNLOCKED", "-u", "100"],
    }
    if config.get("jobs") != [{
        "name": "param:bootevent.boot.completed=true", "condition": "bootevent.boot.completed=true",
        "cmds": ["start qemu_sceneboard_user_unlock", "start qemu_sceneboard_unlock"],
    }]:
        raise ValueError("invalid SceneBoard boot unlock trigger")
    services = config.get("services", [])
    if len(services) != 2 or {s.get("name") for s in services} != set(expected_paths):
        raise ValueError("invalid SceneBoard boot unlock services")
    for service in services:
        if (service.get("path") != expected_paths[service["name"]] or service.get("uid") != "system" or
                service.get("gid") != ["system"] or service.get("apl") != "system_core" or
                service.get("once") != 1 or service.get("start-mode") != "condition" or
                service.get("secon") != "u:r:cem:s0" or set(service.get("permission", [])) != {
                    "ohos.permission.PUBLISH_SYSTEM_COMMON_EVENT", "ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS"}):
            raise ValueError("invalid SceneBoard boot unlock service permissions / routing")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-image", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--product", choices=("arm64_virt", "armv7a_virt", "x86_64_virt"), required=True)
    args = parser.parse_args()
    tool = shutil.which("debugfs")
    if not tool:
        parser.error("debugfs is required")
    with tempfile.TemporaryDirectory(prefix="qemu-sceneboard-evidence-") as temporary:
        work = Path(temporary)
        extract(tool, args.system_image, ("/system/bin/cem", "/bin/cem"), work / "cem")
        extract(tool, args.system_image, ("/system/etc/init/qemu_sceneboard_unlock.cfg",
                                        "/etc/init/qemu_sceneboard_unlock.cfg"), work / "config")
        cem, config = (work / "cem").read_bytes(), (work / "config").read_bytes()
        machine = {"arm64_virt": 183, "armv7a_virt": 40, "x86_64_virt": 62}[args.product]
        validate(cem, json.loads(config), machine)
        extract(tool, args.system_image, ("/system/app/SceneBoard/SceneBoard.hap",
                                        "/app/SceneBoard/SceneBoard.hap"), work / "SceneBoard.hap")
        with ZipFile(work / "SceneBoard.hap") as archive:
            abc_digest = hashlib.sha256(archive.read("ets/modules.abc")).hexdigest()
        if abc_digest != "f1ceb224f8ffa56181c5de199db9bcf7e3c25a84d4dd538f8600330019d63759":
            raise ValueError("installed SceneBoard HAP does not contain the verified unlock-event fix")
        hap_evidence = {
            "legacy_event": "common.event.UNLOCK_SCREEN",
            "ability_manager_event": "usual.event.SCREEN_UNLOCKED",
            "baseline_modules_abc_sha256": "4866846a48fa6247ce48edf449fc306c5ce1a2f19f7338f6377621c5130b1549",
            "patched_modules_abc_sha256": abc_digest,
            "runtime_validated": False,
        }
        evidence = {
            "schema_version": 3, "implementation": "source_built",
            "events": ["usual.event.USER_UNLOCKED", "usual.event.SCREEN_UNLOCKED"],
            "user_id": 100, "trigger": "bootevent.boot.completed=true",
            "cem_path": "/system/bin/cem", "patched_cem_sha256": hashlib.sha256(cem).hexdigest(),
            "init_config_path": "/system/etc/init/qemu_sceneboard_unlock.cfg",
            "init_config_sha256": hashlib.sha256(config).hexdigest(),
            "runtime_validated": False,
        }
    (args.package / "qemu-sceneboard-boot-unlock.json").write_text(json.dumps(evidence, indent=2) + "\n")
    (args.package / "sceneboard-unlock-event.json").write_text(json.dumps(hap_evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
