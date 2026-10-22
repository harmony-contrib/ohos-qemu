"""Independent pure raw decoders. Never treat an application getter as wire."""
import re
from hap_identity_binding import strict_json
from capability578_owned_io import require

ROW_KEYS = {'schema','run_id','boot_id','role','operation_id','action','seq',
    'monotonic_ms','pid','uid','files_dir','kind','code','value'}
ZERO = '0' * 32


def caller_rows(raw, run, boot, role, uid, pid):
    require(type(raw) is str and raw.endswith('\n') and 0 < len(raw.encode()) < 16*1024*1024,
        'complete bounded actual caller journal required')
    result = []; previous = -1
    for seq, line in enumerate(raw.splitlines(), 1):
        row = strict_json(line)
        require(type(row) is dict and set(row) == ROW_KEYS and type(row['schema']) is int and
            row['schema'] == 1 and row['run_id'] == run and row['boot_id'] == boot and row['role'] == role and
            type(row['seq']) is int and row['seq'] == seq and type(row['monotonic_ms']) is int and
            row['monotonic_ms'] >= previous and type(row['uid']) is int and row['uid'] == uid and
            type(row['pid']) is int and row['pid'] == pid and type(row['code']) is int and
            re.fullmatch('[a-f0-9]{32}', row['operation_id']) and type(row['action']) is str and
            type(row['kind']) is str and row['files_dir'] == '/data/storage/el2/base/haps/entry/files',
            'actual caller identity/sequence/monotonic time/schema differs')
        previous = row['monotonic_ms']; result.append(row)
    return result


def terminal(rows, request):
    selected = [r for r in rows if r['operation_id'] == request['operation_id']]
    synchronous = [r for r in selected if r['kind'] not in ('callback','sms-send-callback','sms-delivery-callback')]
    ends = [r for r in synchronous if r['kind'] == 'end']
    require(len(ends) == 1 and synchronous[0]['kind'] == 'begin' and synchronous[-1] == ends[0] and
        synchronous[0]['value'] == request and all(r['action'] == request['action'] for r in selected),
        'actual request/nonce/body and one completion required')
    # Callbacks retain their registration op and may arrive after its end;
    # synchronous request rows, not listener callbacks, define completion.
    return selected


def wire_commands(peer):
    """Frame AT plus real Ctrl-Z SMS bodies without rewriting the input stream."""
    commands = []; pending = bytearray(); sms = False; started = None
    for row in peer:
        if row['kind'] != 'rx': continue
        for ch in bytes.fromhex(row['hex']):
            if started is None and ch not in (10,13): started = row['monotonic_ms']
            if sms:
                if ch == 26:
                    commands.append({'kind':'sms-pdu','raw':bytes(pending),'start':started,
                        'end':row['monotonic_ms'],'peer_seq':row['seq']})
                    pending.clear(); sms = False; started = None
                elif ch not in (10,13): pending.append(ch)
            elif ch in (10,13):
                if pending:
                    raw = bytes(pending)
                    commands.append({'kind':'at','raw':raw,'start':started,'end':row['monotonic_ms'],
                        'peer_seq':row['seq']})
                    sms = re.fullmatch(rb'AT\+CMGS=[1-9][0-9]*',raw) is not None
                    pending.clear(); started = None
            else: pending.append(ch)
    require(not pending and not sms, 'incomplete actual AT/SMS input frame')
    return commands


def submit_pdu(raw):
    """Decode the actual single-part fresh ASCII SMS, retaining both alphabets.

    UCS2 and GSM7 ASCII are sufficient for the fixed L22-HEX payload; extended
    characters, multipart, CDMA, receive and delivery are separate obligations.
    """
    require(re.fullmatch(rb'(?:[a-fA-F0-9]{2})+',raw), 'actual hex SMSC+TPDU bytes required')
    p = bytes.fromhex(raw.decode()); require(len(p) >= 10, 'short SMS PDU')
    offset = 1 + p[0]; require(offset + 5 < len(p), 'short actual TPDU header')
    first = p[offset]; require(first & 3 == 1 and not first & 0x40, 'single-part SMS-SUBMIT TPDU required')
    mr = p[offset+1]; length = p[offset+2]; toa = p[offset+3]; offset += 4
    count = (length + 1) // 2
    require(1 <= length <= 20 and offset + count + 3 <= len(p), 'actual destination field malformed')
    address = ''.join(format(b & 15,'x') + format(b >> 4,'x') for b in p[offset:offset+count])[:length]
    require(address.isdecimal() and toa & 0x80, 'actual numeric destination malformed')
    offset += count; pid = p[offset]; dcs = p[offset+1]; offset += 2
    vpf = (first >> 3) & 3
    offset += 0 if vpf == 0 else 1 if vpf == 2 else 7
    require(offset < len(p), 'actual TPDU validity/UDL truncated')
    length = p[offset]; user = p[offset+1:]
    if dcs & 12 == 8:
        require(length == len(user) and length % 2 == 0, 'actual UCS2 UDL differs')
        text = user.decode('utf-16-be')
    elif dcs & 12 == 0:
        require((length*7+7)//8 == len(user), 'actual GSM7 UDL differs')
        chars = []
        for index in range(length):
            bit = index*7; byte = bit//8; shift = bit%8
            value = (user[byte] >> shift) | ((user[byte+1] << (8-shift)) if shift > 1 and byte+1 < len(user) else 0)
            value &= 127
            require(value == 45 or 48 <= value <= 57 or 65 <= value <= 90 or 97 <= value <= 122,
                'fixed ASCII GSM7 payload contains unexpected alphabet/escape')
            chars.append(chr(value))
        text = ''.join(chars)
    else: raise ValueError('fixed fresh text must use actual GSM7 or UCS2 encoding')
    require(pid == 0, 'unexpected actual SMS protocol identifier')
    return {'destination':address,'toa':toa,'text':text,'tp_mr':mr,'dcs':dcs,'tpdu_octets':len(p)-1-p[0],
        'status_report_requested':bool(first & 0x20)}


def ipv4_udp(raw):
    require(type(raw) is bytes and len(raw) >= 28 and raw[0] == 0x45 and raw[9] == 17 and
        raw[6] & 0x3f == 0 and raw[7] == 0, 'unfragmented actual IPv4 UDP required')
    size = int.from_bytes(raw[2:4],'big'); udp = int.from_bytes(raw[24:26],'big')
    require(size == len(raw) and udp == size - 20 and udp >= 8, 'actual wire IP/UDP length differs')
    checksum = sum(int.from_bytes(raw[n:n+2],'big') for n in range(0,20,2))
    while checksum >> 16: checksum = (checksum & 65535) + (checksum >> 16)
    require(checksum == 65535, 'actual IP checksum differs')
    return {'source':'.'.join(map(str,raw[12:16])), 'destination':'.'.join(map(str,raw[16:20])),
        'source_port':int.from_bytes(raw[20:22],'big'),'destination_port':int.from_bytes(raw[22:24],'big'),
        'payload':raw[28:].decode('ascii')}


def packet_pair(peer, payload):
    actual = []
    for row in peer:
        if row['kind'] != 'backend': continue
        raw = bytes.fromhex(row['hex'])
        if len(raw) < 28 or raw[0] != 0x45: continue
        packet = ipv4_udp(raw)
        if packet['payload'] in (payload,'L22-REPLY:' + payload): actual.append((row,packet))
    require(len(actual) == 2, 'fresh payload must have exactly one actual endpoint request and response')
    (first,a),(last,b) = actual
    require(a['source'] == b['destination'] == '198.18.22.2' and
        a['destination'] == b['source'] == '198.18.22.1' and
        a['destination_port'] == b['source_port'] == 53122 and
        a['source_port'] == b['destination_port'] and a['source_port'] > 0 and
        a['payload'] == payload and b['payload'] == 'L22-REPLY:' + payload and
        first['seq'] < last['seq'] and first['monotonic_ms'] <= last['monotonic_ms'],
        'actual independent endpoint packet directions/ports/payload/causality differ')
    return actual


def status_report(text):
    require(type(text) is str and re.fullmatch(r'(?:[0-9A-Fa-f]{2})+',text),'actual status report hex required')
    p = bytes.fromhex(text); require(p and p[0]+1 < len(p),'actual status report SMSC length invalid')
    offset = p[0]+1
    require(p[offset]&3 == 2 and offset+4 < len(p),'actual SMS-STATUS-REPORT header required')
    reference = p[offset+1]; digits = p[offset+2]; toa = p[offset+3]; offset += 4
    count = (digits+1)//2
    require(0 < digits <= 20 and offset+count+15 == len(p),'actual status report destination/timestamp/status length differs')
    address = ''.join(format(n&15,'x') + format(n>>4,'x') for n in p[offset:offset+count])[:digits]
    require(address.isdecimal() and toa&0x80,'actual status report address malformed')
    return {'message_reference':reference,'destination':address,'status':p[-1]}
