#!/usr/bin/env python3
"""
Virtual AT Modem responder for OpenHarmony QEMU (`riladapter_host` / `libril_vendor.z.so`).

Connects to or listens on a UNIX domain socket backing QEMU's `virtserialport`
(`ohos.ril.at0`, exposed in the guest as `/dev/vport0p1` -> `/dev/ttyUSB0`)
and emulates a 3GPP / Huawei-AT compatible LTE/5G cellular modem with an
active SIM card (`460001380013800`, operator `OpenHarmony` / `46000`).
"""

import argparse
import os
import select
import signal
import socket
import sys
import time
from typing import Dict, List, Optional, Tuple


# Standard Elementary Files (EF) for GSM 11.11 / 3GPP TS 31.102 SIM I/O (AT+CRSM)
# Format: file_id -> (ef_structure, record_len, hex_payload_or_records)
# ef_structure: 0x00 = transparent, 0x01 = linear fixed
SIM_EF_TABLE: Dict[int, Tuple[int, int, List[str]]] = {
    # EF_ICCID (0x2FE2): BCD-swapped 8986001000000000000F
    0x2FE2: (0x00, 0, ["986800100000000000F0"]),
    # EF_IMSI (0x6F07): length 08 + 9064003108108300
    0x6F07: (0x00, 0, ["084906003108108300"]),
    # EF_AD (0x6FAD): Administrative Data (normal operation, MNC length = 2)
    0x6FAD: (0x00, 0, ["00000002"]),
    # EF_PHASE (0x6FAE): Phase 2+
    0x6FAE: (0x00, 0, ["03"]),
    # EF_SPN (0x6F46): Service Provider Name ("OpenHarmony")
    0x6F46: (0x00, 0, ["004F70656E4861726D6F6E79FFFFFFFFFFFF"]),
    # EF_SST (0x6F38): SIM Service Table
    0x6F38: (0x00, 0, ["FF3FFF0300003F03000C0000F00300"]),
    # EF_UST (0x6F38 in USIM): handled above
    # EF_ACC (0x6F78): Access Control Class
    0x6F78: (0x00, 0, ["0001"]),
    # EF_LOCI (0x6F7E): Location Information
    0x6F7E: (0x00, 0, ["FFFFFFFF64F00000010000"]),
    # EF_FPLMN (0x6F7B): Forbidden PLMNs (empty)
    0x6F7B: (0x00, 0, ["FFFFFFFFFFFFFFFFFFFFFFFF"]),
    # EF_GID1 (0x6F3E): Group Identifier Level 1
    0x6F3E: (0x00, 0, ["FFFF"]),
    # EF_GID2 (0x6F3F): Group Identifier Level 2
    0x6F3F: (0x00, 0, ["FFFF"]),
    # EF_LI / EF_ELP (0x6F05): Language Indication ("en", "zh")
    0x6F05: (0x00, 0, ["656E7A68FFFF"]),
    # EF_CPHS_INFO (0x6F16)
    0x6F16: (0x00, 0, ["000000"]),
    # EF_CSP (0x6F15)
    0x6F15: (0x00, 0, ["0000"]),
    # EF_ONS (0x6F14): Operator Name String ("OpenHarmony")
    0x6F14: (0x00, 0, ["4F70656E4861726D6F6E79FFFFFFFF"]),
    # EF_ONS_SHORT (0x6F18): Short Operator Name ("OHOS")
    0x6F18: (0x00, 0, ["4F484F53FFFFFFFFFFFF"]),
    # EF_MSISDN (0x6F40): Linear fixed, 28 bytes/record, "+8613800138000"
    0x6F40: (
        0x01,
        28,
        ["FFFFFFFFFFFFFFFFFFFFFFFFFFFF0891683108108300F0FFFFFFFFFFFF"],
    ),
    # EF_SMSP (0x6F42): Linear fixed, 28 bytes/record, SMSC "+8613800100500"
    0x6F42: (
        0x01,
        28,
        ["FFFFFFFFFFFFFFFFFFFFFFFFFDFFFFFFFFFFFFFF0891683108100005F0FF"],
    ),
    # EF_PNN (0x6FC5): PLMN Network Name ("OpenHarmony")
    0x6FC5: (
        0x01,
        16,
        ["430B804F70656E4861726D6F6E79FFFF"],
    ),
    # EF_OPL (0x6FC6): Operator PLMN List
    0x6FC6: (
        0x01,
        8,
        ["64F0000000FFFE01"],
    ),
    # EF_CFIS (0x6FCB): Call Forwarding Indication Status
    0x6FCB: (
        0x01,
        16,
        ["0100FFFFFFFFFFFFFFFFFFFFFFFFFFFF"],
    ),
    # EF_MWIS (0x6FCA): Message Waiting Indication Status
    0x6FCA: (
        0x01,
        5,
        ["0000000000"],
    ),
    # EF_MBDN (0x6FC7): Mailbox Dialling Numbers
    0x6FC7: (
        0x01,
        28,
        ["FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"],
    ),
    # EF_MBI (0x6FC9): Mailbox Identifier
    0x6FC9: (
        0x01,
        4,
        ["01010101"],
    ),
}


def build_gsm_sim_get_response(file_id: int) -> str:
    """Build a 15-byte GSM 11.11 GET_RESPONSE hex string for AT+CRSM=192."""
    if file_id in SIM_EF_TABLE:
        ef_struct, rec_len, records = SIM_EF_TABLE[file_id]
        if ef_struct == 0x00:
            file_size = len(records[0]) // 2
        else:
            file_size = rec_len * len(records)
    else:
        ef_struct = 0x00
        rec_len = 0
        file_size = 16

    resp = bytearray(15)
    resp[0] = 0x00
    resp[1] = 0x00
    resp[2] = (file_size >> 8) & 0xFF
    resp[3] = file_size & 0xFF
    resp[4] = (file_id >> 8) & 0xFF
    resp[5] = file_id & 0xFF
    resp[6] = 0x04  # EF
    resp[7] = 0x00
    resp[8] = 0x00  # Access conditions: ALW/PIN1
    resp[9] = 0x00
    resp[10] = 0x00
    resp[11] = 0x01  # Valid file status
    resp[12] = 0x02  # Length of following data
    resp[13] = ef_struct
    resp[14] = rec_len & 0xFF
    return resp.hex().upper()


class VirtualAtModem:
    def __init__(self, log_fp=None):
        self.log_fp = log_fp
        self.radio_state = 1
        self.sim_ready = True
        self.imsi = "460001380013800"
        self.imei = "868323050000001"
        self.imeisv = "86832305000000101"
        self.meid = "A0000012345678"
        self.smsc = "+8613800100500"
        self.operator_long = "OpenHarmony"
        self.operator_short = "OHOS"
        self.operator_numeric = "46000"
        self.lac = "0001"
        self.cell_id = "00000101"
        self.act = 7  # 7 = E-UTRAN (LTE)
        self.mute = 0
        self.awaiting_pdu = False
        self.pending_sms_cmd = ""
        self.pdp_contexts: Dict[int, Tuple[str, str, int]] = {
            1: ("IP", "cmnet", 1),
        }
        self.active_calls: List[Dict[str, object]] = []
        self.next_call_id = 1

    def log(self, msg: str) -> None:
        if self.log_fp is not None:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log_fp.write(f"[{ts}] {msg}\n")
            self.log_fp.flush()

    def handle_crsm(self, args_str: str) -> str:
        # Format: AT+CRSM=<command>,<fileid>,<p1>,<p2>,<p3>[,"<data>"[,"<pathid>"]]
        parts = [p.strip().strip('"') for p in args_str.split(",")]
        try:
            command = int(parts[0]) if len(parts) > 0 and parts[0] else 0
            file_id = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            p1 = int(parts[2]) if len(parts) > 2 and parts[2] else 0
            p2 = int(parts[3]) if len(parts) > 3 and parts[3] else 0
            p3 = int(parts[4]) if len(parts) > 4 and parts[4] else 0
        except ValueError:
            return '+CRSM: 144,0,""\r\nOK\r\n'

        # 192 = GET RESPONSE
        if command == 192:
            fcp_hex = build_gsm_sim_get_response(file_id)
            return f'+CRSM: 144,0,"{fcp_hex}"\r\nOK\r\n'

        # 176 = READ BINARY
        if command == 176:
            if file_id in SIM_EF_TABLE:
                _, _, records = SIM_EF_TABLE[file_id]
                data_hex = records[0]
            else:
                data_hex = "FF" * max(p3, 1)
            offset = (p1 << 8) | p2
            start = offset * 2
            if p3 > 0:
                end = start + p3 * 2
                slice_hex = data_hex[start:end]
                if len(slice_hex) < p3 * 2:
                    slice_hex += "FF" * (p3 - len(slice_hex) // 2)
            else:
                slice_hex = data_hex[start:]
            return f'+CRSM: 144,0,"{slice_hex}"\r\nOK\r\n'

        # 178 = READ RECORD
        if command == 178:
            rec_idx = max(p1 - 1, 0)
            if file_id in SIM_EF_TABLE:
                _, rec_len, records = SIM_EF_TABLE[file_id]
                if rec_idx < len(records):
                    rec_hex = records[rec_idx]
                else:
                    rec_hex = "FF" * max(rec_len, p3, 1)
            else:
                rec_hex = "FF" * max(p3, 16)
            return f'+CRSM: 144,0,"{rec_hex}"\r\nOK\r\n'

        # 214 = UPDATE BINARY / 220 = UPDATE RECORD
        return '+CRSM: 144,0,""\r\nOK\r\n'

    def process_line(self, raw_line: str) -> Tuple[str, List[str]]:
        """
        Process a single AT command line.
        Returns (immediate_response, unsolicited_notifications_after_ok).
        """
        line = raw_line.strip()
        if not line:
            return "", []

        self.log(f"RX: {line}")

        if self.awaiting_pdu:
            self.awaiting_pdu = False
            cmd_prefix = "+CMGW" if "CMGW" in self.pending_sms_cmd else "+CMGS"
            self.pending_sms_cmd = ""
            return f"{cmd_prefix}: 1\r\nOK\r\n", []

        upper = line.upper()

        # Combined operator query: AT+COPS=3,0;+COPS?;+COPS=3,1;+COPS?;+COPS=3,2;+COPS?
        if "+COPS=3,0;+COPS?;+COPS=3,1;+COPS?;+COPS=3,2;+COPS?" in upper:
            resp = (
                f'+COPS: 0,0,"{self.operator_long}"\r\n'
                f'+COPS: 0,1,"{self.operator_short}"\r\n'
                f'+COPS: 0,2,"{self.operator_numeric}"\r\n'
                "OK\r\n"
            )
            return resp, []

        # Basic AT / ModemInit setup commands
        if upper in ("AT", "ATE0", "ATE0Q0V1", "ATQ0", "ATV1"):
            return "OK\r\n", []

        # Radio power state
        if upper.startswith("AT+CFUN="):
            arg = upper[len("AT+CFUN=") :].split(",")[0].strip()
            try:
                self.radio_state = int(arg)
            except ValueError:
                self.radio_state = 1
            unsolicited: List[str] = []
            if self.radio_state == 1:
                unsolicited = [
                    "^SIMST: 1\r\n",
                    f'+CREG: 1,"{self.lac}","{self.cell_id}",{self.act}\r\n',
                    f'+CGREG: 1,"{self.lac}","{self.cell_id}",{self.act}\r\n',
                    '^HCSQ: "LTE",55,50,150,25\r\n',
                ]
            return "OK\r\n", unsolicited

        if upper == "AT+CFUN?":
            return f"+CFUN: {self.radio_state}\r\nOK\r\n", []

        # SIM status & card mode
        if upper in ("AT^CARDMODE", "AT^CARDMODE?"):
            # 1 = SIM (uses standard 15-byte GSM 11.11 GET_RESPONSE with file size intact)
            return "^CARDMODE: 1\r\nOK\r\n", []

        if upper == "AT+CPIN?":
            return "+CPIN: READY\r\nOK\r\n", []

        if upper.startswith("AT+CPIN="):
            return "OK\r\n", []

        if upper == "AT^CPIN?":
            return "^CPIN: READY,10,10,3,10,3\r\nOK\r\n", []

        if upper == "AT^CPIN2?":
            return "^CPIN2: READY,10,10,3,10,3\r\nOK\r\n", []

        if upper == "AT+CIMI":
            return f"{self.imsi}\r\nOK\r\n", []

        if upper.startswith("AT+CRSM="):
            return self.handle_crsm(line[len("AT+CRSM=") :]), []

        if upper.startswith("AT+CLCK="):
            if upper.endswith(",2"):
                return "+CLCK: 0\r\nOK\r\n", []
            return "OK\r\n", []

        # Device identity & baseband version
        if upper in ("AT+CGSN", "AT+GSN"):
            return f"{self.imei}\r\nOK\r\n", []

        if upper in ("AT+CFSN", "AT^SN"):
            return "OHOSQEMU000001\r\nOK\r\n", []

        if upper == "AT+IMEISV":
            return f"{self.imeisv}\r\nOK\r\n", []

        if upper == "AT+MEID":
            return f"{self.meid}\r\nOK\r\n", []

        if upper in ("AT+CGMR", "AT^VERSION?"):
            return "OpenHarmony-QEMU-Modem-1.0\r\nOK\r\n", []

        if upper == "AT+CGMM":
            return "QEMU-Virtual-LTE-Modem\r\nOK\r\n", []

        if upper == "AT+CGMI":
            return "OpenHarmony\r\nOK\r\n", []

        # Network registration & signal strength
        if upper == "AT+CREG?":
            return f'+CREG: 2,1,"{self.lac}","{self.cell_id}",{self.act}\r\nOK\r\n', []

        if upper == "AT+CGREG?":
            return f'+CGREG: 2,1,"{self.lac}","{self.cell_id}",{self.act}\r\nOK\r\n', []

        if upper == "AT+CEREG?":
            return f'+CEREG: 2,1,"{self.lac}","{self.cell_id}",{self.act}\r\nOK\r\n', []

        if upper == "AT+COPS?":
            return f'+COPS: 0,0,"{self.operator_long}",{self.act}\r\nOK\r\n', []

        if upper == "AT+COPS=?":
            return (
                f'+COPS: (2,"{self.operator_long}","{self.operator_short}","{self.operator_numeric}",{self.act})\r\n'
                "OK\r\n"
            ), []

        if upper == "AT^HCSQ?":
            # Note: ReqGetSignalStrength checks strlen(result) > 20 and calls
            # ProcessParamSignalStrength which expects 2 integer prefixes before "LTE".
            return '^HCSQ: 0,0,"LTE",55,50,150,25\r\nOK\r\n', []

        if upper == "AT+CSQ":
            return "+CSQ: 28,99\r\nOK\r\n", []

        if upper in ("AT^SYSINFOEX", "AT^SYSINFOEX?"):
            return '^SYSINFOEX: 2,3,0,1,0,6,"LTE",101,"LTE"\r\nOK\r\n', []

        if upper in ("AT^SYSCFGEX?", "AT^SYSCFG?"):
            return '^SYSCFGEX: "030201",3FFFFFFF,1,2,7FFFFFFFFFFFFFFF\r\nOK\r\n', []

        if upper in ("AT^MONSC", "AT^MONNC"):
            return '^MONSC: "LTE",460,00,1650,101,257,1,-85,-8,-55,20\r\nOK\r\n', []

        if upper == "AT+CIREG?":
            return "+CIREG: 2,1,1\r\nOK\r\n", []

        # Cellular Data / PDP contexts
        if upper == "AT+CGACT?":
            lines = [
                f"+CGACT: {cid},{active}"
                for cid, (_, _, active) in sorted(self.pdp_contexts.items())
            ]
            return "\r\n".join(lines) + "\r\nOK\r\n", []

        if upper == "AT+CGDCONT?":
            lines = [
                f'+CGDCONT: {cid},"{ip_type}","{apn}","10.0.2.15",0,0'
                for cid, (ip_type, apn, _) in sorted(self.pdp_contexts.items())
            ]
            return "\r\n".join(lines) + "\r\nOK\r\n", []

        if upper.startswith("AT+CGDCONT="):
            parts = [p.strip().strip('"') for p in line[len("AT+CGDCONT=") :].split(",")]
            try:
                cid = int(parts[0])
                ip_type = parts[1] if len(parts) > 1 and parts[1] else "IP"
                apn = parts[2] if len(parts) > 2 and parts[2] else "cmnet"
                prev_active = self.pdp_contexts.get(cid, ("IP", "cmnet", 1))[2]
                self.pdp_contexts[cid] = (ip_type, apn, prev_active)
            except ValueError:
                pass
            return "OK\r\n", []

        if upper.startswith("AT^NDISDUP="):
            parts = [p.strip() for p in line[len("AT^NDISDUP=") :].split(",")]
            try:
                cid = int(parts[0])
                active = int(parts[1]) if len(parts) > 1 else 1
                ip_type, apn, _ = self.pdp_contexts.get(cid, ("IP", "cmnet", active))
                self.pdp_contexts[cid] = (ip_type, apn, active)
            except ValueError:
                pass
            return "OK\r\n", []

        if upper == "AT^DHCP?":
            # Hex little-endian IPv4 addresses for 10.0.2.15, 255.255.255.0, 10.0.2.2, 10.0.2.2, 10.0.2.3, 8.8.8.8
            return "^DHCP: 0F02000A,00FFFFFF,0202000A,0202000A,0302000A,08080808,150000000,150000000\r\nOK\r\n", []

        # Voice Calls
        if upper in ("AT+CLCC", "AT^CLCC"):
            if not self.active_calls:
                return "OK\r\n", []
            prefix = "^CLCC" if upper == "AT^CLCC" else "+CLCC"
            lines = []
            for c in self.active_calls:
                if prefix == "^CLCC":
                    lines.append(
                        f'{prefix}: {c["id"]},{c["dir"]},{c["state"]},{c["mode"]},{c["mpty"]},'
                        f'1,0,0,"{c["number"]}",{c["type"]}'
                    )
                else:
                    lines.append(
                        f'{prefix}: {c["id"]},{c["dir"]},{c["state"]},{c["mode"]},{c["mpty"]},'
                        f'"{c["number"]}",{c["type"]}'
                    )
            return "\r\n".join(lines) + "\r\nOK\r\n", []

        if upper.startswith("ATD"):
            num = line[3:].rstrip(";").strip()
            call_id = self.next_call_id
            self.next_call_id += 1
            self.active_calls.append(
                {
                    "id": call_id,
                    "dir": 0,
                    "state": 0,  # active
                    "mode": 0,
                    "mpty": 0,
                    "number": num,
                    "type": 145 if num.startswith("+") else 129,
                }
            )
            return "OK\r\n", [f"^CCALLSTATE: {call_id},0,1\r\n"]

        if upper in ("ATH", "AT+CHUP") or upper.startswith("AT+CHLD="):
            self.active_calls.clear()
            return "OK\r\n", ["^CCALLSTATE: 1,6,1\r\n"]

        if upper == "AT+CMUT?":
            return f"+CMUT: {self.mute}\r\nOK\r\n", []

        if upper.startswith("AT+CMUT="):
            try:
                self.mute = int(upper[len("AT+CMUT=") :].strip())
            except ValueError:
                pass
            return "OK\r\n", []

        # SMS
        if upper == "AT+CSCA?":
            return f'+CSCA: "{self.smsc}",145\r\nOK\r\n', []

        if upper.startswith("AT+CSCA="):
            parts = line[len("AT+CSCA=") :].split(",")
            if parts:
                self.smsc = parts[0].strip().strip('"')
            return "OK\r\n", []

        if upper.startswith("AT+CMGS=") or upper.startswith("AT+CMGW="):
            self.awaiting_pdu = True
            self.pending_sms_cmd = upper
            return "\r\n> ", []

        if upper == "AT+CPMS?":
            return '+CPMS: "SM",0,50,"SM",0,50,"ME",0,100\r\nOK\r\n', []

        if upper.startswith("AT+CPMS="):
            return "+CPMS: 0,50,0,50,0,100\r\nOK\r\n", []

        # Default response for all other configuration / vendor AT commands
        return "OK\r\n", []


def serve_socket(sock_path: str, pid_file: Optional[str], log_path: Optional[str]) -> int:
    log_fp = open(log_path, "a", encoding="utf-8") if log_path else None
    modem = VirtualAtModem(log_fp=log_fp)

    try:
        if os.path.exists(sock_path):
            os.unlink(sock_path)
    except OSError:
        pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(sock_path)
    server.listen(2)

    if pid_file:
        with open(pid_file, "w", encoding="utf-8") as pf:
            pf.write(f"{os.getpid()}\n")

    running = True

    def handle_sig(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    modem.log(f"Listening on UNIX socket {sock_path} (pid={os.getpid()})")

    try:
        while running:
            rlist, _, _ = select.select([server], [], [], 1.0)
            if not rlist:
                continue
            try:
                conn, _ = server.accept()
            except OSError:
                continue

            modem.log("QEMU virtserialport client connected")
            conn.setblocking(False)
            buf = b""
            while running:
                cr, _, _ = select.select([conn], [], [], 1.0)
                if not cr:
                    continue
                try:
                    chunk = conn.recv(4096)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                # Normalize Ctrl-Z (\x1a) as a line terminator for SMS PDUs
                buf = buf.replace(b"\x1a", b"\r")
                while b"\r" in buf or b"\n" in buf:
                    idx_r = buf.find(b"\r")
                    idx_n = buf.find(b"\n")
                    if idx_r == -1:
                         cut = idx_n
                    elif idx_n == -1:
                        cut = idx_r
                    else:
                        cut = min(idx_r, idx_n)
                    raw_bytes = buf[:cut]
                    buf = buf[cut + 1 :]
                    # Strip any immediately following \r or \n
                    while buf.startswith((b"\r", b"\n")):
                        buf = buf[1:]
                    cmd_str = raw_bytes.decode("utf-8", errors="ignore").strip()
                    if not cmd_str:
                        continue
                    resp, unsolicited = modem.process_line(cmd_str)
                    if resp:
                        modem.log(f"TX: {resp.strip()}")
                        try:
                            conn.sendall(resp.encode("utf-8"))
                        except OSError:
                            break
                    for urc in unsolicited:
                        modem.log(f"TX URC: {urc.strip()}")
                        try:
                            conn.sendall(urc.encode("utf-8"))
                        except OSError:
                            break
            try:
                conn.close()
            except OSError:
                pass
            modem.log("QEMU virtserialport client disconnected")
    finally:
        try:
            server.close()
        except OSError:
            pass
        try:
            if os.path.exists(sock_path):
                os.unlink(sock_path)
        except OSError:
            pass
        if pid_file and os.path.exists(pid_file):
            try:
                os.unlink(pid_file)
            except OSError:
                pass
        if log_fp:
            log_fp.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenHarmony QEMU Virtual AT Modem")
    parser.add_argument("--socket", required=True, help="UNIX domain socket path")
    parser.add_argument("--pidfile", default=None, help="Optional PID file path")
    parser.add_argument("--log", default=None, help="Optional log file path")
    args = parser.parse_args()
    return serve_socket(args.socket, args.pidfile, args.log)


if __name__ == "__main__":
    sys.exit(main())
