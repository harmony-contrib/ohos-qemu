"""Fresh remote-MIC challenge tolerant of the real DAudio AAC/OPUS codec.

Only sink ALSA playback receives the target PCM. Source AudioCapturer persists
actual remote PCM; independent host analysis decodes each channel separately.
No producer-success flag or getter substitutes for actual recorded content.
"""
from array import array
import hashlib
import math
from pathlib import Path
import re
import secrets
import sys

RATE=48000
FREQUENCIES=((400,600,800,1000,1200,1400,1600,1800),(2200,2400,2600,2800,3000,3200,3400,3600))
PHASES=('running','paused','resumed')


def require(ok,text):
    if not ok:raise ValueError(text)


def reference(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),'actual regular PCM only')
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare(output,run):
    require(re.fullmatch('[a-f0-9]{32}',run),'fresh actual run nonce')
    path=Path(output)/('remote-mic-'+run+'.pcm');require(not path.exists(),'fresh challenge path')
    # Four distinct paired symbols synchronize the independent channel order;
    # twenty random pairs then identify this run across lossy transport codecs.
    sequence=[[0,7],[7,0],[1,6],[6,1]]
    for _ in range(20):
        sequence.append([secrets.choice([i for i in range(8) if i!=sequence[-1][c]]) for c in (0,1)])
    samples=array('h')
    for pair in sequence:
        for n in range(12000):
            envelope=min(1.0,n/240,(9599-n)/240) if n<9600 else 0.0
            samples.extend(round(10000*envelope*math.sin(2*math.pi*FREQUENCIES[c][pair[c]]*n/RATE)) for c in (0,1))
    if sys.byteorder!='little':samples.byteswap()
    with path.open('xb') as stream:stream.write(samples.tobytes())
    return {'run_id':run,'challenge_id':secrets.token_hex(16),'pcm':reference(path),'rate':RATE,'channels':2,
        'format':'S16LE','frame_bytes':4,'frames':RATE*6,'symbols':sequence,'frequencies':[list(v) for v in FREQUENCIES],
        'sync_pairs':4,'tone_ms':200,'gap_ms':50,'repeat':10,'timeout_ms':70000,'provision_to':'sink_ALSA_cable_only'}


def inspect_segment(data,challenge,phase):
    require(phase in PHASES and len(data)%4==0 and RATE*4*4<=len(data)<=16*1024*1024,'actual >=4s stereo recorded phase')
    pcm=array('h');pcm.frombytes(data)
    if sys.byteorder!='little':pcm.byteswap()
    # Exclude the first750ms only for real codec/transport buffered output.
    guard_frames=RATE*3//4;guarded=pcm[guard_frames*2:]
    require(len(guarded)>=RATE*2*3,'at least3s actual post-guard PCM')
    summary={'phase':phase,'bytes':len(data),'frames':len(pcm)//2,'guard_frames':guard_frames,
        'guarded_peak':max(abs(v) for v in guarded),'channels':[]}
    if phase=='paused':
        # DMicClient explicitly supplies zero PCM on both real pause paths.
        # Continuing callbacks/bytes are required; absence of bytes cannot pass.
        summary['nonzero_samples']=sum(v!=0 for v in guarded)
        require(summary['nonzero_samples']==0,'paused remote microphone must persist actual zero PCM, not missing callbacks')
        return summary
    all_frequencies=FREQUENCIES[0]+FREQUENCIES[1]
    sequences=[]
    for channel in (0,1):
        values=list(pcm[channel::12]);observed=[];frames=[]
        for start in range(0,len(values)-800+1,800):
            block=values[start:start+800];energy=sum(v*v for v in block);scores=[]
            for freq in all_frequencies:
                coefficient=2*math.cos(2*math.pi*freq/8000);s1=s2=0.0
                for sample in block:
                    current=sample+coefficient*s1-s2;s2=s1;s1=current
                scores.append(max(0.0,s1*s1+s2*s2-coefficient*s1*s2))
            best=max(range(16),key=lambda n:scores[n]);ratio=scores[best]/(sum(scores)+1.0)
            symbol=best%8 if best//8==channel and ratio>.7 and energy/800>100 else None
            frames.append({'at_ms':start//8,'symbol':symbol,'spectral_ratio':ratio,'rms':math.sqrt(energy/800),'dominant_band':best//8})
            if start>=6000 and symbol is not None and (not observed or observed[-1]!=symbol):observed.append(symbol)
        expected=[pair[channel] for pair in challenge['symbols']]*2;longest=0;match=None
        for a in range(len(expected)):
            for b in range(len(observed)):
                length=0
                while a+length<len(expected) and b+length<len(observed) and expected[a+length]==observed[b+length]:length+=1
                if length>longest:longest=length;match={'source_symbol':a%24,'captured_symbol':b,'length':length}
        require(longest>=8,'actual remote microphone channel '+str(channel)+' did not reproduce eight ordered fresh source symbols')
        sequences.append(match)
        summary['channels'].append({'channel':channel,'actual_frames':frames,'decoded_symbols':observed,'longest_fresh_sequence':longest,'matched':match})
    # The same actual stereo frames must place both independent channel codes
    # within one symbol. A mono mix or two unrelated snippets cannot pass.
    left,right=sequences
    require(min((left['source_symbol']-right['source_symbol'])%24,(right['source_symbol']-left['source_symbol'])%24)<=1,
        'remote input channel codes are not synchronized')
    return summary
