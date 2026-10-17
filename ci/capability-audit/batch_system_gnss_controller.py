#!/usr/bin/env python3
"""Send explicit GNSS measurements or opt-in raw precision-boundary frames; never rewrite UTC."""
import argparse,hashlib,json,math,re,socket,struct,time
from pathlib import Path
REQUIRED={'utc_ms','latitude','longitude','horizontal_accuracy'}
OPTIONAL={'altitude':4,'speed':8,'bearing':16,'vertical_accuracy':64}
def read_exact(stream,size):
    result=b''
    while len(result)<size:
        data=stream.recv(size-len(result))
        if not data:raise ValueError('GNSS input disconnected')
        result+=data
    return result

def encode_sample(nonce,sequence,row):
    if not REQUIRED <= set(row) or set(row)-REQUIRED-set(OPTIONAL)-{'at_ms'}:
        raise ValueError('explicit utc_ms/latitude/longitude/horizontal_accuracy measurements required')
    if any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) for value in row.values()):
        raise ValueError('all measurement fields must be finite numbers')
    if not isinstance(row['utc_ms'],int) or not 1577836800000<=row['utc_ms']<=4102444800000:
        raise ValueError('UTC must be the source measurement epoch in milliseconds')
    if not -90<=row['latitude']<=90 or not -180<=row['longitude']<=180 or not 0<row['horizontal_accuracy']<=100000:
        raise ValueError('invalid WGS84 coordinate or horizontal accuracy')
    altitude=row.get('altitude',0);speed=row.get('speed',0);bearing=row.get('bearing',0);vertical=row.get('vertical_accuracy',0)
    if not -12000<=altitude<=100000 or not 0<=speed<=1500 or not 0<=bearing<360 or not 0<=vertical<=100000 or ('vertical_accuracy' in row and vertical==0):
        raise ValueError('invalid optional measurement')
    flags=sum(bit for key,bit in OPTIONAL.items() if key in row)
    return struct.pack('<4sI16sQQdddffffII',b'QGF1',1,nonce,sequence,row['utc_ms'],row['latitude'],row['longitude'],
                       altitude,row['horizontal_accuracy'],vertical,speed,bearing,flags,0)

PRECISION_PROTOCOL = 'qgn2-precision'
LEGACY_PROTOCOL = 'qgn1'

def encode_precision_sample(nonce,sequence,row):
    """Explicit raw binary32 boundary/fault input; no float conversion of accuracy."""
    required={'utc_ms','latitude','longitude','horizontal_accuracy_bits','horizontal_accuracy_valid'}
    if not required <= set(row) or set(row)-required-set(OPTIONAL)-{'at_ms'}:
        raise ValueError('V2 requires explicit UTC/coordinates/raw accuracy bits/boolean validity')
    if (not isinstance(row['horizontal_accuracy_bits'],str) or
            re.fullmatch('[0-9a-f]{8}',row['horizontal_accuracy_bits']) is None or
            type(row['horizontal_accuracy_valid']) is not bool):
        raise ValueError('raw accuracy must be exactly eight lowercase hexadecimal digits plus boolean validity')
    numbers={key:value for key,value in row.items() if key not in ('horizontal_accuracy_bits','horizontal_accuracy_valid')}
    if any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) for value in numbers.values()):
        raise ValueError('all other V2 measurement fields must remain finite numbers')
    if not isinstance(row['utc_ms'],int) or not 1577836800000<=row['utc_ms']<=4102444800000:
        raise ValueError('UTC must be the source measurement epoch in milliseconds')
    if not -90<=row['latitude']<=90 or not -180<=row['longitude']<=180:
        raise ValueError('invalid WGS84 coordinate')
    altitude=row.get('altitude',0);speed=row.get('speed',0);bearing=row.get('bearing',0);vertical=row.get('vertical_accuracy',0)
    if not -12000<=altitude<=100000 or not 0<=speed<=1500 or not 0<=bearing<360 or not 0<=vertical<=100000 or ('vertical_accuracy' in row and vertical==0):
        raise ValueError('invalid optional measurement')
    flags=sum(bit for key,bit in OPTIONAL.items() if key in row)
    return struct.pack('<4sI16sQQdddIfffII',b'QGF2',2,nonce,sequence,row['utc_ms'],row['latitude'],row['longitude'],
                       altitude,int(row['horizontal_accuracy_bits'],16),vertical,speed,bearing,flags,
                       int(row['horizontal_accuracy_valid']))

def negotiate_precision(stream,nonce):
    """Require an exact affirmative V2 ACK; the preceding legacy hello proves nothing."""
    stream.sendall(struct.pack('<4sI16s64s',b'QGP2',2,nonce,bytes(64)))
    ack=read_exact(stream,32)
    if struct.unpack('<4sI16sII',ack)!=(b'QGA2',2,nonce,88,1):
        raise ValueError('guest did not explicitly acknowledge raw-accuracy V2; no downgrade/fallback')
    return ack

def codec(protocol):
    if protocol==LEGACY_PROTOCOL:return encode_sample
    if protocol==PRECISION_PROTOCOL:return encode_precision_sample
    raise ValueError('explicit supported GNSS protocol required')

def send_trace(stream,rows,protocol=LEGACY_PROTOCOL):
    hello=read_exact(stream,32);magic,version,nonce,size,reserved=struct.unpack('<4sI16sII',hello)
    if (magic,version,size,reserved)!=(b'QGN1',1,88,0):raise ValueError('unexpected GNSS hello')
    encoder=codec(protocol)
    ack=negotiate_precision(stream,nonce) if protocol==PRECISION_PROTOCOL else None
    sent=[];start=time.monotonic()
    for seq,row in enumerate(rows,1):
        delay=start+row['at_ms']/1000-time.monotonic()
        if delay>0:time.sleep(delay)
        frame=encoder(nonce,seq,row);stream.sendall(frame)
        sent.append(dict(sequence=seq,frame_hex=frame.hex(),sent_monotonic_ns=time.monotonic_ns(),measurement=row))
    result=dict(status='external_measurements_sent',hello_hex=hello.hex(),samples=sent,
                location_api_delivery_verified=False,limitations='Sender evidence only; compare independent public GNSS/location observers. Source UTC is preserved, never rewritten. Guest rejects stale (>10s) or future (>1s) fixes and repeated UTC.')
    if ack is not None:
        result.update(status='raw_precision_boundary_inputs_sent_NOT_public_verified',protocol=protocol,
                      capability_ack_hex=ack.hex(),
                      limitations='Explicit private V2 raw boundary/fault input only. No native decoder, HDI acceptance or public callback outcome is implied. Source UTC is not rewritten.')
    return result

def load_trace(path,protocol=LEGACY_PROTOCOL):
    rows=json.loads(path.read_text())
    if not isinstance(rows,list) or not 1<=len(rows)<=100000:raise ValueError('trace must be a nonempty bounded array')
    previous=-1;utc=0
    for row in rows:
        codec(protocol)(bytes(16),1,row)
        at=row.get('at_ms',-1)
        if not previous<at<=3600000 or at<0 or (previous>=0 and at-previous>=4000) or (previous<0 and at>=4000):
            raise ValueError('increasing at_ms within one hour and <4s transfer gaps required')
        if row['utc_ms']<=utc:raise ValueError('source UTC must strictly increase')
        previous=at;utc=row['utc_ms']
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);endpoint=p.add_mutually_exclusive_group(required=True)
    endpoint.add_argument('--unix-path');endpoint.add_argument('--tcp-port',type=int)
    p.add_argument('--protocol',choices=[LEGACY_PROTOCOL,PRECISION_PROTOCOL],default=LEGACY_PROTOCOL,
                   help='V2 raw precision boundaries require explicit guest capability ACK; never falls back')
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=load_trace(a.input,a.protocol)
    if a.output.exists():raise ValueError('evidence output already exists')
    family=socket.AF_UNIX if a.unix_path else socket.AF_INET
    address=a.unix_path if a.unix_path else ('127.0.0.1',a.tcp_port)
    with socket.socket(family,socket.SOCK_STREAM) as stream:
        stream.settimeout(5);stream.connect(address);result=send_trace(stream,rows,a.protocol)
    result['input_sha256']=hashlib.sha256(a.input.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],samples=len(rows))))
