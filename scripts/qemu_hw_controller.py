#!/usr/bin/env python3
"""Host-side hardware capability controller & bridge for OpenHarmony QEMU.

Provides:
1. Daemon mode (--daemon):
   - Listens on --socket / --virtserial-socket (/tmp/openharmony-qemu-hw-<HDC_PORT>.sock)
     for QEMU's virtserialport `ohos.hw.bridge0`.
   - Listens on --ctrl-socket / --control-socket (/tmp/openharmony-qemu-hw-<HDC_PORT>.ctrl.sock)
     for live host CLI commands.
   - Syncs host UTC epoch ms (`TIME <ms>`) and initial state to the guest upon connection/HELLO.
   - Optionally syncs host <-> guest clipboard when --clipboard-sync or --clipboard=on.

2. CLI client mode:
   - `python3 tools/qemu_hw_controller.py [--socket /tmp/openharmony-qemu-hw-5555.ctrl.sock | --port 5555] status`
   - `python3 tools/qemu_hw_controller.py [--port 5555] gps 39.9042 116.4074 50`
   - `python3 tools/qemu_hw_controller.py [--port 5555] accel 0.0 9.8 0.0`
   - `python3 tools/qemu_hw_controller.py [--port 5555] rotation 0.0 0.0 0.0 1.0`
   - `python3 tools/qemu_hw_controller.py [--port 5555] headposture 1.0 0.0 0.0 0.0`
   - `python3 tools/qemu_hw_controller.py [--port 5555] battery 85 Charging`
   - `python3 tools/qemu_hw_controller.py [--port 5555] thermal 32.5`
   - `python3 tools/qemu_hw_controller.py [--port 5555] camera smpte`
   - `python3 tools/qemu_hw_controller.py [--port 5555] clipboard-set "Hello OHOS"`
   - `python3 tools/qemu_hw_controller.py [--port 5555] clipboard-get`
"""

import argparse
import base64
import logging
import os
import select
import signal
import socket
import subprocess
import sys
import time
from typing import Optional


def get_host_clipboard() -> Optional[str]:
    try:
        if sys.platform == "darwin":
            res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                return res.stdout
    except Exception:
        pass
    return None


def run_daemon(args: argparse.Namespace) -> int:
    logging.basicConfig(
        filename=args.log,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    for sock_path in (args.virtserial_socket, args.control_socket):
        if sock_path and os.path.exists(sock_path):
            try:
                os.unlink(sock_path)
            except OSError:
                pass

    vport_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    vport_srv.bind(args.virtserial_socket)
    vport_srv.listen(2)
    vport_srv.setblocking(False)

    ctrl_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    ctrl_srv.bind(args.control_socket)
    ctrl_srv.listen(8)
    ctrl_srv.setblocking(False)

    if args.pidfile:
        with open(args.pidfile, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n")

    running = True

    def handle_sig(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    guest_conn: Optional[socket.socket] = None
    guest_rx_buf = b""
    pending_ctrl_client: Optional[socket.socket] = None
    pending_ctrl_deadline: float = 0.0
    internal_pending_replies: int = 0
    last_clip_check: float = 0.0
    clip_sync = args.clipboard_sync or args.clipboard == "on"
    initial_clip_text: Optional[str] = None
    if args.clipboard not in ("auto", "on", "off", ""):
        initial_clip_text = args.clipboard
    last_host_clip: Optional[str] = get_host_clipboard() if clip_sync else None

    logging.info(
        "QEMU HW controller started: virtserial=%s control=%s clip_sync=%s",
        args.virtserial_socket,
        args.control_socket,
        clip_sync,
    )

    def send_to_guest(line: str, is_internal: bool = False) -> bool:
        nonlocal guest_conn, internal_pending_replies
        if guest_conn is None:
            return False
        if not line.endswith("\n"):
            line += "\n"
        try:
            guest_conn.sendall(line.encode("utf-8", errors="replace"))
            if is_internal:
                internal_pending_replies += 1
            return True
        except OSError:
            try:
                guest_conn.close()
            except OSError:
                pass
            guest_conn = None
            return False

    def push_initial_state() -> None:
        epoch_ms = int(time.time() * 1000)
        send_to_guest(f"TIME {epoch_ms}", is_internal=True)
        if args.gps:
            send_to_guest(f"GPS {args.gps}", is_internal=True)
        if args.sensor:
            parts = args.sensor.split(":", 1)
            if parts[0]:
                send_to_guest(f"ACCEL {parts[0]}", is_internal=True)
            if len(parts) > 1 and parts[1]:
                send_to_guest(f"ROTATION {parts[1]}", is_internal=True)
        if args.battery:
            send_to_guest(f"BATTERY {args.battery}", is_internal=True)
        if args.thermal:
            send_to_guest(f"THERMAL {args.thermal}", is_internal=True)
        if args.camera:
            send_to_guest(f"CAMERA {args.camera}", is_internal=True)
        if initial_clip_text is not None:
            b64 = base64.b64encode(initial_clip_text.encode("utf-8")).decode("ascii")
            send_to_guest(f"CLIPBOARD_SET_B64 {b64}", is_internal=True)

    try:
        while running:
            rlist = [vport_srv, ctrl_srv]
            if guest_conn is not None:
                rlist.append(guest_conn)
            readable, _, _ = select.select(rlist, [], [], 0.25)

            for s in readable:
                if s is vport_srv:
                    conn, _ = vport_srv.accept()
                    if guest_conn is not None:
                        try:
                            guest_conn.close()
                        except OSError:
                            pass
                    guest_conn = conn
                    guest_conn.setblocking(False)
                    guest_rx_buf = b""
                    internal_pending_replies = 0
                    logging.info("QEMU virtserial socket connected")

                elif s is ctrl_srv:
                    c_conn, _ = ctrl_srv.accept()
                    c_conn.settimeout(1.0)
                    try:
                        raw = c_conn.recv(4096)
                    except OSError:
                        c_conn.close()
                        continue
                    cmd = raw.decode("utf-8", errors="replace").strip()
                    if not cmd:
                        c_conn.close()
                        continue
                    if guest_conn is None:
                        try:
                            c_conn.sendall(b"ERR guest bridge not connected\n")
                        except OSError:
                            pass
                        c_conn.close()
                        continue
                    if pending_ctrl_client is not None:
                        try:
                            pending_ctrl_client.close()
                        except OSError:
                            pass
                    pending_ctrl_client = c_conn
                    pending_ctrl_deadline = time.time() + 4.0
                    send_to_guest(cmd, is_internal=False)

                elif s is guest_conn:
                    try:
                        chunk = guest_conn.recv(4096)
                    except BlockingIOError:
                        continue
                    except OSError:
                        chunk = b""
                    if not chunk:
                        try:
                            guest_conn.close()
                        except OSError:
                            pass
                        guest_conn = None
                        continue
                    guest_rx_buf += chunk
                    while b"\n" in guest_rx_buf:
                        line_bytes, guest_rx_buf = guest_rx_buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        logging.info("Guest line: %s", line)
                        if line.startswith("HELLO"):
                            push_initial_state()
                            continue
                        if internal_pending_replies > 0 and pending_ctrl_client is None:
                            internal_pending_replies -= 1
                            continue
                        if internal_pending_replies > 0 and line.startswith("OK TIME"):
                            internal_pending_replies -= 1
                            continue
                        if pending_ctrl_client is not None:
                            try:
                                pending_ctrl_client.sendall((line + "\n").encode("utf-8"))
                            except OSError:
                                pass
                            try:
                                pending_ctrl_client.close()
                            except OSError:
                                pass
                            pending_ctrl_client = None

            now = time.time()
            if pending_ctrl_client is not None and now > pending_ctrl_deadline:
                try:
                    pending_ctrl_client.sendall(b"ERR timeout waiting for guest bridge\n")
                    pending_ctrl_client.close()
                except OSError:
                    pass
                pending_ctrl_client = None

            # Optional host->guest clipboard sync
            if clip_sync and guest_conn is not None and pending_ctrl_client is None and now - last_clip_check >= 2.0:
                last_clip_check = now
                cur_clip = get_host_clipboard()
                if cur_clip is not None and cur_clip != last_host_clip and len(cur_clip) <= 2048:
                    last_host_clip = cur_clip
                    b64 = base64.b64encode(cur_clip.encode("utf-8")).decode("ascii")
                    send_to_guest(f"CLIPBOARD_SET_B64 {b64}", is_internal=True)

    finally:
        if guest_conn is not None:
            try:
                guest_conn.close()
            except OSError:
                pass
        vport_srv.close()
        ctrl_srv.close()
        for p in (args.virtserial_socket, args.control_socket, args.pidfile):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
    return 0


def run_client(args: argparse.Namespace) -> int:
    ctrl_sock = args.control_socket or args.virtserial_socket
    if not ctrl_sock:
        cand1 = f"/tmp/openharmony-qemu-hw-{args.port}.ctrl.sock"
        cand2 = f"/tmp/openharmony-qemu-hwctl-{args.port}.sock"
        ctrl_sock = cand1 if os.path.exists(cand1) else cand2
    if not os.path.exists(ctrl_sock):
        print(f"Control socket not found: {ctrl_sock}", file=sys.stderr)
        return 2

    sub = args.command[0].lower()
    rest = " ".join(args.command[1:]).strip()
    csv_rest = ",".join(p.strip(",") for p in rest.replace(",", " ").split())
    colon_rest = ":".join(p.strip(":") for p in rest.replace(":", " ").split())
    if sub in ("status", "ping"):
        wire = "STATUS"
    elif sub == "gps":
        wire = f"GPS {csv_rest}"
    elif sub in ("sensor", "accel"):
        wire = f"ACCEL {csv_rest}"
    elif sub == "rotation":
        wire = f"ROTATION {csv_rest}"
    elif sub == "headposture":
        wire = f"HEADPOSTURE {csv_rest}"
    elif sub == "battery":
        wire = f"BATTERY {colon_rest}"
    elif sub == "thermal":
        wire = f"THERMAL {rest}"
    elif sub == "camera":
        wire = f"CAMERA {rest}"
    elif sub == "clipboard-set":
        b64 = base64.b64encode(rest.encode("utf-8")).decode("ascii")
        wire = f"CLIPBOARD_SET_B64 {b64}"
    elif sub == "clipboard-get":
        wire = "CLIPBOARD_GET"
    elif sub == "time":
        ms = int(rest) if rest else int(time.time() * 1000)
        wire = f"TIME {ms}"
    else:
        wire = " ".join(args.command)

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect(ctrl_sock)
    s.sendall((wire + "\n").encode("utf-8"))
    resp = s.recv(4096).decode("utf-8", errors="replace").strip()
    s.close()

    if sub == "clipboard-get" and resp.startswith("CLIPBOARD_B64"):
        parts = resp.split(" ", 1)
        b64_payload = parts[1] if len(parts) > 1 else ""
        try:
            decoded = base64.b64decode(b64_payload).decode("utf-8", errors="replace")
            print(decoded)
            return 0
        except Exception as exc:
            print(f"ERR decode clipboard: {exc}", file=sys.stderr)
            return 1

    print(resp)
    return 1 if resp.startswith("ERR") else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenHarmony QEMU Hardware Capability Controller")
    parser.add_argument("--daemon", action="store_true", help="Run as host virtserial bridge daemon")
    parser.add_argument("--port", type=int, default=5555, help="HDC host port (default: 5555)")
    parser.add_argument("--socket", "--virtserial-socket", dest="virtserial_socket", default="", help="VirtIO serial UNIX socket path (or control socket in client mode)")
    parser.add_argument("--ctrl-socket", "--control-socket", dest="control_socket", default="", help="Host control UNIX socket path")
    parser.add_argument("--pidfile", default="", help="PID file path")
    parser.add_argument("--log", default="/tmp/openharmony-qemu-hw.log", help="Log file path")
    parser.add_argument("--gps", default="", help="Initial GPS coordinates")
    parser.add_argument("--sensor", default="", help="Initial sensor coordinates")
    parser.add_argument("--battery", default="", help="Initial battery state")
    parser.add_argument("--thermal", default="", help="Initial thermal temperature")
    parser.add_argument("--camera", default="", help="Initial camera pattern")
    parser.add_argument("--clipboard", default="auto", help="Clipboard mode or initial text")
    parser.add_argument("--clipboard-sync", action="store_true", help="Enable host-to-guest clipboard auto-sync")
    parser.add_argument("command", nargs="*", help="Command when running in CLI client mode")
    args = parser.parse_args()

    if args.daemon:
        if not args.virtserial_socket:
            args.virtserial_socket = f"/tmp/openharmony-qemu-hw-{args.port}.sock"
        if not args.control_socket:
            args.control_socket = f"/tmp/openharmony-qemu-hw-{args.port}.ctrl.sock"
        return run_daemon(args)

    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    return run_client(args)


if __name__ == "__main__":
    sys.exit(main())
