#!/usr/bin/env python3
"""Bind a source-built, signed, complete M144 HAP to its actual build evidence.

This is dependency provenance/ABI verification, never Web or guest acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

from prepare_m144_release_cache import load_lock
from build_m144_sdk_bti_runtimes import ARCHIVES, REVISION as SDK_LLVM_REVISION
from prepare_m144_release_tools import CHROMIUM, GN_REVISION
from snapshot_build_inputs import digest_files
from verify_arkweb_core_image import REQUIRED_LIBRARIES, verify_hap
from m144_dependency_recipe import recipe
from prepare_m144_release_hap_cache import recipe as hap_tool_recipe
from prepare_m144_hap_tools import VERSION_CASES
from verify_m144_hap_native_transform import validate as validate_native_transform, OFFICIAL_INPUTS

ARCHES = {"arm": "armv7a", "arm64": "arm64", "x86_64": "x86_64"}
NATIVE_COMPONENTS = ("m144_v8_shared", "m144_core_build", "m144_webrtc_thread_id",
                     "m144_window_contract", "m144_private_contract", "m144_angle_includes",
                     "m144_adapter_header_format")
REPORTS = ("native-build-inputs.json", "native-build-evidence.json", "release-source-pins.json",
           "sdk-bti-runtime-evidence.json", "release-tools-evidence.json",
           "sdk-preparation-evidence.json", "package-build-inputs.json", "package-build-evidence.json",
           "source-hap-abi-evidence.json", "verify-app.log", "verified-app-cert.cer",
           "verified-app-profile.p7b", "kernel-permission-input.json",
           "hap-host-tools-native.json", "hap-host-tools-package.json", "hap-native-transform.json")
TOOL_PAYLOADS = {
    '0e18eb7f358240275c4ef5f92072c9acec37a168287ae69942f6a86462792b89',
    'fc5e696e4aa5b36103089fbe4113f53d19a8f9880bb906c4554d075fc6632b5a',
    '15cf3019dd864ea64d63e5cf33de1ded76ace4f70cbb224812fccbf03b342096',
    'f1becee9a78f65a094d17f9116727069aab5b235d4c9977346dbf8251a66a5db',
    'f03b8b6cc61704de017ed4a9f991c0c26e30e3a404d436491a9a951d7b648717',
    '889266a51681d55bd4b9e02c9a104fa6ee22ecdfa7e8253532e5ea47e2e4cb4a',
    '36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50',
    '63f0e5128b84f7b0421956a4a40affa472be8da0e58caf27e9acbc84072daee7',
}


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate core provenance key: " + key)
        result[key] = value
    return result


def document(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("missing, aliased or oversized core evidence: " + path.name)
    return json.loads(path.read_text(), object_pairs_hook=unique_keys)


def checked_file(root: Path, name: str) -> Path:
    parsed = PurePosixPath(name)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in name:
        raise ValueError("unsafe core provenance path")
    path = root / name
    if any((root / Path(*parsed.parts[:i])).is_symlink() for i in range(1, len(parsed.parts) + 1)):
        raise ValueError("aliased core provenance path")
    if not path.is_file():
        raise ValueError("missing core provenance input: " + name)
    return path


def validate_recipe_inputs(frozen: Path, repository: Path) -> None:
    if recipe(frozen)['files_sha256'] != recipe(repository)['files_sha256']:
        raise ValueError('core uses stale fixed dependency builders or shared helper inputs')


def check_build(root: Path, arch: str, repository: Path, hap_override: Path | None = None) -> dict:
    if arch not in ARCHES or root.is_symlink():
        raise ValueError("unsupported or aliased core architecture")
    lock = load_lock(repository / "scripts/m144_release_source_lock.json")
    graph = document(root / "release-source-pins.json")
    expected = {p["path"]: p["revision"] for p in lock["projects"]}
    if (graph.get("source_lock_sha256") != checksum(repository / "scripts/m144_release_source_lock.json")
            or graph.get("source_pins") != expected):
        raise ValueError("core does not use the complete fixed 7.0 release graph")
    pgo = {"path": "build/pgo/ohos/arkweb.profdata",
           "sha256": "c98db0441494ecd018d7decbd2aa9b37ec61fd3e960b56e7e81eb19e0afceb1b", "size": 262100672}
    if graph.get("release_lfs_objects") != [pgo]:
        raise ValueError("core lacks the verified actual release PGO object")
    native_inputs = document(root / "native-build-inputs.json")
    native = document(root / "native-build-evidence.json")
    package_inputs = document(root / "package-build-inputs.json")
    package = document(root / "package-build-evidence.json")
    if (native_inputs.get("arch") != arch or type(native.get("exit_code")) is not int
            or native.get("exit_code") != 0 or native.get("failures") != []
            or set(native.get("artifacts", {})) != REQUIRED_LIBRARIES
            or native.get("native_inputs_sha256") != checksum(root / "native-build-inputs.json")
            or native_inputs.get("release_source_graph_sha256") != checksum(root / "release-source-pins.json")
            or package_inputs.get("native_evidence_sha256") != checksum(root / "native-build-evidence.json")
            or type(package.get("exit_code")) is not int or package.get("exit_code") != 0):
        raise ValueError("core native/HAP build failed or has incomplete provenance")
    sdk = document(root / "sdk-preparation-evidence.json")
    if (checksum(root / "sdk-preparation-evidence.json") != native_inputs.get("sdk_evidence_sha256")
            or sdk.get("sdk_metadata", {}).get("apiVersion") != "26"
            or sdk.get("sdk_metadata", {}).get("version") != "26.0.0.39"):
        raise ValueError("core API-26 release SDK evidence differs")
    bti = document(root / 'sdk-bti-runtime-evidence.json')
    if (checksum(root / 'sdk-bti-runtime-evidence.json') != native_inputs.get('sdk_bti_runtime_evidence_sha256')
            or bti.get('status') != 'pass' or bti.get('source_revision') != SDK_LLVM_REVISION
            or set(bti.get('archives', {})) != set(ARCHIVES)
            or bti.get('builder_sha256') != checksum(repository / 'scripts/build_m144_sdk_bti_runtimes.py')
            or any(record.get('all_objects_BTI') is not True or
                   record.get('defined_C_symbols_match_original') is not True for record in bti['archives'].values())):
        raise ValueError('core lacks the actual same-SDK BTI runtime build evidence')
    tools = document(root / 'release-tools-evidence.json')
    if (checksum(root / 'release-tools-evidence.json') != native_inputs.get('release_tools_evidence_sha256')
            or tools.get('status') != 'pass' or tools.get('chromium_revision') != CHROMIUM
            or tools.get('gn', {}).get('revision') != GN_REVISION
            or len(tools.get('tools', [])) != len(TOOL_PAYLOADS)
            or {tool.get('archive_sha256') for tool in tools['tools']} != TOOL_PAYLOADS
            or any(tool.get('source', {}).get('sha256sum') != tool.get('archive_sha256')
                   or tool.get('installed', {}).get('file_count', 0) < 1 for tool in tools['tools'])):
        raise ValueError('core lacks fixed Chromium host-tool/sysroot evidence')
    expected_hap_tools = hap_tool_recipe(repository)
    tool_trees = []
    for name, inputs in (('hap-host-tools-native.json', native_inputs),
                         ('hap-host-tools-package.json', package_inputs)):
        host = document(root / name)
        preflight = host.get('preflight', {})
        node = host.get('release_node', {})
        if (checksum(root / name) != inputs.get('hap_host_tools_evidence_sha256')
                or host.get('status') != 'pass' or host.get('lock') != expected_hap_tools['lock']
                or host.get('recipe_sha256') != expected_hap_tools['recipe_sha256']
                or host.get('sdk_metadata_modified') is not False
                or host.get('official_tool_code_modified') is not False
                or host.get('dependency_network_required') is not False
                or host.get('sdk_version_boundary', {}).get('status') != 'pass'
                or host.get('sdk_version_boundary', {}).get('rows') != [
                    {'value': value, 'expected': wanted, 'accepted': wanted} for value, wanted in VERSION_CASES]
                or type(preflight.get('exit_code')) is not int
                or preflight.get('exit_code') != 0
                or preflight.get('stdout', '').strip() != expected_hap_tools['lock']['hvigor_version']
                or node.get('build_revision') != expected_hap_tools['lock']['build_revision']
                or node.get('node_version') != expected_hap_tools['lock']['node_version']
                or node.get('npm_version') != expected_hap_tools['lock']['npm_version']
                or not isinstance(host.get('installed_tree_sha256'), str)
                or len(host['installed_tree_sha256']) != 64):
            raise ValueError('core lacks paired fixed Release HAP host-tool evidence: ' + name)
        tool_trees.append(host['installed_tree_sha256'])
    if len(set(tool_trees)) != 1:
        raise ValueError('native and HAP use different host-tool trees')
    frozen = root / "frozen-build-inputs"
    # Explicit artifact roots must fail closed too, not just the default
    # recipe-named cache. Unrelated OS/runtime-test files are not engine inputs.
    validate_recipe_inputs(frozen, repository)
    manifest = document(frozen / "build-inputs.json")
    files = digest_files(frozen)
    if (checksum(frozen / "build-inputs.json") != native_inputs.get("frozen_manifest_sha256")
            or manifest.get("files_sha256") != files
            or manifest.get("tree_sha256") != hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
            or manifest.get("tree_sha256") != native_inputs.get("frozen_tree_sha256")):
        raise ValueError("native frozen build inputs changed")
    current = digest_files(repository)
    for component in NATIVE_COMPONENTS:
        prefix = "patches/common/web/arkweb/" + component + "/"
        if ({n: v for n, v in files.items() if n.startswith(prefix) and not n.endswith(".md")} !=
                {n: v for n, v in current.items() if n.startswith(prefix) and not n.endswith(".md")}):
            raise ValueError("core uses stale native component patches: " + component)
    hap_frozen = root / "hap-build-inputs"
    package_files = package_inputs.get("frozen_inputs_sha256", {})
    if not package_files:
        raise ValueError("core HAP frozen inputs are missing")
    for name, digest in package_files.items():
        if checksum(checked_file(hap_frozen, name)) != digest:
            raise ValueError("core HAP input changed: " + name)
    prefix = "patches/common/web/arkweb/m144_core_package/"
    if ({n: v for n, v in package_files.items() if n.startswith(prefix) and not n.endswith(".md")} !=
            {n: v for n, v in current.items() if n.startswith(prefix) and not n.endswith(".md")}):
        raise ValueError("core uses stale HAP packaging patches")
    hap = hap_override if hap_override is not None else checked_file(root, "ArkWebCore.hap")
    observed = verify_hap(hap, ARCHES[arch])
    abi_report = document(root / "source-hap-abi-evidence.json")
    if (abi_report.get("status") != "pass" or abi_report.get("hap_sha256") != observed["hap_sha256"]
            or abi_report.get("native_libraries") != observed["native_libraries"]
            or package.get("hap_sha256") != observed["hap_sha256"]):
        raise ValueError("final signed core HAP differs from verified build output")
    signature = checked_file(root, "verify-app.log").read_text()
    if "verify-app success" not in signature:
        raise ValueError("actual SDK HAP signature verification did not pass")
    for name in ("verified-app-cert.cer", "verified-app-profile.p7b"):
        if checked_file(root, name).stat().st_size == 0:
            raise ValueError("empty SDK-verified signature output")
    permission = document(root / "kernel-permission-input.json")
    if (permission.get("scope") != "unchanged_official_HAP_kernelpermission_input"
            or permission.get("source_revision") != expected["src"]
            or permission.get('files_sha256') != {
                'third_party/ohos_nweb_hap/' + name: digest for name, digest in OFFICIAL_INPUTS.items()}):
        raise ValueError("unknown official engine HAP transformation")
    validate_native_transform(root, native, observed, repository)
    return {"arch": arch, **observed, "release_source_lock_sha256": graph["source_lock_sha256"],
            "source_pins": expected, "native_frozen_tree_sha256": manifest["tree_sha256"],
            "kernel_permission_input": permission}


def record(root: Path, arch: str, repository: Path) -> dict:
    result = check_build(root, arch, repository)
    manifest = {"schema_version": 1, "scope": "signed_source_M144_core_provenance_ABI_NOT_guest_acceptance",
                "first_artifact_behavior_gate_passed": False, "arkweb_behavior_validated": False,
                **result, "evidence_sha256": {name: checksum(checked_file(root, name)) for name in REPORTS}}
    target = root / "core-artifact.json"
    if target.exists() or target.is_symlink():
        raise ValueError("refusing to replace core artifact provenance")
    target.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def validate(root: Path, arch: str, repository: Path, hap_override: Path | None = None) -> dict:
    manifest = document(root / "core-artifact.json")
    if (type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1
            or manifest.get("scope") != "signed_source_M144_core_provenance_ABI_NOT_guest_acceptance"
            or manifest.get("first_artifact_behavior_gate_passed") is not False
            or manifest.get("arkweb_behavior_validated") is not False
            or set(manifest.get("evidence_sha256", {})) != set(REPORTS)):
        raise ValueError("invalid core dependency provenance scope")
    for name, digest in manifest["evidence_sha256"].items():
        if checksum(checked_file(root, name)) != digest:
            raise ValueError("source core evidence changed: " + name)
    observed = check_build(root, arch, repository, hap_override)
    if any(manifest.get(key) != value for key, value in observed.items()):
        raise ValueError("source core differs from recorded actual build")
    return {**observed, "core_artifact_sha256": checksum(root / "core-artifact.json"),
            "m144_source_provenance_validated": True, "arkweb_behavior_validated": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--arch", choices=tuple(ARCHES), nargs="+", required=True)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    operation = record if args.record else validate
    results = {arch: operation(args.artifact_root / arch, arch, repository) for arch in args.arch}
    print(json.dumps({"scope": "source_core_dependency_only_NOT_guest_acceptance", "artifacts": results}))


if __name__ == "__main__":
    main()
