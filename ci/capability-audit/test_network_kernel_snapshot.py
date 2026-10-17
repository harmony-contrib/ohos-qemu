"""Synthetic protocol regressions ONLY: no kernel/socket/guest authenticity proof."""
import copy
import json
import struct
import unittest

import batch_network_kernel_snapshot as snapshot

RUN = 'synthetic-owned-run-0001'
BOOT = '01234567-89ab-cdef-0123-456789abcdef'
PORT = 4217


def attr(kind, data):
    n = 4 + len(data)
    return struct.pack('<HH', n, kind) + data + bytes((-n) % 4)


def payloads():
    values = {
        'links': struct.pack('<BBHiII', 0, 0, 772, 1, 0x49, 0) + attr(3, b'lo\0') + attr(4, struct.pack('<I', 65536)),
        'addresses4': struct.pack('<BBBBI', 2, 8, 0x80, 254, 1) + attr(1, bytes([127, 0, 0, 1])),
        'addresses6': struct.pack('<BBBBI', 10, 128, 0x80, 254, 1) + attr(1, bytes(15) + b'\1')}
    for family, suffix in ((2, '4'), (10, '6')):
        values['routes' + suffix] = struct.pack('<BBBBBBBBI', family, 0, 0, 0, 254, 2, 0, 1, 0) + attr(4, struct.pack('<I', 1))
        values['rules' + suffix] = struct.pack('<BBBBBBBBI', family, 0, 0, 0, 254, 0, 0, 1, 0) + attr(6, struct.pack('<I', 32766))
    return {name: [value] for name, value in values.items()}


def stream(values=None, *, header_pid=PORT, sender_pid=0, data_flags=2, done_payload=bytes(4)):
    values = payloads() if values is None else values
    clock = 1
    rows = [dict(kind='begin', schema=snapshot.SCHEMA, run_id=RUN, boot_id=BOOT,
                 uid=0, euid=0, gid=0, pid=123, netns='net:[4026531992]', local_port=PORT,
                 clock_ns=clock, timeout_ms=5000, datasets=7, atomic=False)]
    total_dg = total_msg = 0
    for index, (name, get, reply, family, size) in enumerate(snapshot.DATASETS):
        clock += 1; seq = index + 100
        request = snapshot.HEADER.pack(16 + size, get, 0x301, seq, PORT) + bytes([family]) + bytes(size - 1)
        rows.append(dict(kind='request', dataset=name, index=index, seq=seq, clock_ns=clock, hex=request.hex()))
        messages = [(reply, p, data_flags) for p in values.get(name, [])] + [(3, done_payload, 2)]
        wire = b''; observations = []
        for message_index, (typ, payload, flags) in enumerate(messages):
            length = 16 + len(payload); data = snapshot.HEADER.pack(length, typ, flags, seq, header_pid) + payload
            observations.append(dict(kind='message', dataset=name, index=message_index, datagram=0,
                offset=len(wire), length=length, type=typ, flags=flags, seq=seq, pid=header_pid, hex=data.hex()))
            wire += data + bytes((-length) % 4)
        clock += 1
        rows.append(dict(kind='datagram', dataset=name, index=0, clock_ns=clock, peer_family=16,
            peer_pid=sender_pid, peer_groups=0, peer_bytes=12, msg_flags=0, bytes=len(wire), hex=wire.hex()))
        rows += observations; clock += 1
        rows.append(dict(kind='dataset_end', dataset=name, datagrams=1, messages=len(messages),
                         data_messages=len(messages) - 1, done_count=1, clock_ns=clock))
        total_dg += 1; total_msg += len(messages)
    rows.append(dict(kind='end', run_id=RUN, boot_id=BOOT, pid=123, clock_ns=clock + 1,
                     datasets=7, datagrams=total_dg, messages=total_msg, status='complete'))
    return rows


def raw(rows):
    return ''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows)


class NetlinkProtocolTests(unittest.TestCase):
    def parse(self, rows):
        return snapshot.parse_snapshot(raw(rows), run_id=RUN, boot_id=BOOT)

    def rejected(self, rows):
        with self.assertRaises((ValueError, UnicodeError)): self.parse(rows)

    def test_complete_independent_raw_decode(self):
        actual = self.parse(stream())
        self.assertEqual(list(actual['datasets']), [r[0] for r in snapshot.DATASETS])
        self.assertEqual(actual['datasets']['links'][0]['attributes'][0]['value'], 'lo')
        self.assertEqual(actual['datasets']['addresses4'][0]['attributes'][0]['value'], '127.0.0.1')
        self.assertFalse(actual['atomic'])
        self.assertEqual(len(actual['raw_sha256']), 64)
        self.assertEqual(actual['kernel_uapi'], snapshot.KERNEL_UAPI)

    def test_sender_and_header_pid_have_distinct_contracts(self):
        self.parse(stream(header_pid=0))
        self.parse(stream(header_pid=PORT))
        self.rejected(stream(header_pid=PORT + 1))
        self.rejected(stream(sender_pid=PORT))

    def test_data_and_done_in_separate_datagrams(self):
        original = stream(); rows = [original[0]]
        for start in range(1, len(original) - 1, 5):
            request, datagram, message, done, end = copy.deepcopy(original[start:start + 5])
            wire = bytes.fromhex(datagram['hex']); split = (message['length'] + 3) & ~3
            first = dict(datagram, bytes=split, hex=wire[:split].hex())
            second = dict(datagram, index=1, bytes=len(wire) - split, hex=wire[split:].hex())
            done.update(datagram=1, offset=0); end['datagrams'] = 2
            rows += [request, first, message, second, done, end]
        rows.append(dict(original[-1], datagrams=14))
        self.parse(rows)
        rows[5]['datagram'] = 0  # Raw framing cannot be reassigned to a different packet.
        self.rejected(rows)

    def test_truncated_every_record_boundary(self):
        rows = stream()
        for end in range(len(rows)):
            with self.subTest(end=end): self.rejected(rows[:end])

    def test_terminal_lf_and_trailing_data(self):
        text = raw(stream())
        for malformed in (text[:-1], text + '\n', text + '{}\n', text + 'S', text.replace('\n', '\r\n'), text + '\0'):
            with self.subTest(tail=repr(malformed[-15:])):
                with self.assertRaises(ValueError): snapshot.parse_snapshot(malformed, run_id=RUN, boot_id=BOOT)

    def test_duplicate_json_key(self):
        text = raw(stream()).replace('"kind":"begin"', '"kind":"begin","kind":"begin"', 1)
        with self.assertRaises(ValueError): snapshot.parse_snapshot(text, run_id=RUN, boot_id=BOOT)

    def test_no_query_error_can_become_empty_state(self):
        self.rejected(stream({}))  # Loopback cannot disappear from a real Linux netns.
        rows = stream(); rows.insert(1, dict(kind='error', reason='recvmsg', errno=13)); self.rejected(rows)
        rows = stream(); rows[2]['hex'] = ''; rows[2]['bytes'] = 0; self.rejected(rows)
        for typ in (1, 2, 4, 18):
            rows = stream(); item = rows[2]; data = bytearray.fromhex(item['hex'])
            struct.pack_into('<H', data, 4, typ); item['hex'] = data.hex(); self.rejected(rows)

    def test_allow_genuinely_empty_address_route_rule_dumps(self):
        values = payloads()
        for name in list(values)[1:]: values[name] = []
        actual = self.parse(stream(values))
        self.assertEqual(actual['datasets']['routes4'], [])

    def test_flags_error_interrupt_filtered_and_ack_are_not_complete(self):
        for flags in (0, 2 | 0x10, 2 | 0x20, 2 | 4, 0xffff):
            with self.subTest(flags=flags): self.rejected(stream(data_flags=flags))
        for payload in (struct.pack('<i', -4), bytes(8), b'\0'):
            self.rejected(stream(done_payload=payload))

    def test_receive_envelope_integrity(self):
        for key, value in (('peer_family', 2), ('peer_groups', 1), ('peer_bytes', 8),
                           ('msg_flags', 32), ('msg_flags', 8), ('bytes', 1), ('index', 2),
                           ('clock_ns', 0)):
            rows = stream(); rows[2][key] = value
            with self.subTest(key=key): self.rejected(rows)

    def test_bad_request_mutation_family_seq_pid_order(self):
        for offset, fmt, value in ((4,'<H',16), (6,'<H',0x305), (8,'<I',999), (12,'<I',0), (16,'<B',2)):
            rows = stream(); data = bytearray.fromhex(rows[1]['hex']); struct.pack_into(fmt,data,offset,value)
            rows[1]['hex'] = data.hex(); self.rejected(rows)
        rows = stream(); rows[1]['dataset'] = 'routes4'; self.rejected(rows)

    def test_datagram_bytes_must_match_each_independent_message(self):
        for key, value in (('seq', 5), ('length', 16), ('pid', 0), ('offset', 4),
                           ('index', True), ('hex', '00')):
            rows = stream(); rows[3][key] = value; self.rejected(rows)
        rows = stream(); data = bytearray.fromhex(rows[2]['hex']); struct.pack_into('<I',data,0,0xffffffff)
        rows[2]['hex'] = data.hex(); self.rejected(rows)
        rows = stream(); rows[2]['hex'] += '00'; rows[2]['bytes'] += 1; self.rejected(rows)

    def test_done_unique_and_final_identity(self):
        rows = stream(); rows.insert(5, copy.deepcopy(rows[4])); self.rejected(rows)
        for key, value in (('datagrams', 0), ('messages', 0), ('datasets', 6), ('pid', 124),
                           ('clock_ns', 1), ('status', 'pass'), ('run_id', 'foreign-owned-run')):
            rows = stream(); rows[-1][key] = value; self.rejected(rows)
        rows = stream(); rows[5]['done_count'] = 0; self.rejected(rows)

    def test_root_boot_run_and_typed_identity(self):
        for key, value in (('uid', 2000), ('uid', False), ('euid', 1), ('local_port', 0),
                           ('pid', True), ('netns', 'net:[0]'), ('boot_id', BOOT.upper()),
                           ('run_id', 'foreign-owned-run'), ('atomic', True)):
            rows = stream(); rows[0][key] = value; self.rejected(rows)

    def test_unknown_address_route_rule_semantics_fail(self):
        for name in ('addresses4', 'routes6', 'rules4', 'links'):
            values = payloads(); values[name][0] += attr(0x1234, bytes(4))
            with self.subTest(name=name): self.rejected(stream(values))
        for kind in (19, 21, 22, 30):
            values = payloads(); values['routes4'][0] += attr(kind, bytes(4)); self.rejected(stream(values))

    def test_attribute_padding_size_duplicates_and_nul(self):
        values = payloads(); values['links'][0] += attr(3, b'other\0'); self.rejected(stream(values))
        values = payloads(); values['links'][0] = values['links'][0].replace(b'lo\0\0', b'lo\0X'); self.rejected(stream(values))
        values = payloads(); values['links'][0] = struct.pack('<BBHiII',0,0,772,1,8,0) + attr(3,b'lo'); self.rejected(stream(values))
        values = payloads(); values['routes4'][0] += struct.pack('<HH', 3, 4); self.rejected(stream(values))
        values = payloads(); values['routes4'][0] += attr(4, struct.pack('<I',1)); self.rejected(stream(values))

    def test_structural_and_volatile_link_attributes_retained(self):
        values = payloads(); values['links'][0] += attr(23, bytes(192)) + attr(33,b'\1') + attr(18,attr(1,b'tun\0'))
        link = self.parse(stream(values))['datasets']['links'][0]
        self.assertEqual([r['type'] for r in link['volatile_attributes']], [23,33])
        self.assertEqual(link['attributes'][-1]['nested'][0]['hex'], b'tun\0'.hex())
        self.assertEqual(link['volatile_attributes'][0]['hex'], bytes(192).hex())

    def test_route_table_and_rule_uid_range_are_real_values(self):
        values = payloads(); values['routes4'][0] += attr(15,struct.pack('<I',10001))
        values['rules4'][0] += attr(20,struct.pack('<II',20000000,20199999))
        actual = self.parse(stream(values))['datasets']
        self.assertEqual(actual['routes4'][0]['attributes'][-1]['value'],10001)
        self.assertEqual(actual['rules4'][0]['attributes'][-1]['value'],[20000000,20199999])

    def test_unresolved_cross_dump_ifindex_rejected_not_erased(self):
        values = payloads(); values['routes4'][0] = values['routes4'][0][:-4] + struct.pack('<I',99)
        self.rejected(stream(values))

    def test_guest_ui_adapter_retains_raw_and_checks_complete_stream(self):
        transport = raw(stream())[:-1]; calls = []
        def shell(command,label): calls.append((command,label)); return transport
        original, decoded = snapshot.capture_snapshot(shell,'baseline',BOOT,
            helper='/data/local/tmp/owned-run/netlink_snapshot',run_id=RUN)
        self.assertEqual(original,transport)
        self.assertEqual(decoded['run_id'],RUN)
        self.assertIn('--run-id ' + RUN,calls[0][0])
        for bad in (transport + '\n', transport + ' ', transport + '\n\n', transport[:-1]):
            with self.assertRaises(ValueError): snapshot.capture_snapshot(lambda *_:bad,'baseline',BOOT,
                helper='/data/local/tmp/owned-run/netlink_snapshot',run_id=RUN)
        with self.assertRaises(ValueError): snapshot.capture_snapshot(shell,'baseline',BOOT,
            helper='/data/local/tmp/../netlink_snapshot',run_id=RUN)

    def test_actual_enclosing_exit_failure_is_not_swallowed(self):
        def failed(*_): raise RuntimeError('actual enclosing guest command failed')
        with self.assertRaises(RuntimeError): snapshot.capture_snapshot(failed,'baseline',BOOT,
            helper='/data/local/tmp/owned-run/netlink_snapshot',run_id=RUN)


if __name__ == '__main__': unittest.main()
