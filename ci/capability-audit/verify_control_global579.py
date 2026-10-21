"""Independent NEW398 memory-snapshot/control parser. Never legacy379 admission.

Production provenance, target build/image/FD inventory, public source/renderer,
TIME/VDI and independent QMP remain Root gates. Only actual new-guest raw may be
consumed; this source candidate was not imported, parsed or tested. This module
never returns accepted/onset/first-gate true.
"""
from __future__ import annotations
import json
import re
import onset579_global_clock as clock

MAGIC = 0x4d353938
SOURCE = 'existing_pcm_hw_shared_status_control_no_added_SYNC_PTR'
MAX_BYTES = 16 * 1024 * 1024
COMMON = ('run','boot','client_pid','client_ticks','holder_pid','holder_ticks','holder_uid','holder_gid','fd',
)
SEQUENCE = ('identity404','request404','ack404','witness404','request404','witness_close404','ack404',
            'sampler_registered404','sampler_exit404','request404','ack404','files404','complete404')

def need(ok, text):
    if not ok: raise ValueError(text)

def integer(row, key, low=0, high=(1<<64)-1):
    n = row.get(key)
    need(type(n) is int and low <= n <= high, 'integer '+key)
    return n

def raw_lines(raw, count, line_bound=12287):
    need(type(raw) is str and raw.endswith('\n') and 0 < len(raw.encode()) <= count*(line_bound+1), 'bounded complete raw lines')
    def pairs(items):
        result={}
        for k,v in items:
            need(k not in result, 'duplicate JSON key'); result[k]=v
        return result
    out=[]
    for line in raw.splitlines():
        need(len(line.encode())<=line_bound, 'native row bound')
        r=json.loads(line,object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        need(type(r) is dict, 'object row');out.append(r)
    need(0 < len(out) <= count, 'row count bound');return out

def wire(row, size):
    text=row.get('wire_hex')
    need(type(text) is str and re.fullmatch('[0-9a-f]{'+str(size*2)+'}',text) is not None, 'exact native wire hex')
    return bytes.fromhex(text)

def number(raw, offset, length, signed=False):
    # Consumer only: source static_asserts + actual native ABI observation must
    # independently bind little-endian112/64. No Python struct builds requests.
    return int.from_bytes(raw[offset:offset+length], 'little', signed=signed)

def request(row, expected, op, epoch, instance):
    b=wire(row,112)
    need(number(b,0,8)==epoch and number(b,8,8)==instance and number(b,16,8)==expected['holder_ticks'] and
         number(b,24,4)==MAGIC and number(b,28,4)==op and number(b,32,4)==expected['holder_pid'] and
         number(b,36,4)==0 and b[40:80]==expected['boot'].encode()+b'\0'*4 and
         b[80:112]==expected['run'].encode(), 'request native fields differ')
    need(integer(row,'op',0,2)==op and integer(row,'sent_fd_count')==(3 if op==1 else 0) and
         integer(row,'scm_pid',2)==expected['client_pid'] and integer(row,'scm_uid')==0 and
         integer(row,'scm_gid')==expected['self_gid'], 'actual sender credential/SCM FD set')

def ack(row, expected, op):
    b=wire(row,64)
    a={name:number(b,off,size,signed) for name,off,size,signed in (
      ('epoch',0,8,False),('instance',8,8,False),('ticks',16,8,False),('rows',24,8,False),('tap',32,8,False),
      ('error',40,4,True),('fd',44,4,True),('pid',48,4,True),('magic',52,4,False),('state',56,4,False),('failed',60,4,False))}
    need(integer(row,'op',0,2)==op and integer(row,'validation_errno')==0 and integer(row,'credential_count')==1 and
         integer(row,'scm_pid',2)==expected['holder_pid'] and integer(row,'scm_uid')==expected['holder_uid'] and
         integer(row,'scm_gid')==expected['holder_gid'], 'kernel ACK peer credential changed')
    need(a['magic']==MAGIC and a['error']==0 and a['failed']==0 and a['ticks']==expected['holder_ticks'] and
         a['pid']==expected['holder_pid'] and a['fd']==expected['fd'] and a['instance']>0 and
         a['rows']<=6000 and a['tap']<=MAX_BYTES, 'ACK native fields/failed/outcome')
    return a

def control(raw, *, expected, exit_code,domain):
    need(type(exit_code) is int and exit_code==0, 'actual native CONTROL exit0 required')
    need(type(expected) is dict and re.fullmatch('[a-f0-9]{32}',expected.get('run','')) is not None and
         re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',expected.get('boot','')) is not None,
         'actual independently bound run/boot inventory required')
    for key in COMMON[2:]+('dev','ino','rdev','self_gid','card','device','subdevice'):
        integer(expected,key,1 if key in ('client_pid','client_ticks','holder_pid','holder_ticks','client_time_ino','holder_time_ino') else 0)
    need(expected['client_pid']!=expected['holder_pid'] and expected['client_pid']>1 and expected['holder_pid']>1,
         'separate actual CONTROL/holder processes required')
    rows=raw_lines(raw,13);need(tuple(r.get('kind') for r in rows)==SEQUENCE,'finite complete CONTROL sequence')
    previous=0
    for seq,row in enumerate(rows):
        need(integer(row,'protocol')==604 and integer(row,'seq')==seq and row.get('onset_proven') is False,'CONTROL scope/sequence')
        for key in COMMON:
            if key not in ('run','boot'):integer(row,key)
            need(key in expected and type(row.get(key)) is type(expected[key]) and row.get(key)==expected[key], 'CONTROL independent identity '+key)
        need(row.get('clock_variant')=='kernel_global_monotonic','explicit native global CONTROL variant')
        client_clock=clock.observation(row['client_clock'],domain=domain,run=expected['run'],role='control_client',
            expected=(expected['client_pid'],expected['client_ticks'],expected['client_pid'],-1))
        holder_fd=rows[0]['holder_clock']['held_pidfd']
        holder_clock=clock.observation(row['holder_clock'],domain=domain,run=expected['run'],role='alsa_holder',
            expected=(expected['holder_pid'],expected['holder_ticks'],expected['client_pid'],holder_fd))
        clock.pair(client_clock,holder_clock)
        m=integer(row,'monotonic_ns',1);integer(row,'realtime_ns',1);need(m>=previous,'CONTROL clock regression');previous=m
    ident=rows[0]
    need(ident.get('byte_order')=='little' and ident.get('request_bytes')==112 and ident.get('ack_bytes')==64 and
         type(ident.get('self_uids')) is list and len(ident['self_uids'])==4 and
         all(type(x) is int and x==0 for x in ident['self_uids']) and integer(ident,'self_gid')==expected['self_gid'] and
         integer(ident,'peer_pid',2)==expected['holder_pid'] and integer(ident,'peer_uid')==expected['holder_uid'] and
         integer(ident,'peer_gid')==expected['holder_gid'], 'native ABI/root/peer inventory')
    for k in ('dev','ino','rdev'):need(integer(ident,k)==expected[k], 'selected HW stat differs')
    request(rows[1],expected,0,0,0);hello=ack(rows[2],expected,0)
    need(hello['state']==0 and hello['epoch']<64, 'HELLO must be idle unique HW')
    epoch=hello['epoch']+1;instance=hello['instance']
    w=rows[3];need(integer(w,'source_pid',2)==expected['holder_pid'] and integer(w,'source_fd')==expected['fd'] and
         integer(w,'pidfd_getfd_rc')==0 and integer(w,'kcmp_rc')==0,'actual holder OFD witness')
    integer(w,'duplicate_fd')
    for k in ('dev','ino','rdev'):need(integer(w,k)==expected[k], 'witness FD stat')
    request(rows[4],expected,1,epoch,instance);need(integer(rows[5],'close_rc')==0,'ARM local witness duplicate close')
    armed=ack(rows[6],expected,1)
    need((armed['epoch'],armed['instance'],armed['state'],armed['rows'],armed['tap'])==(epoch,instance,1,0,0), 'ARM ACK epoch/reset')
    registered,exited=rows[7:9]
    for k in ('sampler_pid','sampler_ticks','sampler_fd'):integer(registered,k,1 if k!='sampler_fd' else 0)
    need(registered['sampler_pid'] not in (expected['holder_pid'],expected['client_pid']) and
         integer(registered,'pidfd_getfd_rc')==integer(registered,'holder_sampler_kcmp_rc')==integer(registered,'duplicate_close_rc')==0,
         'actual separate sampler and closed temporary OFD duplicate')
    need(all(integer(exited,k,1)==registered[k] for k in ('sampler_pid','sampler_ticks')) and
         integer(exited,'pidfd_revents')==1 and integer(exited,'proc_stat_errno')==2,'actual sampler exit before DISARM')
    request(rows[9],expected,2,epoch,instance);sealed=ack(rows[10],expected,2)
    need((sealed['epoch'],sealed['instance'],sealed['state'])==(epoch,instance,0),'quiescent final ACK')
    files=rows[11]
    need(integer(files,'rows')==sealed['rows'] and integer(files,'tap_bytes')==sealed['tap'], 'file/ACK counts')
    for k in ('journal_dev','journal_ino','journal_bytes','tap_dev','tap_ino'):integer(files,k,1 if k.endswith(('ino','bytes')) else 0)
    need((files['journal_dev'],files['journal_ino'])!=(files['tap_dev'],files['tap_ino']), 'distinct real evidence files')
    need(rows[12].get('control_integrity_only') is True and rows[12].get('accepted') is False,'CONTROL never accepts onset')
    return dict(epoch=epoch,instance=instance,rows=rows,files=files,sampler=registered,final_ack=sealed)

def memory_journal(raw,tap,*,control_result,expected,domain):
    need(type(tap) is bytes and len(tap)<=MAX_BYTES and len(tap)%4==0, 'bounded 48k stereo S16 tap bytes')
    rows=raw_lines(raw,6002);need(rows[0].get('kind')=='begin598' and rows[-1].get('kind')=='end598','new398 framed schema ONLY')
    need(all(len(line.encode())<=4095 for line in raw.splitlines()[1:]),'original bounded WRITEI/end rows; only typed begin is larger')
    begin,end=rows[0],rows[-1];epoch=control_result['epoch'];instance=control_result['instance']
    for r in rows:
        need(integer(r,'protocol')==598 and r.get('run')==expected['run'] and integer(r,'epoch')==epoch and
             integer(r,'instance')==instance and r.get('onset_proven') is False,'398 run/epoch/instance/scope')
    for k in ('pid','fd','dev','ino','rdev','card','device','subdevice'):
        wanted=expected['holder_pid'] if k=='pid' else expected[k]
        need(integer(begin,k)==wanted,'begin598 real inventory '+k)
    for key,value in {'start_ticks':expected['holder_ticks'],'boot':expected['boot'],'peer_pid':expected['client_pid'],
        'peer_start_ticks':expected['client_ticks'],'peer_uid':0,'peer_gid':expected['self_gid'],
        'arm_kcmp_rc':0,'arm_witness_closed_before_publish':True}.items():
        need(type(begin.get(key)) is type(value) and begin[key]==value, '398 actual control join '+key)
    need(begin.get('clock_variant')=='kernel_global_monotonic','explicit global ALSA journal')
    holder_clock=clock.observation(begin['holder_clock'],domain=domain,run=expected['run'],role='alsa_holder',
        expected=(expected['holder_pid'],expected['holder_ticks'],expected['holder_pid'],-1))
    peer_clock=clock.observation(begin['peer_clock'],domain=domain,run=expected['run'],role='control_client',
        expected=(expected['client_pid'],expected['client_ticks'],expected['holder_pid'],begin['peer_clock']['held_pidfd']))
    clock.pair(holder_clock,peer_clock)
    need(begin.get('snapshot_source')==SOURCE,'not old synchronous-query witness')
    cursor=0;previous_appl=None;previous_hw=-1;previous_return=0
    for seq,row in enumerate(rows[1:-1]):
        need(row.get('kind')=='write598' and row.get('snapshot_source')==SOURCE and integer(row,'seq')==seq and
             integer(row,'pid')==expected['holder_pid'] and integer(row,'fd')==expected['fd'], 'new398 write sequence/source')
        for k,v in {'snapshot_valid':1,'drain_fd_stat_rc':0,'drain_fd_stat_errno':0,'drain_identity':1,'failed':0}.items():
            need(type(row.get(k)) is int and row[k]==v,'failed/stale new398 '+k)
        need(integer(row,'state_before') in (2,3) and integer(row,'state_after') in (2,3),'PCM reset/xrun/not running')
        a,b=integer(row,'appl_before'),integer(row,'appl_after');h,j=integer(row,'hw_before'),integer(row,'hw_after')
        accepted=integer(row,'accepted');requested=integer(row,'requested',1);empty=integer(row,'empty_eagain',0,1)
        error=row.get('error');need(type(error) is int and ((accepted>0 and empty==0 and error==0) or
            (accepted==0 and empty==1 and error==-11)), 'actual accepted write or no-progress EAGAIN only')
        need(accepted<=requested and b-a==accepted and (previous_appl is None or a==previous_appl) and
             previous_hw<=h<=j<=b and h<=a, 'memory pointer discontinuity/reset')
        lo,mid,hi=(integer(row,k,1) for k in ('before_ns','after_ns','returned_ns'))
        need(previous_return<=lo<=mid<=hi and control_result['rows'][3]['monotonic_ns']<=lo and
             hi<=control_result['rows'][10]['monotonic_ns'],'new398 write lifetime/clock')
        need(integer(row,'tap_offset')==cursor and integer(row,'pcm_bytes')==accepted*4 and accepted*4<=65536,'accepted PCM interval')
        cursor+=accepted*4;previous_appl=b;previous_hw=j;previous_return=hi
    count=len(rows)-2
    need(type(end.get('failed')) is int and end['failed']==0 and integer(end,'reason_errno')==0 and end.get('writer_quiescent') is True,
         'new398 drain/quiescence failed')
    need(integer(end,'produced_rows')==integer(end,'drained_rows')==count==control_result['final_ack']['rows'] and
         integer(end,'produced_pcm_bytes')==integer(end,'drained_pcm_bytes')==cursor==len(tap)==control_result['final_ack']['tap'] and
         len(raw.encode())==control_result['files']['journal_bytes'], 'new398 exact final counts/files')
    return dict(scope='NEW398 memory snapshot/control integrity ONLY; NOT379 syscall witness or onset',
        epoch=epoch,instance=instance,write_rows=count,pcm_bytes=cursor,
        independent_status_sampler_still_required=True,renderer_source_TIME_VDI_QMP_join_still_required=True,
        accepted=False,onset_proven=False,ledger_closed=False,first_artifact_behavior_gate_passed=False)

def verify(control_raw,journal_raw,tap,*,expected,control_exit_code,domain):
    ctl=control(control_raw,expected=expected,exit_code=control_exit_code,domain=domain)
    return memory_journal(journal_raw,tap,control_result=ctl,expected=expected,domain=domain)

def independent_sampler(raw,*,control_result,expected,exit_code,domain):
    """Actual original377 target observer format; separate from398 shared memory.

    Root additionally binds this exact native source/binary/build and held HDC
    process/guest inventory. The raw completed stream alone cannot supply that.
    """
    need(type(exit_code) is int and exit_code==0,'actual independent sampler exit0 required')
    rows=raw_lines(raw,7502);header=rows[0]
    need(all(len(line.encode())<=1400 for line in raw.splitlines()[1:]),'original bounded HW sample rows')
    need(header.get('kind')=='header' and header.get('schema')=='media375-hw-sync-global-clock579/v1' and
         rows[-1]=={'kind':'complete'} and len(rows)>=4,'complete original target sampler stream')
    for k in ('run','boot','fd','dev','ino','rdev','card','device','subdevice'):
        need(type(header.get(k)) is type(expected[k]) and header[k]==expected[k],'independent sampler inventory '+k)
    need(integer(header,'pid',2)==expected['holder_pid'] and integer(header,'ticks',1)==expected['holder_ticks'], 'sampler holder incarnation')
    registered=control_result['sampler']
    need(integer(header,'sampler_pid',2)==registered['sampler_pid'] and
         integer(header,'sampler_ticks',1)==registered['sampler_ticks'] and
         integer(header,'borrowed_fd')==registered['sampler_fd'],'CONTROL registered actual sampler/OFD')
    need(header.get('clock_variant')=='kernel_global_monotonic','explicit native global sampler')
    own=clock.observation(header['sampler_clock'],domain=domain,run=expected['run'],role='status_sampler',
        expected=(registered['sampler_pid'],registered['sampler_ticks'],registered['sampler_pid'],-1))
    held=clock.observation(header['holder_clock'],domain=domain,run=expected['run'],role='alsa_holder',
        expected=(expected['holder_pid'],expected['holder_ticks'],registered['sampler_pid'],header['holder_clock']['held_pidfd']))
    clock.pair(own,held)
    previous_after=previous_hw=previous_appl=-1;offsets=[]
    for seq,row in enumerate(rows[1:-1]):
        need(row.get('kind')=='sample' and integer(row,'seq')==seq,'independent sample sequence')
        before,after=integer(row,'before_ns',1),integer(row,'after_ns',1);real=integer(row,'real_ns',1)
        hw,appl=integer(row,'hw_ptr',0,(1<<63)-1),integer(row,'appl_ptr',0,(1<<63)-1)
        need(previous_after<=before<=after and after-before<=20_000_000 and
             control_result['rows'][6]['monotonic_ns']<=before and after<=control_result['rows'][8]['monotonic_ns'],
             'actual SYNC_PTR query time/order/lifetime')
        need(previous_hw<=hw<=appl and previous_appl<=appl and integer(row,'state') in (2,3),'sampler xrun/reset/wrap')
        need(integer(row,'queued_frames')==appl-hw,'actual sampler queue arithmetic')
        integer(row,'raw_tstamp_sec');integer(row,'raw_tstamp_nsec',0,999999999)
        offsets.append((real-after,real-before));previous_after,previous_hw,previous_appl=after,hw,appl
    interval=[max(a for a,b in offsets),min(b for a,b in offsets)]
    need(interval[0]<=interval[1],'actual independent clock mapping stepped')
    return dict(samples=rows[1:-1],clock_offset_ns=interval,
        scope='original377 kernel SYNC_PTR stream only; new398 memory snapshots remain distinct',accepted=False)

def verify_window(control_raw,journal_raw,tap,status_raw,*,expected,control_exit_code,sampler_exit_code,domain):
    ctl=control(control_raw,expected=expected,exit_code=control_exit_code,domain=domain)
    result=memory_journal(journal_raw,tap,control_result=ctl,expected=expected,domain=domain)
    status=independent_sampler(status_raw,control_result=ctl,expected=expected,exit_code=sampler_exit_code,domain=domain)
    return dict(result,scope='NEW398 control+memory and separate original377 kernel stream; root source/image/renderer/TIME/QMP gates pending',
        independent_status_sampler_still_required=False,independent_samples=len(status['samples']),
        realtime_minus_monotonic_ns=status['clock_offset_ns'],presentation_anchor_proven=False)
