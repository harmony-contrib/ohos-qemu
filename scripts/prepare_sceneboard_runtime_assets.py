#!/usr/bin/env python3
"""Bootstrap ${SCENEBOARD_RUNTIME_ASSET_ROOT} from pinned LFS HAPs and delta archive.

On a fresh machine starting from zero, reconstructs:
  - SceneBoard.hap (with AbilityManager 7.0 unlock event + multi-ABI native libs)
  - NotificationManagement.hap
  - ThemeService.hap
  - ThemeComponent.hap
  - SecurityPrivacyCenter.hap (with canonical OS application signer profile)
and verifies all five output SHA-256 digests against the pinned runtime contract.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from patch_sceneboard_unlock_event import patch_modules_abc  # noqa: E402

DEFAULT_DELTA_ARCHIVE = SCRIPT_DIR.parent / "patches" / "assets" / "sceneboard-runtime-delta.tar.gz"


def sha256_bytes(data: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_original_hap(
    name: str,
    orig_oid: str,
    lfs_asset_root: Path | None,
    ohos_root: Path | None,
) -> bytes:
    candidates: list[Path] = []
    if lfs_asset_root is not None:
        candidates.append(lfs_asset_root / orig_oid[:2] / orig_oid)
    if ohos_root is not None:
        candidates.append(ohos_root / "applications" / "standard" / "hap" / "sceneboard" / name)
    for candidate in candidates:
        if candidate.is_file():
            data = candidate.read_bytes()
            if sha256_bytes(data) == orig_oid:
                return data
    raise SystemExit(
        f"missing pinned original LFS object {orig_oid} for {name}; "
        "run scripts/prepare_ohos_7_0_release_lfs_cache.sh first"
    )


def reconstruct_hap(
    name: str,
    spec: dict,
    tar: tarfile.TarFile,
    orig_bytes: bytes,
) -> bytes:
    headers_blob = tar.extractfile(f"{name}/headers.bin").read()
    tail_blob = tar.extractfile(f"{name}/tail.bin").read()

    orig_zip = zipfile.ZipFile(io.BytesIO(orig_bytes), "r")
    orig_entries = {info.filename: info for info in orig_zip.infolist()}

    output = bytearray()
    for entry in spec["entries"]:
        filename = entry["filename"]
        hdr_off = entry["hdr_off"]
        hdr_len = entry["hdr_len"]
        source_kind = entry["source"]
        output.extend(headers_blob[hdr_off : hdr_off + hdr_len])

        if source_kind == "orig_raw":
            info = orig_entries[filename]
            fn_len = int.from_bytes(orig_bytes[info.header_offset + 26 : info.header_offset + 28], "little")
            ex_len = int.from_bytes(orig_bytes[info.header_offset + 28 : info.header_offset + 30], "little")
            raw_start = info.header_offset + 30 + fn_len + ex_len
            output.extend(orig_bytes[raw_start : raw_start + info.compress_size])
        elif source_kind == "patched_modules_abc":
            patched = patch_modules_abc(orig_zip.read(filename))
            output.extend(patched)
        elif source_kind.startswith("blob:"):
            blob_member = source_kind.split(":", 1)[1]
            output.extend(tar.extractfile(blob_member).read())
        else:
            raise ValueError(f"unsupported delta source kind for {name}/{filename}: {source_kind}")

    output.extend(tail_blob)
    actual_sha = sha256_bytes(output)
    expected_sha = spec["canon_sha256"]
    if len(output) != spec["canon_size"] or actual_sha != expected_sha:
        raise ValueError(
            f"reconstructed {name} mismatch: expected {expected_sha} ({spec['canon_size']} bytes), "
            f"got {actual_sha} ({len(output)} bytes)"
        )
    return bytes(output)


def ensure_sceneboard_runtime_assets(
    asset_root: Path,
    lfs_asset_root: Path | None,
    ohos_root: Path | None,
    delta_archive: Path = DEFAULT_DELTA_ARCHIVE,
) -> dict[str, str]:
    if not delta_archive.is_file():
        raise SystemExit(f"missing SceneBoard runtime delta archive: {delta_archive}")

    asset_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(delta_archive, "r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        results: dict[str, str] = {}
        for name, spec in manifest.items():
            target = asset_root / name
            expected_sha = spec["canon_sha256"]
            if target.is_file() and target.stat().st_size == spec["canon_size"]:
                if sha256_file(target) == expected_sha:
                    results[name] = expected_sha
                    continue
            orig_bytes = resolve_original_hap(name, spec["orig_oid"], lfs_asset_root, ohos_root)
            reconstructed = reconstruct_hap(name, spec, tar, orig_bytes)
            with tempfile.NamedTemporaryFile(
                prefix=f".{name}.", suffix=".tmp", dir=asset_root, delete=False
            ) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(reconstructed)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, target)
            results[name] = expected_sha
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(os.environ.get("CACHE_ROOT", "/Volumes/PSSD/qemu")),
    )
    parser.add_argument("--asset-root", type=Path, default=None)
    parser.add_argument("--lfs-asset-root", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--delta-archive", type=Path, default=DEFAULT_DELTA_ARCHIVE)
    args = parser.parse_args()

    cache_root = args.cache_root.resolve()
    asset_root = (
        args.asset_root.resolve()
        if args.asset_root
        else Path(os.environ.get("SCENEBOARD_RUNTIME_ASSET_ROOT", str(cache_root / "artifacts" / "sceneboard-runtime"))).resolve()
    )
    lfs_asset_root = (
        args.lfs_asset_root.resolve()
        if args.lfs_asset_root
        else Path(os.environ.get("OHOS_LFS_ASSET_ROOT", str(cache_root / "artifacts" / "openharmony-7.0-lfs"))).resolve()
    )
    ohos_root = (
        args.source_root.resolve()
        if args.source_root
        else (cache_root / "openharmony" if (cache_root / "openharmony").is_dir() else None)
    )

    results = ensure_sceneboard_runtime_assets(
        asset_root=asset_root,
        lfs_asset_root=lfs_asset_root,
        ohos_root=ohos_root,
        delta_archive=args.delta_archive.resolve(),
    )
    print(json.dumps({"status": "ready", "asset_root": str(asset_root), "haps": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
