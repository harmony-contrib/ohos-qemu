#!/usr/bin/env python3
"""Fail closed on Web execution timeouts, context-only success, or bad pixels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = {
    "web.js.arithmetic": 2,
    "web.js.dom": "QEMU ArkWeb Audit",
    "web.canvas.2d": True,
    "web.graphics.webgl1": True,
    "web.graphics.webgl2": True,
    "web.js.exception": "Error:QEMU_WEB_EXPECTED_ERROR",
    "web.js.after_exception": 42,
    "web.reload.dom": "QEMU ArkWeb Audit",
    "web.renderer.terminate": True,
    "web.renderer.exit": True,
    "web.renderer.recovery.dom": "QEMU ArkWeb Audit",
}


def decode(value: str):
    for _ in range(2):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return value
        if not isinstance(decoded, str):
            return decoded
        value = decoded
    return value


def verify(log: str) -> dict:
    failures = []
    results = {}
    proxy_callbacks = []
    complete = False
    for line in log.splitlines():
        offset = line.find("web.")
        if offset < 0:
            continue
        key, separator, value = line[offset:].partition("=")
        if not separator:
            continue
        if key.endswith((".error", ".sync_error", ".timeout", ".late")):
            failures.append(f"failed Web step: {key}")
        if key.endswith(".result"):
            name = key.removesuffix(".result")
            decoded = decode(value)
            if name in results and results[name] != decoded:
                failures.append(f"contradictory Web result: {name}")
            results[name] = decoded
        if key == "web.js.proxy.callback":
            proxy_callbacks.append(value.strip())
        if key == "web.execution.complete" and value.strip() == "true":
            complete = True
    if not complete:
        failures.append("Web execution did not complete")
    for name, expected in REQUIRED.items():
        if name not in results or type(results[name]) is not type(expected) or results[name] != expected:
            failures.append(f"missing or unexpected result: {name}")
    for name, shader in (("web.canvas.2d.render", False),
                         ("web.graphics.webgl1.render", True),
                         ("web.graphics.webgl2.render", True),
                         ("web.renderer.recovery.webgl1.render", True),
                         ("web.renderer.recovery.webgl2.render", True)):
        result = results.get(name)
        if not isinstance(result, dict):
            failures.append(f"missing render result: {name}")
            continue
        pixel = result.get("pixel")
        if (result.get("pass") is not True or
                (shader and (type(result.get("error")) is not int or result["error"] != 0 or
                             result.get("invalid_shader_rejected") is not True)) or
                not isinstance(pixel, list) or len(pixel) != 4 or
                any(type(channel) is not int for channel in pixel) or
                any(abs(pixel[i] - value) > 1 for i, value in enumerate((51, 102, 153))) or pixel[3] != 255):
            failures.append(f"shader boundary or pixel readback failed: {name}")
    if proxy_callbacks != ["js", "reload", "renderer.recovery"]:
        failures.append("missing, repeated or out-of-order ArkTS proxy callbacks")
    for count, name in enumerate(("js", "reload", "renderer.recovery"), start=1):
        result = results.get(f"web.{name}.proxy")
        if (not isinstance(result, dict) or result.get("reply") != f"arkts:{name}" or
                type(result.get("calls")) is not int or result["calls"] != count):
            failures.append(f"proxy round trip or retained ArkTS state failed: {name}")
    return {"status": "pass" if not failures else "fail", "failures": failures,
            "results": results, "proxy_callbacks": proxy_callbacks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.log.read_text(encoding="utf-8"))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["status"] == "pass" else 1)
