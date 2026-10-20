"""Pure actual-raw Number495 decoder/state join; no process or resource calls.

The source candidate has no real trace input. A successful chain object is not
an original411/47 verdict. Root must bind real raw, caller and loaded bytes first.
"""
from dataclasses import dataclass
import json
import re

U64 = (1 << 64) - 1
U32 = (1 << 32) - 1
I32 = (1 << 31) - 1
MAX_CLOCK_SPAN_NS = 100_000_000
NATIVE = ('event seq mono_ns pid tid instance connection request route result caller_pid caller_uid caller_token').split()
LOAD = ('event pid tid load mono_ns result path').split()
EVENTS = {'register-enter','register-result','creator-enter','create-result','creator-result',
          'connect-enter','connect-result','query-enter','query-result'}
SONAMES = ('libappkit_native.z.so','libnumber_identity.z.so')
BOOT = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'


class Pending(ValueError):
    """Missing or ambiguous actual evidence; never permission/provider success."""


def need(ok, message):
    if not ok: raise ValueError(message)


def decode_json(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 16*1024*1024, 'bounded raw JSON required')
    def unique(items):
        result={}
        for key,value in items:
            need(key not in result,'duplicate raw JSON field')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def clock(raw, nonce, boot):
    row=decode_json(raw)
    fields={'schema','nonce','boot_id','clk_tck','monotonic_before_ns','boottime_ns','monotonic_after_ns','time_ns_dev','time_ns_inode'}
    need(type(row) is dict and set(row)==fields and row['schema']=='number-native-clock496/v1' and
         re.fullmatch('[0-9a-f]{32}',nonce or '') and row['nonce']==nonce and row['boot_id']==boot and
         re.fullmatch(BOOT,boot or ''), 'actual clock identity/schema mismatch')
    need(all(type(row[k]) is int and 0<row[k]<=U64 for k in
         ('clk_tck','monotonic_before_ns','boottime_ns','monotonic_after_ns','time_ns_dev','time_ns_inode')), 'positive exact clock integers required')
    span=row['monotonic_after_ns']-row['monotonic_before_ns']
    need(span>=0,'clock envelope reversed')
    if span>MAX_CLOCK_SPAN_NS: raise Pending('clock syscall envelope exceeds finite 100ms observation bound')
    return row


def clock_offset(samples):
    need(type(samples) is list and len(samples)>=2,'actual before/after clock envelopes required')
    boot=samples[0]['boot_id'];ticks=samples[0]['clk_tck']
    namespace=(samples[0]['time_ns_dev'],samples[0]['time_ns_inode'])
    if not all((s['time_ns_dev'],s['time_ns_inode'])==namespace for s in samples):
        raise Pending('actual helper time namespace changed; no cross-domain clock join')
    need(all(s['boot_id']==boot and s['clk_tck']==ticks for s in samples),'clock boot/tick rate changed')
    need(all(samples[i]['monotonic_after_ns']<=samples[i+1]['monotonic_before_ns'] for i in range(len(samples)-1)),
         'actual clock sample order/reset differs; do not sort observations')
    lower=max(s['boottime_ns']-s['monotonic_after_ns'] for s in samples)
    upper=min(s['boottime_ns']-s['monotonic_before_ns'] for s in samples)
    if lower>upper: raise Pending('MONOTONIC/BOOTTIME offset envelopes disagree; suspend/delay attribution ambiguous')
    return lower,upper


def payload(text):
    need(type(text) is str and '\n' not in text and '\r' not in text and len(text)<=4096,
         'one complete bounded structured payload required')
    if text.startswith('NUMBER_NATIVE495_LOAD v=1 '):
        kind='load';tail=text[len('NUMBER_NATIVE495_LOAD v=1 '):];names=LOAD
    elif text.startswith('NUMBER_NATIVE495 v=1 '):
        kind='native';tail=text[len('NUMBER_NATIVE495 v=1 '):];names=NATIVE
    else: raise ValueError('exact producer495 prefix/version required')
    parts=tail.split(' ')
    need(len(parts)==len(names) and all(p.startswith(k+'=') for p,k in zip(parts,names)),
         'exact field order/no duplicate/extra payload fields required')
    row={k:p[len(k)+1:] for k,p in zip(names,parts)}
    need(row['event'] in ({'enter','result'} if kind=='load' else EVENTS),'unknown observation event')
    for key in names:
        if key in ('event','path'): continue
        value=row[key]
        need(re.fullmatch('-1|0|[1-9][0-9]{0,19}',value),'canonical decimal event integer required')
        row[key]=int(value)
        limit=U64 if key in ('seq','mono_ns','load','instance','connection','request') else U32 if key=='caller_token' else I32
        need(-1<=row[key]<=limit and (key=='result' or row[key]>=0),'event integer width/range mismatch')
    need(row['pid']>0 and row['tid']>0 and row['mono_ns']>0,'actual self PID/TID/monotonic required')
    if kind=='load':
        need(row['load']>0 and re.fullmatch(r'/[A-Za-z0-9_./+-]+/libnumber_identity\.z\.so',row['path']) and
             '..' not in row['path'].split('/') and '//' not in row['path'], 'exact resolved Number load path required')
        need(row['result']==(-1 if row['event']=='enter' else 1),'failed/incomplete native load is not success')
    else:
        need(row['seq']>0 and 0<=row['route']<=4,'actual sequence and finite route required')
        entering=row['event'].endswith('-enter')
        need(row['result']==(-1 if entering else 1),'failed/incomplete native callback is not success')
        if row['event'].startswith(('register-','creator-enter')):
            need(all(row[k]==0 for k in ('instance','connection','request','route','caller_pid','caller_uid','caller_token')),
                 'non-query/instance event has invented identity')
        elif row['event'] in ('create-result','creator-result'):
            need(row['instance']>0 and all(row[k]==0 for k in ('connection','request','route','caller_pid','caller_uid','caller_token')),
                 'creator must return one instance only')
        elif row['event'].startswith('connect-'):
            need(row['instance']>0 and row['connection']>0 and all(row[k]==0 for k in ('request','route','caller_pid','caller_uid','caller_token')),
                 'connect must identify its returned actual stub only')
        else:
            need(all(row[k]>0 for k in ('instance','connection','request','route','caller_pid','caller_uid','caller_token')),
                 'actual Query route/caller/instance/connection/request required')
    return kind,row


@dataclass(frozen=True)
class Event:
    kind: str
    value: dict
    raw: bytes
    header_pid: int
    header_tid: int


# Actual494 log_print.cpp PrintLogPrefix: local month/day+TIME, MSEC, setw(5)
# decimal PID/TID, level, type-prefix, lowercase hex ShortDomain(width 5), tag.
# The fixed `hilog -x` context defaults to this format without year/zone/color.
HEADER = re.compile(rb'(?P<date>(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])) '
    rb'(?P<time>(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}) '
    rb'(?P<pidpad> *)(?P<pid>[1-9][0-9]{0,9}) (?P<tidpad> *)(?P<tid>[1-9][0-9]{0,9}) '
    rb'(?P<level>[DIWEF]) (?P<type>[ACIP])(?P<domain>[0-9a-f]{5})/(?P<tag>[^:\s]{1,128}): (?P<message>[^\r\n]*)')


def header(line):
    need(type(line) is bytes and 0<len(line)<=65536,'bounded exact raw log line required')
    match=HEADER.fullmatch(line)
    need(match is not None,'actual default Hilog header grammar required; no payload PID authority')
    result=match.groupdict()
    for key in ('pid','tid'):
        need(len(result[key+'pad'])==max(0,5-len(result[key])) and int(result[key])<=U32,
             'actual setw(5) header PID/TID width differs')
        result[key]=int(result[key])
    return result


def structured_events(raw):
    need(type(raw) is bytes and 0<len(raw)<=16*1024*1024 and raw.endswith(b'\n'),
         'complete bounded actual hilog snapshot required')
    result=[]
    for line in raw.splitlines():
        if b'NUMBER_NATIVE495' not in line: continue
        need(line.count(b'NUMBER_NATIVE495')==1,'multiple structured prefixes in one raw record')
        source=header(line)
        message=source['message'];where=message.find(b'NUMBER_NATIVE495')
        need(where>=0 and source['type']==b'C' and source['level']==b'I','real core INFO event header required')
        kind,row=payload(message[where:].decode('ascii'))
        if kind=='native':
            need(source['domain']==b'01f1a' and source['tag']==b'NumberIdentity',
                 'actual Number LOG_CORE/domain/tag differs')
        need(source['pid']==row['pid'] and source['tid']==row['tid'],'actual header/payload PID or TID differs')
        result.append(Event(kind,row,line,source['pid'],source['tid']))
    if not result: raise Pending('no actual495 structured native events in retained raw')
    return result


def caller_pid(raw, journal_rows):
    """Join actual pulled original411 journal rows to OS-header log PID.

    A JSON payload's own flags/identity fields are never PID authority.
    """
    need(type(raw) is bytes and raw.endswith(b'\n') and type(journal_rows) is list and journal_rows,
         'actual caller raw log and independently pulled journal required')
    wanted={row['seq']:row for row in journal_rows}
    need(len(wanted)==len(journal_rows),'duplicate caller journal sequence')
    found={}
    for line in raw.splitlines():
        if b'NUMBER_NAPI411 ' not in line: continue
        source=header(line);message=source['message']
        need(message.count(b'NUMBER_NAPI411 ')==1,'multiple caller journal payload prefixes')
        row=decode_json(message.split(b'NUMBER_NAPI411 ',1)[1])
        if (row.get('run'),row.get('phase'))!=(journal_rows[0]['run'],'napi-read'): continue
        need(row.get('seq') in wanted and row==wanted[row['seq']],'caller log and actual pulled journal differ')
        need(row['seq'] not in found,'duplicate actual caller run/sequence in one snapshot')
        found[row['seq']]=source['pid']
    if set(found)!=set(wanted): raise Pending('actual caller log/journal PID binding incomplete')
    need(len(set(found.values()))==1,'caller generation/PID changed within actual public phase')
    return next(iter(found.values()))


def chain(events, *, process, samples, window, caller, routes=(1,2)):
    """Join a verified generation to unique real caller Query operations.

    Called by the fixed evidence adapter, not from JSON-selected code. `events`
    must be parsed with actual header PID/TID and raw-source provenance.
    """
    need(type(events) is list and events and all(type(e) is Event for e in events),'actual decoded events required')
    need(set(process)=={'pid','uid','start_ticks','bundle'} and process['bundle']=='com.ohos.numberidentity' and
         all(type(process[k]) is int and process[k]>0 for k in ('pid','uid','start_ticks')), 'actual provider generation required')
    need(set(caller)=={'pid','uid','token','start_ticks'} and
         all(type(caller[k]) is int and 0<caller[k]<=U32 for k in ('pid','uid','token')) and
         type(caller['start_ticks']) is int and 0<caller['start_ticks']<=U64,
         'independent actual caller PID/UID/token/kernel birth join required')
    need(type(window) is tuple and len(window)==2 and all(type(v) is int and v>0 for v in window) and
         window[0]<window[1] and window[1]-window[0]<=300_000_000_000,'bounded actual monotonic public-call window required')
    offset=clock_offset(samples)
    if events[0].value['mono_ns']<samples[0]['monotonic_after_ns'] or events[-1].value['mono_ns']>samples[-1]['monotonic_before_ns']:
        raise Pending('actual dual-clock calibration must enclose earliest lifecycle through final Query; unobserved earlier suspend is ambiguous')
    ticks=samples[0]['clk_tck']
    # proc starttime truncates in clock ticks. Require the event to be later
    # than the conservative upper edge, rather than choose a convenient point.
    born_upper=((process['start_ticks']+1)*1_000_000_000+ticks-1)//ticks
    caller_born_upper=((caller['start_ticks']+1)*1_000_000_000+ticks-1)//ticks
    for event in events:
        need(event.header_pid==event.value['pid']==process['pid'] and event.header_tid==event.value['tid'],
             'raw header and payload PID/TID must belong to this provider generation')
        if event.value['mono_ns']+offset[0]<born_upper:
            raise Pending('event precedes conservative current PID birth bound; stale/reused PID is not proof')
    need(all(events[i].value['mono_ns']<=events[i+1].value['mono_ns'] for i in range(len(events)-1)),
         'raw event time/order conflict; do not sort away concurrency')
    loads=[e for e in events if e.kind=='load']
    need(len(loads)==2 and [e.value['event'] for e in loads]==['enter','result'] and
         loads[0].value['load']==loads[1].value['load'] and loads[0].value['path']==loads[1].value['path'] and
         loads[0].value['tid']==loads[1].value['tid'],'one complete same-thread actual dlopen interval required')
    lo,hi=(e.value['mono_ns'] for e in loads)
    need(lo<=hi,'load interval reversed')
    rows=[e.value for e in events if e.kind=='native']
    need(rows and all(rows[i]['seq']<rows[i+1]['seq'] for i in range(len(rows)-1)),
         'duplicate/reused/reordered source sequence refused')
    allocated=set();seqs={r['seq'] for r in rows};previous_seq=0
    def allocate(value):
        need(previous_seq<value<row['seq'] and value not in allocated and value not in seqs,
             'ID reuse/overflow/source allocator order or collision refused')
        allocated.add(value)
    registered=False;register_active=False;creator=None;creator_tid=None;instances=set();connections={};connect_active=None;request_active=None;queries=[]
    for row in rows:
        event=row['event'];instance=row['instance'];connection=row['connection']
        if event=='register-enter':
            need(not registered and not register_active and row['tid']==loads[0].value['tid'] and lo<=row['mono_ns']<=hi,
                 'register must run once on real dlopen thread inside interval')
            register_active=True
        elif event=='register-result':
            need(register_active and not registered and row['tid']==loads[0].value['tid'] and lo<=row['mono_ns']<=hi,
                 'register result thread/order/interval differs')
            register_active=False;registered=True
        elif event=='creator-enter':
            need(registered and row['mono_ns']>=hi and creator is None,'creator before registration/load return or overlapping creators')
            creator=[];creator_tid=row['tid']
        elif event=='create-result':
            need(creator==[] and creator_tid==row['tid'],'create result without same-thread actual active creator')
            allocate(instance);creator.append(instance)
        elif event=='creator-result':
            need(creator==[instance] and creator_tid==row['tid'] and instance not in instances,'creator must return exact just-created instance on same thread')
            instances.add(instance);creator=None;creator_tid=None
        elif event=='connect-enter':
            need(instance in instances and connect_active is None,'unproved instance or concurrent/reentrant OnConnect')
            allocate(connection);connect_active=(instance,connection,row['tid'])
        elif event=='connect-result':
            need(connect_active==(instance,connection,row['tid']) and connection not in connections,'missing/mismatched/duplicate OnConnect result')
            connections[connection]=instance;connect_active=None
        elif event=='query-enter':
            need(connections.get(connection)==instance and request_active is None,'unknown stub/instance or concurrent/reentrant Query')
            allocate(row['request']);request_active=dict(row)
        elif event=='query-result':
            need(request_active is not None,'Query result without entry')
            keys=('instance','connection','request','route','caller_pid','caller_uid','caller_token','tid')
            need(all(request_active[k]==row[k] for k in keys),'Query return belongs to another request/caller/stub/thread')
            queries.append((request_active,row));request_active=None
        previous_seq=row['seq']
    need(registered and not register_active and creator is None and connect_active is None and request_active is None,
         'incomplete lifecycle/callback raw stream')
    selected={}
    for route in routes:
        matches=[(enter,result) for enter,result in queries if enter['route']==route and
            (enter['caller_pid'],enter['caller_uid'],enter['caller_token'])==(caller['pid'],caller['uid'],caller['token']) and
            window[0]<=enter['mono_ns']<=result['mono_ns']<=window[1]]
        if len(matches)!=1: raise Pending('exactly one real caller Query required for route '+str(route)+'; missing/multiple candidates')
        if any(row['mono_ns']+offset[0]<caller_born_upper for row in matches[0]):
            raise Pending('Query precedes conservative current caller PID birth bound; reused caller PID is not proof')
        selected[route]=matches[0]
    # Creation and OnConnect may predate the current window: static helper
    # reuse is permitted only by the same actual generation/instance/stub IDs.
    return dict(provider_generation=dict(process),caller=dict(caller),window_ns=list(window),
        selected_requests={str(route):{'instance':pair[0]['instance'],'connection':pair[0]['connection'],'request':pair[0]['request']} for route,pair in selected.items()},
        scope='native callback source-state chain ONLY; requires fixed raw/loaded-image/caller evidence adapter',
        first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)


def merge_snapshots496(frames, pid):
    """Append actual ordered snapshot streams without sorting event order.

    Each frame was independently bound to the same boot/PID birth by adapter.
    OS-header PID filters foreign provider generations; conflicting/repeated
    keys inside one frame are refused. Cross-frame repetition is allowed only
    as the exact common suffix/prefix produced by reading the same log buffer.
    """
    need(type(frames) is list and type(pid) is int and pid>0,'actual ordered snapshot frames/PID required')
    result=[]
    def key(event):
        return (event.kind,event.value['seq']) if event.kind=='native' else (event.kind,event.value['load'],event.value['event'])
    for frame in frames:
        need(type(frame) is list and all(type(event) is Event for event in frame),'decoded actual frame required')
        selected=[event for event in frame if event.header_pid==pid]
        keys=[key(event) for event in selected]
        need(len(keys)==len(set(keys)),'duplicate native identity inside one actual snapshot')
        need(all(selected[i].value['mono_ns']<=selected[i+1].value['mono_ns'] for i in range(len(selected)-1)),
            'individual actual snapshot native event order differs')
        if not selected:continue
        prior=[key(event) for event in result];overlap=set(prior)&set(keys)
        if overlap:
            count=len(overlap)
            need(prior[-count:]==keys[:count] and all(result[-count+i]==selected[i] for i in range(count)),
                'actual snapshots have conflicting or non-suffix/prefix overlapping native records')
            selected=selected[count:]
        if selected and result:
            need(result[-1].value['mono_ns']<=selected[0].value['mono_ns'],
                'actual retained snapshot order/reset differs; no event sorting')
        result.extend(selected)
    if not result:raise Pending('no current actual provider generation events across retained snapshots')
    return result
