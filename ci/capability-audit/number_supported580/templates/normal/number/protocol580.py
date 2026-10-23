"""Pure Number580 case protocol/oracle; no process, SDK, transport or Owner.

The fixed Owner must independently replay the original411/496, real image seed
extraction, signed-role and final resource receipts. This module alone is never
an aggregate or first-artifact gate. Caller data contains observations only.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

HERE = Path(__file__).resolve().parent
CONTRACT_SHA = None  # typed fixed-source binding, fail closed until normal projection
LOCAL_OBLIGATION = 'number580:phone-supported-local'
ROLES = ('system-granted', 'system-readonly', 'ordinary')
FIELDS = {'schema','run','ownerRun','phase','caseId','seq','time','event','step',
          'valueJSON','codeKnown','code','codeJSON','message','runtimePass','wholeAggregateClosed'}


def need(value, message):
    if not value:
        raise ValueError(message)


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate Number580 JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite Number580 JSON')))


def checked(row, maximum=16*1024*1024):
    need(type(row) is dict and set(row) == {'path','sha256','bytes'} and
         type(row['path']) is str and type(row['bytes']) is int and 0 <= row['bytes'] <= maximum and
         re.fullmatch('[0-9a-f]{64}', row['sha256'] or ''), 'exact bounded Ref3 required')
    path = Path(row['path'])
    need(path.is_absolute() and path.resolve() == path and
         all(not p.is_symlink() for p in (path, *path.parents)), 'canonical immutable Ref path required')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == row['bytes'], 'Ref inode/size changed')
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == row['sha256'], 'Ref bytes changed')
    return path


def contract():
    path = HERE/'CONTRACT580.json'
    need(type(CONTRACT_SHA) is str and re.fullmatch('[0-9a-f]{64}', CONTRACT_SHA) and
         hashlib.sha256(path.read_bytes()).hexdigest() == CONTRACT_SHA, 'normal fixed Number580 contract binding missing/changed')
    return decode(path.read_bytes())


def cases():
    value = contract()['cases']
    need(len(value) == len({v['id'] for v in value}) and all(type(v) is dict for v in value), 'finite unique case table')
    return value


def request(case_id, number):
    selected = [row for row in cases()+contract()['account_cases'] if row['id'] == case_id]
    need(len(selected) == 1 and re.fullmatch(r'\+861810256[0-9]{4}', number or ''),
         'fixed case and same fresh-owned known-prefix number required')
    row = selected[0]
    return dict(caseId=case_id, api=row['api'], numbers=[number if n == '$owned_number' else n for n in row['numbers']],
                exact=row['exact'], operation=row['operation'])


def names(run):
    need(re.fullmatch('[0-9a-f]{32}', run or ''), 'fresh run required')
    return ('number-corpus580-'+run+'.jsonl', 'number-napi-token411-'+run+'-napi-before.json',
            'number-napi-token411-'+run+'-napi-after.json')


def find_script(run):
    return 'find /data -type f \\( '+' -o '.join('-name '+n for n in names(run))+' \\) -print'


def discovered(raw, run):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, 'bounded actual find raw')
    values = raw.decode('ascii').splitlines(); wanted = names(run); found = {}
    need(len(values) == len(set(values)) == 3, 'three unique actual journal/token files')
    for value in values:
        path = PurePosixPath(value)
        need(value.startswith('/data/') and str(path) == value and '..' not in path.parts and
             re.fullmatch('/[A-Za-z0-9_./+-]+', value) and path.name in wanted and path.name not in found,
             'unsafe/foreign actual file path')
        found[path.name] = value
    need(set(found) == set(wanted) and len({str(PurePosixPath(v).parent) for v in found.values()}) == 1,
         'actual journal and token directory differs')
    return tuple(found[n] for n in wanted)


def rows(raw, *, run, owner, case_id):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576 and raw.endswith(b'\n'), 'complete bounded journal raw')
    need(re.fullmatch('[a-f0-9]{32}', run or '') and re.fullmatch('[a-f0-9]{32}', owner or '') and run != owner,
         'fresh separate case and owner run')
    result = [decode(line) for line in raw.splitlines()]
    for index, row in enumerate(result):
        need(type(row) is dict and set(row) == FIELDS and row['schema'] == 'number580-corpus-raw/v1' and
             (row['run'],row['ownerRun'],row['phase'],row['caseId']) == (run,owner,'corpus580',case_id) and
             type(row['seq']) is int and row['seq'] == index and type(row['time']) is int and row['time'] > 0 and
             row['runtimePass'] is False and row['wholeAggregateClosed'] is False and
             type(row['codeKnown']) is bool and type(row['code']) is int and
             all(type(row[k]) is str for k in ('event','step','valueJSON','codeJSON','message')),
             'journal exact identity/sequence/types required')
        need(index == 0 or result[index-1]['time'] <= row['time'], 'journal clock reversed')
        if row['event'] in ('rejected','threw','probe-error'):
            value = None if row['codeJSON'] == '<undefined>' else decode(row['codeJSON'])
            need((row['codeKnown'] and type(value) is int and value == row['code']) or
                 (not row['codeKnown'] and row['code'] == 0), 'raw error encoding differs')
        else:
            need(row['codeKnown'] is False and row['code'] == 0 and row['codeJSON'] == row['message'] == '',
                 'non-error fabricated an error')
    return result


def selected_iso(value):
    need(type(value) is dict and set(value) == {'slotId','networkIso','simIso','systemRegion'} and
         type(value['slotId']) is int and value['slotId'] >= 0 and
         all(type(value[k]) is str for k in ('networkIso','simIso','systemRegion')), 'actual public Core/locale context raw')
    return (value['networkIso'] or value['simIso'] or value['systemRegion']).upper()


def seed_oracle(seeds):
    need(type(seeds) is dict and set(seeds) == {'numberlocation.data','yellowpage.data'}, 'two actual image seed Ref3 inputs required')
    table = contract()['seeds']; decoded = {}
    for name, row in seeds.items():
        need({k:row[k] for k in ('sha256','bytes')} == table[name], 'actual image seed differs from finite public source')
        decoded[name] = [decode(line) for line in checked(row).read_bytes().splitlines() if line]
    locations = {}
    for row in decoded['numberlocation.data'][1:]:
        need(set(row) == {'prefix','province','city','operator'}, 'fixed finite location data shape')
        locations[row['prefix']] = row  # source Parse uses last-write-wins map
    need(len(decoded['numberlocation.data'][1:]) == 11 and len(locations) == 10, 'full11/unique10 finite corpus required')
    yellow = {}
    for group in decoded['yellowpage.data'][1:]:
        for phone in group['phone']:
            need(phone['phone'] not in yellow, 'duplicate yellow-page number')
            yellow[phone['phone']] = phone['name']
    need(len(decoded['yellowpage.data'][1:]) == 3 and len(yellow) == 6, 'complete3/6 yellow-page corpus required')
    return locations, yellow


def location(value, locations):
    # The required image is CN and both actual Core/locale observations must
    # resolve CN. Only these fixed mobile/empty cases enter this finite oracle.
    if value.startswith('+86'):
        value = value[3:]
    elif value.startswith('0086'):
        value = value[4:]
    if not re.fullmatch('1[1-9][0-9]{9}', value):
        return ''
    need(value[:7] in locations, 'oracle never invents an unknown binary dataset entry')
    row = locations[value[:7]]
    place = row['province'] if row['province'] == row['city'] else row['province']+row['city']
    return place+' '+row['operator']


def review(raw, *, role, run, owner, case_id, number, actual_context, seeds):
    need(role in ROLES, 'fixed real role')
    values = rows(raw, run=run, owner=owner, case_id=case_id); cursor = 0
    req = request(case_id, number); locations, yellow = seed_oracle(seeds)
    def take(event, step=''):
        nonlocal cursor
        need(cursor < len(values) and (values[cursor]['event'],values[cursor]['step']) == (event,step),
             'extra/missing/out-of-order Number580 raw: '+event+'/'+step)
        row = values[cursor]; cursor += 1; return row
    need(decode(take('begin')['valueJSON']) == actual_context and decode(take('request')['valueJSON']) == req,
         'actual log/context/request and fixed corpus differ')
    contexts = []
    if role != 'ordinary':
        contexts.append(decode(take('context','before')['valueJSON']))
        need(selected_iso(contexts[-1]) == 'CN', 'actual selected country ISO is not required CN; no locale mutation/fake fallback')
    outcomes = {}
    steps = ('write','read') if req['operation'] in ('mark-create','mark-update','mark-delete') else ('read',)
    for step in steps:
        take('call',step)
        if cursor < len(values) and values[cursor]['event'] == 'threw':
            terminal = take('threw',step)
        else:
            take('dispatched',step)
            need(cursor < len(values) and values[cursor]['event'] in ('resolved','rejected'), 'missing actual Promise terminal')
            terminal = take(values[cursor]['event'],step)
        outcomes[step] = terminal
        if role == 'ordinary':
            need(terminal['event'] == 'threw' and terminal['codeKnown'] and terminal['code'] == 202,
                 'ordinary real non-system API must throw exact source-bound202 before provider')
        elif step == 'write' and role == 'system-readonly':
            # Number permission error has its own domain; actual selected core
            # mapping is replayed independently. Never call arbitrary nonzero a
            # permission success or replace it with a guessed201.
            need(terminal['event'] == 'rejected' and terminal['codeKnown'], 'readonly NAPI write must reject, complete code/raw retained')
        else:
            need(terminal['event'] == 'resolved', 'supported public call did not resolve')
            value = terminal['valueJSON']
            if step == 'write':
                need(value == '<undefined>', 'actual source SetNumberMarkInfo resolves undefined')
                continue
            value = decode(value); operation = req['operation']
            if operation in ('location','empty-location'):
                need(type(value) is str and value == location(req['numbers'][0],locations), 'exact source-derived location differs')
            elif operation == 'locations':
                need(value == [location(n,locations) for n in req['numbers']], 'batch source-derived order/repeat/unknown values differ')
            else:
                need(type(value) is dict and set(value) <= {'markType','markContent','markCount','markSource','isCloud','markDetails'} and
                     type(value.get('markType')) is int, 'actual public mark shape')
                if operation == 'yellow':
                    need(value['markType'] == 10 and value.get('markContent') == yellow[req['numbers'][0]], 'exact finite yellow-page source value differs')
                elif role == 'system-granted' and operation in ('mark-create','mark-update','mark-account-owned'):
                    tag = 'number580:'+owner+(':updated' if operation in ('mark-update','mark-account-owned') else ':created')
                    need(value['markType'] == 8 and value.get('markContent') == tag and value.get('isCloud') is False,
                         'NAPI write/read must join its own actual local row')
                else:
                    need(value['markType'] == 0 and value.get('markContent') is None, 'foreign/preexisting/undeleted mark or readonly mutation')
    if role != 'ordinary':
        contexts.append(decode(take('context','after')['valueJSON']))
        need(contexts[0] == contexts[1] and selected_iso(contexts[1]) == 'CN', 'actual Core/locale context changed')
    take('end'); need(decode(take('summary')['valueJSON']) == 'raw_recorded_NOT_acceptance' and cursor == len(values), 'false/extra summary')
    return dict(schema='number580-corpus-semantic-review/v1', role=role, run=run, case_id=case_id,
                request=req, outcomes=outcomes, context=contexts, semantic_raw_checked=True,
                readonly_error_source_replay_still_required=(role == 'system-readonly' and 'write' in outcomes),
                native_image_identity_and_account_and_owner_replay_still_required=True,
                aggregate_provider_passed=False, first_artifact_behavior_gate_passed=False)


def caller_pid(raw, journal_rows, core):
    wanted = {row['seq']:row for row in journal_rows}; found = {}
    for line in raw.splitlines():
        if b'NUMBER_CORPUS580 ' not in line:
            continue
        header = core.header(line); message = header['message']
        need(message.count(b'NUMBER_CORPUS580 ') == 1, 'ambiguous caller payload')
        row = decode(message.split(b'NUMBER_CORPUS580 ',1)[1])
        if (row.get('run'),row.get('phase')) != (journal_rows[0]['run'],'corpus580'):
            continue
        need(row.get('seq') in wanted and wanted[row['seq']] == row and row['seq'] not in found,
             'pulled journal differs from actual OS-header log')
        found[row['seq']] = header['pid']
    need(set(found) == set(wanted) and len(set(found.values())) == 1, 'complete single actual caller PID required')
    return next(iter(found.values()))


def review_native(bindings, *, admitted, original):
    """Full old496 image/clock/loader machinery, one new fixed case window.

    `original` is the Owner's already byte-admitted original496 module object,
    never a JSON module name. No original496 parser, row, journal or verdict is
    modified. Each case starts exactly once and has one source Query route.
    """
    required = {'schema','hdc','target','source_commit','archive_sha256','before','after',
                'generation_captures','bridge_calls','caller','number_image_report','loader_image_report',
                'system_image','emitter_elfs','build_inputs','producer_sources','seeds'}
    need(type(bindings) is dict and set(bindings) == required and bindings['schema'] == 'number580-case-native/v1',
         'exact new-case binding fields')
    need(admitted is not None and admitted.profile['archive']['sha256'] == bindings['archive_sha256'] and
         admitted.profile['system_image']['sha256'] == bindings['system_image']['sha256'],
         'real original observer admission belongs to another image')
    core = original.core
    need(admitted.evidence['actual_source']['sha256'] == original.CPP_SHA and
         original.checked(admitted.evidence['actual_source']).read_bytes() ==
         (original.HERE/'candidate/number_token_query395.cpp').read_bytes(), 'admitted real observer source changed')
    inputs = decode(checked(bindings['build_inputs'],4*1024*1024).read_bytes())
    need(inputs.get('source_git_revision') == bindings['source_commit'], 'actual new image source revision differs')
    need(type(bindings['producer_sources']) is dict and set(bindings['producer_sources']) == {'capture','observer'} and
         bindings['producer_sources']['capture']['sha256'] == original.CAPTURE_SHA and
         bindings['producer_sources']['observer']['sha256'] == original.CPP_SHA, 'fixed original raw producers')
    for row in bindings['producer_sources'].values():
        checked(row)
    modules = original.original_modules(); c, napi, ui, native = modules
    entries = original.ledger(bindings['bridge_calls'],bindings['hdc'],bindings['target'])
    original.helper_identity(entries,bindings['hdc'],bindings['target'],c,native,admitted)
    before = original.snapshot(bindings['before'],entries,bindings['hdc'],bindings['target'],modules)
    after = original.snapshot(bindings['after'],entries,bindings['hdc'],bindings['target'],modules)
    need(type(bindings['generation_captures']) is list and len(bindings['generation_captures']) == 2,
         'post-reset generation before/after raw required')
    generation = [original.snapshot(row,entries,bindings['hdc'],bindings['target'],modules)
                  for row in bindings['generation_captures']]
    need([row['report']['label'] for row in generation] == ['datashare-cycle-before','datashare-cycle-after'],
         'fixed passive generation source labels')
    frames = generation+[before,after]
    need(after['process'] is not None and all(row['report']['boot_id'] == after['report']['boot_id'] for row in frames) and
         all(max(frames[i]['indices']) < min(frames[i+1]['indices']) for i in range(len(frames)-1)),
         'post-reset generation and case must retain same boot and actual authority order')
    for frame in frames:
        if frame['process'] is not None:
            need(frame['process'] == after['process'] and frame['loaded'] == after['loaded'] and
                 frame['namespace'] == after['namespace'], 'actual provider generation/image/namespace changed')
    caller = bindings['caller']; role = caller['role']; run = caller['run']
    need(role in ROLES, 'unknown caller role')
    bundle = c.ROLES[role][0]
    need(role in ROLES and set(caller) == {'role','run','owner_run','number','case_id','actual_context','journal',
         'token_before','token_after','bms_fields','bms_call','query_call'}, 'exact real caller binding')
    need(before['report']['label'] == role+'-before' and after['report']['label'] == role+'-after', 'actual case labels differ')
    argv = [bindings['hdc'],'-t',bindings['target'],'shell','aa','start','-b',bundle,'-a','EntryAbility',
            '--ps','run',run,'--ps','phase','corpus580','--ps','number',caller['number'],
            '--ps','ownerRun',caller['owner_run'],'--ps','caseId',caller['case_id'],'--ps','role',role]
    starts = [index for index,row in entries.items() if row['argv'] == argv]
    need(len(starts) == 1 and max(before['indices']) < starts[0] < min(after['indices']), 'one fixed actual case start/window')
    journal = checked(caller['journal'],1048576).read_bytes()
    public = review(journal,role=role,run=run,owner=caller['owner_run'],case_id=caller['case_id'],
                    number=caller['number'],actual_context=caller['actual_context'],seeds=bindings['seeds'])
    journal_rows = rows(journal,run=run,owner=caller['owner_run'],case_id=caller['case_id'])
    pid = caller_pid(after['raw'],journal_rows,core)
    bms_raw = original.plain_call(caller['bms_call'],[bindings['hdc'],'-t',bindings['target'],'shell','bm','dump','-n',bundle],entries)
    bms = c.bms_fields(bms_raw,bundle,caller['bms_fields'])
    access_raw = original.plain_call(caller['query_call'],[bindings['hdc'],'-t',bindings['target'],'shell',
                 original.TOKEN_QUERY,run,'identity',bundle,str(bms['token'])],entries)
    access = c.query_access(access_raw,role,run,'identity',after['report']['boot_id'],bms)
    first = c.token_join(checked(caller['token_before'],1048576).read_bytes(),role,run,'napi-before',bms,access)
    last = c.token_join(checked(caller['token_after'],1048576).read_bytes(),role,run,'napi-after',bms,access)
    need(first == last, 'actual new-case tokens differ')
    observed = original.replay_caller_generation(before,after,role,caller['bms_fields'],c)
    need(observed['process']['pid'] == pid and observed['process']['uid'] == first['uid'] and observed['bms'] == bms,
         'actual caller log PID/UID/token/BMS/kernel birth differs')
    images = image_bytes(bindings,after,admitted=admitted,original=original)
    start = before['clocks'][-1]['monotonic_after_ns']; end = after['clocks'][0]['monotonic_before_ns']
    decoded = [core.structured_events(frame['raw']) if frame['process'] is not None and
               b'NUMBER_NATIVE495' in frame['raw'] else [] for frame in frames]
    events = core.merge_snapshots496(decoded,after['process']['pid'])
    samples = [sample for frame in frames for sample in frame['clocks']]
    selected = next(row for row in cases() if row['id'] == caller['case_id'])
    actual_caller = dict(pid=pid,uid=first['uid'],token=first['token'],start_ticks=observed['process']['start_ticks'])
    proof = core.chain(events,process=after['process'],samples=samples,window=(start,end),
                       caller=actual_caller,routes=() if role == 'ordinary' else (selected['route'],))
    if role == 'ordinary':
        need(not any(e.kind == 'native' and e.value['event'] == 'query-enter' and
                     (e.value['caller_pid'],e.value['caller_uid'],e.value['caller_token']) == (pid,first['uid'],first['token']) and
                     start <= e.value['mono_ns'] <= end for e in events), 'ordinary caller unexpectedly entered provider')
    proof.update(schema='number580-case-full-replay/v1',public_api_review=public,image_emitters=images,
                 case_id=caller['case_id'],role=role,native_raw_checked=True,whole_aggregate_closed=False,
                 source_and_image_seed_and_final_owner_still_required=True)
    return proof


def review_account_case(ref,*,report,expected_user,protocol,original,admitted,expected_empty):
    case=decode(checked(ref).read_bytes());c,napi,ui,native=original.original_modules();core=original.core
    need(case['schema']=='number580-account-case/v1' and case['user']==expected_user and
         case['boot_id']==report['boot_id'] and case['owner_run']==report['owner_run'] and case['number']==report['number'] and
         case['case_id']==('account-foreign-read' if expected_empty else 'account-restored-read'), 'actual fixed per-user case')
    entries=original.ledger(report['bridge_calls'],report['hdc'],report['target'])
    local_entries=original.ledger(case['calls'],report['hdc'],report['target'])
    need(all(entries.get(k)==v for k,v in local_entries.items()),'account case raw remains a subset of same original Owner ledger')
    def call(ref,argv):return original.plain_call(ref,[report['hdc'],'-t',report['target'],*argv],entries)
    bundle=c.ROLES['system-granted'][0]
    bms=c.bms_fields(call(case['bms_before'],['shell','bm','dump','-n',bundle,'-u',str(expected_user)]),bundle,case['bms_fields'])
    need(bms==c.bms_fields(call(case['bms_after'],['shell','bm','dump','-n',bundle,'-u',str(expected_user)]),bundle,case['bms_fields']) and
         bms['uid']//200000==expected_user and bms['systemApp'] is True,'actual foreign/restored BMS UID/token/user')
    need(call(case['installed_hap'],['shell','sha256sum',bms['installedHapPath']]).decode().split()==
         [report['number_role']['signed_hap']['sha256'],bms['installedHapPath']], 'actual installed same signed role')
    need(len(case['pulls'])==2 and all(len(series)==3 for series in case['pulls']),'two complete actual account journal/token pulls')
    paths=[];blobs=[];stats=[]
    for index,(first,last) in enumerate(zip(*case['pulls'])):
        need(first['remote']==last['remote'] and first['file']['sha256']==last['file']['sha256'] and
             checked(first['file']).read_bytes()==checked(last['file']).read_bytes(),'account raw changed between pulls')
        remote=first['remote'];paths.append(remote);blobs.append(checked(first['file']).read_bytes())
        for item in (first,last):
            received=decode(checked(item['receive']).read_bytes())
            call(item['receive'],['file','recv',remote,item['file']['path']])
            actual=c.file_stat(call(item['stat_call'],['shell',c.stat_script(remote)]),remote,bms['uid'])
            need(actual['sha256']==item['file']['sha256'] and actual['bytes']==item['file']['bytes'],'actual private file inode/hash custody')
        stats.append(actual)
    need(tuple(paths)==discovered(call(case['find'],['shell',find_script(case['run'])]),case['run']), 'actual complete fresh files')
    public=review(blobs[0],role='system-granted',run=case['run'],owner=case['owner_run'],case_id=case['case_id'],
                  number=case['number'],actual_context=case['context'],seeds=report['seeds'])
    journal_rows=rows(blobs[0],run=case['run'],owner=case['owner_run'],case_id=case['case_id'])
    logs=call(case['hilog'],['shell','hilog','-x']);pid=caller_pid(logs,journal_rows,core)
    process=c.process_identity(str(pid),call(case['process']['status'],['shell','cat','/proc/'+str(pid)+'/status']),
        call(case['process']['cmdline'],['shell','cat','/proc/'+str(pid)+'/cmdline']),
        call(case['process']['stat'],['shell','cat','/proc/'+str(pid)+'/stat']),bundle,bms['uid'])
    for index,row in enumerate(case['mapping']):
        path='/proc/'+str(pid)+'/root'+case['context']+'/'+Path(paths[index]).name
        need(row['path']==path and c.file_stat(call(row['call'],['shell',c.stat_script(path,process_root=True)]),path,bms['uid'])==stats[index],
             'actual per-user process-root private file mapping')
    tokens=[decode(v) for v in blobs[1:]]
    for phase,token in zip(('napi-before','napi-after'),tokens):
        access=dict(bundle=bundle,token=token['accessTokenId'],getResult=token['getResult'],setResult=token['setResult'])
        c.token_join(json.dumps(token).encode(),'system-granted',case['run'],phase,bms,access)
    need(tokens[0]['uid']==tokens[1]['uid']==bms['uid'] and tokens[0]['accessTokenId']==tokens[1]['accessTokenId']==bms['token'],
         'actual self Token before/after independently joins per-user BMS')
    before=original.snapshot(case['before'],entries,report['hdc'],report['target'],(c,napi,ui,native))
    after=original.snapshot(case['after'],entries,report['hdc'],report['target'],(c,napi,ui,native))
    need(before['report']['boot_id']==after['report']['boot_id']==report['boot_id'] and after['process'] is not None and
         max(before['indices'])<min(after['indices']), 'actual account provider window/order/boot')
    argv=['shell','aa','start','-b',bundle,'-a','EntryAbility','-m','entry','-u',str(expected_user),
          '--ps','run',case['run'],'--ps','phase','corpus580','--ps','number',case['number'],'--ps','ownerRun',case['owner_run'],
          '--ps','caseId',case['case_id'],'--ps','role','system-granted']
    call(case['start'],argv)
    start=decode(checked(case['start']).read_bytes())
    need(max(before['indices'])<start['held_index']<min(after['indices']),'actual per-user API start is in native window')
    for key in ('boot_before','boot_after'):
        need(call(case[key],['shell','cat','/proc/sys/kernel/random/boot_id']).decode().strip()==report['boot_id'],'actual account kernel boot raw')
    need(type(report['generation_captures']) is list and len(report['generation_captures'])==2,
         'real post-reset corpus generation calibration pair')
    generation=[original.snapshot(v,entries,report['hdc'],report['target'],(c,napi,ui,native)) for v in report['generation_captures']]
    need([v['report']['label'] for v in generation]==['datashare-cycle-before','datashare-cycle-after'],
         'original passive post-reset generation labels')
    frames=generation+[before,after]
    need(all(v['report']['boot_id']==report['boot_id'] for v in frames) and
         all(max(frames[i]['indices'])<min(frames[i+1]['indices']) for i in range(len(frames)-1)),
         'same actual kernel boot and original held calibration/account order')
    # The clock probe is an independent original helper. Its earlier samples
    # remain real calibration for a new provider only in this proven namespace;
    # a previous provider's lifecycle/raw is never borrowed for the new PID.
    samples=[sample for frame in frames for sample in frame['clocks']]
    need(all((v['time_ns_dev'],v['time_ns_inode'])==after['namespace'] for v in samples),
         'all actual early/late helper clock samples share target time namespace')
    target_frames=[]
    for frame in frames:
        if frame['process'] is None:continue
        if frame['process']['pid']!=after['process']['pid']:continue
        need(frame['process']==after['process'] and frame['loaded']==after['loaded'] and frame['namespace']==after['namespace'],
             'target PID birth/loaded bytes/namespace changed, no stale generation calibration')
        target_frames.append(frame)
    events=core.merge_snapshots496([core.structured_events(v['raw']) for v in target_frames],after['process']['pid'])
    chain=core.chain(events,process=after['process'],samples=samples,
        window=(before['clocks'][-1]['monotonic_after_ns'],after['clocks'][0]['monotonic_before_ns']),
        caller=dict(pid=pid,uid=bms['uid'],token=bms['token'],start_ticks=process['start_ticks']),routes=(2,))
    image_bindings=dict(report['package_inputs'],emitter_elfs=report['package_inputs']['emitter_elfs'])
    image_bytes(image_bindings,after,admitted=admitted,original=original)
    return dict(user=expected_user,case=ref,public=public,native=chain,bms=bms,process=process,
                private_files=paths,raw_custody_checked=True,generation_captures=report['generation_captures'],
                clock_only_earlier_frames=[v['report']['label'] for v in generation if v['process'] is None or v['process']['pid']!=after['process']['pid']],
                independent_token395_user100_not_reused=expected_user!=100)


def image_bytes(bindings, after, *, admitted, original):
    core=original.core; checked=original.checked
    selected=admitted.profile['product'];target=admitted.product.target_spec(selected)
    import struct
    loader=bindings.get('loader_image_report')
    if loader is None: raise core.Pending('independent same-new-image MainThread loader ELF proof missing')
    number=core.decode_json(checked(bindings['number_image_report']).read_bytes())
    loader_report=core.decode_json(checked(loader).read_bytes())
    loader=loader_report.get('loader_library')
    image=bindings['system_image'];checked(image,maximum=16*1024**3)
    core.need(number.get('status')=='pass' and number.get('failures')==[] and
        number.get('system_image_sha256')==image['sha256'],'actual Number image/hash proof required')
    # The parent owns the finite offline loader export. This independent nullable
    # interface does not guess a hash from historical bytes or generated Ninja.
    core.need(loader_report.get('status')=='pass' and loader_report.get('failures')==[] and
        type(loader) is dict and loader.get('scope')=='on-disk loader ELF only; loaded process and callback remain unverified' and
        loader.get('system_image_sha256')==loader_report.get('system_image_sha256')==image['sha256'] and
        loader.get('basename')==core.SONAMES[0] and loader.get('loaded_process_verified') is False and
        loader.get('native_callback_proven') is False and
        (loader.get('elf_class'),loader.get('elf_machine'),loader.get('elf_type'))==(target['class']//32,target['machine'],3) and
        type(loader.get('image_inode')) is int and loader['image_inode']>0 and
        type(loader.get('image_path')) is str,
        'actual independent loader extraction/image binding required')
    aliases=loader.get('image_path_aliases')
    directory='/lib64/' if target['class']==64 else '/lib/'
    candidates=[directory+core.SONAMES[0],'/system'+directory+core.SONAMES[0],
        directory+'platformsdk/'+core.SONAMES[0],'/system'+directory+'platformsdk/'+core.SONAMES[0]]
    core.need(type(aliases) is list and aliases and
        aliases == [path for path in candidates if path in aliases] and
        loader['image_path']==aliases[0],
        'actual loader aliases must retain the finite same-inode extraction order')
    actual={}
    core.need(type(bindings['emitter_elfs']) is dict and set(bindings['emitter_elfs'])==set(core.SONAMES),
        'exact two real emitter ELF descriptors required')
    for soname,descriptor in bindings['emitter_elfs'].items():
        path=checked(descriptor,maximum=256*1024*1024);raw=path.read_bytes()
        core.need(len(raw)>=(64 if target['class']==64 else 52) and raw[:7]==b'\x7fELF'+bytes([target['class']//32,1,1]) and struct.unpack_from('<HH',raw,16)==(3,target['machine']),
            'actual AArch64 dynamic ELF required')
        prefix=b'NUMBER_NATIVE495_LOAD v=1' if soname==core.SONAMES[0] else b'NUMBER_NATIVE495 v=1'
        core.need(prefix in raw,'new diagnostic producer missing from actual image ELF')
        image_sha=loader.get('sha256') if soname==core.SONAMES[0] else number.get('native_libraries',{}).get(soname,{}).get('sha256')
        if soname==core.SONAMES[0]:
            core.need(loader.get('file')==str(path) and loader.get('bytes')==descriptor['bytes'],
                'actual loader export file path/size differs from independent image proof')
        core.need(descriptor['sha256']==image_sha==after['loaded'][soname]['file']['sha256'],
            'new image/dumped ELF/actual mapped file full-byte join differs')
        actual[soname]=descriptor
    core.need(number.get('bundled_native_provider',{}).get('sha256')==actual[core.SONAMES[1]]['sha256'],
        'Number installed system and HAP native implementation differ')
    return actual



# Original496 review body retained; only context aliases and target-aware full image function differ.
def review_original496(bindings, *, admitted, original):
    core=original.core; checked=original.checked; original_modules=original.original_modules
    ledger=original.ledger; helper_identity=original.helper_identity; snapshot=original.snapshot
    plain_call=original.plain_call; replay_caller_generation=original.replay_caller_generation
    CPP_SHA=original.CPP_SHA; CAPTURE_SHA=original.CAPTURE_SHA; HERE=original.HERE; TOKEN_QUERY=original.TOKEN_QUERY
    """Consume actual raw within original admission; return a narrow chain fact.

    No Boolean or JSON status can create `admitted`: parent must replay original
    observer_admission396.admit with the actual build/recheck/profile/ELF inputs.
    This function is not an Owner or an aggregate/full-suite acceptance entry.
    """
    required={'schema','hdc','target','source_commit','archive_sha256','before','after','generation_captures','bridge_calls','caller',
        'number_image_report','loader_image_report','system_image','emitter_elfs','build_inputs','producer_sources'}
    core.need(type(bindings) is dict and set(bindings)==required and bindings['schema']=='number-native-consumer496/v1',
        'fixed source-only consumer bindings schema required')
    missing=[k for k in required-{'schema'} if bindings[k] is None]
    if missing: raise core.Pending('actual inputs pending: '+','.join(sorted(missing)))
    if admitted is None: raise core.Pending('original actual compile/recheck/ELF/profile admission must be replayed, not summarized')
    core.need(re.fullmatch('[0-9a-f]{40}',bindings['source_commit'] or '') and
        re.fullmatch('[0-9a-f]{64}',bindings['archive_sha256'] or ''),'actual new source/archive identity required')
    evidence=admitted.evidence
    core.need(evidence['actual_source']['sha256']==CPP_SHA and checked(evidence['actual_source']).read_bytes()==
        (HERE/'candidate/number_token_query395.cpp').read_bytes(),'actual admitted clock/Token observer source differs')
    checked(evidence['actual_ELF'],maximum=128*1024*1024)
    core.need(admitted.profile['archive']['sha256']==bindings['archive_sha256'] and
        admitted.profile['system_image']['sha256']==bindings['system_image']['sha256'],'original admission belongs to another image')
    sources=bindings['producer_sources']
    core.need(type(sources) is dict and set(sources)=={'capture','observer'} and
        sources['capture']['sha256']==CAPTURE_SHA and sources['observer']['sha256']==CPP_SHA,'fixed reviewed producer source required')
    for row in sources.values():checked(row)
    inputs=core.decode_json(checked(bindings['build_inputs'],maximum=4*1024*1024).read_bytes())
    core.need(inputs.get('source_git_revision')==bindings['source_commit'],'actual new package source commit differs')
    modules=original_modules();c,napi,ui,native=modules
    core.need(type(bindings['generation_captures']) is list and len(bindings['generation_captures'])==2,
        'exact original DataShare-cycle generation before/after descriptors required')
    entries=ledger(bindings['bridge_calls'],bindings['hdc'],bindings['target'])
    helper_identity(entries,bindings['hdc'],bindings['target'],c,native,admitted)
    before=snapshot(bindings['before'],entries,bindings['hdc'],bindings['target'],modules)
    after=snapshot(bindings['after'],entries,bindings['hdc'],bindings['target'],modules)
    generation=[snapshot(row,entries,bindings['hdc'],bindings['target'],modules) for row in bindings['generation_captures']]
    core.need([row['report']['label'] for row in generation]==['datashare-cycle-before','datashare-cycle-after'],
        'fixed original initial generation capture labels required')
    frames=generation+[before,after]
    core.need(all(row['report']['boot_id']==after['report']['boot_id'] for row in frames) and
        all(max(frames[i]['indices'])<min(frames[i+1]['indices']) for i in range(len(frames)-1)),
        'generation/public snapshots must retain same-boot actual Authority order')
    for frame in frames:
        if frame['process'] is not None:
            core.need(frame['process']==after['process'] and frame['loaded']==after['loaded'] and frame['namespace']==after['namespace'],
                'actual provider generation/emitter bytes/namespace changed across generation/public observations')
    core.need(after['process'] is not None and before['report']['boot_id']==after['report']['boot_id'],
        'provider absence/cross-boot is not native callback proof')
    core.need(max(before['indices'])<min(after['indices']),'actual before/after capture authority order differs')
    if before['process'] is not None:
        core.need(before['process']==after['process'] and before['loaded']==after['loaded'] and before['namespace']==after['namespace'],
            'provider generation/emitter bytes/namespace changed across public request')
    caller=bindings['caller']
    caller_keys={'role','run','owner_run','number','actual_context','journal','token_before','token_after','bms_fields','bms_call','query_call'}
    core.need(type(caller) is dict and set(caller)==caller_keys and caller['role'] in ('system-granted','system-readonly'),
        'one real system role public NAPI phase required; ordinary denial remains separate')
    role=caller['role'];run=caller['run'];bundle=c.ROLES[role][0];boot=after['report']['boot_id']
    core.need(before['report']['label']==role+'-before' and after['report']['label']==role+'-after','actual same role public window labels required')
    start_argv=[bindings['hdc'],'-t',bindings['target'],'shell','aa','start','-b',bundle,'-a','EntryAbility',
        '--ps','run',run,'--ps','phase','napi-read','--ps','number',caller['number'],'--ps','ownerRun',caller['owner_run']]
    starts=[index for index,row in entries.items() if row['argv']==start_argv and row['exit_code']==0]
    core.need(len(starts)==1 and max(before['indices'])<starts[0]<min(after['indices']),
        'one actual nonce-bound original public caller start must lie between retained capture commands')
    journal=checked(caller['journal'],maximum=1024*1024).read_bytes()
    public=napi.review(journal,role=role,run=run,owner=caller['owner_run'],number=caller['number'],actual_context=caller['actual_context'])
    journal_rows=napi.rows(journal,run,caller['owner_run'],caller['number'])
    caller_pid=core.caller_pid(after['raw'],journal_rows)
    bms_raw=plain_call(caller['bms_call'],[bindings['hdc'],'-t',bindings['target'],'shell','bm','dump','-n',bundle],entries)
    bms=c.bms_fields(bms_raw,bundle,caller['bms_fields'])
    access_raw=plain_call(caller['query_call'],[bindings['hdc'],'-t',bindings['target'],'shell',TOKEN_QUERY,run,'identity',bundle,str(bms['token'])],entries)
    access=c.query_access(access_raw,role,run,'identity',boot,bms)
    first=c.token_join(checked(caller['token_before'],maximum=1024*1024).read_bytes(),role,run,'napi-before',bms,access)
    last=c.token_join(checked(caller['token_after'],maximum=1024*1024).read_bytes(),role,run,'napi-after',bms,access)
    core.need(first==last,'actual caller Token before/after differs')
    observed=replay_caller_generation(before,after,role,caller['bms_fields'],c)
    core.need(observed['process']['pid']==caller_pid and observed['process']['uid']==first['uid'] and observed['bms']==bms,
        'caller raw header PID/independent Token/BMS/process identity differs')
    images=image_bytes(bindings,after,admitted=admitted,original=original)
    start=before['clocks'][-1]['monotonic_after_ns'];end=after['clocks'][0]['monotonic_before_ns']
    decoded=[core.structured_events(frame['raw']) if frame['process'] is not None and b'NUMBER_NATIVE495' in frame['raw'] else [] for frame in frames]
    events=core.merge_snapshots496(decoded,after['process']['pid'])
    samples=[sample for frame in frames for sample in frame['clocks']]
    proof=core.chain(events,process=after['process'],samples=samples,window=(start,end),
        caller={'pid':caller_pid,'uid':first['uid'],'token':first['token'],
            'start_ticks':observed['process']['start_ticks']})
    proof.update(scope='actual raw native-chain replay within original Number admitted context ONLY',
        image_emitters=images,public_api_review=public,native_callback_chain_checked=True,
        original411_verdict_changed=False,first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)
    return proof


import struct


# Exact original396 admission helpers with fixed normal mount/target-source adaptation.
def artifact_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def admission_relocated(path, origin, directory):
    p = PurePosixPath(path)
    need(p.is_absolute() and p.as_posix() == path and '..' not in p.parts,
         'canonical virtual artifact path required')
    try: relative = p.relative_to(origin)
    except ValueError as error: raise ValueError('artifact outside exact fixed mount') from error
    need(relative.parts, 'actual file below fixed mount required')
    return admission_regular(Path(directory) / Path(*relative.parts))


def admission_commands(report, origin, directory):
    need(type(report.get('commands')) is list and report['commands'], 'actual commands and raw logs required')
    result = {}
    for row in report['commands']:
        need(type(row) is dict and type(row.get('exit_code')) is int and row['exit_code'] == 0 and
             not row.get('timed_out') and type(row.get('argv')) is list and row['argv'] and
             all(type(x) is str for x in row['argv']) and type(row.get('label')) is str,
             'complete successful actual command record required')
        need(row['label'] not in result, 'duplicate actual command label')
        path = admission_relocated(row['log'], origin, directory)
        need(artifact_digest(path) == row['sha256'], 'actual command log changed')
        result[row['label']] = row, path
    return result


def admission_image_witness(build, command_table, directory, profile, product, normal):
    VIRTUAL_BUILD=PurePosixPath('/evidence/helpers');VIRTUAL_KIT=PurePosixPath('/work')
    """Require the original Builder's actual archive/image re-extractions too."""
    witness=build.get('installed_runtime_image_proof')
    need(type(witness) is dict and set(witness)=={'archive_members','tools','dsos'}, 'actual Builder archive/image witness absent')
    expected={name:dict(archive_member=profile[name+'_image']['archive_member'],
        sha256=profile[name+'_image']['sha256'],bytes=profile[name+'_image']['bytes'])
        for name in ('system','vendor') if name+'_image' in profile}
    need(witness['archive_members']==expected and set(witness['dsos'])==set(profile['dsos']),
         'actual original archive/image inventory differs from same-archive profile')
    tools=witness['tools'];need(set(tools)=={'debugfs','extractor','selector'}, 'actual image extraction tools absent')
    for key,name in (('extractor','ext_image_entries.py'),('selector','verify_alsa_config_image.py')):
        local=Path(product.__file__).parents[2]/'scripts'/name; row=tools[key]
        need(row==dict(path=str(VIRTUAL_KIT/'scripts'/name),sha256=artifact_digest(local),bytes=local.stat().st_size) and
             build['inputs'].get(row['path'])==row, 'actual original image extractor source differs')
    need(build['inputs'].get(tools['debugfs']['path'])==tools['debugfs'], 'actual image tool input hash absent')
    for soname,entry in profile['dsos'].items():
        row=witness['dsos'][soname]; path=admission_relocated(row['path'],VIRTUAL_BUILD,directory)
        staged=entry['staged']; partition=staged['path'].removeprefix('/ohos/out/'+profile['product']+'/packages/phone/').split('/',1)[0]
        need(row.get('partition')==partition and row.get('image_path')==entry['image_member'] and
             row.get('image_path_aliases')==[entry['image_member']] and type(row.get('image_inode')) is int and
             row['image_inode']>0 and artifact_digest(path)==row.get('sha256')==staged['sha256'] and
             path.stat().st_size==row.get('bytes')==staged['bytes'] and product.elf_soname(path,product=profile['product'])==soname,
             'actual original image dump inode/aliases/full bytes/SONAME differ')
        key='installed-runtime-stat-'+soname
        need(key in command_table and type(row.get('stat_command')) is int and
             build['commands'][row['stat_command']]==command_table[key][0], 'actual original image stat command binding absent')
        command,log=command_table[key]
        need(command['argv']==[tools['debugfs']['path'],'-R','stat '+entry['image_member'],profile[partition+'_image']['path']] and
             re.search(r'(?m)^Inode: '+str(row['image_inode'])+r'\s+Type: regular\s',log.read_text()),
             'actual original image raw stat inode differs')


def admission_regular(path):
    p=Path(path)
    info=p.stat()
    need(p.is_absolute() and p.resolve()==p and all(not v.is_symlink() for v in (p,*p.parents)) and stat.S_ISREG(info.st_mode) and info.st_nlink==1,
         'one canonical actual artifact inode')
    return p

def admit_normal_observer(proof, *, profile_descriptor, archive_sha256, product, context, elf_reader, normal_source):
    from types import SimpleNamespace
    NAME='number_token_query395';FIXTURE='batch_apps/number_runtime/number_token_query395.cpp'
    OBSERVER_SHA='b56d895cddd5dcc375b7b871e871b199540b43c0a495d7ec8b31ff1106a4e5ed'
    VIRTUAL_KIT=PurePosixPath('/work');VIRTUAL_BUILD=PurePosixPath('/evidence/helpers')
    VIRTUAL_RECHECK=VIRTUAL_BUILD;VIRTUAL_DSOS=PurePosixPath('/evidence/product-dsos')
    BUILDER_SHA=artifact_digest(Path(product.__file__))
    normal=decode(checked(normal_source).read_bytes());snapshot=decode(checked(normal['canonical_snapshot'],maximum=16*1024*1024).read_bytes())
    need(snapshot['source_commit']==normal['source_commit'],'actual complete normal snapshot/source commit')
    for module,relative in ((product,'ci/capability-audit/batch_system_build_runtime_helpers.py'),
                            (context,'ci/capability-audit/native579_artifact_context.py'),
                            (elf_reader,'scripts/verify_runtime_elf_contract.py')):
        rows=[r for r in snapshot['files'] if r['path']==relative]
        need(len(rows)==1 and artifact_digest(Path(module.__file__))==rows[0]['sha256'] and
             Path(module.__file__).stat().st_size==rows[0]['bytes'],'actual fixed normal admission code differs from snapshot')
    need(type(proof) is dict and set(proof) == {'build', 'recheck', 'dsos'},
         'actual build + independent recheck + DSO export descriptors required, never readiness bool')
    build_path, recheck_path, dsos_path = (checked(proof[k]) for k in ('build', 'recheck', 'dsos'))
    need(build_path.name == recheck_path.name == 'build.json' and dsos_path.name == 'manifest.json' and
         build_path != recheck_path and build_path.parent != recheck_path.parent,
         'separate actual original/recheck directories required')
    build, review, exports = (decode(p.read_bytes()) for p in (build_path, recheck_path, dsos_path))
    profile_path = checked(profile_descriptor); profile = decode(profile_path.read_bytes())
    product.validate_installed_profile(profile, archive_sha256=archive_sha256)
    selected=profile['product'];target=product.target_spec(selected)
    need(profile['device'] == 'phone' and profile['source_root'] == '/ohos', 'actual new phone source/profile required')
    for report in (build, review):
        need(report.get('status') == 'pass_compile_link_ONLY' and report.get('plan_only') is False and
             report.get('product') == selected and report.get('source_root') == '/ohos' and
             report.get('build_directory') == '/ohos/out/'+selected and report.get('changed_inputs') == [] and
             report.get('builder_sha256') == BUILDER_SHA and set(report.get('helpers', {})) == {NAME} and
             report.get('requirements_closed') == 0 and report.get('first_artifact_behavior_gate_passed') is False,
             'actual fixed Number build/recheck/source scope differs')
    old, new = build['helpers'][NAME], review['helpers'][NAME]
    need(old.get('fixture') == FIXTURE and old.get('status') == new.get('status') == 'pass_compile_link_ONLY' and
         old.get('runtime_validated') is False and new.get('runtime_validated') is False and
         old.get('CFI_preserved') is True and new.get('CFI_preserved') is True,
         'actual completed original and rechecked CFI diagnostic required')
    source = old.get('source', {})
    need(source.get('path') == str(VIRTUAL_KIT / 'ci/capability-audit/fixtures' / FIXTURE) and
         source.get('sha256') == OBSERVER_SHA and old.get('private_source_sha256') == OBSERVER_SHA and
         source == build.get('inputs', {}).get(source.get('path')) and
         product._runtime_profile(old, archive_sha256) == profile and
         old['installed_runtime_profile'] == build['installed_runtime_profile'] == new['installed_runtime_profile'],
         'actual fixed observer source/profile binding differs')
    expected_profile = dict(path='/runtime-profile/runtime-profile.json', sha256=profile_descriptor['sha256'], bytes=profile_descriptor['bytes'])
    need(build['installed_runtime_profile']['source'] == expected_profile and
         review.get('verify_existing') is True and review.get('original_report') == dict(
             path='/number-previous/helpers/build.json', sha256=proof['build']['sha256'],
             status=build['status'], builder_sha256=BUILDER_SHA, rewritten=False),
         'independent original report/profile recheck differs')
    actual_commands = admission_commands(build, VIRTUAL_BUILD, build_path.parent)
    checked_commands = admission_commands(review, VIRTUAL_RECHECK, recheck_path.parent)
    admission_image_witness(build,actual_commands,build_path.parent,profile,product,normal)
    originals = review.get('original_commands')
    need(type(originals) is list and len(originals) == len(actual_commands), 'independent replay must bind every original command')
    for row in originals:
        original = dict(row); verified = original.pop('verified_log', None)
        need(original['label'] in actual_commands and original == actual_commands[original['label']][0] and
             type(verified) is dict and verified.get('sha256') == original['sha256'], 'original command replay mismatch')
    need(len({row['label'] for row in originals})==len(originals),'duplicate original command replay')
    compile_cmd, link_cmd = old['compile_command'], old['link_command']
    def artifact(row):
        path=row['path']
        if path.startswith('/evidence/helpers/'):
            local=admission_relocated(path,VIRTUAL_BUILD,build_path.parent)
        elif path.startswith('/number-previous/helpers/'):
            local=admission_relocated(path,PurePosixPath('/number-previous/helpers'),build_path.parent)
        else:raise ValueError('artifact outside exact original normal build prefix')
        need(artifact_digest(local)==row['sha256'] and ('bytes' not in row or local.stat().st_size==row['bytes']),'actual retained artifact changed')
        return local
    need(product.effective_cfi(link_cmd) and any(w == '-flto' or w.startswith('-flto=') for w in link_cmd), 'actual link CFI/LTO absent')
    for label, argv in ((NAME+'-compile', compile_cmd), (NAME+'-link', link_cmd)):
        need(label in actual_commands and actual_commands[label][0]['argv'] == argv, 'actual compile/link raw command differs')
    origin = VIRTUAL_BUILD / NAME
    source_path = admission_relocated(str(origin / 'number_token_query395.cpp'), VIRTUAL_BUILD, build_path.parent)
    guard = admission_relocated(str(origin / 'actual_system_abi.h'), VIRTUAL_BUILD, build_path.parent)
    obj = admission_relocated(str(origin / (NAME+'.o')), VIRTUAL_BUILD, build_path.parent)
    binary = admission_relocated(str(origin / NAME), VIRTUAL_BUILD, build_path.parent)
    deps = admission_relocated(str(origin / 'headers.d'), VIRTUAL_BUILD, build_path.parent)
    need(artifact_digest(source_path) == OBSERVER_SHA and source_path.stat().st_size == source['bytes'] and
         guard.read_text() == product.ABI_GUARD and artifact_digest(guard) == old['abi_guard_sha256'] and obj.stat().st_size > 0 and
         artifact_digest(deps) == old['depfile_sha256'], 'actual source/guard/object/depfile artifact differs')
    object_bytes=obj.read_bytes()
    object_kind=(object_bytes.startswith((b'BC\xc0\xde',b'\xde\xc0\x17\x0b')) or
                 len(object_bytes)>=20 and object_bytes[:7]==b'\x7fELF'+bytes([target['class']//32,1,1]) and
                 struct.unpack_from('<HH',object_bytes,16)==(1,target['machine']))
    need(object_kind,'actual LTO bitcode or AArch64 relocatable object artifact required')
    need(product.argument(compile_cmd, '-c') == str(origin/'number_token_query395.cpp') and
         product.argument(compile_cmd, '-o') == str(origin/(NAME+'.o')) and
         product.argument(compile_cmd, '-include') == str(origin/'actual_system_abi.h') and
         product.argument(compile_cmd, '-MF') == str(origin/'headers.d') and
         product.argument(link_cmd, '-o') == str(origin/NAME) and str(origin/(NAME+'.o')) in link_cmd,
         'actual compile/link artifact argv differs')
    expected_compiler='/ohos/prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++'
    need(compile_cmd[0] == link_cmd[0] == expected_compiler, 'actual product compiler only; no SDK compiler')
    dependencies = old.get('actual_compiler_dependencies', [])
    need(dependencies and new.get('actual_compiler_dependencies') == dependencies and
         review.get('original_input_count') == len(build.get('inputs', {})),
         'actual independently rechecked full depfile/header inventory differs')
    for header in ('accesstoken_kit.h', 'hap_token_info.h'):
        matches=[r for r in dependencies if r['path'] == '/ohos/base/security/access_token/interfaces/innerkits/accesstoken/include/'+header]
        need(len(matches)==1 and matches[0] == build['inputs'].get(matches[0]['path']), 'actual target AccessToken header dependency absent')
    artifacts = new.get('reused_artifacts', {})
    expected_artifacts = {'source':source_path, 'abi_guard':guard, 'object_new_hash_capture':obj, 'binary':binary, 'depfile':deps}
    need(set(artifacts) == set(expected_artifacts), 'actual rechecked source/object/ELF/depfile evidence absent')
    for name, actual in expected_artifacts.items():
        row=artifacts[name]
        need(artifact_digest(actual)==row.get('sha256') and actual.stat().st_size==row.get('bytes') and
             admission_relocated(row['path'],PurePosixPath('/number-previous/helpers'),build_path.parent)==actual,
             'independent rechecked artifact bytes differ: '+name)
    context.binding_context(build,old,binary,artifact)
    normal_link=build.get('normal_link_contract')
    elf = product.elf_header(binary, executable=True,product=selected,interpreter_path=None if normal_link is None else normal_link['interpreter'])
    need(elf == old.get('elf') == new.get('elf') and elf['sha256'] == old.get('binary_sha256') == new.get('binary_sha256'),
         'actual original/rechecked ELF bytes differ')
    symbols = elf_reader.read_elf(binary)
    all_symbols = symbols.defined | symbols.undefined
    need(symbols.machine == target['machine'] and '__cfi_check' in symbols.defined and any('St3__h' in s for s in all_symbols) and
         not any('St4__n1' in s for s in all_symbols), 'actual ELF cross-DSO CFI/system __h ABI absent or SDK __n1 present')
    needed = set(product.elf_needed(binary,product=selected))
    need('libaccesstoken_sdk.z.so' in needed and needed == set(old.get('DT_NEEDED', [])) == set(new.get('DT_NEEDED', [])),
         'actual ELF DT_NEEDED differs from original/recheck')
    for index, (table, helper) in enumerate(((actual_commands, old), (checked_commands, new))):
        key=NAME+'-actual-ELF-ABI'; need(key in table, 'actual ELF raw inspection absent')
        cmd, log=table[key]; text=log.read_text()
        need(cmd['argv'] == ['/ohos/prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-readelf','-h','-l','-d','--dyn-syms','--wide','--demangle',str(origin/NAME) if index == 0 else '/number-previous/helpers/'+NAME+'/'+NAME] and
             product.defined_symbol(text,'__cfi_check') and 'std::__h::' in text and 'std::__n1::' not in text and
             product.dynamic_needed(text)==needed,'actual raw ELF inspection differs from actual binary')
        for soname in needed: product.runtime_link_records(helper,soname)
    need(exports.get('scope') == 'fresh installed-runtime actual linker-opened DT_NEEDED full-byte export ONLY_NOT_guest' and
         exports.get('source_root') == '/ohos' and exports.get('build_receipt') == dict(
             path=str(VIRTUAL_BUILD/'build.json'),sha256=proof['build']['sha256'],bytes=proof['build']['bytes']) and
         exports.get('runtime_profile') == build['installed_runtime_profile'] and set(exports.get('files', {}))==needed,
         'actual full linker-opened DSO export differs')
    export_records={}
    for soname in needed:
        row=exports['files'][soname]; linked,=product.runtime_link_records(old,soname)
        path=admission_relocated(row['path'],VIRTUAL_DSOS,dsos_path.parent)
        need(path.name==soname and row.get('original')==linked and row.get('helpers')==[NAME] and
             artifact_digest(path)==row.get('sha256')==linked['sha256'] and path.stat().st_size==row.get('bytes')==linked['bytes'] and
             product.elf_soname(path,product=selected)==soname,'actual exported installed DSO full bytes/SONAME differ')
        export_records[soname]=admission_record(path)
        if soname=='libaccesstoken_sdk.z.so':
            key=NAME+'-linked-'+soname
            need(key in actual_commands and key in checked_commands,'actual AccessToken DSO ELF/CFI raw checks absent')
            for table in (actual_commands,checked_commands):
                need(product.defined_symbol(table[key][1].read_text(),'__cfi_check'),'actual AccessToken DSO raw CFI definition absent')
            actual_symbols=elf_reader.read_elf(path)
            need('__cfi_check' in actual_symbols.defined,'actual AccessToken DSO binary CFI definition absent')
    for descriptor in (*proof.values(),profile_descriptor): checked(descriptor)
    return SimpleNamespace(product=product,context=context,elf_reader=elf_reader,normal_source=normal_source,binary=binary,binary_record=admission_record(binary),helper=old,profile=profile,needed=tuple(sorted(needed)),
        evidence=dict(original_proof=proof,profile=profile_descriptor,actual_source=admission_record(source_path),
                      actual_ELF=admission_record(binary),actual_exported_DSOs=export_records,
                      scope='actual fixed compile/recheck/ELF/profile replay ONLY; no guest permission/provider claim'))


def admission_record(path):
    path=admission_regular(path)
    return dict(path=str(path),sha256=artifact_digest(path),bytes=path.stat().st_size)


def normal_modules(normal_source,*,source_commit):
    """Three literal modules selected by source code, whole snapshot checked first."""
    import importlib.util
    import sys
    root=Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
    normal=decode(checked(normal_source).read_bytes())
    need(normal['source_commit']==source_commit,'actual source context differs')
    snapshot=decode(checked(normal['canonical_snapshot'],maximum=16*1024*1024).read_bytes())
    need(snapshot['source_commit']==source_commit and snapshot['count']==len(snapshot['files']), 'complete actual canonical snapshot')
    result=[]
    for name,relative in (('batch_system_build_runtime_helpers','ci/capability-audit/batch_system_build_runtime_helpers.py'),
                          ('native579_artifact_context','ci/capability-audit/native579_artifact_context.py'),
                          ('verify_runtime_elf_contract','scripts/verify_runtime_elf_contract.py')):
        rows=[v for v in snapshot['files'] if v['path']==relative]
        need(len(rows)==1,'one canonical normal admission source')
        path=root/relative;row=dict(path=str(path),sha256=rows[0]['sha256'],bytes=rows[0]['bytes']);checked(row)
        if name in sys.modules:
            module=sys.modules[name]
            need(Path(module.__file__).resolve()==path and artifact_digest(path)==row['sha256'],'foreign cached normal admission module')
        else:
            definition=importlib.util.spec_from_file_location(name,path)
            module=importlib.util.module_from_spec(definition);sys.modules[name]=module;definition.loader.exec_module(module)
        checked(row);result.append(module)
    return tuple(result)


def seed_selection_script(pid):
    need(type(pid) is int and pid>0,'actual observed provider PID')
    lines=[]
    for name in ('numberlocation.dat','numberlocation.data'):
        path='/proc/'+str(pid)+'/root/data/storage/el2/base/files/'+name
        lines.append('test ! -e '+path+' && test ! -L '+path)
    return ' && '.join(lines)+" && printf 'NUMBER_SEED580 pid="+str(pid)+" update_dat=absent update_data=absent\\n'"


def seed_selection_output(pid):
    return ('NUMBER_SEED580 pid='+str(pid)+' update_dat=absent update_data=absent\n').encode()


def account_scanner(normal_source,*,source_commit):
    """Only the original canonical complete UID scanner; no DATA code path."""
    import importlib.util
    import sys
    root=Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
    relative='ci/capability-audit/batch_network_openvpn_runtime_collect.py'
    normal=decode(checked(normal_source).read_bytes())
    snapshot=decode(checked(normal['canonical_snapshot']).read_bytes())
    need(normal['source_commit']==snapshot['source_commit']==source_commit,'scanner current source context')
    rows=[v for v in snapshot['files'] if v['path']==relative]
    need(len(rows)==1,'exact canonical UID scanner source')
    path=root/relative;ref=dict(path=str(path),sha256=rows[0]['sha256'],bytes=rows[0]['bytes']);checked(ref)
    name='batch_network_openvpn_runtime_collect'
    if name in sys.modules:
        module=sys.modules[name];need(Path(module.__file__).resolve()==path,'foreign cached UID scanner')
    else:
        definition=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(definition);sys.modules[name]=module;definition.loader.exec_module(module)
    checked(ref)
    return module
