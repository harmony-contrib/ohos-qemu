#!/usr/bin/env python3
"""Prepare a private writable API26 SDK for the official ArkWeb stub copier.

Do not replace SDK/public libraries in the OHOS checkout. Retain the prior V8
SDK symlink and record the release SDK metadata plus pinned input revisions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

COMPONENTS = ('native', 'ets', 'js', 'toolchains', 'previewer')


def ensure_dot_sdk_alias(source, sdk):
    alias = source / 'ohos_sdk/26.0.0'
    if alias.is_symlink() and alias.resolve() == sdk.resolve():
        return
    if alias.exists() or alias.is_symlink():
        raise ValueError('unknown existing Release dot-version SDK layout')
    alias.symlink_to(sdk, target_is_directory=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_existing(source, ohos):
    """Add only missing previewer tools to an exact earlier owned SDK copy."""
    source, ohos = Path(source), Path(ohos)
    sdk = source.parent / 'qemu-core-sdk-api26'
    evidence = sdk / 'preparation-evidence.json'
    record = json.loads(evidence.read_text())
    names = set(record.get('components', {}))
    if (record.get('private_sdk') != str(sdk) or not record.get('ohos_source_and_sdk_mounted_readonly')
            or names not in (set(COMPONENTS), set(COMPONENTS) - {'previewer'})):
        raise ValueError('unknown or incomplete prior private SDK evidence')
    sdk_source = ohos / 'prebuilts/ohos-sdk/linux/26.0.0'
    for name, item in record['components'].items():
        original = sdk_source / name
        alias = source / 'ohos_sdk/openharmony' / name
        if (item.get('source') != str(original) or
                sha(original / 'oh-uni-package.json') != item.get('metadata_sha256') or
                sha(sdk / name / 'oh-uni-package.json') != item.get('metadata_sha256') or
                not alias.is_symlink() or alias.resolve() != (sdk / name).resolve()):
            raise ValueError('prior private SDK component changed: ' + name)
    if 'previewer' in names:
        return record
    target, alias = sdk / 'previewer', source / 'ohos_sdk/openharmony/previewer'
    backup = evidence.with_name('preparation-evidence.before-previewer-' + sha(evidence) + '.json')
    if any(path.exists() or path.is_symlink() for path in (target, alias, backup)):
        raise ValueError('refusing to replace unknown previewer SDK state')
    original = sdk_source / 'previewer'
    meta = json.loads((original / 'oh-uni-package.json').read_text())
    if meta.get('apiVersion') != '26' or meta.get('version') != '26.0.0.39':
        raise ValueError('previewer must match the fixed original full API26 SDK')
    subprocess.run(['cp', '--archive', '--reflink=auto', str(original), str(target)], check=True)
    if sha(target / 'oh-uni-package.json') != sha(original / 'oh-uni-package.json'):
        raise ValueError('copied previewer metadata differs')
    alias.symlink_to(target, target_is_directory=True)
    record['components']['previewer'] = {'source': str(original),
        'metadata_sha256': sha(original / 'oh-uni-package.json')}
    evidence.rename(backup)
    evidence.write_text(json.dumps(record, indent=2) + '\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="pinned Chromium src")
    parser.add_argument("--ohos-root", type=Path, required=True)
    parser.add_argument('--complete-components', action='store_true')
    args = parser.parse_args()
    source, ohos = args.source_root.resolve(), args.ohos_root.resolve()
    if not os.statvfs(ohos).f_flag & os.ST_RDONLY:
        raise ValueError("the release OHOS source/SDK must be mounted read-only")
    sdk_source = ohos / "prebuilts/ohos-sdk/linux/26.0.0"
    meta = json.loads((sdk_source / "native/oh-uni-package.json").read_text())
    if meta.get("apiVersion") != "26" or meta.get("version") != "26.0.0.39":
        raise ValueError("full-engine SDK must be the actual fixed 7.0 API26 release")
    sdk = source.parent / "qemu-core-sdk-api26"
    if args.complete_components and (sdk / 'preparation-evidence.json').is_file():
        complete_existing(source, ohos)
        ensure_dot_sdk_alias(source, sdk)
        print(json.dumps({'apiVersion': '26', 'private_sdk': str(sdk), 'components': list(COMPONENTS)}))
        return
    sdk.mkdir(exist_ok=False)
    selected = COMPONENTS
    records = {}
    for name in selected:
        original = sdk_source / name
        if not original.is_dir():
            raise ValueError("release SDK component missing: " + name)
        subprocess.run(["cp", "--archive", "--reflink=auto", str(original), str(sdk / name)], check=True)
        if sha(sdk / name / "oh-uni-package.json") != sha(original / "oh-uni-package.json"):
            raise ValueError("private SDK metadata differs from release source")
        records[name] = {"source": str(original), "metadata_sha256": sha(original / "oh-uni-package.json")}
    destination = source / "ohos_sdk/openharmony"
    destination.mkdir(parents=True, exist_ok=True)
    retained = {}
    for name in selected:
        target = destination / name
        if target.is_symlink():
            if target.resolve() != (sdk_source / name).resolve():
                raise ValueError("unknown existing engine SDK alias: " + name)
            backup = target.with_name(name + ".pre-core-sdk-link")
            if backup.exists() or backup.is_symlink():
                raise ValueError("prior SDK alias backup already exists")
            target.rename(backup)
            retained[name] = str(backup)
        elif target.exists():
            raise ValueError("refusing to overwrite an unknown engine SDK component")
        target.symlink_to(sdk / name, target_is_directory=True)
    for relative, target in (("ohos_sdk/26", sdk), ("ohos_sdk/26.0.0", sdk), ("ohos_sdk/ohos-sdk/linux", destination)):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise ValueError("unknown existing API SDK layout: " + relative)
        path.symlink_to(target, target_is_directory=True)
    for relative in ("build", "deps_code"):
        path = source.parent / relative
        # The release manifest already installs these canonical paths. Older
        # QEMU workspaces did not; do not replace either layout blindly.
        if relative == "deps_code" and path.is_dir() and not path.is_symlink():
            webview = path / "webview"
            alias = source / "arkweb/deps_code"
            if not (webview / ".git").is_dir() or not alias.is_symlink() or alias.resolve() != path.resolve():
                raise ValueError("unknown existing release interface layout")
            continue
        original = source / "arkweb" / relative
        if relative == "build":
            original = original / "build"
            if not (original / "config_to_gn.py").is_file():
                raise ValueError("official config generator layout is incomplete")
        if path.is_symlink() and path.resolve() == original.resolve():
            continue
        if path.exists() or path.is_symlink():
            raise ValueError("unknown existing official-build layout: " + relative)
        path.symlink_to(original, target_is_directory=True)
    result = {"scope": "private_API26_build_SDK_inputs_NOT_new_ArkWeb_HAP_or_guest_acceptance",
              "ohos_source_and_sdk_mounted_readonly": True, "sdk_metadata": meta,
              "components": records, "private_sdk": str(sdk), "retained_previous_sdk_aliases": retained,
              "first_artifact_behavior_gate_passed": False}
    (sdk / "preparation-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"apiVersion": "26", "private_sdk": str(sdk)}))


if __name__ == "__main__":
    main()
