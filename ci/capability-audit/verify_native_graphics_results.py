"""Validate narrow native graphics behavior, never compositor or browser proof."""
import json
import re

KINDS = ("vulkan-device", "vulkan-headless", "vulkan-ohos-surface", "gles", "gles-llvm")


def verify(kind, log, exit_code, run_id=None):
    if kind not in KINDS or type(exit_code) is not int or exit_code != 0:
        raise ValueError("native graphics probe did not exit successfully")
    lines = log.replace("\r", "").splitlines()
    if kind == "gles-llvm":
        if len(lines) != 1 or not isinstance(run_id, str) or not re.fullmatch("[a-f0-9]{32}", run_id):
            raise ValueError("isolated real GLES run nonce required")
        row = json.loads(lines[0])
        required = {
            "runId": run_id, "backend": "llvmpipe", "glesVersions": [2, 3],
            "contextGenerations": 6, "shaderPrograms": 6, "shaderPixels": 19507428,
            "pbufferPixels": 6, "swapCount": 6, "teardownCount": 6,
            "scope": "native_GLES_LLVM_shader_lifecycle",
            "compositorTested": False, "pass": True,
        }
        if (set(row) != set(required) | {"pid", "uid", "patternHash"} or
                any(type(row.get(key)) is not type(value) or row[key] != value
                    for key, value in required.items()) or
                type(row["pid"]) is not int or row["pid"] <= 0 or
                type(row["uid"]) is not int or row["uid"] < 0 or
                any(type(value) is not int for value in row["glesVersions"]) or
                not isinstance(row["patternHash"], str) or
                not re.fullmatch("[a-f0-9]{16}", row["patternHash"]) or
                row["patternHash"] == "0" * 16):
            raise ValueError("complete LLVM GLES2/3 shaders, bounds or teardown proof missing")
        return {"scope": row["scope"], "shader_pixels": row["shaderPixels"],
                "context_generations": 6, "backend": "llvmpipe",
                "compositor_tested": False, "webgl_tested": False}
    if kind == "vulkan-device":
        patterns = (r"loader_api=\d+\.\d+\.\d+", r"instance=ok",
                    r"physical_devices=[1-9][0-9]* name=.+ api=\d+\.\d+\.\d+",
                    r"logical_device=ok compute_queue_family=\d+",
                    r"mapped_buffer=ok byte=5a size=4096",
                    r"device_fill=ok words=1024 pattern=12345678")
        if len(lines) != len(patterns) or any(not re.fullmatch(pattern, line)
                                             for pattern, line in zip(patterns, lines)):
            raise ValueError("incomplete Vulkan device/queue/actual data readback")
        return {"scope": "Vulkan logical device queue submission and 1024-word readback only",
                "verified_words": 1024, "compositor_tested": False}
    if kind == "vulkan-headless":
        if len(lines) != 1 or not re.fullmatch(
                r"headless_surface=ok queue_family=\d+ swapchain_images=[1-9][0-9]*", lines[0]):
            raise ValueError("incomplete Vulkan headless surface/swapchain")
        return {"scope": "Vulkan headless swapchain creation only, not rendered frames",
                "compositor_tested": False}
    if kind == "vulkan-ohos-surface":
        expected = {"scope": "OHOS NativeWindow buffer-queue WSI (not compositor)",
                    "presented_frames": 10, "verified_rgba_pixels": 1500,
                    "resize_out_of_date": True, "pass": True}
        if len(lines) != 1:
            raise ValueError("incomplete NativeWindow WSI probe")
        actual = json.loads(lines[0])
        if (actual != expected or any(type(actual[key]) is not type(value)
                                      for key, value in expected.items())):
            raise ValueError("NativeWindow WSI frames/pixels/resize boundary failed")
        return {**expected, "compositor_tested": False}
    for version in (2, 3):
        prefix = f"gles{version}"
        patterns = (prefix + r"\.egl_get_display=1 initialize=1 error=0x3000 version=\d+\.\d+",
                    prefix + r"\.choose=1 count=[1-9][0-9]* error=0x3000",
                    prefix + r"\.surface=1 context=1 current=1 error=0x3000 vendor=.+ renderer=.+ gl_version=.+",
                    prefix + r"\.readback=51,102,153,255 gl_error=0x0 pass=1")
        part = lines[(version - 2) * 4:(version - 1) * 4]
        if len(part) != 4 or any(not re.fullmatch(pattern, line) for pattern, line in zip(patterns, part)):
            raise ValueError("GLES2/3 context or actual RGBA readback failed")
    if len(lines) != 8:
        raise ValueError("mixed or duplicate GLES result")
    return {"scope": "native GLES2/3 offscreen context and RGBA readback only",
            "webgl_tested": False, "compositor_tested": False}
