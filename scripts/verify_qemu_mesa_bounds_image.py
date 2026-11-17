#!/usr/bin/env python3
"""Verify that system.img and vendor.img contain the Issue #35 bounds & 2in1 WM fixes."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from verify_runtime_elf_contract import read_elf, verify_machine


PRODUCT_META: dict[str, tuple[int, str, str, str]] = {
    "arm64_virt": (
        183,
        "/system/lib64/kms_swrast_dri.so",
        "/system/lib64/libwm.z.so",
        "/lib64/passthrough/libdisplay_buffer_vendor.z.so",
    ),
    "x86_64_virt": (
        62,
        "/system/lib64/kms_swrast_dri.so",
        "/system/lib64/libwm.z.so",
        "/lib64/passthrough/libdisplay_buffer_vendor.z.so",
    ),
    "armv7a_virt": (
        40,
        "/system/lib/kms_swrast_dri.so",
        "/system/lib/libwm.z.so",
        "/lib/passthrough/libdisplay_buffer_vendor.z.so",
    ),
}

MESA_REQUIRED_MARKERS: tuple[bytes, ...] = (
    b"LP_QEMU_4X4_BOUNDS_CLIP_V1",
    b"KMS_QEMU_GUARD_MAP_V1",
)
WM_REQUIRED_MARKERS: tuple[bytes, ...] = (
    b"OHOS_QEMU_WM_PAD_DECOR_COMPAT_V1",
)
GBM_REQUIRED_MARKERS: tuple[bytes, ...] = (
    b"OHOS_QEMU_GBM_HEIGHT_ALIGN_4_V1",
)


def debugfs_bin() -> str:
    for cand in (
        shutil.which("debugfs"),
        "/opt/homebrew/opt/e2fsprogs/sbin/debugfs",
        "/usr/sbin/debugfs",
        "/sbin/debugfs",
    ):
        if cand and Path(cand).is_file():
            return cand
    raise RuntimeError("debugfs binary not found")


def dump_from_image(dbg: str, image: Path, candidates: tuple[str, ...], dst: Path) -> str:
    for ext_path in candidates:
        stat = subprocess.run([dbg, "-R", f"stat {ext_path}", str(image)], capture_output=True, text=True)
        if stat.returncode == 0 and "Inode:" in stat.stdout:
            res = subprocess.run([dbg, "-R", f"dump {ext_path} {dst}", str(image)], capture_output=True, text=True)
            if res.returncode != 0 or re.search(r"(?:error|not found|no such file)", res.stderr, re.I):
                raise RuntimeError(f"debugfs dump {ext_path} from {image} failed: {res.stderr.strip()}")
            if not dst.is_file() or dst.stat().st_size == 0:
                raise RuntimeError(f"dumped empty file for {ext_path} from {image}")
            return ext_path
    raise RuntimeError(f"missing {candidates} in {image}")


def verify_elf_markers(
    path: Path,
    expected_machine: int,
    markers: tuple[bytes, ...],
    required_syms: tuple[str, ...] = (),
) -> None:
    info = read_elf(path)
    verify_machine(info, expected_machine, path)
    missing_syms = sorted(set(required_syms) - info.defined)
    if missing_syms:
        raise RuntimeError(f"{path} missing required exported symbol(s): {', '.join(missing_syms)}")
    payload = path.read_bytes()
    for marker in markers:
        if marker not in payload:
            raise RuntimeError(f"{path} missing required Issue #35 marker {marker.decode('ascii')}")


def _alt_system_path(rel: str) -> str:
    return rel[len("/system") :] if rel.startswith("/system/") else f"/system{rel}"


def verify_images(product: str, system_image: Path, vendor_image: Path) -> None:
    if product not in PRODUCT_META:
        raise ValueError(f"unsupported product: {product}")
    expected_machine, mesa_rel, wm_rel, gbm_rel = PRODUCT_META[product]
    mesa_alt = _alt_system_path(mesa_rel)
    wm_alt = _alt_system_path(wm_rel)
    gbm_alt = f"/vendor{gbm_rel}"

    dbg = debugfs_bin()
    with tempfile.TemporaryDirectory(prefix="verify-mesa-bounds-") as td:
        work = Path(td)
        mesa_so = work / "kms_swrast_dri.so"
        wm_so = work / "libwm.z.so"
        gbm_so = work / "libdisplay_buffer_vendor.z.so"

        dump_from_image(dbg, system_image, (mesa_rel, mesa_alt), mesa_so)
        dump_from_image(dbg, system_image, (wm_rel, wm_alt), wm_so)
        dump_from_image(dbg, vendor_image, (gbm_rel, gbm_alt), gbm_so)

        verify_elf_markers(
            mesa_so,
            expected_machine,
            MESA_REQUIRED_MARKERS,
            ("__driDriverGetExtensions_kms_swrast",),
        )
        verify_elf_markers(
            wm_so,
            expected_machine,
            WM_REQUIRED_MARKERS,
        )
        verify_elf_markers(
            gbm_so,
            expected_machine,
            GBM_REQUIRED_MARKERS,
            ("_ZN4OHOS3HDI7DISPLAY20GbmGrallocInitializeEv",),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", required=True, choices=sorted(PRODUCT_META))
    parser.add_argument("--system-image", type=Path, required=True)
    parser.add_argument("--vendor-image", type=Path, required=True)
    args = parser.parse_args(argv)
    verify_images(args.product, args.system_image, args.vendor_image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
