#!/usr/bin/env python3
"""Ensure pinned Lottie and Live Captions dependency inputs exist under CACHE_ROOT.

On a fresh machine starting from zero, this script unpacks the repository-bundled
license/notice files and downloads the pinned upstream model/HAR archives into
${CACHE_ROOT}/artifacts/livecaptions-lottie-7.0, verifying every SHA-256 checksum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "patches/lib"))
from livecaptions579_arm32_sources import DEPENDENCIES  # noqa: E402

NOTICES_ARCHIVE = REPO_ROOT / "patches/assets/livecaptions-notices.tar.gz"
CPU_PROVIDER_ARM32_ASSETS = (
    REPO_ROOT / "patches/common/drivers/peripheral/intelligent_voice/cpu_provider/assets/arm32"
)

DOWNLOADS = {
    "r66-lottie-production-input579-06/lottie/lottie-2.0.23.har": (
        "https://ohpm.openharmony.cn/ohpm/@ohos/lottie/-/lottie-2.0.23.har",
        "c05579c5378e6ac696a4c36e7ae0a1fde09f611bc47ec198fc91100c8db2cbc5",
        193331,
    ),
    "r66-asr-product-inputs579-04/inputs/tiny.en-encoder.int8.onnx": (
        "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/d026532c022fa99fd789d6b32446a1df7b6bfc43/tiny.en-encoder.int8.onnx",
        "0ce578b827c94a961aacb8fa14b02f096504b337e5c94be37c36238cbe3e8bc6",
        12937772,
    ),
    "r66-asr-product-inputs579-04/inputs/tiny.en-decoder.int8.onnx": (
        "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/d026532c022fa99fd789d6b32446a1df7b6bfc43/tiny.en-decoder.int8.onnx",
        "06c0e6ff6348d427e51839219d1c886c18cfdf411e629e33f5e1679bff9c1527",
        89853865,
    ),
    "r66-asr-product-inputs579-04/inputs/tiny.en-tokens.txt": (
        "https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en/resolve/d026532c022fa99fd789d6b32446a1df7b6bfc43/tiny.en-tokens.txt",
        "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
        835554,
    ),
    "r66-asr-product-inputs579-04/inputs/silero_vad.onnx": (
        "https://raw.githubusercontent.com/snakers4/silero-vad/v4.0/files/silero_vad.onnx",
        "a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28",
        1807522,
    ),
    "r66-asr-product-inputs579-04/inputs/sherpa_onnx-1.11.2.har": (
        "https://ohpm.openharmony.cn/ohpm/sherpa_onnx/-/sherpa_onnx-1.11.2.har",
        "d196941c571f4bd7dd98e6c03097aa4873b9a934ceced64800fb85b25892e6a0",
        13894230,
    ),
}

NOTICES = {
    "r66-asr-product-assets579-05/notices/LIVE_CAPTIONS_NOTICES.txt": "23a28ff194d9611ce38979598b16923b6a0d0f205dd3d0e2f5a1513e52c7858b",
    "r66-asr-product-assets579-05/notices/actual-ohos-sdk-llvm-NOTICE": "22208a1d78a9271ec1d6eaf7d21db5dda6049ed14af09d7d0f8d7787b6bffb77",
    "r66-asr-product-inputs579-04/inputs/openai-v20250625-LICENSE": "b5d65a59060e68c4ff940e1eddfa6f94b2d68fdf58ed7f4dd57721c997e35e9d",
    "r66-asr-product-inputs579-04/inputs/sherpa-1.11.2-LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "r66-asr-product-inputs579-04/inputs/ort-1.16.3-LICENSE": "2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c",
    "r66-asr-product-inputs579-04/inputs/ort-1.16.3-ThirdPartyNotices.txt": "d7d726424fc23a8395c139bbc7eb2aefa2b5bb2eb3332ec34ad0442d149d2308",
    "r66-asr-product-inputs579-04/inputs/silero-v4-LICENSE": "2e63e9a38b6e8fc0c7bc37ce174caca1862870856c6daf5697cfb785e925520b",
}

ARM32_EXTRA = {
    "sherpa-onnx-v1.11.2.tar.gz": (
        CPU_PROVIDER_ARM32_ASSETS / "sherpa-onnx-v1.11.2.tar.gz",
        "https://github.com/k2-fsa/sherpa-onnx/archive/refs/tags/v1.11.2.tar.gz",
        "076031e8801d0f079f008733ad3ad73140ca57ca024bb114a69943eef93f76ba",
    ),
    "onnxruntime-ohos-armeabi-v7a-1.16.3.zip": (
        CPU_PROVIDER_ARM32_ASSETS / "onnxruntime-ohos-armeabi-v7a-1.16.3.zip",
        "https://huggingface.co/csukuangfj/onnxruntime-libs/resolve/c5ad3699dbc2902c93b0128a1e427201cec95df4/onnxruntime-ohos-armeabi-v7a-1.16.3.zip",
        "cecbae2a8404a26ad1595f3ff0886e2e1353933c0883e2dfa846f063dfe34902",
    ),
    "node-addon-api-c679f6f4c9dc6bf9fc0d99cbe5982bd24a5e2c7b.tar.gz": (
        None,
        "https://github.com/nodejs/node-addon-api/archive/c679f6f4c9dc6bf9fc0d99cbe5982bd24a5e2c7b.tar.gz",
        "5bedae00cf74848e61a308688da0bcebacf2149b9d186ba493ca167571c6db17",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_file(target: Path, url: str, expected_sha256: str, expected_bytes: int | None = None) -> None:
    if target.is_file() and not target.is_symlink():
        if sha256_file(target) == expected_sha256 and (expected_bytes is None or target.stat().st_size == expected_bytes):
            return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as tmp:
        pending = Path(tmp.name)
    try:
        print(f"downloading {url} -> {target}", flush=True)
        subprocess.run(
            ["curl", "-fL", "--connect-timeout", "20", "--retry", "3", "-o", str(pending), url],
            check=True,
        )
        actual_sha = sha256_file(pending)
        if actual_sha != expected_sha256:
            raise ValueError(f"checksum mismatch for {target}: expected {expected_sha256}, got {actual_sha}")
        if expected_bytes is not None and pending.stat().st_size != expected_bytes:
            raise ValueError(f"size mismatch for {target}: expected {expected_bytes}, got {pending.stat().st_size}")
        os.chmod(pending, 0o644)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)


def write_json_atomic(target: Path, payload: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
        pending = Path(tmp.name)
        json.dump(payload, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    os.chmod(pending, 0o644)
    os.replace(pending, target)


def prepare(cache_root: Path, *, arm32: bool = False) -> None:
    root = cache_root.resolve() / "artifacts/livecaptions-lottie-7.0"
    root.mkdir(parents=True, exist_ok=True)

    missing_notices = any(
        not (root / rel).is_file() or sha256_file(root / rel) != expected
        for rel, expected in NOTICES.items()
    )
    if missing_notices:
        with tarfile.open(NOTICES_ARCHIVE, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                dest = root / member.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(member).read())
                dest.chmod(0o644)
    for rel, expected in NOTICES.items():
        if sha256_file(root / rel) != expected:
            raise ValueError(f"notice file checksum mismatch: {root / rel}")

    for rel, (url, sha, size) in DOWNLOADS.items():
        ensure_file(root / rel, url, sha, size)

    lottie_har = root / "r66-lottie-production-input579-06/lottie/lottie-2.0.23.har"
    lottie_json = root / "r66-lottie-production-input579-06/lottie-input.json"
    write_json_atomic(
        lottie_json,
        {
            "path": str(lottie_har),
            "sha256": "c05579c5378e6ac696a4c36e7ae0a1fde09f611bc47ec198fc91100c8db2cbc5",
            "bytes": 193331,
        },
    )

    product_assets_json = root / "r66-asr-product-assets579-05/product-assets.json"
    inputs_dir = root / "r66-asr-product-inputs579-04/inputs"
    notices_dir = root / "r66-asr-product-assets579-05/notices"
    write_json_atomic(
        product_assets_json,
        {
            "language": "en",
            "model": "whisper-tiny.en",
            "assets": {
                "encoder": {
                    "path": str(inputs_dir / "tiny.en-encoder.int8.onnx"),
                    "sha256": "0ce578b827c94a961aacb8fa14b02f096504b337e5c94be37c36238cbe3e8bc6",
                },
                "decoder": {
                    "path": str(inputs_dir / "tiny.en-decoder.int8.onnx"),
                    "sha256": "06c0e6ff6348d427e51839219d1c886c18cfdf411e629e33f5e1679bff9c1527",
                },
                "tokens": {
                    "path": str(inputs_dir / "tiny.en-tokens.txt"),
                    "sha256": "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
                },
                "vad": {
                    "path": str(inputs_dir / "silero_vad.onnx"),
                    "sha256": "a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28",
                },
                "har": {
                    "path": str(inputs_dir / "sherpa_onnx-1.11.2.har"),
                    "sha256": "d196941c571f4bd7dd98e6c03097aa4873b9a934ceced64800fb85b25892e6a0",
                },
                "notices": {
                    "path": str(notices_dir / "LIVE_CAPTIONS_NOTICES.txt"),
                    "sha256": "23a28ff194d9611ce38979598b16923b6a0d0f205dd3d0e2f5a1513e52c7858b",
                },
            },
            "licenses": {
                "whisper": {
                    "path": str(inputs_dir / "openai-v20250625-LICENSE"),
                    "sha256": "b5d65a59060e68c4ff940e1eddfa6f94b2d68fdf58ed7f4dd57721c997e35e9d",
                },
                "sherpa": {
                    "path": str(inputs_dir / "sherpa-1.11.2-LICENSE"),
                    "sha256": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
                },
                "ort": {
                    "path": str(inputs_dir / "ort-1.16.3-LICENSE"),
                    "sha256": "2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c",
                },
                "ort_notices": {
                    "path": str(inputs_dir / "ort-1.16.3-ThirdPartyNotices.txt"),
                    "sha256": "d7d726424fc23a8395c139bbc7eb2aefa2b5bb2eb3332ec34ad0442d149d2308",
                },
                "silero": {
                    "path": str(inputs_dir / "silero-v4-LICENSE"),
                    "sha256": "2e63e9a38b6e8fc0c7bc37ce174caca1862870856c6daf5697cfb785e925520b",
                },
                "libcxx": {
                    "path": str(notices_dir / "actual-ohos-sdk-llvm-NOTICE"),
                    "sha256": "22208a1d78a9271ec1d6eaf7d21db5dda6049ed14af09d7d0f8d7787b6bffb77",
                },
            },
            "first_artifact_behavior_gate_passed": False,
        },
    )

    if arm32:
        arm32_dir = root / "arm32-sources"
        arm32_dir.mkdir(parents=True, exist_ok=True)
        for filename, (local_src, url, sha) in ARM32_EXTRA.items():
            target = arm32_dir / filename
            if (not target.is_file() or sha256_file(target) != sha) and local_src is not None and local_src.is_file():
                shutil.copy2(local_src, target)
            ensure_file(target, url, sha)
        for filename, url, sha in DEPENDENCIES.values():
            ensure_file(arm32_dir / filename, url, sha)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(os.environ.get("CACHE_ROOT", "/Volumes/PSSD/qemu")),
    )
    parser.add_argument("--arm32", action="store_true")
    args = parser.parse_args()
    prepare(args.cache_root, arm32=args.arm32)


if __name__ == "__main__":
    main()
