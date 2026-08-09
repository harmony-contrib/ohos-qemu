#!/usr/bin/env python3
"""Preserve iptables match/target variants on case-insensitive filesystems."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


SOURCE_RENAMES = {
    "libxt_connmark.c": "libxt_connmark_match_ohos.c",
    "libxt_CONNMARK.c": "libxt_connmark_target_ohos.c",
    "libxt_dscp.c": "libxt_dscp_match_ohos.c",
    "libxt_DSCP.c": "libxt_dscp_target_ohos.c",
    "libxt_mark.c": "libxt_mark_match_ohos.c",
    "libxt_MARK.c": "libxt_mark_target_ohos.c",
    "libxt_rateest.c": "libxt_rateest_match_ohos.c",
    "libxt_RATEEST.c": "libxt_rateest_target_ohos.c",
    "libxt_set.c": "libxt_set_match_ohos.c",
    "libxt_SET.c": "libxt_set_target_ohos.c",
    "libxt_tcpmss.c": "libxt_tcpmss_match_ohos.c",
    "libxt_TCPMSS.c": "libxt_tcpmss_target_ohos.c",
    "libxt_tos.c": "libxt_tos_match_ohos.c",
    "libxt_TOS.c": "libxt_tos_target_ohos.c",
    "libipt_ttl.c": "libipt_ttl_match_ohos.c",
    "libipt_TTL.c": "libipt_ttl_target_ohos.c",
    "libip6t_hl.c": "libip6t_hl_match_ohos.c",
    "libip6t_HL.c": "libip6t_hl_target_ohos.c",
}

HEADER_PAIRS = (
    (
        "include/linux/netfilter/xt_connmark.h",
        "include/linux/netfilter/xt_CONNMARK.h",
    ),
    (
        "include/linux/netfilter/xt_dscp.h",
        "include/linux/netfilter/xt_DSCP.h",
    ),
    (
        "include/linux/netfilter/xt_mark.h",
        "include/linux/netfilter/xt_MARK.h",
    ),
    (
        "include/linux/netfilter/xt_rateest.h",
        "include/linux/netfilter/xt_RATEEST.h",
    ),
    (
        "include/linux/netfilter/xt_tcpmss.h",
        "include/linux/netfilter/xt_TCPMSS.h",
    ),
    (
        "include/linux/netfilter_ipv4/ipt_ttl.h",
        "include/linux/netfilter_ipv4/ipt_TTL.h",
    ),
    (
        "include/linux/netfilter_ipv6/ip6t_hl.h",
        "include/linux/netfilter_ipv6/ip6t_HL.h",
    ),
)

LIBEXT_EXISTING_EXCLUDES = (
    "libxt_cgroup.c",
    "libxt_ipvs.c",
    "libxt_TCPOPTSTRIP.c",
    "libxt_connlabel.c",
    "libxt_dccp.c",
)


def git_blob(repo_root: Path, relative_path: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), "show", f"HEAD:{relative_path}"]
    )


def header_guard(data: bytes) -> str | None:
    match = re.search(rb"(?m)^#ifndef[ \t]+([A-Za-z0-9_]+)[ \t]*$", data)
    return match.group(1).decode() if match else None


def combined_header(lower: bytes, upper: bytes, lower_path: str) -> bytes:
    lower_guard = header_guard(lower)
    upper_guard = header_guard(upper)
    if lower_guard and upper_guard and lower_guard == upper_guard:
        replacement = f"{upper_guard}_OHOS_TARGET_COMPAT".encode()
        upper = upper.replace(upper_guard.encode(), replacement)
    include_target = lower_path.removeprefix("include/").encode()
    upper = re.sub(
        rb"(?m)^#include[ \t]+<"
        + re.escape(include_target)
        + rb">[ \t]*(?:\n|$)",
        b"",
        upper,
    )
    return (
        lower.rstrip()
        + b"\n\n/* Case-insensitive host compatibility: target definitions. */\n"
        + upper.lstrip()
    )


def replace_once_or_verify(text: str, old: str, new: str, source: Path) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"unexpected iptables build layout in {source}: {old!r}")


def patch_build_file(build_file: Path) -> None:
    text = build_file.read_text()
    for original, safe_name in SOURCE_RENAMES.items():
        old = f'"$LIBEXT_COMMON_PATH/{original}"'
        new = f'"$LIBEXT_COMMON_PATH/{safe_name}"'
        text = replace_once_or_verify(text, old, new, build_file)

    libext_excludes = LIBEXT_EXISTING_EXCLUDES + tuple(
        name for name in SOURCE_RENAMES if name.startswith("libxt_")
    )
    old_libext = (
        '"[' + ",".join(LIBEXT_EXISTING_EXCLUDES) + ']",'
    )
    new_libext = '"[' + ",".join(libext_excludes) + ']",'
    text = replace_once_or_verify(text, old_libext, new_libext, build_file)

    old_libext4 = '''args_libext4 = [
  "libipt",
  "[]",
  "initext4.c",
'''
    new_libext4 = '''args_libext4 = [
  "libipt",
  "[libipt_ttl.c,libipt_TTL.c]",
  "initext4.c",
'''
    text = replace_once_or_verify(text, old_libext4, new_libext4, build_file)

    old_libext6 = '''args_libext6 = [
  "libip6t_",
  "[]",
  "initext6.c",
'''
    new_libext6 = '''args_libext6 = [
  "libip6t_",
  "[libip6t_hl.c,libip6t_HL.c]",
  "initext6.c",
'''
    text = replace_once_or_verify(text, old_libext6, new_libext6, build_file)

    warning_line = '    "-Wno-nonportable-include-path",\n'
    if warning_line not in text:
        anchor = '    "-Wno-tautological-pointer-compare",\n'
        if text.count(anchor) != 3:
            raise RuntimeError(
                f"unexpected iptables warning config layout in {build_file}"
            )
        text = text.replace(anchor, anchor + warning_line)
    build_file.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.source_root / "third_party/iptables"
    extensions = repo_root / "extensions"
    collapsed_pairs = [
        (lower, upper)
        for lower, upper in HEADER_PAIRS
        if not (repo_root / lower).exists()
        or not (repo_root / upper).exists()
        or os.path.samefile(repo_root / lower, repo_root / upper)
    ]
    if not collapsed_pairs:
        print("iptables case variants are distinct; no compatibility fix needed")
        return 0

    for original, safe_name in SOURCE_RENAMES.items():
        destination = extensions / safe_name
        destination.write_bytes(git_blob(repo_root, f"extensions/{original}"))

    for lower, upper in HEADER_PAIRS:
        lower_path = repo_root / lower
        upper_path = repo_root / upper
        if (lower, upper) not in collapsed_pairs:
            continue
        lower_blob = git_blob(repo_root, lower)
        upper_blob = git_blob(repo_root, upper)
        lower_path.parent.mkdir(parents=True, exist_ok=True)

        # A checkout copied from a case-insensitive host into a Linux volume
        # can contain only one member of the pair. Recreate both names from
        # Git first. They remain independent on a case-sensitive volume; on
        # macOS both paths still alias and need the combined-header fallback.
        lower_path.write_bytes(lower_blob)
        upper_path.write_bytes(upper_blob)
        if os.path.samefile(lower_path, upper_path):
            lower_path.write_bytes(
                combined_header(lower_blob, upper_blob, lower)
            )

    patch_build_file(extensions / "BUILD.gn")
    print(
        "configured case-insensitive iptables compatibility: "
        f"{len(SOURCE_RENAMES)} uniquely named sources and "
        f"{len(collapsed_pairs)} restored/collapsed header pairs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
