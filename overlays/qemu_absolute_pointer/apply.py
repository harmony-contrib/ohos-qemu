#!/usr/bin/env python3
"""Apply the OpenHarmony QEMU absolute-pointer coordinate fix."""

from __future__ import annotations

import sys
from pathlib import Path


MARKER = "QEMU_ABSOLUTE_POINTER_SYNC"
RELATIVE_BLOCK = """    unaccelerated_.dx = libinput_event_pointer_get_dx_unaccelerated(data);
    unaccelerated_.dy = libinput_event_pointer_get_dy_unaccelerated(data);
    ctx.dx = unaccelerated_.dx;
    ctx.dy = unaccelerated_.dy;
    ctx.libinputEventType = libinput_event_get_type(event);
    ctx.offset = Offset { unaccelerated_.dx, unaccelerated_.dy };
"""
EVENT_TYPE_BLOCK = """    ctx.libinputEventType = libinput_event_get_type(event);
"""
DISPLAY_BLOCK = """    ctx.displayInfo = winMgr->GetPhysicalDisplay(cursorPos.displayId);
    if (ctx.displayInfo == nullptr) {
        MMI_HILOGE(\"displayInfo is nullptr\");
        return ctx;
    }

    ctx.deviceType = CheckDeviceType(ctx.displayInfo->width, ctx.displayInfo->height);
"""
ABSOLUTE_BLOCK = """    ctx.displayInfo = winMgr->GetPhysicalDisplay(cursorPos.displayId);
    if (ctx.displayInfo == nullptr) {
        MMI_HILOGE(\"displayInfo is nullptr\");
        return ctx;
    }

    // QEMU_ABSOLUTE_POINTER_SYNC: map the virtio-tablet range to the current
    // guest framebuffer. This keeps pointer coordinates correct when QEMU's
    // window is scaled or the guest GPU resolution changes.
    if (ctx.libinputEventType == LIBINPUT_EVENT_POINTER_MOTION_ABSOLUTE) {
        const int32_t width = ctx.displayInfo->validWidth > 0 ?
            ctx.displayInfo->validWidth : ctx.displayInfo->width;
        const int32_t height = ctx.displayInfo->validHeight > 0 ?
            ctx.displayInfo->validHeight : ctx.displayInfo->height;
        if (width <= 0 || height <= 0) {
            MMI_HILOGE(\"Invalid display size, width:%{public}d height:%{public}d\", width, height);
            return ctx;
        }
        ctx.offset.dx = libinput_event_pointer_get_absolute_x_transformed(
            data, static_cast<uint32_t>(width));
        ctx.offset.dy = libinput_event_pointer_get_absolute_y_transformed(
            data, static_cast<uint32_t>(height));
        ctx.dx = ctx.offset.dx;
        ctx.dy = ctx.offset.dy;
    } else {
        unaccelerated_.dx = libinput_event_pointer_get_dx_unaccelerated(data);
        unaccelerated_.dy = libinput_event_pointer_get_dy_unaccelerated(data);
        ctx.dx = unaccelerated_.dx;
        ctx.dy = unaccelerated_.dy;
        ctx.offset = Offset { unaccelerated_.dx, unaccelerated_.dy };
    }

    ctx.deviceType = CheckDeviceType(ctx.displayInfo->width, ctx.displayInfo->height);
"""
MOTION_BRANCH = """    if (ctx.libinputEventType == LIBINPUT_EVENT_POINTER_MOTION_TOUCHPAD) {
"""
ABSOLUTE_BRANCH = """    if (ctx.libinputEventType == LIBINPUT_EVENT_POINTER_MOTION_ABSOLUTE) {
        pointerEvent_->ClearFlag(InputEvent::EVENT_FLAG_TOUCHPAD_POINTER);
        pointerEvent_->ClearFlag(InputEvent::EVENT_FLAG_VIRTUAL_TOUCHPAD_POINTER);
        ctx.cursorX = ctx.offset.dx;
        ctx.cursorY = ctx.offset.dy;
        ret = RET_OK;
    } else if (ctx.libinputEventType == LIBINPUT_EVENT_POINTER_MOTION_TOUCHPAD) {
"""


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"cannot apply absolute-pointer overlay: expected one {description}, found {count}"
        )
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply.py OHOS_ROOT")

    root = Path(sys.argv[1]).resolve()
    target = root / (
        "foundation/multimodalinput/input/service/mouse_event_normalize/src/"
        "mouse_transform_processor.cpp"
    )
    if not target.is_file():
        raise SystemExit(f"OpenHarmony mouse transform source not found: {target}")

    text = target.read_text(encoding="utf-8")
    required = (
        MARKER,
        "libinput_event_pointer_get_absolute_x_transformed",
        "libinput_event_pointer_get_absolute_y_transformed",
        "ctx.cursorX = ctx.offset.dx",
        "ctx.cursorY = ctx.offset.dy",
    )
    if all(token in text for token in required):
        print(f"QEMU absolute-pointer overlay already applied: {target}")
        return
    if MARKER in text:
        raise SystemExit(f"incomplete QEMU absolute-pointer overlay in {target}")

    text = replace_once(text, RELATIVE_BLOCK, EVENT_TYPE_BLOCK, "relative extraction block")
    text = replace_once(text, DISPLAY_BLOCK, ABSOLUTE_BLOCK, "display lookup block")
    text = replace_once(text, MOTION_BRANCH, ABSOLUTE_BRANCH, "motion dispatch branch")
    target.write_text(text, encoding="utf-8")
    print(f"applied QEMU absolute-pointer overlay: {target}")


if __name__ == "__main__":
    main()
