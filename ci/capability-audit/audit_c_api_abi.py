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
FUNCTION_RE = re.compile(r"\b((?:OH_|OHOS_)[A-Za-z0-9_]+)\s*\((?!\s*\*)")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-native", required=True, type=Path)
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
    return {
        fields[-1].split("@", 1)[0]
        for line in result.stdout.splitlines()
        if (fields := line.split())
    }


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
    include = sdk / "sysroot/usr/include"
    sdk_lib = sdk / "sysroot/usr/lib" / sdk_triple(args.arch)
    nm = sdk / "llvm/bin/llvm-nm"
    matrix = {
        row["syscap"]: row
        for row in json.loads(args.matrix.read_text(encoding="utf-8"))["capabilities"]
    }

    contracts: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    header_files: dict[str, set[str]] = defaultdict(set)
    documentation_name_mismatches: dict[str, set[str]] = defaultdict(set)
    for header in include.rglob("*.h"):
        source = header.read_text(encoding="utf-8", errors="ignore")
        syscaps = set(SYSCAP_RE.findall(source))
        libraries = {name for name in LIBRARY_RE.findall(source) if name != "NA"}
        if not syscaps or not libraries:
            continue
        code = strip_comments(source)
        macros = set(
            re.findall(
                r"^\s*#\s*define\s+((?:OH_|OHOS_)[A-Za-z0-9_]+)\s*\(",
                code,
                flags=re.MULTILINE,
            )
        )
        functions = set(FUNCTION_RE.findall(code)) - macros
        functions = {name for name in functions if not re.fullmatch(r"[A-Z0-9_]+", name)}
        for library in libraries:
            resolved, documented_name = resolve_sdk_library(library, sdk_lib)
            if documented_name:
                documentation_name_mismatches[resolved].add(documented_name)
            for syscap in syscaps:
                contracts[syscap][resolved].update(functions)
                header_files[syscap].add(str(header.relative_to(include)))

    runtime_paths: dict[str, list[Path]] = defaultdict(list)
    for line in args.runtime_library_index.read_text(encoding="utf-8").splitlines():
        if not line.startswith("/"):
            continue
        path = Path(line.strip())
        runtime_paths[path.name].append(path)

    rows: list[dict[str, Any]] = []
    missing_library_count = 0
    missing_symbol_count = 0
    for syscap in sorted(contracts):
        matrix_device = matrix.get(syscap, {}).get("devices", {}).get(args.device, {})
        libraries: list[dict[str, Any]] = []
        for library, functions in sorted(contracts[syscap].items()):
            candidates = sorted(runtime_paths.get(library, []), key=runtime_priority)
            library_row: dict[str, Any] = {
                "library": library,
                "documented_library_aliases": sorted(documentation_name_mismatches[library]),
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
        "summary": {
            "syscap_contract_count": len(rows),
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
