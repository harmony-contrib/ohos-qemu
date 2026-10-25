#!/usr/bin/env python3
"""Fresh external PCM + public surface challenge, independent real-file decode diagnostic."""
import argparse
from array import array
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('batch_recorder_pcm',HERE/'batch_media_audio_capture_challenge.py')
pcm=importlib.util.module_from_spec(spec);spec.loader.exec_module(pcm)
# AAC candidate protocol: slower real random input symbols survive lossy encoding.
pcm.CHIP=64;pcm.CORRELATION=0.94
FRAMES=60;CYCLES=2;WIDTH=HEIGHT=64;TILES=64

def sha(data):return hashlib.sha256(data).hexdigest()
def generate(directory,run):
 if re.fullmatch('[0-9a-f]{32}',run or '') is None:raise ValueError('explicit fresh run id required')
 directory=Path(directory)
 if directory.exists() and any(directory.iterdir()):raise ValueError('preserve previous challenge directory')
 manifest=pcm.generate(directory,run)
 video=bytes(48+12*secrets.randbelow(14) for _ in range(FRAMES*CYCLES*TILES))
 video_name=f'recorder-{run}-video.bin'
 with (directory/video_name).open('xb') as out:out.write(video)
 os.chmod(directory/video_name,0o600)
 combined={'version':1,'protocol':'public-avrecorder-aac-avc-v1','run_id':run,'audio':manifest,
  'video':{'file':video_name,'sha256':sha(video),'width':WIDTH,'height':HEIGHT,'fps':30,'frames_per_cycle':FRAMES,'cycles':CYCLES,'tiles_per_frame':TILES,'tile_pixels':8}}
 with (directory/'recorder-challenge.json').open('x') as out:json.dump(combined,out,indent=2);out.write('\n')
 return combined

def load_reference(directory,run):
 directory=Path(directory);manifest=json.loads((directory/'recorder-challenge.json').read_text())
 if manifest.get('protocol')!='public-avrecorder-aac-avc-v1' or manifest.get('run_id')!=run:raise ValueError('recorder challenge mismatch')
 audio,reference=pcm.load_reference(directory/'challenge.json',directory/'challenge.pcm',run)
 if manifest.get('audio')!=audio:raise ValueError('audio challenge changed')
 expected={'file':f'recorder-{run}-video.bin','width':64,'height':64,'fps':30,'frames_per_cycle':60,'cycles':2,'tiles_per_frame':64,'tile_pixels':8}
 if any(manifest.get('video',{}).get(k)!=v for k,v in expected.items()):raise ValueError('video challenge parameters changed')
 video=(directory/expected['file']).read_bytes()
 if len(video)!=7680 or sha(video)!=manifest['video'].get('sha256') or any(x<48 or x>204 for x in video):raise ValueError('video challenge changed/truncated')
 return manifest,reference,video

def rgb_content(data,video,cycle):
 frame_bytes=WIDTH*HEIGHT*3
 if len(data)!=FRAMES*frame_bytes:raise ValueError('decode must yield exactly60 challenged video frames')
 maximum=0;total=0;count=0
 for frame in range(FRAMES):
  tiles=video[((cycle-1)*FRAMES+frame)*TILES:((cycle-1)*FRAMES+frame+1)*TILES]
  for tile,value in enumerate(tiles):
   row,column=divmod(tile,8)
   for y in range(row*8+3,row*8+5):
    for x in range(column*8+3,column*8+5):
     offset=frame*frame_bytes+(y*WIDTH+x)*3
     for actual in data[offset:offset+3]:
      error=abs(actual-value);maximum=max(maximum,error);total+=error;count+=1
 if maximum>14 or total/count>4:raise ValueError('independent decoded pixels do not match fresh input tiles/frame order')
 return {'frames':FRAMES,'checked_channel_values':count,'maximum_error':maximum,'mean_error':total/count}

def timeline(probe,frame_rows,steps,pause):
 streams=probe.get('streams',[])
 audio=[s for s in streams if s.get('codec_type')=='audio'];video=[s for s in streams if s.get('codec_type')=='video']
 if len(streams)!=2 or len(audio)!=1 or len(video)!=1:raise ValueError('real encoded audio/video tracks required')
 a,v=audio[0],video[0]
 if a.get('codec_name')!='aac' or int(a.get('sample_rate',0))!=48000 or a.get('channels')!=2:raise ValueError('actual AAC format mismatch')
 if v.get('codec_name')!='h264' or v.get('width')!=64 or v.get('height')!=64:raise ValueError('actual AVC format mismatch')
 frames=[f for f in probe.get('frames',[]) if f.get('media_type')=='video']
 if len(frames)!=FRAMES:raise ValueError('missing, duplicate or dropped encoded video frames')
 pts=[float(f['best_effort_timestamp_time']) for f in frames]
 if any(y<=x or not 0.015<=y-x<=0.09 for x,y in zip(pts,pts[1:])) or not 1.85<=pts[-1]-pts[0]<=2.1:raise ValueError('video PTS/rate/pause gap invalid')
 by_name={s['name']:s for s in steps};removed=(by_name['resume']['monotonic_ns']-by_name['pause']['monotonic_ns'])/1e9
 if not 0.28<=removed<=1:raise ValueError('pause duration/handshake invalid')
 origin=frame_rows[0]['input_ns']
 for row,point in zip(frame_rows,pts):
  expected=(row['input_ns']-origin)/1e9-(removed if row['phase']==2 else 0)
  if abs(point-pts[0]-expected)>0.06:raise ValueError('encoded PTS disagrees with real surface input/pause removal')
 durations=[]
 for stream in [a,v]:
  packets=[p for p in probe.get('packets',[]) if p.get('stream_index')==stream['index']]
  if not packets:raise ValueError('real encoded packets missing')
  times=[float(p['pts_time']) for p in packets];dts=[float(p['dts_time']) for p in packets]
  if any(y<=x for x,y in zip(dts,dts[1:])):raise ValueError('packet DTS did not advance')
  durations.append(max(times)-min(times)+float(packets[-1].get('duration_time','0')))
 if any(not 1.85<=d<=2.2 for d in durations) or abs(durations[0]-durations[1])>0.18:raise ValueError('audio/video duration or synchronization invalid')
 if pause['after_ns']-pause['before_ns']<280000000:raise ValueError('actual pause interval absent')
 return {'video_pts':pts,'track_durations':durations,'removed_pause_seconds':removed}

STEPS=['create','state_callback','error_callback','output_open','prepare','input_surface','surface_geometry','surface_format','surface_usage','surface_timeout','start','pause','resume','stop','reset','release']
def cycle_rows(rows,cycle,run,uid):
 group=[r for r in rows if r.get('cycle')==cycle]
 steps=[r for r in group if r.get('type')=='recorder_step']
 if [r.get('name') for r in steps]!=STEPS or any(r.get('actual')!=0 or r.get('expected')!=0 for r in steps):raise ValueError('actual public Recorder lifecycle failed')
 frames=[r for r in group if r.get('type')=='recorder_frame']
 if len(frames)!=FRAMES or [r.get('frame') for r in frames]!=list(range(FRAMES)):raise ValueError('incomplete input frame sequence')
 if any(r.get('phase')!=(1 if r['frame']<30 else 2) or r.get('flushed') is not True or type(r.get('input_ns'))is not int or r['input_ns']<=0 or r.get('after_ns',0)<r['input_ns'] for r in frames):raise ValueError('surface input failure or invalid timestamp')
 states=[r for r in group if r.get('type')=='recorder_state']
 if [r.get('state') for r in states]!=[1,2,3,2,4,0,5] or any(r.get('reason')!=0 for r in states):raise ValueError('actual Recorder state callbacks mismatch')
 files=[r for r in group if r.get('type')=='recorder_file'];pauses=[r for r in group if r.get('type')=='recorder_pause']
 if len(files)!=1 or len(pauses)!=1 or files[0].get('basename')!=f'recorder-{run}-cycle{cycle}.mp4' or files[0].get('persisted') is not True:raise ValueError('private actual file/pause evidence missing')
 if any(r.get('type') not in {'recorder_step','recorder_frame','recorder_state','recorder_pause','recorder_file'} for r in group):raise ValueError('native failure/error event present')
 return files[0],frames,steps,pauses[0]

def decode(ffmpeg,ffprobe,path,evidence):
 if not Path(ffmpeg).is_file() or not Path(ffprobe).is_file():raise ValueError('explicit real ffmpeg/ffprobe executables required')
 evidence.mkdir(parents=True,exist_ok=False)
 commands=[[str(ffprobe),'-v','error','-show_streams','-show_frames','-show_packets','-of','json',str(path)],
  [str(ffmpeg),'-v','error','-threads','1','-i',str(path),'-map','0:v:0','-frames:v','61','-fps_mode','passthrough','-enc_time_base','1:1000000','-pix_fmt','rgb24','-f','rawvideo',str(evidence/'video.rgb')],
  [str(ffmpeg),'-v','error','-threads','1','-i',str(path),'-map','0:a:0','-t','3','-c:a','pcm_s16le','-f','s16le',str(evidence/'audio.pcm')]]
 for index,command in enumerate(commands):
  result=subprocess.run(command,capture_output=True,timeout=30)
  (evidence/f'command{index}.json').write_text(json.dumps(command)+'\n');(evidence/f'command{index}.stderr').write_bytes(result.stderr)
  (evidence/f'command{index}.stdout').write_bytes(result.stdout)
  if result.returncode or result.stderr:raise ValueError('independent real decoder reported a failure/error')
  if index==0:
   preliminary=json.loads(result.stdout)
   streams=preliminary.get('streams',[])
   for stream in streams:
    if stream.get('codec_type')=='video' and (stream.get('codec_name')!='h264' or stream.get('width')!=64 or stream.get('height')!=64):raise ValueError('reject unexpected decoder geometry/codec before allocating raw output')
    if stream.get('codec_type')=='audio' and (stream.get('codec_name')!='aac' or int(stream.get('sample_rate',0))!=48000 or stream.get('channels')!=2):raise ValueError('reject unexpected decoder audio format before allocating raw output')
   if len(streams)!=2:raise ValueError('exactly two media streams required before decode')
 probe=json.loads((evidence/'command0.stdout').read_text())
 # ffprobe interleaves -show_packets and -show_frames under packets_and_frames.
 if 'packets_and_frames'in probe:
  probe['frames']=[r for r in probe['packets_and_frames'] if r.get('type')=='frame']
  probe['packets']=[r for r in probe['packets_and_frames'] if r.get('type')=='packet']
 return probe,(evidence/'video.rgb').read_bytes(),(evidence/'audio.pcm').read_bytes()

def verify(results,directory,challenge,identity,run,ffmpeg,ffprobe,evidence):
 manifest,reference,video=load_reference(challenge,run)
 text=Path(identity).read_text()
 if text.startswith('org.harmonycontrib.capabilityaudit:\n'):text=text.split('\n',1)[1]
 app=json.loads(text)['applicationInfo'];uid=app.get('uid')
 if type(uid)is not int or uid<20000000 or app.get('isSystemApp')is not False or app.get('appPrivilegeLevel')!='normal':raise ValueError('independent normal application identity required')
 rows=[json.loads(line) for line in Path(results).read_text().splitlines() if line.strip()]
 if not rows or any(r.get('run_id')!=run for r in rows):raise ValueError('mixed or stale recorder evidence')
 head,tail=rows[0],rows[-1]
 if head.get('type')!='recorder_identity' or head.get('uid')!=uid or head.get('euid')!=uid or head.get('expected_denied')is not False:raise ValueError('actual ordinary granted HAP required')
 if tail.get('type')!='recorder_summary' or tail.get('cycles')!=2 or tail.get('candidate_ok')is not True or tail.get('independent_decode_required')is not True:raise ValueError('native Recorder lifecycle incomplete')
 if sum(r.get('type')=='recorder_identity' for r in rows)!=1 or sum(r.get('type')=='recorder_summary' for r in rows)!=1:raise ValueError('duplicate native summary/identity')
 if rows[1].get('type')!='recorder_step' or rows[1].get('cycle')!=0 or rows[1].get('name')!='video_challenge' or rows[1].get('actual')!=0:raise ValueError('video source challenge unavailable')
 reports=[]
 for cycle in [1,2]:
  item,frames,steps,pause=cycle_rows(rows,cycle,run,uid);path=Path(directory)/item['basename'];data=path.read_bytes()
  if not 1024<=len(data)<=16*1024*1024 or item.get('bytes')!=len(data):raise ValueError('output file changed/truncated/oversized')
  probe,rgb,audio=decode(ffmpeg,ffprobe,path,Path(evidence)/f'cycle{cycle}')
  pixels=rgb_content(rgb,video,cycle);timing=timeline(probe,frames,steps,pause)
  values=pcm.pcm_values(audio);count=len(values)//2
  if not 92000<=count<=105600:raise ValueError('actual decoded audio length mismatch')
  phases=[]
  for start in [8192,56192]:phases.append(pcm.phase_content(audio[start*4:(start+32768)*4],reference))
  actual=(phases[1]['first_window']['source_frame']-phases[0]['first_window']['source_frame'])%48000
  expected=timing['removed_pause_seconds']*48000%48000
  difference=(actual-expected)%48000
  if min(difference,48000-difference)>2400:raise ValueError('captured source did not advance during actual pause')
  reports.append({'cycle':cycle,'file_sha256':sha(data),'pixels':pixels,'timing':timing,'audio_phases':phases,'decoded_audio_frames':count})
 return {'status':'candidate_recorder_decode_diagnostic_pass','run_id':run,'challenge':manifest,'cycles':reports,'closed_requirements':0,'first_artifact_behavior_gate_passed':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
 gen=sub.add_parser('generate');gen.add_argument('--directory',type=Path,required=True);gen.add_argument('--run-id',required=True)
 check=sub.add_parser('verify')
 for key in ['results','directory','challenge','identity','ffmpeg','ffprobe','evidence','output']:check.add_argument('--'+key,type=Path,required=True)
 check.add_argument('--run-id',required=True);args=parser.parse_args()
 if args.action=='generate':print(json.dumps(generate(args.directory,args.run_id)));return
 result=verify(args.results,args.directory,args.challenge,args.identity,args.run_id,args.ffmpeg,args.ffprobe,args.evidence)
 with args.output.open('x') as out:json.dump(result,out,indent=2);out.write('\n')
 print(result['status'])
if __name__=='__main__':main()
