# From-Zero Build and Packaging Guide

This guide explains how to build all six OpenHarmony 7.0 Release QEMU packages (`phone` and `2in1` × `arm64_virt`, `x86_64_virt`, `armv7a_virt`) from scratch on a new machine.

## 1. Host Prerequisites

- **OS**: macOS (Apple Silicon or Intel) with Docker Desktop / OrbStack, or Linux `x86_64` with Docker Engine.
  - Because OpenHarmony's prebuilt toolchains target `linux/amd64`, macOS hosts run the build containers under `linux/amd64` emulation (Rosetta 2 in Docker Desktop / OrbStack).
- **Disk Space**:
  - At least **250 GB** of free space on the volume hosting `CACHE_ROOT` (for M144 Chromium sources/out, LFS cache, Git fallback mirrors, and output packages) and **180 GB** inside Docker's virtual disk (for the case-sensitive `ohos-qemu-7_0-release-source` and `ohos-qemu-7_0-release-out` volumes).
- **Host Tools**: `bash`, `git`, `curl`, `python3` (`3.10+`), `tar`, `shasum`, and `docker`.

## 2. Step-by-Step From-Zero Workflow

### Step 1: Set `CACHE_ROOT` and Prepare All External Dependencies

[`scripts/prepare_qemu_release_dependencies.sh`](../scripts/prepare_qemu_release_dependencies.sh) builds or verifies all M144 artifacts (`ArkWebCore.hap`, `libv8_shared.so`, `libvk_swiftshader.so`, `libopenh264.so`) and the QEMU Mesa private LLVM archive (`libllvm.a`) for a target product:

```bash
export CACHE_ROOT=/path/to/qemu-cache

# Prepare dependencies for arm64_virt, x86_64_virt, and armv7a_virt
bash scripts/prepare_qemu_release_dependencies.sh arm64_virt
bash scripts/prepare_qemu_release_dependencies.sh x86_64_virt
bash scripts/prepare_qemu_release_dependencies.sh armv7a_virt
```

On a fresh machine, `prepare_qemu_release_dependencies.sh` automatically:
1. Builds the `ohos-m144-build:ubuntu22.04` Docker image.
2. Synchronizes the pinned 156-project Chromium/ArkWeb M144 source tree into Docker volume `ohos-m144-7_0-release-src`.
3. Builds `ArkWebCore.hap`, `jsvm` (`libv8_shared.so`), `swiftshader` (`libvk_swiftshader.so`), and `avc` (`libopenh264.so`) under `${CACHE_ROOT}/artifacts/`.
4. Builds `libllvm.a` for Mesa `gallivm` under `${CACHE_ROOT}/artifacts/qemu-mesa-llvm/`.

### Step 2: Build a Single QEMU Package (`phone` or `2in1`)

Use [`scripts/run_2in1_full_build_docker.sh`](../scripts/run_2in1_full_build_docker.sh) to build and package any single `(DEVICE_TYPE, PRODUCTS)` pair:

```bash
export CACHE_ROOT=/path/to/qemu-cache
export PACKAGE_ROOT="${CACHE_ROOT}/packages/release-matrix"

# First run on a new machine: syncs OpenHarmony 7.0 Release into Docker volume
# ohos-qemu-7_0-release-source, downloads the 35 fallback Git mirrors and 77 LFS
# assets, prepares LiveCaptions/Lottie and SceneBoard caches, and builds arm64 phone.
DEVICE_TYPE=phone \
PRODUCTS=arm64_virt \
PACKAGE_ROOT="${PACKAGE_ROOT}" \
CACHE_ROOT="${CACHE_ROOT}" \
DOCKER_BUILD_CPUS=10 \
DOCKER_BUILD_MEMORY=20g \
DOCKER_BUILD_MEMORY_SWAP=24g \
BUILD_JOBS=8 \
KERNEL_BUILD_JOBS=8 \
CCACHE_MAXSIZE=80G \
bash scripts/run_2in1_full_build_docker.sh
```

For subsequent packages on the same machine, pass `SKIP_REPO_SYNC=1 SKIP_PREBUILTS=1 SKIP_GIT_LFS=1` to reuse the initialized `ohos-qemu-7_0-release-source` Docker volume without re-running network synchronization:

```bash
# Example: build arm64_virt 2in1 reusing the prepared source volume
DEVICE_TYPE=2in1 \
PRODUCTS=arm64_virt \
PACKAGE_ROOT="${PACKAGE_ROOT}" \
CACHE_ROOT="${CACHE_ROOT}" \
SKIP_REPO_SYNC=1 \
SKIP_PREBUILTS=1 \
SKIP_GIT_LFS=1 \
DOCKER_BUILD_CPUS=10 \
DOCKER_BUILD_MEMORY=20g \
DOCKER_BUILD_MEMORY_SWAP=24g \
BUILD_JOBS=8 \
KERNEL_BUILD_JOBS=8 \
CCACHE_MAXSIZE=80G \
bash scripts/run_2in1_full_build_docker.sh
```

### Step 3: Build the Complete Six-Package Matrix

[`scripts/run_device_type_matrix_build_docker.sh`](../scripts/run_device_type_matrix_build_docker.sh) orchestrates all six packages (`phone,2in1` × `arm64_virt,x86_64_virt,armv7a_virt`) and writes `SHA256SUMS` plus `matrix-manifest.json`:

```bash
export CACHE_ROOT=/path/to/qemu-cache
export PACKAGE_ROOT="${CACHE_ROOT}/packages/device-matrix-7.0-release"

DOCKER_BUILD_CPUS=10 \
DOCKER_BUILD_MEMORY=20g \
DOCKER_BUILD_MEMORY_SWAP=24g \
BUILD_JOBS=8 \
KERNEL_BUILD_JOBS=8 \
CCACHE_MAXSIZE=80G \
bash scripts/run_device_type_matrix_build_docker.sh
```

## 3. Output Archive Layout

Each build produces a directory and a compressed `.tar.gz` archive under `${PACKAGE_ROOT}`:

- `openharmony-qemu-arm64-arm64_virt-phone.tar.gz`
- `openharmony-qemu-arm64-arm64_virt-2in1.tar.gz`
- `openharmony-qemu-x86_64-x86_64_virt-phone.tar.gz`
- `openharmony-qemu-x86_64-x86_64_virt-2in1.tar.gz`
- `openharmony-qemu-armv7a-armv7a_virt-phone.tar.gz`
- `openharmony-qemu-armv7a-armv7a_virt-2in1.tar.gz`

Inside each extracted archive:
- `images/`: Kernel (`Image` / `bzImage` / `zImage`), `ramdisk.img`, `system.img`, `vendor.img`, `userdata.img`, `sys_prod.img`, `chip_prod.img`, `updater.img`, and UEFI firmware (`QEMU_EFI.fd` / `OVMF_CODE.fd`).
- `launch/`: Cross-platform launchers (`linux.sh`, `macos.command`, `windows.ps1`) supporting `--headless`, `--a11y`, `--qmp-socket`, `--hdc-port`, `--resolution`, and `--accel`.
- `tools/`: `sign-hap.sh` and `install-hap-signer.sh`.
- `manifest.json` & `device-profile.json`: Complete source baseline hashes, capability flags, and resolved product part lists.

## 4. Key Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CACHE_ROOT` | `/Volumes/PSSD/qemu` | Host directory storing LFS assets, Git mirrors, M144 artifacts, and Mesa LLVM |
| `PACKAGE_ROOT` | `${CACHE_ROOT}/packages/...` | Output directory for packaged `.tar.gz` archives and manifests |
| `DEVICE_TYPE` | `2in1` | Target device profile (`phone` or `2in1`) for `run_2in1_full_build_docker.sh` |
| `PRODUCTS` | `arm64_virt` | Space-separated list of target products (`arm64_virt`, `x86_64_virt`, `armv7a_virt`) |
| `DOCKER_SOURCE_VOLUME` | `ohos-qemu-7_0-release-source` | Case-sensitive Linux Docker volume holding the OpenHarmony source checkout |
| `DOCKER_OUT_VOLUME` | `ohos-qemu-7_0-release-out` | Case-sensitive Linux Docker volume holding `out/` and `ccache` |
| `BUILD_JOBS` | `4` | Ninja compile parallelism inside Docker (recommended: `8` with 10 CPUs / 20 GiB RAM) |
| `KERNEL_BUILD_JOBS` | `2` | Linux kernel compile parallelism (recommended: `8` with 10 CPUs) |
| `CCACHE_MAXSIZE` | `80G` (`run_2in1`) | Maximum ccache size inside `DOCKER_OUT_VOLUME` |
| `SKIP_REPO_SYNC` | `0` | Set to `1` after initial checkout to reuse the prepared Docker source volume |
| `SKIP_PREBUILTS` | `0` | Set to `1` after initial prebuilts download to skip re-running `prebuilts_download.sh` |
| `SKIP_GIT_LFS` | `0` | Set to `1` after initial LFS restoration to skip re-copying the 77 LFS assets |
