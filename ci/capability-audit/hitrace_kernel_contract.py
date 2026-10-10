"""Require kernel-observed public native/ArkTS markers, not successful void calls."""
import json
import re

COUNTS = [-2147483649, 0, 2147483648]
SCOPE = 'ordinary_public_Cxx_ArkTS_markers_in_real_kernel_trace_NOT_all_HiTrace_APIs'


def trace_configuration(text):
    """Compare configured capacity, not Linux's lazy initial buffer allocation."""
    lines = [line.strip() for line in text.strip().splitlines()]
    if len(lines) != 6 or lines[0] not in ('0', '1') or lines[1] != 'nop':
        raise ValueError('bounded actual nop trace configuration required')
    size = re.fullmatch(r'([0-9]+)(?: \(expanded: ([0-9]+)\))?', lines[2])
    clocks = re.findall(r'\[([a-z_]+)\]', lines[3])
    if (not size or len(clocks) != 1 or re.fullmatch('[0-9]+', lines[4]) is None or
            re.fullmatch('-?[0-9]+', lines[5]) is None):
        raise ValueError('invalid actual trace capacity, clock or parameters')
    return dict(on=lines[0], tracer=lines[1], buffer=size[2] or size[1],
                clock=clocks[0], tags=lines[4], pid=lines[5])


def verify_restored_configuration(before, after, page_size, arch):
    # Pinned Linux 6.6 ring_buffer.c: buffer_data_page (u64, local_t),
    # no HAVE_64BIT_ALIGNED_ACCESS in these three products; resize uses
    # DIV_ROUND_UP(bytes, PAGE_SIZE - offsetof(data)), read prints bytes >> 10.
    if type(page_size) is not int or page_size != 4096 or arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('verified QEMU kernel page size and ABI required')
    payload = page_size - (12 if arch == 'armv7a' else 16)
    requested = int(before['buffer']) * 1024
    capacity = max(2, (requested + payload - 1) // payload) * payload // 1024
    if after != dict(before, buffer=str(capacity)):
        raise ValueError('trace policy was not restored with exact kernel buffer rounding')
    return dict(status='restored', requested_buffer_kb=int(before['buffer']),
                actual_buffer_kb=capacity, page_size=page_size, page_payload_bytes=payload,
                note='lazy allocation is expanded; configured request, tracer, clock, tags and PID restored')


def verify_rows(text, run_id, uid):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or type(uid) is not int or uid < 20010000:
        raise ValueError('fresh run and ordinary app UID required')
    rows = [json.loads(line) for line in text.splitlines()]
    names = ['identity', 'native.0', 'arkts.0', 'native.1', 'arkts.1', 'summary']
    if len(rows) != len(names):
        raise ValueError('complete actual trace caller observations required')
    for row, name in zip(rows, names):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or any(type(v) is not int for v in row['values'])):
            raise ValueError('foreign, failed, malformed or reordered trace caller')
    identity = rows[0]['values']
    if len(identity) != 3 or identity[0] <= 0 or identity[1:] != [uid, uid]:
        raise ValueError('actual ordinary PID and UID required')
    first = rows[1]['values']
    if len(first) != 5 or first[:4] != [identity[0], uid, uid, 1] or first[4] <= 0:
        raise ValueError('native trace must be enabled for actual ordinary PID/TID')
    if rows[3]['values'] != first or rows[2]['values'] != [1] or rows[4]['values'] != [1] or rows[5]['values'] != [2]:
        raise ValueError('same-process two-generation native and ArkTS calls required')
    return identity[0], first[4]


def expected(run_id):
    records = []
    for generation in range(2):
        native = f'oqht-{run_id}-n{generation}'
        arkts = f'oqht-{run_id}-a{generation}'
        records += [('B', native + '-sync', None), ('B', native + '-nested', None)]
        records += [('C', native + '-count', value) for value in COUNTS]
        records += [('E', native + '-nested', None), ('E', native + '-sync', None)]
        records += [(kind, native + '-async', task) for kind, task in
                    (('S', 0), ('S', 2147483647), ('F', 2147483647), ('F', 0))]
        records += [('S', arkts + '-async', 0), ('S', arkts + '-async', 2147483647)]
        records += [('C', arkts + '-count', value) for value in COUNTS]
        records += [('F', arkts + '-async', 2147483647), ('F', arkts + '-async', 0)]
    return records


def verify_trace(text, run_id, pid, tid):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or any(type(v) is not int or v <= 0 for v in (pid, tid)):
        raise ValueError('real caller identity required')
    if not text.startswith('# tracer:') or 'entries-in-buffer/entries-written' not in text:
        raise ValueError('actual kernel text trace header required')
    stack, actual = [], []
    prefix = 'oqht-' + run_id + '-'
    for line in text.splitlines():
        match = re.match(r'^\s*.+-(\d+)\s+(?:\(\s*(?:\d+|-------)\)\s+)?\[\d+\].*?:\s+tracing_mark_write:\s+(.+)$', line)
        if not match:
            if prefix in line:
                raise ValueError('nonce found outside an actual kernel marker record')
            continue
        source_tid = int(match[1])
        fields = match[2].split('|')
        if len(fields) < 3 or fields[0] not in ('B', 'E', 'S', 'F', 'C') or not fields[1].isdigit():
            if prefix in line:
                raise ValueError('malformed actual nonce marker')
            continue
        kind, source_pid = fields[0], int(fields[1])
        if source_tid != tid or source_pid != pid:
            if prefix in line:
                raise ValueError('trace payload or emitting kernel thread has wrong identity')
            continue
        name = fields[2].removeprefix('H:')
        # The real meter may prepend the current public HiTraceChain identity.
        name = re.sub(r'^\[[0-9a-f]+,[0-9a-f]+,[0-9a-f]+\]#', '', name)
        if kind == 'B':
            stack.append(name)
            if name.startswith(prefix):
                actual.append((kind, name, None))
        elif kind == 'E':
            if stack:
                ended = stack.pop()
                if ended.startswith(prefix):
                    actual.append((kind, ended, None))
        elif name.startswith(prefix):
            if len(fields) < 4 or re.fullmatch('-?[0-9]+', fields[3]) is None:
                raise ValueError('actual async cookie/counter lost numeric precision')
            actual.append((kind, name, int(fields[3])))
    if any(name.startswith(prefix) for name in stack) or actual != expected(run_id):
        raise ValueError('kernel trace lost, duplicated, reordered or changed actual public API records')
    return dict(closed=[], scope=SCOPE, pid=pid, tid=tid, generations=2,
                public_api_kernel_records=len(actual), signed_64bit_counters=COUNTS,
                not_claimed='disabled_filtering_trace_chain_listener_APIs_or_full_gate')
