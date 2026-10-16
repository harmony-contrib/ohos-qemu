#!/usr/bin/env python3
"""Independent PCM challenge diagnostic. Does not close requirements or modify the shared verifier."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sys

RATE=48000
CHANNELS=2
FRAME_BYTES=4
CHIP=8
WINDOW=8192
CORRELATION=0.995


def pcm_values(data):
    if len(data)%FRAME_BYTES:raise ValueError('truncated/interleaved S16LE PCM')
    values=array('h');values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    return values


def generate(directory,run_id):
    if re.fullmatch('[0-9a-f]{32}',run_id or '') is None:raise ValueError('fresh explicit run id required')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if any((directory/name).exists() for name in ['challenge.pcm','challenge.json']):
        raise ValueError('existing challenge files must be preserved')
    entropy=secrets.token_bytes(RATE//CHIP*2)
    samples=array('h')
    for index in range(RATE//CHIP):
        left=8192 if entropy[index*2]&1 else -8192
        right=8192 if entropy[index*2+1]&1 else -8192
        samples.extend([left,right]*CHIP)
    if sys.byteorder!='little':samples.byteswap()
    data=samples.tobytes()
    manifest={'version':1,'run_id':run_id,'challenge_id':secrets.token_hex(16),'rate':RATE,'channels':2,
        'format':'S16LE','frame_bytes':FRAME_BYTES,'frames':RATE,'chip_frames':CHIP,
        'sha256':hashlib.sha256(data).hexdigest(),'pcm_file':'challenge.pcm'}
    # No existing challenge or evidence is overwritten; the HAP never receives these files.
    with (directory/'challenge.pcm').open('xb') as output:output.write(data)
    with (directory/'challenge.json').open('x') as output:json.dump(manifest,output,indent=2);output.write('\n')
    return manifest


def pearson(left,right):
    if len(left)!=len(right) or not left:return 0.0
    length=len(left);a=sum(left)/length;b=sum(right)/length
    numerator=sum((x-a)*(y-b) for x,y in zip(left,right))
    aa=sum((x-a)**2 for x in left);bb=sum((y-b)**2 for y in right)
    return numerator/math.sqrt(aa*bb) if aa>0 and bb>0 else 0.0


def match_window(window,reference):
    """Find a fresh two-channel NRZ sequence, then independently compare all sample values."""
    if len(window)!=WINDOW*CHANNELS:raise ValueError('incomplete correlation window')
    frames=len(reference)//CHANNELS
    symbols=bytes(((reference[i*CHANNELS]>0)<<1)|(reference[i*CHANNELS+1]>0)
                  for i in range(0,frames,CHIP))
    doubled=symbols*2
    candidates=set()
    # The callback may begin in any sample of a source chip. Candidate search uses
    # only channel signs; the acceptance check below compares every actual sample.
    for shift in range(CHIP):
        needle=bytes(((window[i*CHANNELS]>0)<<1)|(window[i*CHANNELS+1]>0)
                     for i in range(shift,WINDOW,CHIP))
        found=doubled.find(needle)
        while found>=0 and found<len(symbols):
            for fraction in range(CHIP):candidates.add((found*CHIP+fraction-shift)%frames)
            found=doubled.find(needle,found+1)
    if not candidates:raise ValueError('fresh independent stereo challenge sequence missing')
    actual=[window[channel::CHANNELS] for channel in range(CHANNELS)]
    best=None
    for offset in candidates:
        expected=[array('h',(reference[((offset+i)%frames)*CHANNELS+channel] for i in range(WINDOW)))
                  for channel in range(CHANNELS)]
        scores=[pearson(actual[c],expected[c]) for c in range(CHANNELS)]
        cross=[abs(pearson(actual[c],expected[1-c])) for c in range(CHANNELS)]
        score=min(scores)
        if best is None or score>best['minimum_correlation']:
            best={'source_frame':offset,'correlations':scores,'cross_channel_correlations':cross,
                  'minimum_correlation':score}
    if best['minimum_correlation']<CORRELATION or max(best['cross_channel_correlations'])>0.25:
        raise ValueError('fresh PCM correlation/channel separation failed')
    return best


def phase_content(data,reference):
    values=pcm_values(data);frames=len(values)//CHANNELS
    if frames<2*WINDOW:raise ValueError('phase too short for independent disjoint content windows')
    start=match_window(values[:WINDOW*CHANNELS],reference)
    end=match_window(values[-WINDOW*CHANNELS:],reference)
    period=len(reference)//CHANNELS
    displacement=(end['source_frame']-start['source_frame']-(frames-WINDOW))%period
    error=min(displacement,period-displacement)
    if error>1:raise ValueError('PCM sequence discontinuity, stale replay, wrong sample rate or dropped frames')
    return {'frames':frames,'first_window':start,'last_window':end,'continuity_error_frames':error}


def integer(row,key,low=0):
    value=row.get(key)
    if type(value) is not int or value<low:raise ValueError('invalid '+key)
    return value


def load_reference(manifest_path,pcm_path,run_id):
    manifest=json.loads(Path(manifest_path).read_text());data=Path(pcm_path).read_bytes()
    expected={'version':1,'run_id':run_id,'rate':RATE,'channels':CHANNELS,'format':'S16LE',
              'frame_bytes':FRAME_BYTES,'frames':RATE,'chip_frames':CHIP,'pcm_file':'challenge.pcm'}
    if any(manifest.get(k)!=v or type(manifest.get(k)) is not type(v) for k,v in expected.items()):
        raise ValueError('challenge parameters/run mismatch')
    if re.fullmatch('[0-9a-f]{32}',manifest.get('challenge_id','')) is None:raise ValueError('fresh challenge id missing')
    if len(data)!=RATE*FRAME_BYTES or hashlib.sha256(data).hexdigest()!=manifest.get('sha256'):
        raise ValueError('challenge file changed or truncated')
    values=pcm_values(data)
    if any(abs(v)!=8192 for v in values):raise ValueError('not a fresh host NRZ challenge')
    if abs(pearson(values[::2],values[1::2]))>0.1:raise ValueError('source channels are not independent')
    return manifest,values


def timestamp_phase(snapshots,phase):
    points=[r for r in snapshots if r.get('phase')==phase]
    if len(points)!=3:raise ValueError('three actual timestamp/frame snapshots required per phase')
    previous=None
    for row in points:
        for key in ['timestamp_result','frames_result']:
            if integer(row,key)!=0:raise ValueError('public Capturer timestamp/frame query failed')
        position=integer(row,'position');timestamp=integer(row,'timestamp_ns',1)
        before=integer(row,'before_ns',1);after=integer(row,'after_ns',1)
        frames=integer(row,'frames_read',1);copied=integer(row,'copied_bytes',1)
        if integer(row,'phase',1)!=phase or frames+4800<position or frames+4800<copied//FRAME_BYTES:
            raise ValueError('native frame position/read count disagrees with actual stored PCM')
        if copied%FRAME_BYTES or after<before or after-before>200000000 or not before-1000000000<=timestamp<=after+100000000:
            raise ValueError('timestamp clock domain/query interval invalid')
        if previous:
            p,t,f,b=previous;delta=timestamp-t;advance=position-p
            if delta<200000000 or advance<=0 or frames<=f or copied<=b:
                raise ValueError('native frames/timestamps/actual stored bytes did not progress')
            observed=advance*1000000000/delta
            if not RATE*0.98<=observed<=RATE*1.02:raise ValueError('actual timestamp/sample rate mismatch')
        previous=(position,timestamp,frames,copied)
    return {'phase':phase,'snapshots':points}


CONFIG_STEPS=[('create',0),('invalid_channels',1),('rate',0),('channels',0),('format',0),
 ('encoding',0),('latency',0),('microphone',0),('read_callback',0),('error_callback',0),('generate',0),
 ('get_rate',0),('get_channels',0),('get_format',0),('prepared',0),('prepared.value',1),('pause_before_start',2),
 ('start',0),('running',0),('running.value',2),('pause',0),('paused',0),('paused.value',5),('flush',0),
 ('resume',0),('resumed',0),('resumed.value',2),('stop',0),('stopped',0),('stopped.value',3),('release',0),('destroy',0)]


def verify(results_path,pcm_directory,manifest_path,challenge_path,run_id,identity_path):
    if re.fullmatch('[0-9a-f]{32}',run_id or '') is None:raise ValueError('explicit run id required')
    manifest,reference=load_reference(manifest_path,challenge_path,run_id)
    identity_text=Path(identity_path).read_text()
    if identity_text.startswith('org.harmonycontrib.capabilityaudit:\n'):identity_text=identity_text.split('\n',1)[1]
    app=json.loads(identity_text)['applicationInfo'];uid=app.get('uid')
    if type(uid) is not int or uid<20000000 or app.get('isSystemApp') is not False or app.get('appPrivilegeLevel')!='normal':
        raise ValueError('independent normal non-system application identity required')
    rows=[json.loads(line) for line in Path(results_path).read_text().splitlines() if line.strip()]
    if not rows or any(type(r) is not dict or r.get('run_id')!=run_id for r in rows):raise ValueError('stale or mixed capture results')
    if sum(r.get('type')=='identity' for r in rows)!=1 or sum(r.get('type')=='summary' for r in rows)!=1:
        raise ValueError('duplicate capture identity/summary')
    head,tail=rows[0],rows[-1]
    if head.get('type')!='identity' or head.get('uid')!=uid or head.get('euid')!=uid or head.get('mode')!='granted':
        raise ValueError('capture must run inside the granted normal HAP process')
    if tail.get('type')!='summary' or tail.get('cycles')!=2 or tail.get('candidate_ok') is not True:
        raise ValueError('public capture native lifecycle candidate failed')
    if any(r.get('type') not in {'identity','summary','step','format','snapshot','quiet','chunk','pcm_file'} for r in rows):
        raise ValueError('unexpected capture failure/result event')
    evidence=[]
    for cycle in [1,2]:
        group=[r for r in rows[1:-1] if r.get('cycle')==cycle]
        steps=[r for r in group if r.get('type')=='step']
        if len(steps)!=len(CONFIG_STEPS):raise ValueError('incomplete capture lifecycle steps')
        last_time=0
        for row,(name,expected) in zip(steps,CONFIG_STEPS):
            actual=integer(row,'actual');requested=integer(row,'expected');clock=integer(row,'monotonic_ns',1)
            if row.get('name')!=name or actual!=expected or requested!=expected or clock<last_time:
                raise ValueError('capture lifecycle/boundary result mismatch')
            last_time=clock
        formats=[r for r in group if r.get('type')=='format']
        if len(formats)!=1 or any(type(formats[0].get(k)) is not int or formats[0].get(k)!=v for k,v in {'rate':RATE,'channels':2,'sample_format':1,'frame_bytes':4}.items()):
            raise ValueError('actual public capturer format mismatch')
        quiet=[r for r in group if r.get('type')=='quiet']
        if [r.get('name') for r in quiet]!=['paused','stopped','released'] or any(
            integer(r,'before_bytes')!=integer(r,'after_bytes') or integer(r,'unexpected')!=0 for r in quiet):
            raise ValueError('capturer delivered data after pause/stop/release')
        files=[r for r in group if r.get('type')=='pcm_file'];expected_name=f'audio-capture-{run_id}-cycle{cycle}.pcm'
        if len(files)!=1 or files[0].get('basename')!=expected_name or files[0].get('persisted') is not True:
            raise ValueError('fresh private capture file missing')
        item=files[0];pcm_path=Path(pcm_directory)/expected_name
        if pcm_path.is_symlink() or not 0<pcm_path.stat().st_size<=RATE*FRAME_BYTES*8:
            raise ValueError('invalid private PCM file type/size')
        data=pcm_path.read_bytes()
        if len(data)!=integer(item,'bytes',1) or len(data)!=integer(item,'written_bytes',1) or any(
            integer(item,key)!=0 for key in ['invalid_buffers','unexpected_buffers','callback_error']):
            raise ValueError('capture PCM was truncated, invalid or errored')
        chunks=[r for r in group if r.get('type')=='chunk'];offset=0;clock=0;phase_data={1:bytearray(),2:bytearray()};last_phase=1
        for row in chunks:
            length=integer(row,'bytes',1);current=integer(row,'monotonic_ns',1);phase=integer(row,'phase',1)
            if integer(row,'offset')!=offset or length%4 or phase not in (1,2) or phase<last_phase or current<clock:
                raise ValueError('capture callback data ranges/phase/timing invalid')
            phase_data[phase].extend(data[offset:offset+length]);offset+=length;clock=current;last_phase=phase
        if offset!=len(data):raise ValueError('stored PCM not fully supported by actual callback chunks')
        snapshots=[r for r in group if r.get('type')=='snapshot']
        if len(snapshots)!=6 or any(integer(r,'copied_bytes',1)>len(data) for r in snapshots):
            raise ValueError('invalid public capture timestamp coverage')
        evidence.append({'cycle':cycle,'pcm_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'phases':[{'phase':p,'content':phase_content(phase_data[p],reference),
                       'timing':timestamp_phase(snapshots,p)} for p in [1,2]]})
    if any(r.get('type') not in ('identity','summary') and r.get('cycle') not in (1,2) for r in rows):
        raise ValueError('unexpected capture cycle')
    return {'status':'candidate_pcm_diagnostic_pass','run_id':run_id,'challenge':manifest,'cycles':evidence,
        'scope':'ordinary public Capturer raw PCM/lifecycle/clock diagnostic only; permission revocation, Recorder and final gate owned by parent',
        'closed_requirements':0,'first_artifact_behavior_gate_passed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    create=sub.add_parser('generate');create.add_argument('--directory',type=Path,required=True);create.add_argument('--run-id',required=True)
    check=sub.add_parser('verify')
    for name in ['results','pcm-directory','manifest','challenge','application-identity','output']:check.add_argument('--'+name,type=Path,required=True)
    check.add_argument('--run-id',required=True);args=parser.parse_args()
    if args.action=='generate':print(json.dumps(generate(args.directory,args.run_id)));return 0
    try:result=verify(args.results,args.pcm_directory,args.manifest,args.challenge,args.run_id,args.application_identity)
    except (OSError,ValueError,TypeError,KeyError) as error:result={'status':'fail','error':str(error),'closed_requirements':0,'first_artifact_behavior_gate_passed':False}
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':result['status'],'closed_requirements':0}));return 0 if result['status']=='candidate_pcm_diagnostic_pass' else 1

if __name__=='__main__':raise SystemExit(main())
