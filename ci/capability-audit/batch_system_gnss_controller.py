#!/usr/bin/env python3
"""Send an explicit live GNSS measurement/replay trace; never manufacture UTC or a fix."""
import argparse,hashlib,json,math,socket,struct,time
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

def send_trace(stream,rows):
    hello=read_exact(stream,32);magic,version,nonce,size,reserved=struct.unpack('<4sI16sII',hello)
    if (magic,version,size,reserved)!=(b'QGN1',1,88,0):raise ValueError('unexpected GNSS hello')
    sent=[];start=time.monotonic()
    for seq,row in enumerate(rows,1):
        delay=start+row['at_ms']/1000-time.monotonic()
        if delay>0:time.sleep(delay)
        frame=encode_sample(nonce,seq,row);stream.sendall(frame)
        sent.append(dict(sequence=seq,frame_hex=frame.hex(),sent_monotonic_ns=time.monotonic_ns(),measurement=row))
    return dict(status='external_measurements_sent',hello_hex=hello.hex(),samples=sent,
                location_api_delivery_verified=False,limitations='Sender evidence only; compare independent public GNSS/location observers. Source UTC is preserved, never rewritten. Guest rejects stale (>10s) or future (>1s) fixes and repeated UTC.')

def load_trace(path):
    rows=json.loads(path.read_text())
    if not isinstance(rows,list) or not 1<=len(rows)<=100000:raise ValueError('trace must be a nonempty bounded array')
    previous=-1;utc=0
    for row in rows:
        encode_sample(bytes(16),1,row)
        at=row.get('at_ms',-1)
        if not previous<at<=3600000 or at<0 or (previous>=0 and at-previous>=4000) or (previous<0 and at>=4000):
            raise ValueError('increasing at_ms within one hour and <4s transfer gaps required')
        if row['utc_ms']<=utc:raise ValueError('source UTC must strictly increase')
        previous=at;utc=row['utc_ms']
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);endpoint=p.add_mutually_exclusive_group(required=True)
    endpoint.add_argument('--unix-path');endpoint.add_argument('--tcp-port',type=int)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=load_trace(a.input)
    if a.output.exists():raise ValueError('evidence output already exists')
    family=socket.AF_UNIX if a.unix_path else socket.AF_INET
    address=a.unix_path if a.unix_path else ('127.0.0.1',a.tcp_port)
    with socket.socket(family,socket.SOCK_STREAM) as stream:
        stream.settimeout(5);stream.connect(address);result=send_trace(stream,rows)
    result['input_sha256']=hashlib.sha256(a.input.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],samples=len(rows))))
