#!/usr/bin/env python3
"""Compare the API 26 public C surface with libraries shipped by one guest.

The SDK shared objects are link-time stubs.  A successful application build is
therefore not evidence that the packaged guest exports the same symbols.  This
tool maps public functions to SysCaps and libraries using SDK header metadata,
then checks both library presence and exported symbols in pulled guest files.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


SYSCAP_RE = re.compile(r"@syscap\s+(SystemCapability\.[A-Za-z0-9_.]+)")
LIBRARY_RE = re.compile(r"@library\s+([^\s*]+)")
FUNCTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\((?!\s*\*)")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-native", required=True, type=Path)
    parser.add_argument(
        "--sdk-c-source",
        type=Path,
        help=(
            "Latest interface_sdk_c checkout. When set, use its headers and "
            "*.ndk.json manifests as the ABI contract instead of the possibly "
            "older shared-object stubs bundled with DevEco Studio."
        ),
    )
    parser.add_argument("--runtime-library-index", required=True, type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--device", required=True, choices=("phone", "2in1"))
    parser.add_argument("--arch", required=True, choices=("arm64", "armv7a", "x86_64"))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def sdk_triple(arch: str) -> str:
    return {
        "arm64": "aarch64-linux-ohos",
        "armv7a": "arm-linux-ohos",
        "x86_64": "x86_64-linux-ohos",
    }[arch]


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def declared_function_names(source: str) -> set[str]:
    """Return exported-function candidates from one public header.

    Candidate names are intersected with the SDK stub's dynamic symbol table
    later. Removing preprocessor declarations and typedefs keeps macros,
    opaque types, and callback typedef names out of the ABI contract while
    preserving APIs with prefixes such as napi_, JSVM_, ffrt_, vk and TEEC_.
    """
    code = strip_comments(source)
    code = re.sub(r"^\s*#.*(?:\\\r?\n.*)*", "", code, flags=re.MULTILINE)
    code = re.sub(r"\btypedef\b.*?;", "", code, flags=re.DOTALL)
    return {
        name for name in FUNCTION_RE.findall(code)
        if name not in {"if", "for", "while", "switch", "return", "sizeof", "alignof"}
    }


def exported_symbols(nm: Path, library: Path) -> set[str]:
    result = subprocess.run(
        [str(nm), "-D", "--defined-only", str(library)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        return set()
    symbols = {
        fields[-1].split("@", 1)[0]
        for line in result.stdout.splitlines()
        if (fields := line.split())
    }
    # These are ELF lifecycle entry points emitted by the SDK stub linker, not
    # callable OpenHarmony SDK APIs.
    return symbols - {"_init", "_fini", "_edata", "_end", "__bss_start"}


def resolve_sdk_library(name: str, sdk_lib: Path) -> tuple[str, str | None]:
    candidates = [name]
    if name.endswith(".z.so"):
        candidates.append(name.removesuffix(".z.so") + ".so")
    if not name.startswith("lib"):
        candidates.extend("lib" + candidate for candidate in list(candidates))
    for candidate in candidates:
        if (sdk_lib / candidate).exists():
            return candidate, name if candidate != name else None
    return name, None


def resolve_runtime_library(
    name: str, runtime_paths: dict[str, list[Path]]
) -> tuple[str, str | None]:
    candidates = [name]
    if name.endswith(".z.so"):
        candidates.append(name.removesuffix(".z.so") + ".so")
    if not name.startswith("lib"):
        candidates.extend("lib" + candidate for candidate in list(candidates))
    for candidate in candidates:
        if candidate in runtime_paths:
            return candidate, name if candidate != name else None
    return name, None


def load_ndk_manifest_symbols(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load callable ABI names published by interface_sdk_c.

    The manifest also contains constants and type names. Intersecting these
    names with function declarations parsed from the headers below keeps the
    result limited to callable ABI symbols while retaining every supported
    prefix (OH_, napi_, JSVM_, ffrt_, vk*, TEEC_ and standard-library APIs).
    """
    symbols: dict[str, dict[str, Any]] = {}
    manifests: list[str] = []
    for path in sorted(root.rglob("*.ndk.json")):
        if "zh-cn" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, list):
            continue
        manifests.append(str(path.relative_to(root)))
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                symbols[item["name"]] = {**item, "manifest": str(path.relative_to(root))}
    return symbols, manifests


def runtime_priority(path: Path) -> tuple[int, str]:
    value = "/" + str(path).lstrip("/")
    if "/ndk/" in value:
        rank = 0
    elif re.search(r"/system/lib(?:64)?/[^/]+$", value):
        rank = 1
    elif "/platformsdk/" in value:
        rank = 2
    else:
        rank = 3
    return rank, value


def main() -> int:
    args = arguments()
    sdk = args.sdk_native.resolve()
    source_contract = args.sdk_c_source.resolve() if args.sdk_c_source else None
    include = source_contract or (sdk / "sysroot/usr/include")
    sdk_lib = sdk / "sysroot/usr/lib" / sdk_triple(args.arch)
    nm = sdk / "llvm/bin/llvm-nm"
    matrix = {
        row["syscap"]: row
        for row in json.loads(args.matrix.read_text(encoding="utf-8"))["capabilities"]
    }

    runtime_paths: dict[str, list[Path]] = defaultdict(list)
    for line in args.runtime_library_index.read_text(encoding="utf-8").splitlines():
        if not line.startswith("/"):
            continue
        path = Path(line.strip())
        runtime_paths[path.name].append(path)

    contracts: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    header_files: dict[str, set[str]] = defaultdict(set)
    documentation_name_mismatches: dict[str, set[str]] = defaultdict(set)
    manifest_symbols: dict[str, dict[str, Any]] = {}
    manifest_files: list[str] = []
    if source_contract:
        manifest_symbols, manifest_files = load_ndk_manifest_symbols(source_contract)
    for header in include.rglob("*.h"):
        if source_contract and "zh-cn" in header.parts:
            continue
        source = header.read_text(encoding="utf-8", errors="ignore")
        syscaps = set(SYSCAP_RE.findall(source))
        libraries = {name for name in LIBRARY_RE.findall(source) if name != "NA"}
        if not syscaps or not libraries:
            continue
        functions = declared_function_names(source)
        if source_contract:
            functions &= manifest_symbols.keys()
        for library in libraries:
            if source_contract:
                resolved, documented_name = resolve_runtime_library(library, runtime_paths)
            else:
                resolved, documented_name = resolve_sdk_library(library, sdk_lib)
            if documented_name:
                documentation_name_mismatches[resolved].add(documented_name)
            for syscap in syscaps:
                contracts[syscap][resolved].update(functions)
                header_files[syscap].add(str(header.relative_to(include)))

    # In installed-SDK mode, shared-object stubs are the ABI allowlist. In
    # source mode, *.ndk.json is the allowlist. Header parsing provides the
    # library and SysCap ownership in both modes.
    sdk_library_symbols: dict[str, set[str]] = {}
    for syscap_libraries in contracts.values():
        for library, header_functions in syscap_libraries.items():
            if library not in sdk_library_symbols:
                if source_contract:
                    sdk_library_symbols[library] = set()
                else:
                    stub = sdk_lib / library
                    sdk_library_symbols[library] = (
                        exported_symbols(nm, stub) if stub.exists() else set()
                    )
            if source_contract:
                sdk_library_symbols[library].update(header_functions)

    rows: list[dict[str, Any]] = []
    missing_library_count = 0
    missing_symbol_count = 0
    for syscap in sorted(contracts):
        matrix_device = matrix.get(syscap, {}).get("devices", {}).get(args.device, {})
        libraries: list[dict[str, Any]] = []
        for library, header_functions in sorted(contracts[syscap].items()):
            functions = sdk_library_symbols.get(library, set()) & header_functions
            candidates = sorted(runtime_paths.get(library, []), key=runtime_priority)
            library_row: dict[str, Any] = {
                "library": library,
                "documented_library_aliases": sorted(documentation_name_mismatches[library]),
                "header_function_candidate_count": len(header_functions),
                "sdk_exported_symbol_count": len(functions),
                # Retain the old key for readers written before the complete
                # SDK-stub comparison. It now means all exported ABI symbols.
                "public_function_count": len(functions),
                "runtime_paths": [str(path) for path in candidates],
                "preferred_runtime_path": str(candidates[0]) if candidates else None,
                "status": "present_not_symbol_checked" if candidates else "library_missing",
                "missing_symbols": [],
            }
            if not candidates:
                missing_library_count += 1
            elif args.runtime_root:
                pulled = args.runtime_root / str(candidates[0]).lstrip("/")
                if not pulled.exists():
                    library_row["status"] = "runtime_file_not_pulled"
                else:
                    missing = sorted(functions - exported_symbols(nm, pulled))
                    library_row["missing_symbols"] = missing
                    library_row["status"] = "symbols_missing" if missing else "symbols_match"
                    missing_symbol_count += len(missing)
            libraries.append(library_row)
        rows.append(
            {
                "syscap": syscap,
                "declared": matrix_device.get("declared", False),
                "official_sdk_profile": matrix_device.get("official_sdk_profile", False),
                "declaration_status": matrix_device.get("declaration_status", "not_in_image_matrix"),
                "headers": sorted(header_files[syscap]),
                "libraries": libraries,
            }
        )

    result = {
        "device": args.device,
        "arch": args.arch,
        "sdk_native": str(sdk),
        "sdk_c_source": str(source_contract) if source_contract else None,
        "contract_source": "interface_sdk_c_ndk_manifests" if source_contract else "sdk_stubs",
        "summary": {
            "syscap_contract_count": len(rows),
            "ndk_manifest_count": len(manifest_files),
            "ndk_manifest_symbol_count": len(manifest_symbols),
            "header_backed_manifest_function_count": len(
                set().union(*(set(symbols) for libraries in contracts.values() for symbols in libraries.values()))
            ) if contracts else 0,
            "library_contract_count": sum(len(row["libraries"]) for row in rows),
            "missing_library_contract_count": missing_library_count,
            "missing_symbol_count": missing_symbol_count,
            "official_profile_missing_library_contract_count": sum(
                library["status"] == "library_missing"
                for row in rows
                if row["official_sdk_profile"]
                for library in row["libraries"]
            ),
            "declared_missing_library_contract_count": sum(
                library["status"] == "library_missing"
                for row in rows
                if row["declared"]
                for library in row["libraries"]
            ),
            "official_profile_missing_symbol_count": sum(
                len(library["missing_symbols"])
                for row in rows
                if row["official_sdk_profile"]
                for library in row["libraries"]
            ),
            "declared_missing_symbol_count": sum(
                len(library["missing_symbols"])
                for row in rows
                if row["declared"]
                for library in row["libraries"]
            ),
        },
        "capabilities": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
