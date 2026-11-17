#!/usr/bin/env python3
"""Exact QEMU gralloc repair; no permissions, kernel ABI or format substitution."""
import argparse
from pathlib import Path
import subprocess

REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
FILE = 'common/virt_full/hardware/display/src/display_gralloc/hi_gbm.cpp'
OLD_GEOMETRY = '''static uint32_t AdjustStrideFromFormat(uint32_t format, uint32_t height)
{
    uint32_t tmpHeight = height;
    const FormatInfo *fmtInfo = GetFormatInfo(format);
    if ((fmtInfo != nullptr) && (fmtInfo->planes != nullptr)) {
        uint32_t sum = fmtInfo->planes->radio[0];
        for (uint32_t i = 1; (i < fmtInfo->planes->numPlanes) && (i < MAX_PLANES); i++) {
            sum += fmtInfo->planes->radio[i];
        }
        if (sum > 0) {
            tmpHeight = DIV_ROUND_UP((height * sum), fmtInfo->planes->radio[0]);
        }
        DISPLAY_LOGD("height adjust to : %{public}d", tmpHeight);
    }
    return tmpHeight;
}
'''
NEW_GEOMETRY = '''static bool PrepareDumbGeometry(uint32_t width, uint32_t height, const FormatInfo &format,
    bool virtioGpu, uint32_t usage, struct drm_mode_create_dumb &dumb)
{
    if (width == 0 || height == 0) {
        return false;
    }
    uint64_t storageHeight = height;
    if (format.planes != nullptr) {
        const auto &planes = *format.planes;
        if (planes.numPlanes < 2 || planes.numPlanes > MAX_PLANES || planes.radio[0] == 0 || width % 2 != 0) {
            return false;
        }
        uint64_t sum = 0;
        for (uint32_t i = 0; i < planes.numPlanes; ++i) {
            sum += planes.radio[i];
        }
        if (sum < 2ULL * planes.radio[0] && height % 2 != 0) {
            return false;
        }
        storageHeight = (static_cast<uint64_t>(height) * sum + planes.radio[0] - 1) / planes.radio[0];
    }
    storageHeight = (storageHeight + HEIGHT_ALIGN - 1) / HEIGHT_ALIGN * HEIGHT_ALIGN;
    const uint64_t storageWidth = (static_cast<uint64_t>(width) + WIDTH_ALIGN - 1) / WIDTH_ALIGN * WIDTH_ALIGN;
    const uint64_t pitch = storageWidth * format.bitsPerPixel / 8;
    // BufferHandle and the media allocator use signed 32-bit byte sizes.
    if (pitch == 0 || pitch > UINT32_MAX || storageHeight > UINT32_MAX ||
        storageHeight > static_cast<uint64_t>(INT32_MAX - 65535) / pitch) {
        return false;
    }
    dumb.width = static_cast<uint32_t>(storageWidth);
    dumb.height = static_cast<uint32_t>(storageHeight);
    dumb.bpp = format.bitsPerPixel;
    if (virtioGpu && format.bitsPerPixel != 32) {
        const uint32_t cpu = GBM_BO_USE_SW_READ_OFTEN | GBM_BO_USE_SW_READ_RARELY |
            GBM_BO_USE_SW_WRITE_OFTEN | GBM_BO_USE_SW_WRITE_RARELY;
        if (format.bitsPerPixel != 8 || format.planes == nullptr || (usage & cpu) == 0 ||
            (usage & (GBM_BO_USE_SCANOUT | GBM_BO_USE_PROTECTED)) != 0) {
            return false;
        }
        // Virtio dumb resources are 32-bit, but these CPU-accessible YUV
        // buffers need byte storage, not a YUV KMS scanout resource. Pack four
        // bytes per storage pixel; keep the logical YUV format, dimensions,
        // actual byte pitch and plane layout in the exported buffer handle.
        dumb.width = static_cast<uint32_t>(pitch / 4);
        dumb.bpp = 32;
    }
    return true;
}

static bool IsVirtioGpu(struct gbm_device *gbm)
{
    drmVersionPtr version = drmGetVersion(gbm->fd);
    const char expected[] = "virtio_gpu";
    const bool result = version != nullptr && version->name != nullptr &&
        version->name_len == static_cast<int>(sizeof(expected) - 1) &&
        memcmp(version->name, expected, sizeof(expected) - 1) == 0;
    if (version != nullptr) {
        drmFreeVersion(version);
    }
    return result;
}
'''
REPLACEMENTS = (
    ('#include <cstdlib>\n', '#include <cstdlib>\n#include <climits>\n'),
    (OLD_GEOMETRY, NEW_GEOMETRY),
    ('    DISPLAY_UNUSED(usage);\n', ''),
    ('    bo = (struct gbm_bo *)calloc(1, sizeof(struct gbm_bo));\n',
     '    DISPLAY_CHK_RETURN(gbm == nullptr, nullptr, DISPLAY_LOGE("gbm is null"));\n'
     '    DISPLAY_CHK_RETURN(!PrepareDumbGeometry(width, height, *fmtInfo, IsVirtioGpu(gbm), usage, dumb),\n'
     '        nullptr, DISPLAY_LOGE("invalid or unsupported dumb buffer geometry/usage"));\n'
     '    bo = (struct gbm_bo *)calloc(1, sizeof(struct gbm_bo));\n'),
    ('    dumb.height = ALIGN_UP(AdjustStrideFromFormat(format, height), HEIGHT_ALIGN);\n'
     '    dumb.width = ALIGN_UP(width, WIDTH_ALIGN);\n    dumb.flags = 0;\n'
     '    dumb.bpp = fmtInfo->bitsPerPixel;\n', '    dumb.flags = 0;\n'),
    ('    DISPLAY_CHK_RETURN((ret != 0), nullptr, DISPLAY_LOGE("DRM_IOCTL_MODE_CREATE_DUMB failed errno %{public}d", errno));\n',
     '    if (ret != 0) {\n'
     '        DISPLAY_LOGE("DRM_IOCTL_MODE_CREATE_DUMB failed errno %{public}d", errno);\n'
     '        free(bo);\n        return nullptr;\n    }\n'),
    ('    DISPLAY_CHK_RETURN_NOT_VALUE((ret), DISPLAY_LOGE("dumb buffer destroy failed errno %{public}d", errno));\n    free(bo);\n',
     '    if (ret != 0) {\n'
     '        DISPLAY_LOGE("dumb buffer destroy failed errno %{public}d", errno);\n    }\n    free(bo);\n'),
)


def repaired_source(original):
    repaired = original
    for old, new in REPLACEMENTS:
        if repaired.count(old) != 1:
            raise ValueError('unexpected fixed QEMU GBM source structure')
        repaired = repaired.replace(old, new)
    return repaired


def validate(root, require_patched=False):
    project = root / 'device/qemu'
    path = project / FILE
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('QEMU gralloc destination contains a symlink')
        cursor = cursor.parent
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('QEMU gralloc requires the fixed 7.0 device source')
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + FILE]).decode()
    repaired = repaired_source(original)
    current = path.read_text()
    if current != repaired and (require_patched or current != original):
        raise ValueError('unknown/incomplete QEMU gralloc edits; preserving source')
    return current == repaired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('QEMU CPU YUV storage patch present: ' + str(validate(args.source_root.resolve(), args.require_patched)))


if __name__ == '__main__':
    main()
