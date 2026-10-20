"""Source-only nonce WAV generator and independent captured-PCM oracle.

Only the source guest receives the generated WAV. The sink is inspected through
its actual QEMU DAC capture, not a file reader or locally played target asset.
"""
from array import array
import hashlib
import math
from pathlib import Path
import re
import secrets
import sys
import wave

FREQUENCIES = (400, 600, 800, 1000, 1200, 1400, 1600, 1800)
RATE = 48000


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def ref(path):
    p = Path(path)
    return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def prepare(output, run):
    require(re.fullmatch('[a-f0-9]{32}',run), 'actual nonce required')
    path = Path(output) / ('cast-'+run+'.wav')
    require(not path.exists(), 'fresh source-only media path')
    indices=[]
    for _ in range(150):
        choices=[n for n in range(len(FREQUENCIES)) if not indices or n!=indices[-1]]
        indices.append(secrets.choice(choices))
    samples=array('h')
    for index in indices:
        freq=FREQUENCIES[index]
        for n in range(16800):
            envelope=min(1.0,n/240,(16799-n)/240)
            samples.append(round(9000*envelope*math.sin(2*math.pi*freq*n/RATE)))
        samples.extend([0]*2400)
    if sys.byteorder!='little':samples.byteswap()
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(RATE);out.writeframes(samples.tobytes())
    return {'run_id':run,'wav':ref(path),'sample_rate':RATE,'symbols':indices,'frequencies':list(FREQUENCIES),
            'tone_ms':350,'gap_ms':50,'duration_ms':60000,'provision_to':'source_only'}


def actual_symbols(reference):
    path=Path(reference['path']);require(hashlib.sha256(path.read_bytes()).hexdigest()==reference['sha256'],'actual captured WAV changed')
    with wave.open(str(path),'rb') as stream:
        require((stream.getframerate(),stream.getsampwidth(),stream.getnchannels(),stream.getcomptype())==(RATE,2,2,'NONE'), 'actual sink DAC format')
        require(0<stream.getnframes()<=RATE*120,'bounded independent capture duration')
        pcm=array('h',stream.readframes(stream.getnframes()))
    if sys.byteorder!='little':pcm.byteswap()
    # Analyze each DAC channel independently: averaging could cancel opposite
    # phases. Decimate48k→8k; all challenge tones are below the4k Nyquist bound.
    channels=[list(pcm[channel::12]) for channel in (0,1)]
    frames=[]
    for start in range(0,min(map(len,channels))-800+1,800):
        best=None
        for channel,data in enumerate(channels):
            block=data[start:start+800];energy=sum(x*x for x in block)
            scores=[]
            for freq in FREQUENCIES:
                coefficient=2*math.cos(2*math.pi*freq/8000);s1=s2=0.0
                for sample in block:
                    current=sample+coefficient*s1-s2;s2=s1;s1=current
                scores.append(max(0.0,s1*s1+s2*s2-coefficient*s1*s2))
            order=sorted(range(len(scores)),key=lambda n:scores[n],reverse=True)
            ratio=scores[order[0]]/(sum(scores)+1.0)
            candidate={'at_ms':start*1000//8000,'channel':channel,'rms':math.sqrt(energy/800),
                'symbol':order[0] if ratio>.8 and energy/800>25 else None,'spectral_ratio':ratio}
            if best is None or candidate['spectral_ratio']>best['spectral_ratio']:best=candidate
        frames.append(best)
    return frames


def assess(reference, challenge, *, audible):
    frames=actual_symbols(reference)
    # Ignore only the first500ms of the captured segment for actual output
    # buffering. Keep every frame in the evidence, including that guard.
    sequence=[]
    for row in frames:
        if row['at_ms']<500 or row['symbol'] is None:continue
        if not sequence or sequence[-1]!=row['symbol']:sequence.append(row['symbol'])
    expected=challenge['symbols'];longest=0;matched=None
    for offset in range(len(expected)):
        for observed in range(len(sequence)):
            size=0
            while offset+size<len(expected) and observed+size<len(sequence) and expected[offset+size]==sequence[observed+size]:size+=1
            if size>longest:longest=size;matched={'source_symbol_offset':offset,'captured_symbol_offset':observed,'symbols':size}
    if audible:
        require(longest>=12,'independent sink DAC did not decode at least12 ordered fresh source-only tone symbols')
    else:
        inspected=[row for row in frames if row['at_ms']>=500]
        require(len(inspected)>=20 and sum(row['symbol'] is not None for row in inspected)<=2,
                'quiet boundary must contain at least2s actual output and at most200ms residual challenge-band tones')
        require(longest<3,'paused/disconnected/baseline sink still emits the fresh source challenge')
    return {'actual_wav':reference,'audible_required':audible,'frames':frames,'observed_symbols':sequence,
            'longest_exact_source_sequence':longest,'matched':matched,'guard_ms':500,
            'scope':'independent_sink_DAC_PCM_only; not a controller-getter or file-presence oracle'}
