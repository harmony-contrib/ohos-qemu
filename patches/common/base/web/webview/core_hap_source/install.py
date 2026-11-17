#!/usr/bin/env python3
"""Install verified source HAPs before profile evaluation or build traversal."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPOSITORY = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPOSITORY / "scripts"))
from m144_core_artifacts import checksum, validate

PRODUCTS = {"armv7a_virt": "arm", "arm64_virt": "arm64", "x86_64_virt": "x86_64"}
WEBVIEW_REVISION = "d421b6b549fa3038ad01cf34589b959286137be9"


def install(source: Path, artifacts: Path, products: list[str]) -> None:
    webview = source / "base/web/webview"
    actual = subprocess.check_output(["git", "-C", str(webview), "rev-parse", "HEAD"], text=True).strip()
    if actual != WEBVIEW_REVISION:
        raise ValueError("main 7.0 webview revision differs; review source HAP selection before building")
    records = {PRODUCTS[product]: validate(artifacts / PRODUCTS[product], PRODUCTS[product], REPOSITORY)
               for product in products}
    destination = webview / "ohos_nweb/qemu-core"
    for arch, record in records.items():
        target = destination / arch / "ArkWebCore.hap"
        owner = target.parent / "installed-source-core.json"
        for parent in (webview, webview / "ohos_nweb", destination, target.parent, target, owner):
            if parent.is_symlink():
                raise ValueError("unexpected source core alias; preserving it")
        if target.exists() or owner.exists():
            if (not target.is_file() or not owner.is_file()
                    or json.loads(owner.read_text()).get("hap_sha256") != checksum(target)):
                raise ValueError("unknown or modified existing source core; preserving it")
    component = Path(__file__).parent
    subprocess.run(["bash", str(REPOSITORY / "patches/lib/apply_component_dir.sh"), str(component),
                    "--source-root", str(source)], check=True)
    for patch in component.glob("[0-9][0-9][0-9][0-9]-*.patch"):
        subprocess.run(["git", "-C", str(source), "apply", "--check", "--reverse", str(patch)], check=True)
    for arch, record in records.items():
        target = destination / arch / "ArkWebCore.hap"
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".source-core-", dir=target.parent)
        os.close(descriptor)
        temporary = Path(name)
        shutil.copyfile(artifacts / arch / "ArkWebCore.hap", temporary)
        if checksum(temporary) != record["hap_sha256"]:
            raise ValueError("source HAP changed during installation; temporary copy retained")
        os.replace(temporary, target)
        (target.parent / "installed-source-core.json").write_text(json.dumps({
            "scope": "source_core_installation_NOT_guest_acceptance", "arch": arch,
            "hap_sha256": record["hap_sha256"], "core_artifact_sha256": record["core_artifact_sha256"],
            "release_source_lock_sha256": record["release_source_lock_sha256"],
            "first_artifact_behavior_gate_passed": False}, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--product", choices=tuple(PRODUCTS), action="append", required=True)
    args = parser.parse_args()
    install(args.source_root, args.artifact_root, args.product)


if __name__ == "__main__":
    main()
