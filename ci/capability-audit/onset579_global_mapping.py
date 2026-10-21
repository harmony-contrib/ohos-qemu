"""Pure replay of source-frame0 -> actual mixed bytes -> same-OFD HW interval.

Call only after the unchanged original480 raw/constructor/VDI/PCM verifier.
No resources, shell, compiler, guessed latency, affine queue clock or fallback.
"""
from pathlib import Path
import hashlib,io,json,re,wave
import onset579_global_clock as clock
MAX_RAW = 64 * 1024 * 1024
PREFIX_BYTES = 4096
SYNC_BUDGET_NS = 200_000_000  # existing public virtual TIME audit budget

def need(ok,message):
    if not ok:raise ValueError('no_onset_anchor: '+message)
def integer(row,key,lo=0,hi=(1<<64)-1):
    n=row.get(key);need(type(n) is int and lo<=n<=hi,'invalid actual '+key);return n
def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:need(k not in d,'duplicate raw field');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite raw number')))
def lines(raw,limit):
    need(type(raw) is str and 0<len(raw.encode())<=MAX_RAW and raw.endswith('\n'),'bounded complete LF raw ledger required')
    values=raw.replace('\r\n','\n').splitlines();need(0<len(values)<=limit,'bounded complete rows required')
    return [decode(line) for line in values]
def bytes_row(row):
    value=row.get('pcm_hex');need(type(value) is str and len(value)<=32768 and len(value)%2==0 and re.fullmatch('[a-f0-9]*',value) is not None,'actual bounded PCM hex')
    return bytes.fromhex(value)
def af_journal(raw,*,run,boot,domain):
    rows=lines(raw,12002);begin,end=rows[0],rows[-1]
    need(begin.get('kind')=='begin580' and end.get('kind')=='end580','actual AF journal edges')
    need(begin.get('boot')==boot and begin.get('run')==end.get('run')==run,'actual same-boot AF run')
    for row in rows:need(row.get('protocol')==580 and row.get('run')==run and row.get('onset_proven') is False,'raw producer cannot claim onset')
    need(begin.get('source')=='actual_renderer_read_and_HPAE_lineage','exact product producer')
    for key in ('pid','birth','peer_pid','peer_birth','journal_ino'):integer(begin,key,1)
    need(integer(begin,'peer_uid')==0 and begin.get('clock_variant')=='kernel_global_monotonic','AF/root native global domain')
    for edge in (begin,end):
        own=clock.observation(edge['producer_clock'],domain=domain,run=run,role='af_producer',
            expected=(begin['pid'],begin['birth'],begin['pid'],-1))
        peer=clock.observation(edge['peer_clock'],domain=domain,run=run,role='af_client',
            expected=(begin['peer_pid'],begin['peer_birth'],begin['pid'],begin['peer_clock']['held_pidfd']))
        clock.pair(own,peer)
    need(end.get('writer_quiescent') is True and integer(end,'lost')==integer(end,'error')==0,'loss/failure/nonquiescent AF journal')
    need(integer(end,'produced')==integer(end,'drained')==len(rows)-2,'actual AF complete row counts')
    previous=raw_bytes=0;cuts={};commits={};packets=[]
    for seq,row in enumerate(rows[1:-1]):
        need(row.get('kind')=='row580' and integer(row,'seq')==seq,'AF ring sequence')
        lo,hi=integer(row,'before_ns',1),integer(row,'after_ns',1)
        need(previous<=lo<=hi,'AF actual monotonic ordering');previous=hi
        pcm=bytes_row(row);raw_bytes+=len(pcm);kind=integer(row,'type',1,4)
        if kind==1:
            cut=integer(row,'cut',1);need(cut not in cuts,'duplicate actual ReadCut')
            need(integer(row,'renderer',1)>0 and integer(row,'frames',1)>0 and integer(row,'channels',1,16)>0 and integer(row,'rate',1,768000)>0,'actual bounded read cut metadata')
            cuts[cut]=dict(row,pcm=pcm)
        elif kind==3:
            cut=integer(row,'cut',1);need(cut in cuts and cut not in commits and type(row.get('committed')) is bool and not pcm,'actual single ReadCut commit')
            commits[cut]=row['committed']
        elif kind==2:
            need(integer(row,'renderer',1)>0 and integer(row,'rate',1,768000)>0 and integer(row,'channels',1,16)>0,'actual output packet metadata')
            spans=row.get('spans');need(type(spans) is list and len(spans)<=64 and type(row.get('lineage_valid')) is bool,'bounded output span vector')
            for span in spans:
                need(type(span) is list and len(span)==4 and all(type(v) is int and v>=0 for v in span),'actual interval span fields')
                cut,src,out,count=span
                need(cut in cuts and commits.get(cut) is True and count>0 and src+count<=cuts[cut]['frames'] and out+count<=16384,'span outside actual committed PCM')
            packets.append(dict(row,pcm=pcm))
        else:
            need(False,'producer reported unknown path')
    need(raw_bytes==integer(end,'raw_bytes') and raw_bytes<=64*1024*1024,'AF actual copied-byte count')
    return begin,end,cuts,commits,packets

def qap_rows(raws):
    values={}
    for raw in raws:
        need(type(raw) is str and len(raw.encode())<=MAX_RAW,'bounded actual hilog')
        for line in raw.splitlines():
            marker='AUDIO_PROVENANCE505 '
            if marker not in line:continue
            body=line.split(marker,1)[1];need(body.startswith('{') and body.endswith('}'),'truncated native provenance row')
            row=decode(body);need(row.get('schema')=='qap505-raw-v1' and row.get('source_frame_relation_known') is False and row.get('onset_proven') is False,'original513 raw scope')
            values[json.dumps(row,sort_keys=True,separators=(',',':'))]=row
    need(values,'actual native source/metadata/renderer rows missing')
    return list(values.values())
def source_identity(qaps,stat_raw,source_raw):
    # This actual file is root-staged into the ordinary owner's filesDir; the
    # original collector independently verifies full SHA/owner/inode before use.
    fields=stat_raw.strip().split();need(len(fields)==4 and all(x.isdecimal() for x in fields),'actual source dev/ino/uid/size stat')
    dev,ino,uid,size=map(int,fields);need(size==len(source_raw),'actual full staged WAV size')
    with wave.open(io.BytesIO(source_raw),'rb') as f:
        need(f.getnchannels()==2 and f.getsampwidth()==2 and f.getframerate()==48000 and f.getcomptype()=='NONE','fresh source PCM format')
        pcm=f.readframes(f.getnframes())
    need(len(pcm)>=PREFIX_BYTES and len(pcm)%4==0,'fresh source prefix itself required')
    need(source_raw[:4]==b'RIFF' and source_raw[8:12]==b'WAVE' and int.from_bytes(source_raw[4:8],'little')+8==len(source_raw),'actual complete RIFF size')
    position=12;data_offsets=[]
    while position+8<=len(source_raw):
        count=int.from_bytes(source_raw[position+4:position+8],'little');start=position+8
        need(start+count<=len(source_raw),'actual RIFF chunk bounds')
        if source_raw[position:position+4]==b'data':data_offsets.append((start,count))
        position=start+count+(count%2)
    need(position==len(source_raw) and len(data_offsets)==1 and data_offsets[0][1]==len(pcm),'actual unique PCM data chunk')
    prefix=pcm[:PREFIX_BYTES];need(pcm.find(prefix,4)==-1,'source frame0 prefix itself is ambiguous in this fresh nonce asset')
    digest128=hashlib.sha256(pcm[:128]).hexdigest();sources=[]
    for row in qaps:
        if row.get('kind')!='source_native':continue
        text=row.get('source_descriptor');need(type(text) is str and text.startswith('qap505v1:'),'exact source descriptor')
        parts=text[9:].split(':');need(len(parts)==15 and all(re.fullmatch('[0-9]+',s) for s in parts[:14]),'complete source descriptor fields')
        n=list(map(int,parts[:14]));need(all(v<(1<<64) for v in n),'source descriptor native ranges')
        if (n[3],n[4],n[5],n[6],n[7],n[8],n[9],n[10],n[11],n[12],n[13],parts[14])==(dev,ino,0,size,1,data_offsets[0][0],len(pcm),48000,2,2,128,digest128):
            sources.append((row,n,text))
    need(len(sources)==1,'exact one native source generation for actual owner WAV')
    source,n,descriptor=sources[0];key=(n[0],n[1],n[2])
    forwarded=[r for r in qaps if r.get('kind')=='metadata_forwarded' and r.get('source_descriptor')==descriptor]
    need(forwarded,'actual private source metadata forwarding absent')
    selected=[r for r in qaps if r.get('kind')=='input' and (r.get('source_pid'),r.get('source_birth_ticks'),r.get('source_generation'))==key and r.get('ingress_byte_begin')==0 and r.get('detail')=='sha256:'+digest128+':bytes:128' and r.get('mapping_invalid') is False and r.get('renderer_session_known') is True]
    need(len(selected)==1,'actual first decoded PCM ingress/session missing or ambiguous')
    first=selected[0];session=integer(first,'renderer_session_id',1)
    writes=[r for r in qaps if r.get('kind')=='write' and all(r.get(k)==first.get(k) for k in ('receiver_pid','receiver_birth_ticks','plugin_instance','metadata_binding_instance','source_pid','source_birth_ticks','source_generation','renderer_session_id')) and r.get('ingress_byte_begin')==0 and r.get('write_renderer_session_known') is True and r.get('write_renderer_session_id')==session and r.get('old_generation') is False and r.get('mapping_invalid') is False and r.get('detail')=='valid_return' and r.get('write_accepted_bytes',0)>0]
    need(len(writes)==1,'actual accepted frame0 renderer write/session is absent or replayed')
    return dict(source_descriptor=descriptor,source_pid=n[0],source_birth=n[1],source_generation=n[2],session=session,
        receiver_pid=first['receiver_pid'],receiver_birth=first['receiver_birth_ticks'],owner_uid=uid,
        prefix=prefix,prefix_sha256=hashlib.sha256(prefix).hexdigest(),wav_sha256=hashlib.sha256(source_raw).hexdigest())

def locate_source_zero(cuts,commits,identity):
    runs=[];current=[];previous=None
    for cut,row in sorted(cuts.items(),key=lambda item:item[1]['seq']):
        if not commits.get(cut) or row['session']!=identity['session']:continue
        need(row['rate']==48000 and row['channels']==2 and row['format']==1 and len(row['pcm'])==row['frames']*4,'selected source session actual PCM format changed')
        key=(row['renderer'],row['uid'],row['session'])
        if previous is None or key!=previous[0] or row['ring_frame']!=previous[1]:
            if current:runs.append(current)
            current=[]
        current.append((cut,row));previous=(key,row['ring_frame']+row['frames'])
    if current:runs.append(current)
    matches=[]
    for run in runs:
        pcm=b''.join(row['pcm'] for _,row in run);at=pcm.find(identity['prefix'])
        if at<0:continue
        need(at%4==0 and pcm.find(identity['prefix'],at+1)<0,'ambiguous or unaligned source frame0 itself in real cuts')
        offset=0
        for cut,row in run:
            if offset<=at<offset+len(row['pcm']):matches.append(dict(cut=cut,frame=(at-offset)//4,renderer=row['renderer'],uid=row['uid'],session=row['session'],ring_frame=row['ring_frame']+(at-offset)//4));break
            offset+=len(row['pcm'])
    need(len(matches)==1,'fresh source frame0 itself has no unique actual committed ReadCut')
    return matches[0]

def locate_mix_zero(packets,source_zero,tap):
    hits=[]
    for ordinal,p in enumerate(packets):
        if not p['lineage_valid']:continue
        for cut,begin,out,count in p['spans']:
            if cut!=source_zero['cut'] or not begin<=source_zero['frame']<begin+count:continue
            need(p['rate']==48000 and p['channels']==2 and p['format']==1 and len(p['pcm'])%4==0 and out+count<=len(p['pcm'])//4,'selected actual mixed packet format/span changed')
            direct_frame=out+source_zero['frame']-begin
            # Context begins with the packet actually containing frame0, then
            # consecutive successful accepted packets of this same sink. Never
            # find a later waveform peak and subtract a guessed media offset.
            context=p['pcm']
            for later in packets[ordinal+1:]:
                if len(context)>=PREFIX_BYTES:break
                if later['renderer']==p['renderer']:
                    need(later['rate']==48000 and later['channels']==2 and later['format']==1 and len(later['pcm'])%4==0,'same output changed PCM format')
                    context+=later['pcm']
            need(len(context)>=1024 and direct_frame*4<len(p['pcm']),'bounded nonce-bearing frame0 packet context missing')
            at=tap.find(context)
            need(at>=0 and at%4==0 and tap.find(context,at+1)<0,'actual full mixed packet does not uniquely join accepted same-OFD tap')
            hits.append(dict(packet_seq=p['seq'],output_instance=p['renderer'],packet_frame=direct_frame,
                tap_byte=at+direct_frame*4,context_tap_byte=at,context_bytes=len(context),context_sha256=hashlib.sha256(context).hexdigest()))
    need(len(hits)==1,'source frame0 was lost, copied to multiple outputs, replayed, or never observed after mixing')
    return hits[0]

def accepted_frame(journal_rows,mix_zero,segments):
    need(journal_rows[0]['kind']=='begin598' and journal_rows[-1]['kind']=='end598','original398 journal required')
    mode=None
    for row in journal_rows:
        fields=tuple(integer(row,k) for k in ('clock579_epoch','reset579_epoch','clock579_type','clock579_mode'))
        need(fields[0]>0 and fields[0]%2==0 and fields[2:]==(1,1),'actual successful MONOTONIC+ENABLE SW_PARAMS witness absent')
        if mode is None:mode=fields
        need(fields==mode,'same OFD clock/reset generation changed in the window')
        if row['kind']=='write398':need(row.get('clock579_unchanged')==1,'mode/reset changed across actual WRITEI')
    matches=[]
    for row,segment in zip(journal_rows[1:-1],segments):
        need(segment['seq']==row['seq'] and segment['tap_byte_interval']==[row['tap_offset'],row['tap_offset']+row['pcm_bytes']] and segment['appl_frame_interval']==[row['appl_before'],row['appl_after']],'independently replayed original480 intervals differ')
        lo,hi=segment['tap_byte_interval']
        if lo<=mix_zero['tap_byte']<hi:
            delta=mix_zero['tap_byte']-lo;need(delta%4==0,'mixed source frame is not an accepted ALSA frame')
            frame=row['appl_before']+delta//4;need(frame<row['appl_after'],'source frame outside actual accepted prefix')
            matches.append(dict(write_seq=row['seq'],appl_frame=frame,mode_epoch=mode[0],reset_generation=mode[1]))
    need(len(journal_rows)-2==len(segments) and len(matches)==1,'one actual accepted interval must own frame0')
    return matches[0]

def hardware_crossing(samples,target):
    # Hardware timestamps are interpreted only after accepted_frame proves the
    # effective same-OFD mode/type and a constant reset generation through seal.
    candidates=[]
    for before,after in zip(samples,samples[1:]):
        if not before['hw_ptr']<=target<after['hw_ptr']:continue
        upper=integer(after,'raw_tstamp_sec')*1_000_000_000+integer(after,'raw_tstamp_nsec',0,999999999)
        need(after['state']==3 and 0<upper<=after['after_ns'],'actual running HW MONOTONIC upper timestamp absent')
        if before['state']==2:
            # PREPARED proves the device was not yet started at this actual
            # HWSYNC read; use its query bracket conservatively, never zero as
            # a fabricated kernel timestamp. Required for real global frame0.
            lower=before['before_ns'];origin='actual_PREPARED_HWSYNC_before_ns'
        else:
            need(before['state']==3 and before['hw_ptr']<target,'equal running pointer does not bound frame0 start')
            lower=integer(before,'raw_tstamp_sec')*1_000_000_000+integer(before,'raw_tstamp_nsec',0,999999999)
            need(0<lower<=before['after_ns'],'actual HW MONOTONIC lower timestamp absent');origin='actual_HW_MONOTONIC'
        need(0<lower<=upper and upper-lower<=50_000_000,'hardware crossing is unbounded/clock-inconsistent')
        candidates.append(dict(monotonic_interval_ns=[lower,upper],lower_source=origin,
            lower_sample=before['seq'],upper_sample=after['seq'],lower_hw=before['hw_ptr'],upper_hw=after['hw_ptr'],target_appl_frame=target,
            scope='actual same-OFD hardware-pointer frame0 crossing; independent PCM consumption still mandatory'))
    need(len(candidates)==1,'no unique actual same-OFD hardware crossing of mapped frame0')
    return candidates[0]

def verify_mapping(*,af_raw,run,boot,qap_raws,source_stat_raw,source_wav_raw,tap,journal_rows,segments,status_samples,haptic_episode,domain):
    begin,end,cuts,commits,packets=af_journal(af_raw,run=run,boot=boot,domain=domain)
    identity=source_identity(qap_rows(qap_raws),source_stat_raw,source_wav_raw)
    zero=locate_source_zero(cuts,commits,identity);mixed=locate_mix_zero(packets,zero,tap)
    accepted=accepted_frame(journal_rows,mixed,segments);cross=hardware_crossing(status_samples,accepted['appl_frame'])
    lo,hi=cross['monotonic_interval_ns'];hlo,hhi=haptic_episode['start_ns']
    need(all(type(n) is int for n in (hlo,hhi)) and 0<hlo<=hhi,'original actual VDI/TIME onset interval required')
    delta=[hlo-hi,hhi-lo]
    need(-SYNC_BUDGET_NS<=delta[0]<=delta[1]<=SYNC_BUDGET_NS,'full measured haptic/audio interval exceeds original200ms virtual TIME budget')
    return dict(schema='source-frame0-mixed-sameOFD-HW579/v1',run=run,boot=boot,
        source={k:v for k,v in identity.items() if k!='prefix'},source_zero=zero,mixed_zero=mixed,accepted_frame=accepted,hardware_crossing=cross,
        producer=dict(pid=begin['pid'],birth=begin['birth'],clock_domain=begin['producer_clock']),
        haptic_minus_audio_interval_ns=delta,virtual_TIME_budget_ns=SYNC_BUDGET_NS,
        stream_frame_zero_mapping_proven=True,presentation_anchor_proven=True,synchronization_verified=True,
        scope='source-bound hardware-pointer interval plus original independent virtual TIME/PCM evidence; no physical motor or acoustic precision claim',
        accepted=False,full82=False,first_artifact_behavior_gate_passed=False)

