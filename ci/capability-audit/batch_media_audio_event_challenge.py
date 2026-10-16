#!/usr/bin/env python3
"""Independent actual event/PCM diagnosis; token/second-app/service evidence stays parent-owned."""
import argparse,importlib.util,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('event_pcm_oracle',HERE/'batch_media_audio_capture_challenge.py');pcm=importlib.util.module_from_spec(spec);spec.loader.exec_module(pcm)

def verify_primer(rows,directory,reference,run,ready,ack,main_steps):
 # Explicitly separate the contender's genuine MIC primer from VOIP focus input.
 steps=[r for r in rows if r.get('type')=='event_primer_step']
 names=['create','rate','channels','format','encoding','source','read_callback','interrupt_callback','error_callback','generate','start','stop','release','destroy']
 if [r.get('name') for r in steps]!=names or any(r.get('actual')!=0 for r in steps):raise ValueError('real MIC primer lifecycle missing or failed')
 if not steps[-2]['monotonic_ns']<=main_steps[0]['monotonic_ns']:raise ValueError('VOIP generated before real primer release')
 snapshots=[r for r in rows if r.get('type')=='event_snapshot' and r.get('point')=='primer_baseline']
 if len(snapshots)!=50 or any(r.get('phase')!=0 or r.get('state_result')!=0 or r.get('state')!=2 or r.get('frames_result')!=0 or r.get('timestamp_result')!=0 or r.get('invalid')!=0 for r in snapshots):raise ValueError('MIC primer was not actually RUNNING with valid timestamps')
 first,last=snapshots[0],snapshots[-1];delta=last['timestamp_ns']-first['timestamp_ns']
 if delta<=0 or not 48000*.98<=(last['position']-first['position'])*1e9/delta<=48000*1.02:raise ValueError('MIC primer frame/timestamp rate mismatch')
 items=[r for r in rows if r.get('type')=='event_primer_pcm'];name=f'audio-event-{run}-mode2-primer-full.pcm'
 if len(items)!=1:raise ValueError('MIC primer PCM file missing')
 data=(Path(directory)/name).read_bytes();item=items[0]
 if item.get('basename')!=name or item.get('persisted')is not True or item.get('bytes')!=len(data) or item.get('invalid')!=0 or not 0<len(data)<=48000*4*40:raise ValueError('MIC primer PCM file failed or truncated')
 chunks=[r for r in rows if r.get('type')=='event_primer_chunk'];offset=0;previous=0
 for row in chunks:
  size=row.get('bytes');time=row.get('monotonic_ns')
  if type(size)is not int or size<=0 or size%4 or row.get('offset')!=offset or type(time)is not int or time<previous or row.get('phase')!=0:raise ValueError('MIC primer actual PCM callback ranges invalid')
  offset+=size;previous=time
 if offset!=len(data):raise ValueError('MIC primer PCM callback ranges incomplete')
 if not any(ready['monotonic_ns']-200000000<=r['monotonic_ns']<=ack['monotonic_ns'] for r in chunks):raise ValueError('MIC primer has no fresh PCM around contender readiness')
 points=[r for r in rows if r.get('type')=='event_primer_checkpoint'];name=f'audio-event-{run}-mode2-primer.pcm'
 if len(points)!=1:raise ValueError('MIC primer checkpoint missing')
 checkpoint=(Path(directory)/name).read_bytes();point=points[0]
 if point.get('basename')!=name or point.get('persisted')is not True or point.get('bytes')!=len(checkpoint) or data[:len(checkpoint)]!=checkpoint or point['monotonic_ns']>ready['monotonic_ns']:raise ValueError('MIC primer checkpoint changed or late')
 correlation=pcm.phase_content(checkpoint[4800*4:-4800*4],reference)
 if any(r.get('kind')==2 or (r.get('kind')==1 and r.get('hint')==3) for r in rows if r.get('type')=='event_primer_callback'):raise ValueError('MIC primer errored or lost focus before deliberate VOIP start')
 return {'checkpoint':point,'PCM_correlation':correlation,'bytes':len(data),'closed_requirements':0}

def verify(results,directory,manifest,challenge,identity,run,mode):
 _,reference=pcm.load_reference(manifest,challenge,run)
 text=Path(identity).read_text()
 if '\n'in text and re.fullmatch(r'org\.harmonycontrib\.capabilityaudit[a-zA-Z0-9_.]*:',text.split('\n',1)[0]):text=text.split('\n',1)[1]
 app=json.loads(text)['applicationInfo'];uid=app.get('uid')
 if type(uid)is not int or uid<20000000 or app.get('isSystemApp')is not False or app.get('appPrivilegeLevel')!='normal':raise ValueError('independent ordinary application identity required')
 rows=[json.loads(line) for line in Path(results).read_text().splitlines() if line.strip()]
 if not rows or any(r.get('run_id')!=run for r in rows):raise ValueError('stale or mixed event evidence')
 head,tail=rows[0],rows[-1]
 if head.get('type')!='event_identity' or head.get('mode')!=mode or head.get('uid')!=uid or head.get('euid')!=uid:raise ValueError('actual ordinary process identity mismatch')
 if tail.get('type')!='event_summary' or tail.get('mode')!=mode or tail.get('candidate_complete')is not True:raise ValueError('native action protocol incomplete')
 steps=[r for r in rows if r.get('type')=='event_step'];names=['create','rate','channels','format','encoding','source','read_callback','interrupt_callback','error_callback','generate','start']+(['restart_after_focus'] if mode==1 else [])+['release','destroy']
 if [r.get('name') for r in steps]!=names or any(r.get('actual')!=0 for r in steps):raise ValueError('public stream operation failed')
 signals=['revoke'] if mode==0 else ['focus_begin','focus_end'] if mode==1 else ['contender_start','contender_stop']
 ready=[r for r in rows if r.get('type')=='event_ready'];acks=[r for r in rows if r.get('type')=='event_ack']
 if [r.get('action') for r in ready]!=signals or [r.get('action') for r in acks]!=signals:raise ValueError('action handshake sequence incomplete')
 for source,ack in zip(ready,acks):
  if re.fullmatch('[0-9a-f]{32}',source.get('nonce',''))is None or ack.get('nonce')!=source['nonce'] or not 0<=ack['monotonic_ns']-source['monotonic_ns']<=15000000000:raise ValueError('nonce/action replay or invalid acknowledgment clock')
 if len({r['nonce'] for r in ready})!=len(ready):raise ValueError('reused action nonce')
 files=[r for r in rows if r.get('type')=='event_pcm']
 if len(files)!=1:raise ValueError('actual PCM evidence missing')
 item=files[0];name=f'audio-event-{run}-mode{mode}.pcm';data=(Path(directory)/name).read_bytes()
 if item.get('basename')!=name or item.get('bytes')!=len(data) or item.get('persisted')is not True or item.get('invalid')!=0 or len(data)>48000*4*40:raise ValueError('actual PCM file failed/truncated/oversized')
 chunks=[r for r in rows if r.get('type')=='event_chunk'];offset=0;previous=0
 for row in chunks:
  size=row.get('bytes');time=row.get('monotonic_ns')
  if type(size)is not int or size<=0 or size%4 or row.get('offset')!=offset or type(time)is not int or time<previous or row.get('phase')not in [1,2,3]:raise ValueError('actual PCM callback ranges/clock invalid')
  offset+=size;previous=time
 if offset!=len(data):raise ValueError('actual PCM ranges incomplete')
 baseline_ready=ready[1] if mode==2 else ready[0]
 pre=b''.join(data[r['offset']:r['offset']+r['bytes']] for r in chunks if r['phase']==1 and r['monotonic_ns']<baseline_ready['monotonic_ns']-100000000)
 pre=pre[4800*4:] # exclude startup; two disjoint fresh correlation windows remain
 baseline=pcm.phase_content(pre,reference)
 snapshots=[r for r in rows if r.get('type')=='event_snapshot'];initial=[r for r in snapshots if r.get('point')=='baseline']
 if len(initial)!=50 or any(r.get('state_result')!=0 or r.get('state')!=2 or r.get('frames_result')!=0 or r.get('timestamp_result')!=0 or r.get('invalid')!=0 for r in initial):raise ValueError('actual running baseline states/frame/timestamp queries failed')
 first,last=initial[0],initial[-1];advance=last['position']-first['position'];delta=last['timestamp_ns']-first['timestamp_ns']
 if delta<=0 or not 48000*.98<=advance*1e9/delta<=48000*1.02:raise ValueError('native baseline frame/timestamp rate mismatch')
 checkpoints=[r for r in rows if r.get('type')=='event_checkpoint']
 if len(checkpoints)!=1:raise ValueError('fresh pre-action PCM checkpoint required')
 checkpoint=checkpoints[0];checkpoint_name=f'audio-event-{run}-mode{mode}-baseline.pcm';checkpoint_data=(Path(directory)/checkpoint_name).read_bytes()
 if checkpoint.get('basename')!=checkpoint_name or checkpoint.get('persisted')is not True or checkpoint.get('bytes')!=len(checkpoint_data) or data[:len(checkpoint_data)]!=checkpoint_data:raise ValueError('pre-action PCM checkpoint changed')
 pcm.phase_content(checkpoint_data[4800*4:-4800*4],reference)
 intervals=[r for r in rows if r.get('type')=='event_start_interval']
 if len(intervals)!=1 or intervals[0].get('actual')!=0 or type(intervals[0].get('before_ns'))is not int or not 0<=intervals[0].get('after_ns',-1)-intervals[0]['before_ns']<2000000000:raise ValueError('actual Start call interval missing/invalid')
 callbacks=[r for r in rows if r.get('type')=='event_callback']
 def quiet(action,point):
  ack=next(r for r in acks if r['action']==action);after=ack['monotonic_ns']+200000000
  post=[r for r in snapshots if r.get('point')==point and r.get('before_ns',0)>=after]
  if len(post)<10 or any(r.get('state_result')!=0 or r.get('state')not in [3,4,5] for r in post):raise ValueError('actual stream did not stop/pause after external action')
  leaked=b''.join(data[r['offset']:r['offset']+r['bytes']] for r in chunks if r['monotonic_ns']>=after and (mode==0 or r['phase']==2))
  if any(leaked):raise ValueError('real nonzero microphone samples continued after denial/interruption')
  return {'observations':len(post),'post_action_pcm_bytes':len(leaked),'post_action_nonzero_bytes':0}
 report={'status':'candidate_audio_event_PCM_diagnostic_pass','run_id':run,'mode':mode,'uid':uid,'baseline':baseline,'start_interval':intervals[0],'checkpoint':checkpoint,'signals':ready,'acks':acks,'callbacks':callbacks,'closed_requirements':0,'first_artifact_behavior_gate_passed':False,'external_token_or_second_app_policy_evidence_required':True}
 if mode==2:report['primer']=verify_primer(rows,directory,reference,run,ready[0],acks[0],steps)
 if mode==0:
  report['quiet']=quiet('revoke','after_revoke');restarts=[r for r in rows if r.get('type')=='event_restart_after_revoke']
  if len(restarts)!=1 or type(restarts[0].get('actual'))is not int or restarts[0]['actual']==0:raise ValueError('Start succeeded after live microphone revocation')
  report['denied_restart']=restarts[0]
 elif mode==1:
  report['quiet']=quiet('focus_begin','interrupted')
  if not any(r.get('kind')==1 and r.get('code')==0 and r.get('hint')==3 and ready[0]['monotonic_ns']<=r.get('monotonic_ns',0)<=acks[0]['monotonic_ns'] for r in callbacks):raise ValueError('actual forced STOP focus callback missing')
  resumed=b''.join(data[r['offset']:r['offset']+r['bytes']] for r in chunks if r['phase']==3)
  report['resumed']=pcm.phase_content(resumed[4800*4:],reference)
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['results','directory','manifest','challenge','identity','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--run-id',required=True);p.add_argument('--mode',type=int,choices=[0,1,2],required=True);a=p.parse_args()
 result=verify(a.results,a.directory,a.manifest,a.challenge,a.identity,a.run_id,a.mode)
 with a.output.open('x') as out:json.dump(result,out,indent=2);out.write('\n')
 print(result['status'])
if __name__=='__main__':main()
