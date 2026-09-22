#!/usr/bin/env python3
"""Build an exhaustive OpenHarmony capability and device-boundary audit index.

The output deliberately separates declaration evidence from runtime evidence.
Presence in syscap.json, a bundle.json, or an XTS source tree is never reported
as proof that the capability works on the packaged emulator.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SYSCAP_RE = re.compile(r"@syscap\s+([^\s*]+)")
DOCUMENTED_SYSCAP_RE = re.compile(r"SystemCapability\.[A-Za-z0-9_.]+")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
METHOD_RE = re.compile(
    r"(?:OH_[A-Za-z0-9_]+|[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)\s*\("
)
EXACT_SYSCAP_RE = re.compile(r"^SystemCapability\.[A-Za-z0-9_.]+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ohos-root", required=True, type=Path)
    parser.add_argument("--docs-root", type=Path)
    parser.add_argument("--sdk-js-root", type=Path)
    parser.add_argument("--sdk-c-root", type=Path)
    parser.add_argument("--phone-syscap", required=True, type=Path)
    parser.add_argument("--two-in-one-syscap", required=True, type=Path)
    parser.add_argument("--findings", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rg_files(root: Path, *paths: str, glob: str) -> list[Path]:
    command = ["rg", "--files"]
    existing_paths = [path for path in paths if (root / path).exists()]
    command.extend(existing_paths)
    command.extend(["-g", glob])
    result = subprocess.run(
        command,
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return [root / line for line in result.stdout.splitlines() if line]


def load_image_syscaps(path: Path) -> tuple[set[str], dict[str, list[str]]]:
    data = read_json(path)
    caps: set[str] = set()
    components: dict[str, list[str]] = defaultdict(list)
    for component in data.get("components", []):
        component_name = component.get("component", "")
        for cap in component.get("syscap", []):
            if not isinstance(cap, str) or not EXACT_SYSCAP_RE.fullmatch(cap):
                continue
            caps.add(cap)
            if component_name:
                components[cap].append(component_name)
    return caps, dict(components)


def load_sdk_profiles(sdk_js_root: Path) -> dict[str, set[str]]:
    profile_root = sdk_js_root / "api/device-define"
    profiles: dict[str, set[str]] = {}
    for path in sorted(profile_root.glob("*.json")):
        data = read_json(path)
        profiles[path.stem] = set(data.get("SysCaps", []))
    if "default" not in profiles or "2in1" not in profiles:
        raise RuntimeError("SDK default.json and 2in1.json are required")
    return profiles


def load_documented_device_profiles(docs_root: Path) -> dict[str, set[str]]:
    """Load the human-readable minimum device profiles from OHOS 7 docs.

    The SDK and documentation are independent release artifacts and currently
    disagree.  Keeping both prevents the audit from silently dropping a
    documented phone capability merely because ``default.json`` omitted it.
    There is no separate PC/2in1 document, so the tablet list is retained as a
    comparison profile and is not treated as an exact 2in1 requirement.
    """
    reference = docs_root / "zh-cn/application-dev/reference"
    result: dict[str, set[str]] = {}
    for name, filename in (
        ("phone", "phone-syscap-list.md"),
        ("tablet_reference_for_2in1", "tablet-syscap-list.md"),
    ):
        text = (reference / filename).read_text(encoding="utf-8", errors="ignore")
        result[name] = set(
            re.findall(r"^-\s+(SystemCapability\.[A-Za-z0-9_.]+)\s*$", text, re.MULTILINE)
        )
    return result


def load_bundle_index(root: Path) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    registry: set[str] = set()
    for path in rg_files(root, glob="bundle.json"):
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        component = data.get("component") or {}
        entry = {
            "path": str(path.relative_to(root)),
            "component": component.get("name"),
            "subsystem": component.get("subsystem"),
            "adapted_system_type": component.get("adapted_system_type") or [],
            "features": component.get("features") or [],
        }
        for cap in component.get("syscap") or []:
            if not isinstance(cap, str) or not EXACT_SYSCAP_RE.fullmatch(cap):
                continue
            registry.add(cap)
            index[cap].append(entry)
    return dict(index), registry


def load_annotation_index(
    root: Path, paths: Iterable[str], glob: str
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    counts: Counter[str] = Counter()
    files: dict[str, set[str]] = defaultdict(set)
    registry: set[str] = set()
    for path in rg_files(root, *paths, glob=glob):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for cap in SYSCAP_RE.findall(text):
            cap = cap.rstrip(".,;")
            if not cap.startswith("SystemCapability."):
                continue
            counts[cap] += 1
            files[cap].add(str(path.relative_to(root)))
            registry.add(cap)
    return {
        cap: {"annotation_count": counts[cap], "files": sorted(files[cap])}
        for cap in sorted(registry)
    }, registry


def collect_syscap_strings(value: Any, output: set[str]) -> None:
    # Some test manifests contain expressions such as
    # "SystemCapability.Foo = false".  Those are configuration snippets, not
    # SysCap identifiers, and must not create fake public capabilities.
    if isinstance(value, str) and EXACT_SYSCAP_RE.fullmatch(value):
        output.add(value)
    elif isinstance(value, list):
        for item in value:
            collect_syscap_strings(item, output)
    elif isinstance(value, dict):
        for item in value.values():
            collect_syscap_strings(item, output)


def load_xts_index(root: Path) -> tuple[dict[str, list[str]], set[str]]:
    files: dict[str, set[str]] = defaultdict(set)
    registry: set[str] = set()
    for path in rg_files(root, "test/xts", glob="syscap.json"):
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        caps: set[str] = set()
        collect_syscap_strings(data, caps)
        for cap in caps:
            files[cap].add(str(path.relative_to(root)))
            registry.add(cap)
    return {cap: sorted(values) for cap, values in files.items()}, registry


def section_end(lines: list[str], heading_index: int, heading_level: int) -> int:
    """Find the end of the documentation section owning a SysCap marker."""
    for index in range(heading_index + 1, len(lines)):
        heading = HEADING_RE.match(lines[index])
        if heading and len(heading.group(1)) <= heading_level:
            return index
    return len(lines)


def extract_api_version(heading: str, section: list[str]) -> int | None:
    heading_match = re.search(r"<sup>\s*(\d+)\+?\s*</sup>", heading, re.IGNORECASE)
    if heading_match:
        return int(heading_match.group(1))
    for line in section[:24]:
        match = re.search(r"(?:起始版本|从API version)\s*[：:]?\s*(\d+)", line, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def extract_signature(lines: list[str]) -> str:
    """Extract the first source-like signature below a documentation heading."""
    in_fence = False
    for raw in lines[:36]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not stripped or stripped.startswith(("<!--", "**", "|", ">", "#")):
            continue
        candidate = compact_text(stripped)
        if not candidate:
            continue
        if in_fence and ("(" in candidate or candidate.startswith(("struct ", "enum ", "class "))):
            return candidate
        if re.search(r"(?:OH_[A-Za-z0-9_]+|[A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)", candidate):
            return candidate
    return ""


def load_documented_api_index(
    root: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], set[str]]:
    """Index every documented API section, inheriting file-level contracts.

    Many Native API pages state their SysCap once in ``概述`` and omit it from
    every function below.  Looking only for method-local SysCap markers drops
    thousands of C functions.  This parser starts from API headings and uses a
    method-local contract when present, otherwise the file's leading contract.
    Entries whose documentation has no SysCap at either scope stay in the
    inventory with ``syscap=None`` so the omission cannot disappear silently.
    """
    reference_root = root / "zh-cn/application-dev/reference"
    rows: list[dict[str, Any]] = []
    registry: set[str] = set()
    per_cap_count: Counter[str] = Counter()
    per_cap_files: dict[str, set[str]] = defaultdict(set)
    doc_paths = rg_files(root, str(reference_root.relative_to(root)), glob="*.md")
    doc_lines: dict[Path, list[str]] = {}
    direct_file_caps: dict[Path, set[str]] = {}
    for doc_path in doc_paths:
        try:
            cached_lines = doc_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        doc_lines[doc_path.resolve()] = cached_lines
        direct_file_caps[doc_path.resolve()] = {
            cap.rstrip(".,;:）)")
            for line in cached_lines
            if re.search(r"系统能力|SystemCapability", line)
            for cap in DOCUMENTED_SYSCAP_RE.findall(line)
            if "xxx" not in cap.lower()
        }

    for path in doc_paths:
        # Error-code guides contain troubleshooting snippets that look like
        # function signatures, but they are not API declaration pages.
        if path.name.startswith("errorcode-"):
            continue
        lines = doc_lines.get(path.resolve())
        if lines is None:
            continue
        headings: list[tuple[int, int, str, str]] = []
        for index, line in enumerate(lines):
            heading_match = HEADING_RE.match(line)
            if heading_match:
                raw_heading = heading_match.group(2).strip()
                headings.append(
                    (
                        index,
                        len(heading_match.group(1)),
                        raw_heading,
                        compact_text(raw_heading),
                    )
                )

        generic_headings = {
            "汇总", "概述", "导入模块", "使用说明", "函数说明", "属性说明",
            "接口说明", "类说明", "枚举说明", "结构体说明", "类型说明",
            "常量说明", "字段说明", "成员函数说明", "成员变量说明", "错误码",
            "错误码异常处理", "相关实例", "系统能力说明",
        }
        provisional_api_indices = []
        for heading_index, _level, raw_heading, heading_label in headings:
            probe = lines[heading_index + 1 : min(len(lines), heading_index + 38)]
            if (
                "(" in heading_label
                or extract_signature(probe)
                or (
                    extract_api_version(raw_heading, probe) is not None
                    and heading_label not in generic_headings
                )
            ):
                provisional_api_indices.append(heading_index)
        first_api_heading = min(provisional_api_indices, default=min(len(lines), 160))
        leading_lines = lines[:first_api_heading]
        module_constraint = device_constraint_text(leading_lines)

        def caps_in(section_lines: list[str]) -> set[str]:
            return {
                cap.rstrip(".,;:）)")
                for section_line in section_lines
                if re.search(r"系统能力|SystemCapability", section_line)
                for cap in DOCUMENTED_SYSCAP_RE.findall(section_line)
                if "xxx" not in cap.lower()
            }

        file_caps = caps_in(leading_lines)
        if not file_caps:
            # Use the first explicit contract as the file fallback.  Do not
            # union every method-local SysCap: some modules intentionally use
            # different capabilities for different methods.
            for section_line in lines:
                first_caps = caps_in([section_line])
                if first_caps:
                    file_caps = first_caps
                    break
        if not file_caps:
            # Struct/type pages often omit SysCap but link their owning C
            # header or module.  Follow those local documentation links and
            # inherit the linked file's explicit contract.
            for link in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]+)?\)", "\n".join(lines[:100])):
                target = (path.parent / link).resolve()
                linked_caps = direct_file_caps.get(target, set())
                if linked_caps:
                    file_caps = linked_caps
                    break

        seen_entries: set[tuple[int, str | None]] = set()
        for heading_position, (heading_index, heading_level, heading, heading_label) in enumerate(headings):
            end = section_end(lines, heading_index, heading_level)
            section = lines[heading_index:end]
            heading_plain = compact_text(
                re.sub(r"<sup>.*?</sup>", "", heading, flags=re.IGNORECASE)
            )
            signature = extract_signature(section[1:])
            start_version = extract_api_version(heading, section)
            explicit_caps = caps_in(section)
            is_module_entry = heading_plain in {"概述", "系统能力说明"} and bool(explicit_caps)
            is_api_entry = heading_plain not in generic_headings and (
                "(" in heading_plain
                or bool(signature)
                or (start_version is not None and heading_plain not in generic_headings)
            )
            if not is_module_entry and not is_api_entry:
                continue

            effective_caps: list[str | None] = sorted(explicit_caps or file_caps) or [None]
            boundary_blocks = [
                device_boundary_block(section, boundary_index)
                for boundary_index, boundary_line in enumerate(section)
                if "设备行为差异" in boundary_line
            ]
            section_constraint = device_constraint_text(section)
            boundary_text = compact_text(
                " ".join(boundary_blocks or ([section_constraint] if section_constraint else []))
            )
            effective_constraint = boundary_text or module_constraint
            permission_lines = [
                compact_text(section_line)
                for section_line in section
                if re.search(r"\*\*(?:需要权限|权限要求|权限)\s*[：:]", section_line)
            ]
            if is_module_entry:
                entry_kind = "module_or_header"
            elif "(" in heading_plain or signature:
                entry_kind = "callable"
            else:
                entry_kind = "type_or_constant"
            for cap in effective_caps:
                key = (heading_index, cap)
                if key in seen_entries:
                    continue
                seen_entries.add(key)
                if cap is not None:
                    registry.add(cap)
                    per_cap_count[cap] += 1
                    per_cap_files[cap].add(str(path.relative_to(root)))
                rows.append(
                    {
                        "syscap": cap,
                        "source": str(path.relative_to(root)),
                        "line": heading_index + 1,
                        "heading": heading_plain,
                        "signature": signature,
                        "entry_kind": entry_kind,
                        "start_api_version": start_version,
                        "system_api": any("系统接口" in value for value in section[:36]),
                        "deprecated": any("废弃" in value for value in section[:36]),
                        "permissions": permission_lines,
                        "device_boundary": effective_constraint,
                        "device_boundary_scope": (
                            "method" if boundary_text else ("module" if module_constraint else "none")
                        ),
                        "phone_documented_behavior": (
                            infer_device_behavior(effective_constraint, "phone")
                            if effective_constraint
                            else "default_contract"
                        ),
                        "2in1_documented_behavior": (
                            infer_device_behavior(effective_constraint, "2in1")
                            if effective_constraint
                            else "default_contract"
                        ),
                    }
                )
    rows.sort(key=lambda row: (row["syscap"] or "", row["source"], row["line"]))
    index = {
        cap: {
            "entry_count": per_cap_count[cap],
            "files": sorted(per_cap_files[cap]),
        }
        for cap in sorted(registry)
    }
    return rows, index, registry


def compact_text(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*`|>]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


DEVICE_NAME_RE = re.compile(
    r"(?:(?<![A-Za-z])(?:Phone|phone|PHONE)(?![A-Za-z])|手机|"
    r"PC\s*/\s*2in1|PC/2in1|2in1|PC设备|"
    r"(?<![A-Za-z])Tablet(?![A-Za-z])|平板|"
    r"(?<![A-Za-z])Wearable(?![A-Za-z])|穿戴|"
    r"(?<![A-Za-z])TV(?![A-Za-z])|智慧屏|"
    r"(?<![A-Za-z])Car(?![A-Za-z])|车机)"
)
DEVICE_CONTRACT_RE = re.compile(
    r"(?:设备行为差异|仅支持|仅在|只支持|只在|适用于|可正常|正常调用|"
    r"不支持|不可用|不生效|返回\s*\d+\s*错误码|新增支持|设备使用)"
)


def device_constraint_text(lines: list[str]) -> str:
    """Collect device-family contracts even when docs omit the standard marker.

    OpenHarmony reference pages use both a formal ``设备行为差异`` field and
    prose notes such as ``本模块仅支持PC/2in1设备``.  The old audit only read the
    former and silently lost module-wide and partial-device restrictions.
    """
    selected: list[str] = []
    for line in lines:
        normalized = compact_text(line)
        if not normalized or not DEVICE_NAME_RE.search(normalized):
            continue
        if DEVICE_CONTRACT_RE.search(normalized):
            selected.append(normalized)
    return compact_text(" ".join(dict.fromkeys(selected)))


def device_named(text: str, device: str) -> bool:
    if device == "phone":
        return bool(re.search(r"(?:(?<![A-Za-z])(?:Phone|phone|PHONE)(?![A-Za-z])|手机)", text))
    return bool(re.search(r"(?:PC\s*/\s*2in1|PC/2in1|2in1|PC设备|PC中|PC和)", text))


FAILURE_WORDS = (
    "不支持",
    "返回",
    "不生效",
    "无效果",
    "无法",
    "不可",
    "未定义",
    "不执行",
    "异常",
)
SUCCESS_WORDS = ("正常使用", "正常调用", "正常执行", "正常生效", "支持", "可用", "生效")


def infer_device_behavior(text: str, device: str) -> str:
    """Classify the documented behavior for one device family.

    This records the API 26 documentation contract, not emulator runtime
    success. Conditional hardware, policy and window-mode contracts remain
    explicit so they cannot be mistaken for unconditional support.
    """
    normalized = compact_text(text)
    if not normalized or normalized.rstrip("：:") == "设备行为差异":
        return "review_required"

    if any(word in normalized for word in ("真机调试", "硬件支持", "器件", "发射器", "部分Phone")):
        return "conditional_hardware"
    if any(word in normalized for word in ("企业策略", "企业管控")):
        return "conditional_policy"
    if any(word in normalized for word in ("自由窗口", "电脑模式", "折叠设备", "折叠屏")):
        return "conditional_mode"

    # Documentation containing versioned bullets is assembled newest first.
    # API 26 is the audit target, so classify the first applicable bullet only.
    versioned = re.split(r"(?=从API version\s*\d+|API版本\s*\d+(?:\.\d+\.\d+)?\+)", normalized)
    versioned = [item for item in versioned if re.search(r"(?:从API version|API版本)", item)]
    if versioned:
        normalized = versioned[0]

    other = re.search(r"(?:在)?(?:其他|其余)设备(?:类型)?(?:中|上)?", normalized)
    if other:
        before = normalized[: other.start()]
        after = normalized[other.start() :]
        before_success = any(word in before for word in SUCCESS_WORDS)
        before_failure = any(word in before for word in FAILURE_WORDS)
        after_success = any(word in after for word in SUCCESS_WORDS)
        after_failure = any(word in after for word in FAILURE_WORDS)
        named_before = device_named(before, device)

        if named_before and before_success and after_failure:
            return "supported"
        if named_before and before_failure and after_success:
            return "unsupported"
        if not named_before and before_failure and after_success:
            return "supported"
        if not named_before and before_success and after_failure:
            return "unsupported"

    only = re.search(r"(?:仅支持|仅在|只支持|只在)(.+)", normalized)
    if only:
        scope = re.split(r"(?:中|上)?(?:可正常|正常|支持|生效|设备)", only.group(1), maxsplit=1)[0]
        return "supported" if device_named(scope, device) else "unsupported"

    applicable = re.search(r"(?:适用于|支持在?)(.+)", normalized)
    if applicable and DEVICE_NAME_RE.search(applicable.group(1)):
        # Phrases that explicitly enumerate supported device families are a
        # positive allow-list.  This also handles API-26 notes such as
        # "新增支持在手机、平板上使用".
        scope = re.split(r"(?:设备)?(?:使用|调用|运行|，|。)", applicable.group(1), maxsplit=1)[0]
        return "supported" if device_named(scope, device) else "unsupported"

    # A statement that names only another family as failing is an explicit
    # device exception. Phone and 2in1 therefore follow the general contract.
    if any(word in normalized for word in FAILURE_WORDS):
        named_target = device_named(normalized, device)
        named_other_family = bool(re.search(r"Wearable|TV|Car|Tablet", normalized))
        if named_target:
            return "unsupported"
        if named_other_family:
            return "supported"

    return "review_required"


def device_boundary_block(lines: list[str], index: int) -> str:
    """Return the marker line plus any continuation bullets/paragraph."""
    collected = [lines[index]]
    marker_has_contract = len(compact_text(lines[index]).rstrip("：:")) > len("设备行为差异")
    if marker_has_contract:
        return lines[index]
    for line in lines[index + 1 : index + 12]:
        stripped = line.strip()
        if not stripped:
            if len(collected) > 1:
                break
            continue
        if HEADING_RE.match(stripped) or re.match(r"\*\*(?:参数|返回值|错误码|系统能力|系统接口)", stripped):
            break
        if stripped.startswith("|"):
            break
        collected.append(stripped)
    return " ".join(collected)


def load_device_boundaries(root: Path) -> list[dict[str, Any]]:
    reference_root = root / "zh-cn/application-dev/reference"
    rows: list[dict[str, Any]] = []
    for path in rg_files(root, str(reference_root.relative_to(root)), glob="*.md"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        headings: list[tuple[int, str]] = []
        for line_number, line in enumerate(lines, 1):
            heading = HEADING_RE.match(line)
            if heading:
                headings.append((line_number, compact_text(heading.group(2))))
            if "设备行为差异" not in line:
                continue
            nearest_heading = ""
            for heading_line, heading_text in reversed(headings):
                if heading_line <= line_number:
                    nearest_heading = heading_text
                    break
            block = device_boundary_block(lines, line_number - 1)
            methods = METHOD_RE.findall(block)
            rows.append(
                {
                    "source": str(path.relative_to(root)),
                    "line": line_number,
                    "heading": nearest_heading,
                    "methods_on_line": sorted(set(method.rstrip("(").strip() for method in methods)),
                    "phone": infer_device_behavior(block, "phone"),
                    "2in1": infer_device_behavior(block, "2in1"),
                    "text": compact_text(block),
                }
            )
    return rows


def finding_matches(finding: dict[str, Any], cap: str) -> bool:
    match = finding.get("match") or {}
    if cap in set(match.get("exact") or []):
        return True
    return any(cap.startswith(prefix) for prefix in match.get("prefixes") or [])


def declaration_status(declared: bool, expected: bool) -> str:
    if declared and expected:
        return "declared_as_expected"
    if declared:
        return "declared_outside_official_profile"
    if expected:
        return "missing_from_image"
    return "not_declared_for_device"


def base_audit_status(declared: bool, expected: bool) -> str:
    if declared and not expected:
        return "invalid_declaration"
    if expected and not declared:
        return "missing_capability"
    if declared and expected:
        return "runtime_validation_required"
    return "not_applicable"


def main() -> int:
    args = parse_args()
    root = args.ohos_root.resolve()
    docs_root = (args.docs_root or (root / "docs")).resolve()
    sdk_js_root = (args.sdk_js_root or (root / "interface/sdk-js")).resolve()
    sdk_c_root = (args.sdk_c_root or (root / "interface/sdk_c")).resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    phone_caps, phone_components = load_image_syscaps(args.phone_syscap)
    two_caps, two_components = load_image_syscaps(args.two_in_one_syscap)
    profiles = load_sdk_profiles(sdk_js_root)
    documented_profiles = load_documented_device_profiles(docs_root)
    phone_expected = profiles["default"]
    two_expected = profiles["2in1"]
    phone_documented = documented_profiles["phone"]
    tablet_reference = documented_profiles["tablet_reference_for_2in1"]

    bundles, bundle_registry = load_bundle_index(root)
    arkts, arkts_registry = load_annotation_index(
        sdk_js_root, ("api", "kits"), "*.d.ts"
    )
    capi, capi_registry = load_annotation_index(
        sdk_c_root, (".",), "*.h"
    )
    xts, xts_registry = load_xts_index(root)
    documented_apis, documented_api_index, documented_registry = load_documented_api_index(docs_root)
    boundaries = load_device_boundaries(docs_root)

    findings = []
    if args.findings:
        findings = read_json(args.findings).get("findings", [])

    advertised_universe = sorted(
        phone_caps | two_caps | phone_expected | two_expected | phone_documented
    )
    registry_universe = sorted(
        set().union(
            *profiles.values(),
            *documented_profiles.values(),
            phone_caps,
            two_caps,
            bundle_registry,
            arkts_registry,
            capi_registry,
            documented_registry,
        )
    )

    def build_capability_row(cap: str) -> dict[str, Any]:
        item: dict[str, Any] = {
            "syscap": cap,
            "image_components": {
                "phone": phone_components.get(cap, []),
                "2in1": two_components.get(cap, []),
            },
            "bundle_definitions": bundles.get(cap, []),
            "arkts": arkts.get(cap, {"annotation_count": 0, "files": []}),
            "c_api": capi.get(cap, {"annotation_count": 0, "files": []}),
            "xts": {"source_count": len(xts.get(cap, [])), "files": xts.get(cap, [])},
            "documented_api": documented_api_index.get(cap, {"entry_count": 0, "files": []}),
            "devices": {},
        }
        matching_findings = [finding for finding in findings if finding_matches(finding, cap)]
        for device, declared, expected, documented_expected, reference_only in (
            ("phone", cap in phone_caps, cap in phone_expected, cap in phone_documented, False),
            ("2in1", cap in two_caps, cap in two_expected, cap in tablet_reference, True),
        ):
            device_findings = [
                {
                    "id": finding.get("id"),
                    **(finding.get("devices", {}).get(device) or {}),
                }
                for finding in matching_findings
                if finding.get("devices", {}).get(device)
            ]
            contract_expected = expected or (documented_expected and not reference_only)
            status = base_audit_status(declared, contract_expected)
            if device_findings:
                status = device_findings[0].get("status", status)
            item["devices"][device] = {
                "declared": declared,
                "official_sdk_profile": expected,
                "documented_minimum_profile": documented_expected,
                "documented_profile_is_reference_only": reference_only,
                "contract_expected": contract_expected,
                "profile_source_status": (
                    "matches"
                    if expected == documented_expected
                    else ("sdk_only" if expected else "documentation_only")
                ),
                "declaration_status": declaration_status(declared, expected),
                "contract_declaration_status": declaration_status(declared, contract_expected),
                "audit_status": status,
                "findings": device_findings,
            }
        return item

    all_rows = [build_capability_row(cap) for cap in registry_universe]
    rows = [item for item in all_rows if item["syscap"] in advertised_universe]

    write_json(output / "advertised-capability-matrix.json", {"capabilities": rows})
    write_json(output / "all-capability-matrix.json", {"capabilities": all_rows})
    with (output / "advertised-capability-matrix.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        fieldnames = [
            "syscap",
            "phone_declared",
            "phone_official_profile",
            "phone_documented_profile",
            "phone_contract_expected",
            "phone_declaration_status",
            "phone_contract_declaration_status",
            "phone_audit_status",
            "2in1_declared",
            "2in1_official_profile",
            "2in1_tablet_reference_profile",
            "2in1_declaration_status",
            "2in1_audit_status",
            "components",
            "arkts_annotations",
            "c_api_annotations",
            "xts_source_count",
            "documented_api_entries",
            "finding_ids",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for item in rows:
            finding_ids = sorted(
                {
                    finding.get("id", "")
                    for device in item["devices"].values()
                    for finding in device["findings"]
                    if finding.get("id")
                }
            )
            writer.writerow(
                {
                    "syscap": item["syscap"],
                    "phone_declared": item["devices"]["phone"]["declared"],
                    "phone_official_profile": item["devices"]["phone"]["official_sdk_profile"],
                    "phone_documented_profile": item["devices"]["phone"]["documented_minimum_profile"],
                    "phone_contract_expected": item["devices"]["phone"]["contract_expected"],
                    "phone_declaration_status": item["devices"]["phone"]["declaration_status"],
                    "phone_contract_declaration_status": item["devices"]["phone"]["contract_declaration_status"],
                    "phone_audit_status": item["devices"]["phone"]["audit_status"],
                    "2in1_declared": item["devices"]["2in1"]["declared"],
                    "2in1_official_profile": item["devices"]["2in1"]["official_sdk_profile"],
                    "2in1_tablet_reference_profile": item["devices"]["2in1"]["documented_minimum_profile"],
                    "2in1_declaration_status": item["devices"]["2in1"]["declaration_status"],
                    "2in1_audit_status": item["devices"]["2in1"]["audit_status"],
                    "components": ";".join(
                        sorted(
                            set(item["image_components"]["phone"])
                            | set(item["image_components"]["2in1"])
                        )
                    ),
                    "arkts_annotations": item["arkts"]["annotation_count"],
                    "c_api_annotations": item["c_api"]["annotation_count"],
                    "xts_source_count": item["xts"]["source_count"],
                    "documented_api_entries": item["documented_api"]["entry_count"],
                    "finding_ids": ";".join(finding_ids),
                }
            )

    registry_rows = []
    for cap in registry_universe:
        registry_rows.append(
            {
                "syscap": cap,
                "advertised_or_expected": cap in advertised_universe,
                "sdk_profiles": sorted(name for name, values in profiles.items() if cap in values),
                "documented_device_profiles": sorted(
                    name for name, values in documented_profiles.items() if cap in values
                ),
                "bundle_definition_count": len(bundles.get(cap, [])),
                "arkts_annotation_count": arkts.get(cap, {}).get("annotation_count", 0),
                "c_api_annotation_count": capi.get(cap, {}).get("annotation_count", 0),
                "xts_source_count": len(xts.get(cap, [])),
                "documented_api_entry_count": documented_api_index.get(cap, {}).get(
                    "entry_count", 0
                ),
            }
        )
    write_json(output / "ohos-public-syscap-registry.json", {"capabilities": registry_rows})
    write_json(output / "public-api-inventory.json", {"entries": documented_apis})
    with (output / "public-api-inventory.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        fieldnames = (
            "syscap",
            "source",
            "line",
            "heading",
            "signature",
            "entry_kind",
            "start_api_version",
            "system_api",
            "deprecated",
            "permissions",
            "phone_documented_behavior",
            "2in1_documented_behavior",
            "device_boundary",
            "device_boundary_scope",
        )
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in documented_apis:
            writer.writerow({**row, "permissions": ";".join(row["permissions"])})
    write_json(output / "method-device-boundaries.json", {"boundaries": boundaries})
    with (output / "method-device-boundaries.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "source",
                "line",
                "heading",
                "methods_on_line",
                "phone",
                "2in1",
                "text",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in boundaries:
            writer.writerow({**row, "methods_on_line": ";".join(row["methods_on_line"])})

    status_counts: dict[str, Counter[str]] = {"phone": Counter(), "2in1": Counter()}
    declaration_counts: dict[str, Counter[str]] = {"phone": Counter(), "2in1": Counter()}
    for item in rows:
        for device in ("phone", "2in1"):
            status_counts[device][item["devices"][device]["audit_status"]] += 1
            declaration_counts[device][item["devices"][device]["declaration_status"]] += 1
    boundary_counts = {
        device: dict(Counter(row[device] for row in boundaries))
        for device in ("phone", "2in1")
    }
    summary = {
        "advertised_or_expected_capability_count": len(advertised_universe),
        "ohos_public_syscap_registry_count": len(registry_universe),
        "phone": {
            "image_declared": len(phone_caps),
            "official_sdk_profile": len(phone_expected),
            "documented_minimum_profile": len(phone_documented),
            "documented_not_in_sdk_profile": len(phone_documented - phone_expected),
            "sdk_not_in_documented_profile": len(phone_expected - phone_documented),
            "declaration_counts": dict(declaration_counts["phone"]),
            "audit_status_counts": dict(status_counts["phone"]),
        },
        "2in1": {
            "image_declared": len(two_caps),
            "official_sdk_profile": len(two_expected),
            "tablet_reference_profile": len(tablet_reference),
            "tablet_reference_not_in_sdk_profile": len(tablet_reference - two_expected),
            "sdk_not_in_tablet_reference_profile": len(two_expected - tablet_reference),
            "declaration_counts": dict(declaration_counts["2in1"]),
            "audit_status_counts": dict(status_counts["2in1"]),
        },
        "api_index": {
            "arkts_syscap_count": len(arkts),
            "c_api_syscap_count": len(capi),
            "xts_syscap_count": len(xts),
            "documented_syscap_count": len(documented_api_index),
            "documented_api_entry_count": len(documented_apis),
            "documented_callable_count": sum(
                row["entry_kind"] == "callable" for row in documented_apis
            ),
        },
        "method_device_boundaries": {
            "count": len(boundaries),
            "classification": boundary_counts,
        },
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
