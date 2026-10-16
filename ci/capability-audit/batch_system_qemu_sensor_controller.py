#!/usr/bin/env python3
"""Send an explicit external acceleration trace; receipts require separate API observation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import struct
import time

MAX_ACCELERATION = struct.unpack('<f', struct.pack('<f', 156.9064))[0]


def read_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        data = stream.recv(size - len(result))
        if not data:
            raise ValueError('sensor input connection closed before complete hello')
        result.extend(data)
    return bytes(result)


def load_trace(path):
    rows = json.loads(Path(path).read_text())
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100000:
        raise ValueError('trace must contain 1..100000 externally supplied samples')
    previous = -1
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'at_ms', 'x', 'y', 'z'}:
            raise ValueError('each sample requires at_ms, x, y, z only')
        if any(isinstance(row[key], bool) or not isinstance(row[key], (int, float)) or
               not math.isfinite(row[key]) for key in row):
            raise ValueError('finite numeric timestamp and acceleration values required')
        at = row['at_ms']
        if at < 0 or at <= previous or at > 3600000 or (previous >= 0 and at - previous >= 4000):
            raise ValueError('timestamps must increase, stay within one hour, and keep each gap below 4 s')
        values = [struct.unpack('<f', struct.pack('<f', row[key]))[0] for key in ('x', 'y', 'z')]
        if any(abs(value) > MAX_ACCELERATION for value in values):
            raise ValueError('sample exceeds the advertised +/-16 g range in m/s^2')
        result.append(dict(at_ms=at, x=values[0], y=values[1], z=values[2]))
        previous = at
    if result[0]['at_ms'] >= 4000:
        raise ValueError('first sample must arrive within 4 s')
    return result


def send_trace(trace, *, unix_path=None, tcp_port=None):
    if (unix_path is None) == (tcp_port is None):
        raise ValueError('select exactly one Unix socket or local HDC forwarded TCP port')
    if unix_path:
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        endpoint = unix_path
    else:
        if not 1 <= tcp_port <= 65535:
            raise ValueError('invalid TCP port')
        stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        endpoint = ('127.0.0.1', tcp_port)
    with stream:
        stream.settimeout(5)
        stream.connect(endpoint)
        hello = read_exact(stream, 32)
        magic, version, nonce, sensor_type, reserved = struct.unpack('<4sI16sII', hello)
        if (magic, version, sensor_type, reserved) != (b'QSN1', 1, 1, 0):
            raise ValueError('unexpected sensor hello')
        sent = []
        start = time.monotonic()
        for seq, sample in enumerate(trace, 1):
            delay = start + sample['at_ms'] / 1000 - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            frame = struct.pack('<4sI16sQfff', b'QSF1', 1, nonce, seq,
                                sample['x'], sample['y'], sample['z'])
            stream.sendall(frame)
            sent.append(dict(sequence=seq, sent_monotonic_ns=time.monotonic_ns(),
                             frame_hex=frame.hex(), **sample))
    return dict(status='external_samples_sent', endpoint=str(endpoint), hello_hex=hello.hex(),
                samples=sent, sensor_api_delivery_verified=False,
                limitations='Successful send is transport evidence only. Compare a separately subscribed '
                            'Sensor API/MSDP observer against the challenge and inspect lifecycle/denials.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    endpoint = parser.add_mutually_exclusive_group(required=True)
    endpoint.add_argument('--unix-path')
    endpoint.add_argument('--tcp-port', type=int)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    trace = load_trace(args.input)
    result = send_trace(trace, unix_path=args.unix_path, tcp_port=args.tcp_port)
    result['input_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], samples=len(result['samples']))))
