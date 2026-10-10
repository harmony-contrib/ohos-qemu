"""Validate actual public allocation accounting, without claiming the kernel gap closed."""
import json
import re


def verify(text, run_id, uid):
    if re.fullmatch('[a-f0-9]{32}', run_id or '') is None or type(uid) is not int or uid < 10000:
        raise ValueError('fresh ordinary application identity required')
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != 6:
        raise ValueError('five real allocation snapshots and completion required')
    keys = {'runId', 'phase', 'native', 'gl', 'graph', 'total', 'error', 'publicTypes', 'publicValues'}
    pid = None
    graph = []
    for phase, row in enumerate(rows):
        if phase < 5 and row.get('publicTypes') != ['number', 'number', 'number']:
            raise ValueError('public HiDebug fields must remain numbers: ' + str(row.get('publicTypes')))
        if (set(row) != keys or row['runId'] != run_id or type(row['phase']) is not int or
                row['phase'] != phase or row['error'] != '' or
                any(type(row[k]) is not int or row[k] < 0 for k in ('gl', 'graph', 'total'))):
            raise ValueError('malformed, foreign or failed graphics memory record')
        if phase == 5:
            if (row['native'] != [] or row['publicTypes'] != [] or row['publicValues'] != [] or
                    any(row[k] for k in ('gl', 'graph', 'total'))):
                raise ValueError('completion must follow all real buffer releases')
            continue
        if row['publicValues'] != [str(row[key]) for key in ('gl', 'graph', 'total')]:
            raise ValueError('public numeric values were coerced or changed')
        values = row['native']
        if (not isinstance(values, list) or len(values) != 14 or any(type(v) is not int for v in values) or
                values[0] <= 1 or values[1:3] != [uid, uid] or values[3] != 0 or values[5] != 0 or
                values[8:10] != [401, 401] or values[10] != phase or values[11] != [0, 1, 2, 1, 0][phase]):
            raise ValueError('actual ordinary native API, null boundaries or buffer lifecycle failed')
        if pid is not None and values[0] != pid:
            raise ValueError('application process changed between allocations')
        pid = values[0]
        if (values[4] != values[6] + values[7] or values[4] != row['total'] or
                values[6] != row['gl'] or values[7] != row['graph'] or
                row['total'] != row['gl'] + row['graph']):
            raise ValueError('C++ and ArkTS public accounting disagree')
        graph.append(row['graph'])
    size0, size1 = rows[2]['native'][12:14]
    if size0 < 16384 or size1 < 16384:
        raise ValueError('two actual large RGBA allocations required')
    if (rows[0]['native'][12:14] != [0, 0] or rows[1]['native'][12:14] != [size0, 0] or
            any(rows[phase]['native'][12:14] != [size0, size1] for phase in (2, 3, 4))):
        raise ValueError('allocation geometry changed across the retained-buffer lifecycle')
    expected = [graph[0], graph[0] + size0, graph[0] + size0 + size1, graph[0] + size1, graph[0]]
    if graph != expected:
        raise ValueError('public DMA-BUF accounting does not follow allocation/release: ' + str(graph) +
                         '; expected ' + str(expected))
    return dict(pid=pid, uid=uid, graph_kib=graph, allocation_kib=[size0, size1], closed=[],
                not_claimed='raw_kernel_inode_correlation_or_complete_HiDebug_API_or_full_gate')
