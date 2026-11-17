#!/usr/bin/env python3
"""Clamp llvmpipe 4x4 edge stamps and reserve KMS tail guard pages in Mesa 21.3.3."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

BASE_SHAS = {
    "src/gallium/drivers/llvmpipe/lp_rast_priv.h": '83fba87b109029dc4d882f7e9106886137a47252e3239157abdc5a2b6926f163',
    "src/gallium/drivers/llvmpipe/lp_rast.c": '60a38abb16256c11c264f097c7b0e6f03de3b88dbe26fe0416a02d67769ee62e',
    "src/gallium/drivers/llvmpipe/lp_rast_linear_fallback.c": 'daea3f0e33c9680f1b28a1e38fad3d0d406692d49434f8ebb606437518534d28',
    "src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c": 'e34309672d2bec5db3ed89e53fa340d8cbcac89dfa7f074c3280673ddc3a5687',
}
REPAIRED_SHAS = {
    "src/gallium/drivers/llvmpipe/lp_rast_priv.h": 'b0aa94b6785e82930fde2c5d23b53b9468718aec03c5ec2d7cf36411b0272164',
    "src/gallium/drivers/llvmpipe/lp_rast.c": '3f9b504c2d66ba0e49b72f29a7e8a4f38eb165de039986ab32a9d2c0379a17c0',
    "src/gallium/drivers/llvmpipe/lp_rast_linear_fallback.c": 'f9aac1c844be955a3c67f373991d3ee7e06a67d2250b80ce3818afa5e0d4041d',
    "src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c": 'e4914ef5b8cfefe8f496ffd79018e2eb93ef2f778824878bbbb746b500b0bfe9',
}
KMS_PRE_MAPPING_SHAS = {
    "b8b8736f347fb473a718c610abf3099bfb72d5a9f28bf75e3620fb72f8592194",  # Mesa 21.3.3 original
    "e5fef3b60fa2c555bc4447cba13a2dd23819fd7f6bf33c065a597a9bca909670",  # After 0001 mapping patch
    "e34309672d2bec5db3ed89e53fa340d8cbcac89dfa7f074c3280673ddc3a5687",  # After 0001+0002 lifetime patch
}
PATCHES = (
    ('0001-clip-llvmpipe-partial-4x4-edge-stamps.patch', 'd51edb601b8f54cafff2b731915aec21699be3678d2b76109b9bee7fcd95e524'),
    ('0002-reserve-kms-dumb-bo-tail-guard-vma.patch', 'b0e1375f5bfdd278457166904a50c1f21435130ac46d7d0bf7e138ad63026657'),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    path = root / relative
    for current in (path, *path.parents):
        if current == root:
            return path
        if current.is_symlink():
            raise ValueError("symlink in historical Mesa bounds input: " + relative)
    raise ValueError("bounds input outside Mesa source root: " + relative)


def _clean_git_env(ceiling: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(name, None)
    env["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    return env


def _verify_recipe(component_dir: Path, root: Path) -> tuple[Path, Path]:
    if checked_path(root, "VERSION").read_text().strip() != "21.3.3":
        raise ValueError("exact historical Mesa 21.3.3 source required")
    resolved = []
    for name, expected_sha in PATCHES:
        patch = component_dir / name
        if patch.is_symlink() or not patch.is_file() or digest(patch) != expected_sha:
            raise ValueError("exact historical Mesa bounds patch required: " + name)
        resolved.append(patch)
    return resolved[0], resolved[1]


def _classify_state(root: Path, *, allow_pre_mapping_for_rewind: bool = False) -> str:
    states = {}
    for rel, base_sha in BASE_SHAS.items():
        actual = digest(checked_path(root, rel))
        if actual == REPAIRED_SHAS[rel]:
            states[rel] = "repaired"
        elif actual == base_sha or (
            allow_pre_mapping_for_rewind
            and rel == "src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c"
            and actual in KMS_PRE_MAPPING_SHAS
        ):
            states[rel] = "base"
        else:
            raise ValueError("unknown/incomplete Mesa bounds state; preserving source: " + rel)
    distinct = set(states.values())
    if len(distinct) != 1:
        raise ValueError("partial Mesa bounds state across files; preserving source")
    return next(iter(distinct))


def _atomic_publish(source: Path, staged_file: Path, expected_before_sha: str, root: Path, rel: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=source.parent, prefix=".bounds-guard-", delete=False) as stream:
            temporary = Path(stream.name)
            with staged_file.open("rb") as payload:
                shutil.copyfileobj(payload, stream)
            os.fchmod(stream.fileno(), source.stat().st_mode & 0o777)
            stream.flush()
            os.fsync(stream.fileno())
        checked_path(root, rel)
        if digest(source) != expected_before_sha:
            raise ValueError("Mesa source changed before atomic publication: " + rel)
        os.replace(temporary, source)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply(root: Path, *, rewind: bool = False) -> str:
    root = Path(root).resolve()
    component_dir = Path(__file__).resolve().parent
    p1, p2 = _verify_recipe(component_dir, root)
    state = _classify_state(root, allow_pre_mapping_for_rewind=rewind)
    if (not rewind and state == "repaired") or (rewind and state == "base"):
        return "already_repaired" if not rewind else "already_base"

    lock_fd = os.open(root / ".ohos-qemu-bounds-guard.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a"):
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        state = _classify_state(root, allow_pre_mapping_for_rewind=rewind)
        if (not rewind and state == "repaired") or (rewind and state == "base"):
            return "already_repaired" if not rewind else "already_base"

        expected_before = REPAIRED_SHAS if rewind else BASE_SHAS
        expected_after = BASE_SHAS if rewind else REPAIRED_SHAS
        patch_seq = (p2, p1) if rewind else (p1, p2)
        git_flags = ["-R"] if rewind else []

        with tempfile.TemporaryDirectory(prefix="mesa-bounds-guard-") as temporary:
            staged = Path(temporary)
            for rel in BASE_SHAS:
                dst = staged / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(checked_path(root, rel), dst)
            env = _clean_git_env(staged.parent)
            for patch in patch_seq:
                for op in ("--check", "--whitespace=nowarn"):
                    subprocess.run(
                        ["git", "-C", str(staged), "apply", *git_flags, op, str(patch)],
                        check=True,
                        env=env,
                    )
            for rel, exp_after in expected_after.items():
                if digest(staged / rel) != exp_after:
                    raise ValueError("unexpected patched Mesa bounds content for " + rel)
            for rel, exp_before in expected_before.items():
                _atomic_publish(checked_path(root, rel), staged / rel, exp_before, root, rel)

        return "rewound" if rewind else "applied"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--rewind", action="store_true")
    args = parser.parse_args()
    status = apply(args.source_root, rewind=args.rewind)
    print(f"verified historical Mesa 4x4 bounds clip and KMS tail guard VMA ({status})")
