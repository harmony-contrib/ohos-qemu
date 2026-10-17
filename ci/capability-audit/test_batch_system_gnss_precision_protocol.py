#!/usr/bin/env python3
"""Python wire/transcript and C++ source contract checks ONLY.

No native code, provider, HDI, guest or package behavior is executed or proven.
"""
import ast
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest

import batch_system_gnss_controller as sender

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/device/qemu/external_gnss'
NONCE = bytes(range(16))
WORDS = ['00000000', '80000000', '3f800000', 'bf800000', '7f800000', 'ff800000',
         '7fc01234', 'ffc05678', '7f800001', '00000001', '7f7fffff', '80000001']


def row(bits='00000000', valid=False):
    # Fixed protocol example, not a current/live GNSS measurement or guest run.
    return dict(at_ms=0, utc_ms=1700000034567, latitude=31.25, longitude=121.5,
                horizontal_accuracy_bits=bits, horizontal_accuracy_valid=valid)


def cpp_function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 0
    for i in range(opening, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if depth == 0:
            return text[start:i + 1]
    raise AssertionError(signature)


class Transcript:
    """Bytes supplied to the real Python sender; not a simulated OHOS provider."""
    def __init__(self, answer=b'', hello=None):
        self.pending = (struct.pack('<4sI16sII', b'QGN1', 1, NONCE, 88, 0)
                        if hello is None else hello) + answer
        self.sent = []

    def recv(self, count):
        # Exercise read_exact's fragmented handshake handling.
        count = min(count, 3)
        out, self.pending = self.pending[:count], self.pending[count:]
        return out

    def sendall(self, value):
        self.sent.append(bytes(value))


class PrecisionWireTests(unittest.TestCase):
    def test_all_raw_binary32_words_and_valid_bits_are_exact(self):
        for word in WORDS:
            for valid in (False, True):
                with self.subTest(word=word, valid=valid):
                    packet = sender.encode_precision_sample(NONCE, 7, row(word, valid))
                    self.assertEqual(88, len(packet))
                    self.assertEqual((b'QGF2', 2, NONCE, 7, row()['utc_ms']),
                                     struct.unpack_from('<4sI16sQQ', packet))
                    self.assertEqual(bytes.fromhex(word)[::-1], packet[64:68])
                    self.assertEqual((0, int(valid)), struct.unpack_from('<II', packet, 80))
                    self.assertEqual((31.25, 121.5, 0.0), struct.unpack_from('<ddd', packet, 40))

    def test_legacy_default_uses_exact_v1_bytes_without_probe(self):
        sample = dict(at_ms=0, utc_ms=1700000034567, latitude=31.25,
                      longitude=121.5, horizontal_accuracy=2.5)
        stream = Transcript()
        result = sender.send_trace(stream, [sample])
        expected = struct.pack('<4sI16sQQdddffffII', b'QGF1', 1, NONCE, 1,
                               sample['utc_ms'], 31.25, 121.5, 0, 2.5, 0, 0, 0, 0, 0)
        self.assertEqual([expected], stream.sent)
        self.assertEqual('external_measurements_sent', result['status'])
        self.assertNotIn('capability_ack_hex', result)
        self.assertEqual('qgn1', inspect.signature(sender.send_trace).parameters['protocol'].default)
        for invalid in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                sender.encode_sample(NONCE, 1, {**sample, 'horizontal_accuracy': invalid})

    def test_explicit_v2_requires_exact_nonce_bound_ack_before_data(self):
        ack = struct.pack('<4sI16sII', b'QGA2', 2, NONCE, 88, 1)
        stream = Transcript(ack)
        result = sender.send_trace(stream, [row('7fc01234')], sender.PRECISION_PROTOCOL)
        self.assertEqual(struct.pack('<4sI16s64s', b'QGP2', 2, NONCE, bytes(64)), stream.sent[0])
        self.assertEqual(sender.encode_precision_sample(NONCE, 1, row('7fc01234')), stream.sent[1])
        self.assertEqual(ack.hex(), result['capability_ack_hex'])
        self.assertFalse(result['location_api_delivery_verified'])

    def test_old_hello_alone_and_wrong_ack_never_downgrade(self):
        answers = [b'', b'QGA2',
            struct.pack('<4sI16sII', b'QGA1', 2, NONCE, 88, 1),
            struct.pack('<4sI16sII', b'QGA2', 1, NONCE, 88, 1),
            struct.pack('<4sI16sII', b'QGA2', 2, bytes(16), 88, 1),
            struct.pack('<4sI16sII', b'QGA2', 2, NONCE, 87, 1),
            struct.pack('<4sI16sII', b'QGA2', 2, NONCE, 88, 0),
            struct.pack('<4sI16sII', b'QGA2', 2, NONCE, 88, 3)]
        for answer in answers:
            with self.subTest(answer=answer.hex()):
                stream = Transcript(answer)
                with self.assertRaises(ValueError):
                    sender.send_trace(stream, [row()], sender.PRECISION_PROTOCOL)
                self.assertEqual(1, len(stream.sent))
                self.assertEqual(b'QGP2', stream.sent[0][:4])

    def test_wrong_hello_and_unknown_protocol_send_no_frames(self):
        for hello in (struct.pack('<4sI16sII', b'QGN2', 1, NONCE, 88, 0),
                      struct.pack('<4sI16sII', b'QGN1', 2, NONCE, 88, 0),
                      struct.pack('<4sI16sII', b'QGN1', 1, NONCE, 88, 1)):
            stream = Transcript(hello=hello)
            with self.assertRaises(ValueError):
                sender.send_trace(stream, [row()], sender.PRECISION_PROTOCOL)
            self.assertEqual([], stream.sent)
        stream = Transcript()
        with self.assertRaises(ValueError):
            sender.send_trace(stream, [row()], 'qgn3')
        self.assertEqual([], stream.sent)

    def test_v2_schema_preserves_other_input_constraints(self):
        invalid = [dict(horizontal_accuracy_bits='NaN'), dict(horizontal_accuracy_bits='7FC01234'),
                   dict(horizontal_accuracy_bits=0), dict(horizontal_accuracy_valid=0),
                   dict(horizontal_accuracy_valid='false'), dict(horizontal_accuracy=0),
                   dict(latitude=90.00001), dict(longitude=-180.00001), dict(latitude=math.nan),
                   dict(utc_ms=True), dict(utc_ms=0), dict(utc_ms=1700000034567.0),
                   dict(altitude=100001), dict(speed=-1), dict(bearing=360), dict(vertical_accuracy=0)]
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(ValueError):
                sender.encode_precision_sample(NONCE, 1, {**row(), **update})
        for optional in (dict(altitude=2.25, speed=1.5, bearing=45, vertical_accuracy=3.5), {}):
            packet = sender.encode_precision_sample(NONCE, 1, {**row(), **optional})
            self.assertEqual(sum(sender.OPTIONAL[k] for k in optional), struct.unpack_from('<I', packet, 80)[0])

    def test_trace_keeps_source_utc_and_old_timing_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.json'
            rows = [row(), {**row('7f800000', True), 'at_ms': 1000, 'utc_ms': row()['utc_ms'] + 1000}]
            path.write_text(json.dumps(rows))
            self.assertEqual(rows, sender.load_trace(path, sender.PRECISION_PROTOCOL))
            with self.assertRaises(ValueError):
                sender.load_trace(path)  # Explicit selection is mandatory.
            for update in (dict(utc_ms=rows[0]['utc_ms']), dict(at_ms=4000), dict(at_ms=0)):
                path.write_text(json.dumps([rows[0], {**rows[1], **update}]))
                with self.assertRaises(ValueError):
                    sender.load_trace(path, sender.PRECISION_PROTOCOL)


class PrecisionStaticContractTests(unittest.TestCase):
    def test_legacy_cpp_functions_and_python_encoder_are_unchanged(self):
        value = json.loads((ROOT / 'ci/capability-audit/fixtures/batch_system/gnss_precision_protocol_contract.json').read_text())
        records = value['unchanged_functions_sha256']
        for name, signatures in records.items():
            if name == 'legacy_python_encode_sample_sha256':
                text = (ROOT / 'ci/capability-audit/batch_system_gnss_controller.py').read_text()
                node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'encode_sample')
                self.assertEqual(signatures, hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest())
            else:
                text = (ROOT / name).read_text()
                for signature, digest in signatures.items():
                    self.assertEqual(digest, hashlib.sha256(cpp_function(text, signature).encode()).hexdigest(), signature)

    def test_v2_cpp_retains_nonce_sequence_utc_and_nonaccuracy_limits(self):
        text = (COMPONENT / 'files/qemu_gnss_protocol.h').read_text()
        legacy = cpp_function(text, 'inline bool DecodeFrame(')
        precision = cpp_function(text, 'inline bool DecodePrecisionFrame(')
        start = '    uint64_t next = ReadLe'
        end = '    Fix fix'
        self.assertEqual(legacy[legacy.index(start):legacy.index(end)],
                         precision[precision.index(start):precision.index(end)])
        for guard in ('std::memcmp(frame.data() + 8, nonce.data(), nonce.size()) != 0',
                      'constexpr uint32_t OPTIONAL = 4 | 8 | 16 | 64;',
                      'fix.latitude < -90 || fix.latitude > 90 || fix.longitude < -180 || fix.longitude > 180',
                      'fix.altitude < -12000 || fix.altitude > 100000',
                      'fix.speed < 0 || fix.speed > 1500 || fix.bearing < 0 || fix.bearing >= 360',
                      'fix.verticalAccuracy < 0 || fix.verticalAccuracy > 100000'):
            self.assertIn(guard, precision)
        self.assertNotIn('ReadNumber<float>(frame.data()+64)', precision)
        self.assertNotIn('isfinite(fix.horizontalAccuracy)', precision)
        self.assertIn('ReadLe(frame.data() + 84, 4) > 1', precision)
        self.assertIn('static_cast<uint32_t>(ReadLe(frame.data() + 64, 4))', precision)

    def test_native_state_machine_and_vendor_raw_copy_are_explicit(self):
        text = (COMPONENT / 'files/qemu_gnss_input.cpp').read_text()
        serve = cpp_function(text, 'void GnssInput::Serve(')
        self.assertIn('if (!Authorized(fd, state->config.writerUid)) return;', serve)
        self.assertIn('protocol == 0 && IsPrecisionProbe(frame, nonce)', serve)
        self.assertIn('if (protocol == 0) protocol = 1;', serve)
        self.assertIn('protocol == 1 ? DecodeFrame', serve)
        self.assertIn('DecodePrecisionFrame(frame, nonce, sequence, utc, sample)', serve)
        self.assertEqual(2, serve.count('generation != state->sessionGeneration'))
        vendor = (COMPONENT / 'files/qemu_gnss_vendor.cpp').read_text()
        self.assertIn('Provider provider({"/dev/unix/socket/qemu_gnss/input", 0});', vendor)
        self.assertIn('(!fix.rawHorizontalAccuracy || fix.horizontalAccuracyValid) ? 32 : 0', vendor)
        self.assertIn('std::memcpy(&location.horizontalAccuracy, &fix.horizontalAccuracyBits, sizeof(location.horizontalAccuracy));', vendor)
        self.assertIn('static_assert(sizeof(location.horizontalAccuracy) == sizeof(fix.horizontalAccuracyBits));', vendor)

    def test_component_manifest_pins_all_changed_cpp_files(self):
        value = json.loads((COMPONENT / 'manifest.json').read_text())
        for row in value['files'].values():
            path = COMPONENT / row['component_file']
            if path.exists():
                self.assertEqual(row['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
