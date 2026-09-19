#!/usr/bin/env python3
"""Keep a headless QEMU guest active and wake it if it suspends."""

import argparse
import json
import socket
import time


def command(connection, stream, name: str, arguments: dict | None = None) -> dict:
    request = {"execute": name, "id": name}
    if arguments is not None:
        request["arguments"] = arguments
    connection.sendall(json.dumps(request).encode() + b"\n")
    while True:
        line = stream.readline()
        if not line:
            raise ConnectionError("QMP disconnected")
        reply = json.loads(line)
        if reply.get("id") == name:
            return reply


def wake(path: str) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(path)
        with connection.makefile("rwb", buffering=0) as stream:
            greeting = stream.readline()
            if "QMP" not in json.loads(greeting):
                raise RuntimeError("unexpected QMP greeting")
            if "return" not in command(connection, stream, "qmp_capabilities"):
                raise RuntimeError("QMP capabilities negotiation failed")
            woke = "return" in command(connection, stream, "system_wakeup")
            # The headless x86 guest locks its screen after inactivity even
            # when its screen-off timeout is overridden. A harmless key event
            # keeps the test window active so aa test can launch abilities.
            key = {"type": "qcode", "data": "a"}
            events = [
                {"type": "key", "data": {"down": True, "key": key}},
                {"type": "key", "data": {"down": False, "key": key}},
            ]
            activity = command(connection, stream, "input-send-event", {"events": events})
            if "error" in activity:
                raise RuntimeError(f"QMP input-send-event failed: {activity['error']}")
            return woke


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("socket")
    args = parser.parse_args()
    first_activity = True
    while True:
        try:
            woke = wake(args.socket)
            if first_activity:
                print("QMP keyboard keepalive active", flush=True)
                first_activity = False
            if woke:
                print(f"woke suspended guest at {time.strftime('%Y-%m-%dT%H:%M:%S%z')}", flush=True)
        except (OSError, ValueError, RuntimeError) as error:
            print(f"QMP wake retry: {error}", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
