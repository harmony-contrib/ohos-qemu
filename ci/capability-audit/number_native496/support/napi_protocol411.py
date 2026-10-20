"""Finite raw NAPI replay. No resource calls or invented error-code authority."""
import json
import re
from pathlib import PurePosixPath

FIELDS = set(('schema scope run ownerRun phase number seq event api valueJSON codeKnown code codeJSON message time '
              'firstArtifactGatePassed aggregateProviderPassed nativeLoadingProved').split())
SCHEMA = 'number-napi411-raw/v1'
SCOPE = 'actual_API_raw_ONLY_requires_independent_identity_source_and_loading_proof'


def need(ok, text):
    if not ok: raise ValueError(text)


def decode(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            need(k not in result, 'duplicate raw JSON key'); result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite raw JSON')))


def names(run):
    need(type(run) is str and re.fullmatch('[a-f0-9]{32}', run), 'exact run required')
    return ('number-napi411-' + run + '-napi-read.jsonl',
            'number-napi-token411-' + run + '-napi-before.json',
            'number-napi-token411-' + run + '-napi-after.json')


def find_script(run):
    return 'find /data -type f \\( ' + ' -o '.join('-name ' + n for n in names(run)) + ' \\) -print'


def discovered(raw, run):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, 'bounded actual find bytes required')
    lines = raw.decode('ascii').splitlines(); expected = names(run); result = {}
    need(len(lines) == len(set(lines)) == 3, 'exactly three unique actual NAPI file hits required')
    for line in lines:
        p = PurePosixPath(line)
        need(line.startswith('/data/') and str(p) == line and '..' not in p.parts and
             re.fullmatch('/[A-Za-z0-9_./+-]+', line) and p.name in expected and p.name not in result,
             'foreign/unsafe/duplicate NAPI file hit')
        result[p.name] = line
    need(set(result) == set(expected) and len({str(PurePosixPath(p).parent) for p in result.values()}) == 1,
         'NAPI journal and both tokens must share actual directory')
    return tuple(result[n] for n in expected)


def rows(raw, run, owner, number):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576 and raw.endswith(b'\n'), 'complete bounded JSONL required')
    lines = raw.splitlines(); need(lines and all(lines), 'empty journal record refused')
    result = [decode(line) for line in lines]
    for i, r in enumerate(result):
        need(type(r) is dict and set(r) == FIELDS and r['schema'] == SCHEMA and r['scope'] == SCOPE and
             (r['run'], r['ownerRun'], r['phase'], r['number']) == (run, owner, 'napi-read', number) and
             type(r['seq']) is int and r['seq'] == i and type(r['time']) is int and r['time'] > 0 and
             type(r['code']) is int and type(r['codeKnown']) is bool and
             all(type(r[k]) is str for k in ('event', 'api', 'valueJSON', 'message', 'codeJSON')) and
             all(r[k] is False for k in ('firstArtifactGatePassed','aggregateProviderPassed','nativeLoadingProved')),
             'exact raw NAPI identity/types/sequence/gates required')
        need(i == 0 or result[i-1]['time'] <= r['time'], 'journal time reversed')
        if r['event'] not in ('threw','rejected','probe-error'):
            need(r['codeKnown'] is False and r['code'] == 0 and r['message'] == '' and r['codeJSON'] == '', 'nonerror fabricated code')
        else:
            actual_code = None if r['codeJSON'] == '<undefined>' else decode(r['codeJSON'])
            if r['codeKnown']:
                need(type(actual_code) is int and actual_code == r['code'], 'numeric error code/raw encoding differs')
            else:
                need(r['code'] == 0, 'unknown numeric code must stay unknown; raw code retained separately')
    return result


def context(calls, run, owner, number):
    found = set()
    for call in calls:
        for line in call['stdout'].decode('utf-8').splitlines():
            if 'NUMBER_NAPI411 ' not in line: continue
            try: r = decode(line.split('NUMBER_NAPI411 ', 1)[1])
            except ValueError: continue
            if (r.get('run'),r.get('ownerRun'),r.get('phase'),r.get('number'),r.get('event')) == (run,owner,'napi-read',number,'begin'):
                need(set(r) == FIELDS and r['schema'] == SCHEMA and r['seq'] == 0, 'malformed actual NAPI begin')
                p = decode(r['valueJSON']); need(type(p) is str, 'actual filesDir string required'); found.add(p)
    need(len(found) == 1, 'unique actual NAPI context log required')
    value = found.pop(); p = PurePosixPath(value)
    need(value.startswith('/') and str(p) == value and '..' not in p.parts and
         re.fullmatch('/[A-Za-z0-9_./+-]+',value), 'unsafe actual context log')
    return value


def review(raw, *, role, run, owner, number, actual_context):
    need(role in ('system-granted','system-readonly','ordinary') and
         all(type(v) is str and re.fullmatch('[a-f0-9]{32}',v) for v in (run,owner)) and
         type(number) is str and re.fullmatch(r'\+?[0-9]{7,20}',number),'finite role/run/owner/number required')
    r = rows(raw, run, owner, number); cursor = 0; pending = []; outcomes = {}
    def take(event, api=''):
        nonlocal cursor
        need(cursor < len(r) and (r[cursor]['event'],r[cursor]['api']) == (event,api),
             'extra/missing/out-of-order NAPI event: ' + event + '/' + api)
        row = r[cursor]; cursor += 1; return row
    first = take('begin'); need(decode(first['valueJSON']) == actual_context, 'actual log/file filesDir mismatch')
    snapshots = []
    def snapshot(label):
        s = decode(take('snapshot',label)['valueJSON'])
        need(type(s) is dict and set(s) == {'count','number','name','classify','isCloud'} and
             type(s['count']) is int and s['count'] == 1 and type(s['isCloud']) is int and s['isCloud'] == 0 and
             type(s['number']) is str and re.fullmatch(r'\+?[0-9]{7,20}',s['number']) and
             s['name'] == 'number-local375:' + owner + ':persist' and s['classify'] == 'custom',
             'actual persisted owned row required; empty/foreign rows refused')
        snapshots.append(s)
    if role != 'ordinary': snapshot('before')
    for api in ('getNumberMarkInfo','getNumberLocation'):
        take('call',api)
        need(cursor < len(r), 'incomplete NAPI outcome')
        if r[cursor]['event'] == 'threw': outcome = take('threw',api)
        else:
            take('dispatched',api)
            need(cursor < len(r) and r[cursor]['event'] in ('resolved','rejected'), 'missing Promise terminal')
            outcome = take(r[cursor]['event'],api)
        outcomes[api] = dict(outcome)
        if role == 'ordinary':
            need(outcome['event'] != 'resolved', 'ordinary caller resolved system API; no denial inference')
            pending.append(api + ': actual raw error retained; exact target public error translation unbound')
        elif outcome['event'] != 'resolved':
            pending.append(api + ': actual ' + outcome['event'] + '; raw code is not permission success')
        elif api == 'getNumberMarkInfo':
            mark = decode(outcome['valueJSON'])
            need(type(mark) is dict and type(mark.get('markType')) is int and mark['markType'] == 8 and
                 mark.get('markContent') == 'number-local375:' + owner + ':persist' and
                 set(mark) <= {'markType','markContent','markCount','markSource','isCloud','markDetails'} and
                 ('isCloud' not in mark or mark['isCloud'] is False), 'NAPI mark must join the real owned DataShare row')
        else:
            value = decode(outcome['valueJSON']); need(type(value) is str, 'actual location string required')
            pending.append('getNumberLocation: string observation only; independent real dataset/business oracle not supplied')
    if role != 'ordinary':
        snapshot('after'); need(snapshots[0] == snapshots[1], 'NAPI read changed persisted row')
    take('end'); last = take('summary')
    need(decode(last['valueJSON']) == 'raw_recorded_NOT_acceptance' and cursor == len(r), 'extra/false success summary')
    return dict(scope='raw NAPI/public persisted-row cross-read ONLY', outcomes=outcomes, snapshots=snapshots,
                pending=pending, native_callback_proven=False, aggregate_provider_passed=False,
                first_artifact_behavior_gate_passed=False)
