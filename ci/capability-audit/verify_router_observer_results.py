"""Replay actual typed router callbacks; never infer other observer support."""
import argparse
import json
from pathlib import Path
import re

from router_observer_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh router observer run required')
    rows = [json.loads(line) for line in text.splitlines()]
    keys = {'runId', 'name', 'listener', 'generation', 'phase', 'index', 'pageName',
            'path', 'state', 'pageId', 'contextMatches', 'counts'}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != keys or row['runId'] != run_id or
                any(type(row[k]) is not str for k in ('name', 'listener', 'pageName', 'path', 'pageId')) or
                any(type(row[k]) is not int for k in ('generation', 'phase', 'index', 'state')) or
                row['contextMatches'] is not True or not isinstance(row['counts'], list) or
                len(row['counts']) != 2 or any(type(v) is not int or v < 0 for v in row['counts'])):
            raise ValueError('malformed or foreign actual callback record')
    cursor = 0
    ids = set()
    for generation in range(2):
        counts = [0, 0]
        for phase, start, end in ((0, 'registered', 'both-returned'),
                                  (1, 'first-removed', 'second-returned'),
                                  (2, 'all-removed', 'unsubscribed-returned')):
            def marker(name):
                nonlocal cursor
                if cursor >= len(rows):
                    raise ValueError('incomplete routed lifecycle')
                row = rows[cursor]
                expected = dict(runId=run_id, name=name, listener='', generation=generation,
                    phase=phase, index=0, pageName='', path='', state=0, pageId='',
                    contextMatches=True, counts=counts[:])
                if row != expected:
                    raise ValueError('wrong phase, count, or unsubscribed callback')
                cursor += 1
            marker(start)
            events = []
            while cursor < len(rows) and rows[cursor]['name'] == 'event':
                row = rows[cursor]
                if (phase == 2 or row['generation'] != generation or row['phase'] != phase or
                        row['listener'] not in (('a', 'b') if phase == 0 else ('b',)) or
                        row['index'] < 0 or row['state'] not in range(6) or not row['pageId'] or
                        not row['path']):
                    raise ValueError('callback continued after removal or has invalid actual page fields')
                counts[0 if row['listener'] == 'a' else 1] += 1
                if row['counts'] != counts:
                    raise ValueError('actual callback counters are inconsistent')
                events.append(row)
                cursor += 1
            if phase < 2:
                page_ids = set()
                for listener in (('a', 'b') if phase == 0 else ('b',)):
                    child = [row for row in events if row['listener'] == listener and
                             re.search(r'(?:^|/)pages/ObserverDetail(?:\.(?:js|ets))?$', row['path'])]
                    if (not child or not {0, 1, 2, 3}.issubset({row['state'] for row in child}) or
                            len({row['pageId'] for row in child}) != 1 or
                            len({row['index'] for row in child}) != 1 or child[0]['index'] < 1):
                        raise ValueError('real child appear/show/hide/disappear lifecycle missing')
                    states = [row['state'] for row in child]
                    if not states.index(0) < states.index(2) < states.index(3) < states.index(1):
                        raise ValueError('real child lifecycle order wrong')
                    page_ids.add(child[0]['pageId'])
                if len(page_ids) != 1 or ids.intersection(page_ids):
                    raise ValueError('listeners disagree or routed child was not recreated')
                ids.update(page_ids)
                if phase == 0:
                    a = [{k: row[k] for k in ('index', 'pageName', 'path', 'state', 'pageId')}
                         for row in events if row['listener'] == 'a']
                    b = [{k: row[k] for k in ('index', 'pageName', 'path', 'state', 'pageId')}
                         for row in events if row['listener'] == 'b']
                    if a != b:
                        raise ValueError('both listeners must observe the same real page events')
            marker(end)
    if len(rows) != cursor + 1 or rows[-1] != dict(runId=run_id, name='summary', listener='',
            generation=2, phase=2, index=0, pageName='', path='', state=0, pageId='',
            contextMatches=True, counts=counts):
        raise ValueError('completed two-generation subscription proof required')
    return dict(closed=[], generations=2, observed_child_instances=4,
        callback_specific_removal=True, all_callbacks_removed=True,
        not_claimed='constructor_exports_density_breakpoints_or_full_gate')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch,
        archive_sha256=digest(args.archive), results_sha256=digest(args.results),
        application_identity_sha256=digest(args.application_identity), compiled_inputs_sha256=digest(args.inputs),
        verifier_sha256=digest(Path(__file__)), first_artifact_behavior_gate_passed=False, failures=[])
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], failures=report['failures'])))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
