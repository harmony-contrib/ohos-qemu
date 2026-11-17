#!/usr/bin/env python3
"""Restore Linux netfilter case-distinct files on case-insensitive hosts."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


HEADER_COPIES = {
    "include/uapi/linux/netfilter/xt_connmark.h":
        "include/uapi/linux/netfilter/xt_connmark_ohos.h",
    "include/uapi/linux/netfilter/xt_mark.h":
        "include/uapi/linux/netfilter/xt_mark_ohos.h",
    "include/uapi/linux/netfilter/xt_DSCP.h":
        "include/uapi/linux/netfilter/xt_dscp_ohos_target.h",
    "include/uapi/linux/netfilter/xt_dscp.h":
        "include/uapi/linux/netfilter/xt_dscp_ohos_match.h",
    "include/uapi/linux/netfilter/xt_RATEEST.h":
        "include/uapi/linux/netfilter/xt_rateest_ohos_target.h",
    "include/uapi/linux/netfilter/xt_rateest.h":
        "include/uapi/linux/netfilter/xt_rateest_ohos_match.h",
    "include/uapi/linux/netfilter/xt_TCPMSS.h":
        "include/uapi/linux/netfilter/xt_tcpmss_ohos_target.h",
    "include/uapi/linux/netfilter/xt_tcpmss.h":
        "include/uapi/linux/netfilter/xt_tcpmss_ohos_match.h",
    "include/uapi/linux/netfilter_ipv4/ipt_ECN.h":
        "include/uapi/linux/netfilter_ipv4/ipt_ecn_ohos_target.h",
    "include/uapi/linux/netfilter_ipv4/ipt_TTL.h":
        "include/uapi/linux/netfilter_ipv4/ipt_ttl_ohos_target.h",
    "include/uapi/linux/netfilter_ipv4/ipt_ttl.h":
        "include/uapi/linux/netfilter_ipv4/ipt_ttl_ohos_match.h",
    "include/uapi/linux/netfilter_ipv6/ip6t_HL.h":
        "include/uapi/linux/netfilter_ipv6/ip6t_hl_ohos_target.h",
    "include/uapi/linux/netfilter_ipv6/ip6t_hl.h":
        "include/uapi/linux/netfilter_ipv6/ip6t_hl_ohos_match.h",
}

SOURCE_COPIES = {
    "net/netfilter/xt_connmark.c": "net/netfilter/xt_connmark_ohos.c",
    "net/netfilter/xt_mark.c": "net/netfilter/xt_mark_ohos.c",
    "net/netfilter/xt_DSCP.c": "net/netfilter/xt_dscp_ohos_target.c",
    "net/netfilter/xt_dscp.c": "net/netfilter/xt_dscp_ohos_match.c",
    "net/netfilter/xt_HL.c": "net/netfilter/xt_hl_ohos_target.c",
    "net/netfilter/xt_hl.c": "net/netfilter/xt_hl_ohos_match.c",
    "net/netfilter/xt_RATEEST.c": "net/netfilter/xt_rateest_ohos_target.c",
    "net/netfilter/xt_rateest.c": "net/netfilter/xt_rateest_ohos_match.c",
    "net/netfilter/xt_TCPMSS.c": "net/netfilter/xt_tcpmss_ohos_target.c",
    "net/netfilter/xt_tcpmss.c": "net/netfilter/xt_tcpmss_ohos_match.c",
    "net/ipv4/netfilter/ipt_ECN.c":
        "net/ipv4/netfilter/ipt_ecn_ohos_target.c",
}

INCLUDE_REPLACEMENTS = {
    "<linux/netfilter/xt_connmark.h>":
        "<linux/netfilter/xt_connmark_ohos.h>",
    "<linux/netfilter/xt_mark.h>":
        "<linux/netfilter/xt_mark_ohos.h>",
    "<linux/netfilter/xt_DSCP.h>":
        "<linux/netfilter/xt_dscp_ohos_target.h>",
    "<linux/netfilter/xt_dscp.h>":
        "<linux/netfilter/xt_dscp_ohos_match.h>",
    "<linux/netfilter/xt_RATEEST.h>":
        "<linux/netfilter/xt_rateest_ohos_target.h>",
    "<linux/netfilter/xt_rateest.h>":
        "<linux/netfilter/xt_rateest_ohos_match.h>",
    "<linux/netfilter/xt_TCPMSS.h>":
        "<linux/netfilter/xt_tcpmss_ohos_target.h>",
    "<linux/netfilter/xt_tcpmss.h>":
        "<linux/netfilter/xt_tcpmss_ohos_match.h>",
    "<linux/netfilter_ipv4/ipt_ECN.h>":
        "<linux/netfilter_ipv4/ipt_ecn_ohos_target.h>",
    "<linux/netfilter_ipv4/ipt_TTL.h>":
        "<linux/netfilter_ipv4/ipt_ttl_ohos_target.h>",
    "<linux/netfilter_ipv4/ipt_ttl.h>":
        "<linux/netfilter_ipv4/ipt_ttl_ohos_match.h>",
    "<linux/netfilter_ipv6/ip6t_HL.h>":
        "<linux/netfilter_ipv6/ip6t_hl_ohos_target.h>",
    "<linux/netfilter_ipv6/ip6t_hl.h>":
        "<linux/netfilter_ipv6/ip6t_hl_ohos_match.h>",
}

NETFILTER_OBJECTS = {
    "obj-$(CONFIG_NETFILTER_XT_MARK) += xt_mark.o":
        "obj-$(CONFIG_NETFILTER_XT_MARK) += xt_mark_ohos.o",
    "obj-$(CONFIG_NETFILTER_XT_CONNMARK) += xt_connmark.o":
        "obj-$(CONFIG_NETFILTER_XT_CONNMARK) += xt_connmark_ohos.o",
    "obj-$(CONFIG_NETFILTER_XT_TARGET_DSCP) += xt_DSCP.o":
        "obj-$(CONFIG_NETFILTER_XT_TARGET_DSCP) += xt_dscp_ohos_target.o",
    "obj-$(CONFIG_NETFILTER_XT_TARGET_HL) += xt_HL.o":
        "obj-$(CONFIG_NETFILTER_XT_TARGET_HL) += xt_hl_ohos_target.o",
    "obj-$(CONFIG_NETFILTER_XT_TARGET_RATEEST) += xt_RATEEST.o":
        "obj-$(CONFIG_NETFILTER_XT_TARGET_RATEEST) += xt_rateest_ohos_target.o",
    "obj-$(CONFIG_NETFILTER_XT_TARGET_TCPMSS) += xt_TCPMSS.o":
        "obj-$(CONFIG_NETFILTER_XT_TARGET_TCPMSS) += xt_tcpmss_ohos_target.o",
    "obj-$(CONFIG_NETFILTER_XT_MATCH_DSCP) += xt_dscp.o":
        "obj-$(CONFIG_NETFILTER_XT_MATCH_DSCP) += xt_dscp_ohos_match.o",
    "obj-$(CONFIG_NETFILTER_XT_MATCH_HL) += xt_hl.o":
        "obj-$(CONFIG_NETFILTER_XT_MATCH_HL) += xt_hl_ohos_match.o",
    "obj-$(CONFIG_NETFILTER_XT_MATCH_RATEEST) += xt_rateest.o":
        "obj-$(CONFIG_NETFILTER_XT_MATCH_RATEEST) += xt_rateest_ohos_match.o",
    "obj-$(CONFIG_NETFILTER_XT_MATCH_TCPMSS) += xt_tcpmss.o":
        "obj-$(CONFIG_NETFILTER_XT_MATCH_TCPMSS) += xt_tcpmss_ohos_match.o",
}


def git_blob(root: Path, relative: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "show", f"HEAD:{relative}"],
        text=True,
    )


def write_if_changed(path: Path, content: str) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def rewrite_includes(content: str) -> str:
    for original, replacement in INCLUDE_REPLACEMENTS.items():
        content = content.replace(original, replacement)
    return content


def patch_makefile(path: Path, replacements: dict[str, str]) -> None:
    content = path.read_text(encoding="utf-8")
    updated = content
    for original, replacement in replacements.items():
        if replacement in updated:
            continue
        if original not in updated:
            raise SystemExit(f"unexpected netfilter Makefile layout: {path}: {original}")
        updated = updated.replace(original, replacement, 1)
    write_if_changed(path, updated)


def is_case_insensitive(root: Path) -> bool:
    upper = root / "include/uapi/linux/netfilter/xt_MARK.h"
    lower = root / "include/uapi/linux/netfilter/xt_mark.h"
    return upper.exists() and lower.exists() and upper.samefile(lower)


def configure_kernel(root: Path) -> bool:
    if not root.is_dir() or not is_case_insensitive(root):
        return False

    for source, destination in HEADER_COPIES.items():
        write_if_changed(root / destination, rewrite_includes(git_blob(root, source)))
    for source, destination in SOURCE_COPIES.items():
        write_if_changed(root / destination, rewrite_includes(git_blob(root, source)))

    patch_makefile(root / "net/netfilter/Makefile", NETFILTER_OBJECTS)
    patch_makefile(
        root / "net/ipv4/netfilter/Makefile",
        {
            "obj-$(CONFIG_IP_NF_TARGET_ECN) += ipt_ECN.o":
                "obj-$(CONFIG_IP_NF_TARGET_ECN) += ipt_ecn_ohos_target.o",
        },
    )
    print(f"configured case-insensitive kernel netfilter sources: {root}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()

    configured = 0
    for version in ("6.6", "5.10"):
        configured += configure_kernel(
            args.source_root / f"kernel/linux/linux-{version}"
        )
    if configured == 0:
        print("kernel netfilter case-fold compatibility not required")


if __name__ == "__main__":
    main()
