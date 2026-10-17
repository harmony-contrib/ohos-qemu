#!/usr/bin/env python3
"""Independent decoder for GET-only guest rtnetlink JSONL observations.

parse_snapshot requires original complete LF-terminated helper stdout. It does
not trust the native message summary, counters, or success marker. Seven dumps
are sequential, not globally atomic; this is observation, not VPN acceptance.
capture_snapshot adapts only GuestUi/command_output's exact no-terminal-LF
transport contract and returns (unchanged_transport_raw, decoded).
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
import shlex
import struct

SCHEMA = 'ohos-readonly-rtnetlink/v1'
# name, GET, NEW, family, fixed payload bytes
DATASETS = (('links', 18, 16, 0, 16), ('addresses4', 22, 20, 2, 8),
            ('addresses6', 22, 20, 10, 8), ('routes4', 26, 24, 2, 12),
            ('routes6', 26, 24, 10, 12), ('rules4', 34, 32, 2, 12),
            ('rules6', 34, 32, 10, 12))
HEADER = struct.Struct('<IHHII')
BOOT = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
LIMIT = 64 * 1024 * 1024
# Root's current-native Linux 5.10 source-only export, independently SHA-checked
# before implementing these enums. Unsupported newer semantic attrs fail closed.
# BASE/r57-native-kernel-uapi-export-01/export.json; no source/out access.
KERNEL_UAPI = {
    'rtnetlink.h': '5c40e4276109535a30e7e3797683f73c99528eb36d5671ba388b91046cfaf77c',
    'if_link.h': '9e5c5ecbcc69c88b1b8212f94939b1dac4afd0266db02b5438869add15af55dc',
    'if_addr.h': 'a819341157b7d465d1e7023a8f404ccafd6ecc2296c8270a03b04519febbf968',
    'fib_rules.h': '0466b97d9d657f59c9766f6ce24bc0970ce0474fb0a86fe9600b6bf9739e1497',
    'netlink.h': '1327db40235701c90d4891c87789804511d276fc3c81a88906619eb11d0c58f6'}


def require(value, message):
    if not value: raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def integer(value, low=0, high=0xffffffff):
    require(type(value) is int and low <= value <= high, 'integer bounds/type')
    return value


def shape(row, keys):
    require(isinstance(row, dict) and set(row) == set(keys.split()), 'record shape')


def unhex(value):
    require(isinstance(value, str) and len(value) % 2 == 0 and
            re.fullmatch('[0-9a-f]*', value) is not None, 'canonical complete hex required')
    return bytes.fromhex(value)


def scalar(data, fmt):
    require(len(data) == struct.calcsize(fmt), 'attribute scalar width')
    return struct.unpack(fmt, data)[0]


def text(data):
    require(data and data[-1] == 0 and b'\0' not in data[:-1], 'exact NUL terminated string')
    value = data[:-1].decode('ascii')
    require(value and all(32 < ord(c) < 127 for c in value), 'bounded ASCII kernel name')
    return value


def attrs(data):
    """Retain flags, payload and full aligned bytes; never discard unknown TLVs."""
    result = []; pos = 0
    while pos < len(data):
        require(len(data) - pos >= 4, 'truncated attribute header')
        length, kind = struct.unpack_from('<HH', data, pos)
        aligned = (length + 3) & ~3
        require(length >= 4 and aligned <= len(data) - pos, 'truncated attribute body/padding')
        require(not any(data[pos + length:pos + aligned]), 'nonzero attribute padding')
        result.append({'type': kind & 0x3fff, 'flags': kind & 0xc000,
                       'hex': data[pos + 4:pos + length].hex(),
                       'raw_hex': data[pos:pos + aligned].hex()})
        pos += aligned
    return result


def ip(data, family):
    require(len(data) == (4 if family == 2 else 16), 'address family/width differs')
    return str(ipaddress.ip_address(data))


# Known link attributes are retained, including opaque device-specific payloads.
# They are not interpreted as routes or policy. Statistics/carrier observations
# are explicitly volatile and excluded from the structural comparison view.
LINK_NAMES = dict(enumerate(('UNSPEC ADDRESS BROADCAST IFNAME MTU LINK QDISC STATS COST PRIORITY MASTER '
    'WIRELESS PROTINFO TXQLEN MAP WEIGHT OPERSTATE LINKMODE LINKINFO NET_NS_PID IFALIAS NUM_VF VFINFO_LIST '
    'STATS64 VF_PORTS PORT_SELF AF_SPEC GROUP NET_NS_FD EXT_MASK PROMISCUITY NUM_TX_QUEUES NUM_RX_QUEUES '
    'CARRIER PHYS_PORT_ID CARRIER_CHANGES PHYS_SWITCH_ID LINK_NETNSID PHYS_PORT_NAME PROTO_DOWN GSO_MAX_SEGS '
    'GSO_MAX_SIZE PAD XDP EVENT NEW_NETNSID IF_NETNSID CARRIER_UP_COUNT CARRIER_DOWN_COUNT NEW_IFINDEX '
    'MIN_MTU MAX_MTU PROP_LIST ALT_IFNAME PERM_ADDRESS PROTO_DOWN_REASON').split()))
LINK_VOLATILE = {7, 11, 14, 23, 33, 35, 44, 47, 48}
LINK_U32 = {4, 5, 10, 13, 19, 21, 27, 28, 29, 30, 31, 32, 35, 37, 40, 41, 44,
            45, 46, 47, 48, 49, 50, 51}
LINK_U8 = {16, 17, 33, 39}
LINK_STR = {3, 6, 20, 38, 53}
LINK_NESTED = {12, 18, 22, 24, 25, 26, 43, 52, 55}


def link_attributes(rows):
    structural = []; volatile = []; seen = set()
    for a in rows:
        n = a['type']; data = unhex(a['hex'])
        require(n in LINK_NAMES and n not in (0, 8, 9, 15), 'unsupported link attribute')
        require(n not in seen or n in (42, 53), 'duplicate structural link attribute')
        seen.add(n)
        require(not a['flags'] & 0x4000, 'unsupported network-order link attribute')
        require(not a['flags'] & 0x8000 or n in LINK_NESTED, 'nested flag on nonnested link attribute')
        a['name'] = LINK_NAMES[n]
        if n in LINK_STR: a['value'] = text(data)
        elif n in LINK_U32: a['value'] = scalar(data, '<i' if n in (28, 37, 45, 46) else '<I')
        elif n in LINK_U8: a['value'] = scalar(data, '<B')
        elif n in LINK_NESTED:
            # Retaining typed nesting is explicit; device-specific binary leaves
            # stay opaque, and are never silently treated as absent/default.
            a['nested'] = attrs(data); a['interpretation'] = 'opaque_device_specific_retained'
        elif n == 7: require(len(data) >= 92 and len(data) % 4 == 0, 'stats32 width')
        elif n == 23: require(len(data) >= 184 and len(data) % 8 == 0, 'stats64 width')
        elif n == 42: require(not data, 'link pad payload')
        else: a['interpretation'] = 'known_binary_retained'
        (volatile if n in LINK_VOLATILE else structural).append(a)
    names = [a for a in structural if a['type'] == 3]
    require(len(names) == 1, 'one real interface name required')
    return structural, volatile


ADDRESS = {1: 'ADDRESS', 2: 'LOCAL', 3: 'LABEL', 4: 'BROADCAST', 5: 'ANYCAST',
           6: 'CACHEINFO', 7: 'MULTICAST', 8: 'FLAGS', 9: 'RT_PRIORITY',
           10: 'TARGET_NETNSID'}
ROUTE = {1: 'DST', 2: 'SRC', 3: 'IIF', 4: 'OIF', 5: 'GATEWAY', 6: 'PRIORITY',
         7: 'PREFSRC', 8: 'METRICS', 9: 'MULTIPATH', 11: 'FLOW', 12: 'CACHEINFO',
         15: 'TABLE', 16: 'MARK', 17: 'MFC_STATS', 18: 'VIA', 19: 'NEWDST', 20: 'PREF',
         21: 'ENCAP_TYPE', 22: 'ENCAP', 23: 'EXPIRES', 24: 'PAD', 25: 'UID',
         26: 'TTL_PROPAGATE', 27: 'IP_PROTO', 28: 'SPORT', 29: 'DPORT', 30: 'NH_ID'}
RULE = {1: 'DST', 2: 'SRC', 3: 'IIFNAME', 4: 'GOTO', 6: 'PRIORITY', 10: 'FWMARK',
        11: 'FLOW', 12: 'TUN_ID', 13: 'SUPPRESS_IFGROUP', 14: 'SUPPRESS_PREFIXLEN',
        15: 'TABLE', 16: 'FWMASK', 17: 'OIFNAME', 18: 'PAD', 19: 'L3MDEV',
        20: 'UID_RANGE', 21: 'PROTOCOL', 22: 'IP_PROTO', 23: 'SPORT_RANGE', 24: 'DPORT_RANGE'}


def semantic_attributes(rows, kind, family):
    names = {'address': ADDRESS, 'route': ROUTE, 'rule': RULE}[kind]
    seen = set()
    for a in rows:
        n = a['type']; data = unhex(a['hex'])
        require(n in names and n not in seen, 'unknown/duplicate ' + kind + ' attribute')
        seen.add(n); a['name'] = names[n]
        # Route encapsulation/new-destination semantics require a dedicated
        # protocol decoder. Preserve raw receipt, fail instead of assuming none.
        require(not a['flags'] or kind == 'route' and n == 8 and a['flags'] == 0x8000,
                'unsupported attribute flags')
        if kind == 'address':
            if n in (1, 2, 4, 5, 7): a['value'] = ip(data, family)
            elif n == 3: a['value'] = text(data)
            elif n == 6:
                require(len(data) == 16, 'address cacheinfo width')
                a['value'] = dict(zip(('preferred','valid','created','updated'), struct.unpack('<IIII', data)))
                a['volatile'] = True
            else: a['value'] = scalar(data, '<i' if n == 10 else '<I')
        elif kind == 'rule':
            if n in (1, 2): a['value'] = ip(data, family)
            elif n in (3, 17): a['value'] = text(data)
            elif n == 12: a['value'] = scalar(data, '>Q')
            elif n == 18: require(not data, 'rule pad payload')
            elif n in (19, 21, 22): a['value'] = scalar(data, '<B')
            elif n == 20:
                require(len(data) == 8, 'rule uid range width'); a['value'] = list(struct.unpack('<II', data))
                require(a['value'][0] <= a['value'][1], 'uid range reversed')
            elif n in (23, 24):
                require(len(data) == 4, 'rule port range width'); a['value'] = list(struct.unpack('<HH', data))
                require(a['value'][0] <= a['value'][1], 'port range reversed')
            else: a['value'] = scalar(data, '<I')
        else:
            if n in (1, 2, 5, 7): a['value'] = ip(data, family)
            elif n in (3, 4, 6, 11, 15, 16, 23, 25): a['value'] = scalar(data, '<I')
            elif n in (20, 26, 27): a['value'] = scalar(data, '<B')
            elif n in (28, 29): a['value'] = scalar(data, '>H')
            elif n == 24: require(not data, 'route pad payload')
            elif n == 12:
                require(len(data) == 32, 'route cacheinfo width'); a['volatile'] = True
                a['value'] = list(struct.unpack('<IIIIIIII', data))
            elif n == 8:
                a['nested'] = attrs(data)
                for metric in a['nested']:
                    require(not metric['flags'] and 1 <= metric['type'] <= 17, 'unknown route metric')
                    metric['value'] = text(unhex(metric['hex'])) if metric['type'] == 16 else scalar(unhex(metric['hex']), '<I')
            elif n == 9:
                hops = []; pos = 0
                while pos < len(data):
                    require(len(data) - pos >= 8, 'multipath header')
                    size, flags, weight, index = struct.unpack_from('<HBBi', data, pos)
                    aligned = (size + 3) & ~3
                    require(size >= 8 and aligned <= len(data) - pos and index > 0 and
                            not any(data[pos + size:pos + aligned]), 'multipath shape')
                    nested = attrs(data[pos + 8:pos + size])
                    semantic_attributes(nested, 'route', family)
                    require(all(x['type'] in (5, 18) for x in nested), 'unsupported multipath nested semantics')
                    hops.append(dict(flags=flags, hops=weight, ifindex=index, attributes=nested)); pos += aligned
                require(hops, 'empty multipath'); a['value'] = hops
            elif n == 18:
                require(len(data) >= 2, 'route via family'); via_family = scalar(data[:2], '<H')
                require(via_family in (2, 10), 'unsupported route via family')
                a['value'] = {'family': via_family, 'address': ip(data[2:], via_family)}
            else: raise ValueError('unsupported route semantic attribute: ' + names[n])
    return rows


def decode_message(payload, name, family):
    if name == 'links':
        require(len(payload) >= 16, 'link payload')
        fam, pad, typ, index, flags, change = struct.unpack_from('<BBHiII', payload)
        require(fam == 0 and pad == 0 and index > 0, 'link fixed header')
        structural, volatile = link_attributes(attrs(payload[16:]))
        ifname = next(a['value'] for a in structural if a['type'] == 3)
        return dict(ifindex=index, ifname=ifname, family=fam, type=typ, flags=flags, change=change,
                    attributes=structural, volatile_attributes=volatile)
    size = 8 if name.startswith('addresses') else 12
    require(len(payload) >= size and payload[0] == family, 'dataset family/fixed payload')
    if size == 8:
        fam, prefix, flags, scope, index = struct.unpack_from('<BBBBI', payload)
        require(index > 0 and prefix <= (32 if family == 2 else 128), 'address fixed header')
        return dict(family=fam, prefixlen=prefix, flags=flags, scope=scope, ifindex=index,
                    attributes=semantic_attributes(attrs(payload[8:]), 'address', family))
    fam, dst, src, tos, table, protocol, scope, typ, flags = struct.unpack_from('<BBBBBBBBI', payload)
    require(dst <= (32 if family == 2 else 128) and src <= (32 if family == 2 else 128), 'prefix bounds')
    if name.startswith('rules'):
        require(protocol == scope == 0 and typ in (1, 2, 3, 6, 7, 8), 'rule reserved bytes/unsupported action')
        return dict(family=fam, dst_len=dst, src_len=src, tos=tos, table=table, action=typ, flags=flags,
                    attributes=semantic_attributes(attrs(payload[12:]), 'rule', family))
    require(1 <= typ <= 11, 'unsupported route type')
    return dict(family=fam, dst_len=dst, src_len=src, tos=tos, table=table,
                protocol=protocol, scope=scope, type=typ, flags=flags,
                attributes=semantic_attributes(attrs(payload[12:]), 'route', family))


def parse_snapshot(raw, *, run_id, boot_id):
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= LIMIT and raw.endswith('\n') and
            not raw.endswith('\n\n') and '\r' not in raw and '\0' not in raw, 'complete bounded JSONL framing')
    lines = raw[:-1].split('\n')
    require(all(line.startswith('{') and line.endswith('}') and line == line.strip() for line in lines),
            'no partial prefixes/suffixes or transport whitespace')
    rows = [json.loads(line, object_pairs_hook=unique) for line in lines]
    require(len(rows) >= 23 and all(isinstance(r, dict) for r in rows), 'seven complete object datasets required')
    first = rows[0]
    shape(first, 'kind schema run_id boot_id uid euid gid pid netns local_port clock_ns timeout_ms datasets atomic')
    require(first['kind'] == 'begin' and first['schema'] == SCHEMA and
            re.fullmatch('[A-Za-z0-9_-]{16,64}', run_id) and re.fullmatch(BOOT, boot_id) and
            first['run_id'] == run_id and first['boot_id'] == boot_id and first['uid'] == first['euid'] == 0 and
            type(first['uid']) is int and type(first['euid']) is int and first['datasets'] == 7 and
            type(first['datasets']) is int and first['atomic'] is False and
            re.fullmatch(r'net:\[[1-9][0-9]*\]', first['netns']), 'actual root/run/boot/socket contract')
    integer(first['gid']); integer(first['pid'], 1); port = integer(first['local_port'], 1)
    clock = integer(first['clock_ns'], 1, 2**63 - 1); integer(first['timeout_ms'], 100, 30000)
    cursor = 1; result = {}; total_dg = total_msg = 0; previous_seq = None
    for dataset_index, (name, get, reply, family, fixed) in enumerate(DATASETS):
        require(cursor < len(rows), 'missing request'); request = rows[cursor]; cursor += 1
        shape(request, 'kind dataset index seq clock_ns hex')
        seq = integer(request['seq'], 1)
        require(request['kind'] == 'request' and request['dataset'] == name and
                type(request['index']) is int and request['index'] == dataset_index and
                (previous_seq is None or seq == previous_seq + 1), 'request order/sequence')
        expected = HEADER.pack(16 + fixed, get, 0x301, seq, port) + bytes([family]) + bytes(fixed - 1)
        require(unhex(request['hex']) == expected, 'only exact GET dump requests permitted')
        previous_seq = seq
        require(integer(request['clock_ns'], 1, 2**63 - 1) >= clock, 'request clock regressed')
        clock = request['clock_ns']; request_clock = clock; dg = msg_count = done = 0; decoded = []
        while cursor < len(rows) and rows[cursor].get('kind') == 'datagram':
            record = rows[cursor]; cursor += 1
            shape(record, 'kind dataset index clock_ns peer_family peer_pid peer_groups peer_bytes msg_flags bytes hex')
            data = unhex(record['hex'])
            require(record['dataset'] == name and type(record['index']) is int and record['index'] == dg and
                    integer(record['peer_family']) == 16 and integer(record['peer_pid']) == 0 and
                    integer(record['peer_groups']) == 0 and integer(record['peer_bytes']) == 12 and
                    integer(record['msg_flags']) == 0 and integer(record['bytes'], 1, 262144) == len(data) and
                    not done, 'datagram kernel sender/flags/count/after-DONE')
            require(integer(record['clock_ns'], 1, 2**63 - 1) >= clock, 'receive clock regressed')
            clock = record['clock_ns']; pos = 0
            while pos < len(data):
                require(len(data) - pos >= 16 and not done, 'truncated header/message after DONE')
                length, typ, flags, actual_seq, pid = HEADER.unpack_from(data, pos)
                aligned = (length + 3) & ~3
                require(length >= 16 and aligned <= len(data) - pos and actual_seq == seq and pid in (0, port) and
                        flags == 2 and not any(data[pos + length:pos + aligned]), 'message length/sequence/pid/flags/padding')
                require(cursor < len(rows), 'missing independent message observation')
                message = rows[cursor]; cursor += 1
                shape(message, 'kind dataset index datagram offset length type flags seq pid hex')
                require(message == dict(kind='message', dataset=name, index=msg_count, datagram=dg,
                    offset=pos, length=length, type=typ, flags=flags, seq=seq, pid=pid,
                    hex=data[pos:pos + length].hex()) and all(type(message[k]) is int for k in
                    ('index','datagram','offset','length','type','flags','seq','pid')), 'native message differs from original datagram')
                payload = data[pos + 16:pos + length]
                if typ == 3:
                    require(payload in (b'', b'\0' * 4), 'DONE status/extended shape')
                    done += 1
                else:
                    require(typ == reply, 'ERROR/OVERRUN/NOOP/unexpected response')
                    decoded.append(decode_message(payload, name, family))
                msg_count += 1; pos += aligned
            dg += 1
        require(cursor < len(rows), 'missing dataset terminator')
        end = rows[cursor]; cursor += 1
        shape(end, 'kind dataset datagrams messages data_messages done_count clock_ns')
        require(end == dict(kind='dataset_end', dataset=name, datagrams=dg, messages=msg_count,
                data_messages=len(decoded), done_count=1, clock_ns=end['clock_ns']) and done == 1 and dg > 0 and
                all(type(end[k]) is int for k in ('datagrams','messages','data_messages','done_count')), 'incomplete/forged dataset terminator')
        require(clock <= integer(end['clock_ns'], 1, 2**63 - 1) and
                end['clock_ns'] - request_clock <= (first['timeout_ms'] + 1000) * 1000000, 'dump clock/timeout')
        clock = end['clock_ns']; total_dg += dg; total_msg += msg_count; result[name] = decoded
    require(cursor == len(rows) - 1, 'missing final framing or trailing records')
    end = rows[cursor]
    shape(end, 'kind run_id boot_id pid clock_ns datasets datagrams messages status')
    require(end == dict(kind='end', run_id=run_id, boot_id=boot_id, pid=first['pid'],
        clock_ns=end['clock_ns'], datasets=7, datagrams=total_dg, messages=total_msg, status='complete') and
        all(type(end[k]) is int for k in ('pid','datasets','datagrams','messages')) and
        integer(end['clock_ns'], 1, 2**63 - 1) >= clock, 'final identity/completeness counters')
    # Dumps are non-atomic. A missing interface can be churn; never silently
    # erase the address/route/rule. Caller may retry a new FULL observation.
    indices = {r['ifindex'] for r in result['links']}
    require(len(indices) == len(result['links']), 'duplicate interface index')
    require(sum(bool(r['flags'] & 8) and r['type'] == 772 for r in result['links']) == 1,
            'one real loopback link required; query errors cannot become empty links')
    for name, records in result.items():
        if name == 'links': continue
        for record in records:
            if 'ifindex' in record: require(record['ifindex'] in indices, 'cross-dump unresolved interface; new full snapshot required')
            for a in record['attributes']:
                if name.startswith('routes') and a['type'] in (3, 4):
                    require(a['value'] in indices, 'route interface absent from links; new full snapshot required')
                if name.startswith('routes') and a['type'] == 9:
                    require(all(h['ifindex'] in indices for h in a['value']), 'multipath interface absent')
    return {'schema': SCHEMA, 'run_id': run_id, 'boot_id': boot_id, 'identity': first,
            'datasets': result, 'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'observations': rows, 'kernel_uapi': KERNEL_UAPI, 'atomic': False,
            'status': 'complete_readonly_observation_NOT_VPN_acceptance'}


def capture_snapshot(shell, label, boot_id, *, helper, run_id=None, timeout_ms=5000):
    """shell(command,label) MUST verify actual remote exit via enclosing nonce.

    This function neither installs/removes the helper nor owns VM cleanup. Root
    must verify its binary and actual guest runtime hashes before this call.
    """
    run_id = run_id or secrets.token_hex(16)
    require(re.fullmatch(r'/data/local/tmp/[A-Za-z0-9_./-]+', str(helper)) and
            all(part not in ('', '.', '..') for part in str(helper).split('/')[1:]), 'owned absolute helper path required')
    integer(timeout_ms, 100, 30000)
    command = shlex.quote(str(helper)) + ' --run-id ' + shlex.quote(run_id) + ' --timeout-ms ' + str(timeout_ms)
    raw = shell(command, label)
    require(isinstance(raw, str) and raw and not raw.endswith(('\n', '\r')), 'exact GuestUi no-terminal-LF transport required')
    return raw, parse_snapshot(raw + '\n', run_id=run_id, boot_id=boot_id)


def structural_view(decoded):
    """Comparable structure while retaining explicit volatile-attribute presence.

    Callers must separately assess captured dynamic link flags, route/address
    lifetimes, namespaces and process/TUN evidence. This never decides cleanup.
    """
    require(decoded.get('status') == 'complete_readonly_observation_NOT_VPN_acceptance', 'fully decoded snapshot required')
    def attribute(a):
        if a.get('volatile'):
            return {key: a[key] for key in ('type','flags','name')} | {'volatile_payload_retained_in_raw': True}
        return a
    result = {}
    for name, records in decoded['datasets'].items():
        result[name] = []
        for record in records:
            item = {key: value for key, value in record.items() if key not in ('attributes','volatile_attributes')}
            item['attributes'] = [attribute(a) for a in record['attributes']]
            if 'volatile_attributes' in record:
                item['volatile_attribute_presence'] = [{k: a[k] for k in ('type','flags','name')}
                                                       for a in record['volatile_attributes']]
            result[name].append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--boot-id', required=True)
    args = parser.parse_args()
    print(json.dumps(parse_snapshot(args.raw.read_bytes().decode('utf-8'), run_id=args.run_id, boot_id=args.boot_id), indent=2))


if __name__ == '__main__': main()
