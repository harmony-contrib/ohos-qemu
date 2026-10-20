"""Strict raw AT/public-state oracle, composed only with original VM receipts."""
import json
import re

ICCID='89000101000000000001'
IMSI='460000123456789'
ZERO='0'*32
KEYS={'schema','run_id','boot_id','pid','uid','seq','monotonic_ms','kind','operation_id','hex'}


def need(ok,why):
    if not ok: raise ValueError(why)


def unique(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,'duplicate actual raw journal field');out[key]=value
    return out


def peer_rows(raw,run,boot,pid,uid):
    need(type(raw) is str and raw.endswith('\n') and len(raw.encode())<32*1024*1024,'complete bounded guest peer journal required')
    rows=[];last=-1
    for index,line in enumerate(raw.splitlines(),1):
        row=json.loads(line,object_pairs_hook=unique)
        need(type(row) is dict and set(row)==KEYS and type(row['schema']) is int and row['schema']==1 and row['run_id']==run and
             row['boot_id']==boot and type(row['pid']) is int and row['pid']==pid and
             type(row['uid']) is int and row['uid']==uid and type(row['seq']) is int and row['seq']==index and
             type(row['monotonic_ms']) is int and row['monotonic_ms']>=last and
             row['kind'] in ('ready','control','rx','tx','backend','closed') and
             re.fullmatch('[a-f0-9]{32}',row['operation_id']) is not None and
             re.fullmatch('(?:[a-f0-9]{2}){0,4096}',row['hex']) is not None,'actual peer PID/UID/boot/nonce/sequence/raw differs')
        last=row['monotonic_ms'];rows.append(row)
    need(rows and rows[0]['kind']=='ready' and rows[0]['operation_id']==ZERO and
         re.fullmatch(rb'/dev/pts/[0-9]+',bytes.fromhex(rows[0]['hex'])) is not None,'one genuine created PTY required')
    return rows


def readiness(rows):
    commands=[];carry=b'';sent=[]
    for row in rows:
        raw=bytes.fromhex(row['hex'])
        if row['kind']=='rx':
            carry+=raw
            parts=re.split(rb'[\r\n]',carry)
            carry=parts.pop()
            commands.extend(p.decode('ascii') for p in parts if p)
        elif row['kind']=='tx': sent.append(raw)
    need(not carry,'complete actual incoming AT command frames required')
    need({'AT^CARDMODE','AT+CPIN?','AT+CIMI'}<=set(commands),'actual RIL SIM initialization queries missing')
    need(b'\r\n^CARDMODE: 1\r\n\r\nOK\r\n' in sent and
         b'\r\n+CPIN: READY\r\n\r\nOK\r\n' in sent and
         ('\r\n'+IMSI+'\r\n\r\nOK\r\n').encode() in sent,'actual classic-SIM ready/IMSI responses missing')
    for file_id,length in ((0x2fe2,10),(0x6fad,4),(0x6f38,8)):
        need(any(re.fullmatch(r'AT\+CRSM=192,'+str(file_id)+r',0,0,15,"","[0-9A-F]+"',cmd) for cmd in commands) and
             any(re.fullmatch(r'AT\+CRSM=176,'+str(file_id)+r',0,0,'+str(length)+r',"","[0-9A-F]+"',cmd) for cmd in commands),
             'essential real EF GET_RESPONSE/READ_BINARY chain missing: '+hex(file_id))
    need(b'\r\n+CRSM: 144,0,"98001010000000000010"\r\n\r\nOK\r\n' in sent,
         'actual ICCID file bytes were not transferred through the owned RIL PTY')
    need(any(re.fullmatch(r'AT\^HVSST=[01],1',cmd) for cmd in commands),'actual RIL active-SIM command missing')
    return {'commands':commands,'tx_count':len(sent),'iccid':ICCID,'imsi':IMSI,
            'scope':'virtual SIM AT prerequisite only; no APN/RF/PDP capability pass'}


def public_state(row,active):
    """row is the actual fsynced controller snapshot journal, bound by root collector."""
    need(type(row) is dict and row.get('event')=='snapshot' and row.get('code')==0 and
         type(row.get('uid')) is int and row['uid']>10000 and type(row.get('pid')) is int and row['pid']>1 and
         re.fullmatch('[a-f0-9]{32}',row.get('operation','')) is not None,'actual typed public snapshot journal required')
    value=json.loads(row['value'],object_pairs_hook=unique)
    need(type(value['hasSim']) is bool and type(value['active']) is bool and type(value['accounts']) is list and
         type(value['state']) is int and type(value['defaultSlot']) is int and type(value['dataState']) is int,
         'actual public API value types differ')
    if active:
        need(value['hasSim'] is True and value['active'] is True and value['state'] in (4,5) and
             value.get('iccid')==ICCID and value.get('operator')=='46000' and value['defaultSlot']==0,
             'real SIM state/ICCID/MCCMNC/active/default slot prerequisite incomplete')
        need(len(value['accounts'])==1,'one real active SIM account required')
        account=value['accounts'][0]
        need(account['slotIndex']==0 and account['isActive'] is True and account['isEsim'] is False and
             account['iccId']==ICCID and type(account['simId']) is int and account['simId']>0,
             'real account service did not produce the activated virtual card')
        need(value['dataState'] in (-1,0),'finite SIM fixture must not claim connected/connecting cellular data')
    else:
        need(value['hasSim'] is False and value['active'] is False and value['state']==1 and not value['accounts'],
             'actual removed-card service/account state did not return to no SIM')
    return value
