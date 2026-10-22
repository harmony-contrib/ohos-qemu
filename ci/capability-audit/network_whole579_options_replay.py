"""Pure exact positive native options replay inside the original final actor.

Inputs are completed original IO, full kernel GET7, native private journals and
wire bytes from its ONE original held TLS peer. No transport or producer runs.
"""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import ipaddress
import re
import struct
from network_whole579_records import need, raw, doc, ref, loads


def question(data):
    need(17 <= len(data) <= 4096 and data[4:6] == b'\0\1', 'one bounded DNS question')
    at=12; labels=[]
    while at<len(data) and data[at]:
        size=data[at];need(0<size<=63 and at+size+1<len(data),'complete uncompressed DNS question')
        labels.append(data[at+1:at+1+size].decode('ascii').lower());at+=size+1
    need(at+5<=len(data) and data[at]==0, 'DNS question terminator/type/class')
    typ,cls=struct.unpack_from('!HH',data,at+1);need(cls==1 and typ in (1,28),'actual A/AAAA IN question')
    return '.'.join(labels),typ,at+5


def answer_matches(query,answer):
    name,typ,end=question(query)
    need(len(answer)>=end+12 and answer[:2]==query[:2] and answer[2]&0x80 and answer[3]&15==0 and
        answer[4:6]==b'\0\1' and answer[6:8]==b'\0\1' and answer[12:end]==query[12:end],
        'actual complete DNS ID/question/success/one-answer match')
    need(answer[end:end+2]==b'\xc0\x0c','fixed independent peer answer name')
    got,cls,ttl,size=struct.unpack_from('!HHIH',answer,end+2)
    need(got==typ and cls==1 and ttl==0 and size==(4 if typ==1 else 16) and len(answer)==end+12+size,
        'complete actual independent DNS RDATA/zero TTL')
    return name,typ,str(ipaddress.ip_address(answer[end+12:]))


def attrs(row):return {v['type']:v.get('value') for v in row['attributes']}


def interface(claim):
    args=claim['client']['argv'];values=[args[i+2] for i in range(len(args)-2) if args[i:i+2]==['--setenv','OHOS_OPENVPN_INTERFACE']]
    need(len(values)==1 and re.fullmatch(r'[A-Za-z0-9_-]{1,15}',values[0]),'real fixed TUN interface in actual client argv')
    return values[0]


def link(snapshot,name):
    rows=[v for v in snapshot['datasets']['links'] if v['ifname']==name]
    need(len(rows)==1,'one actual same-session kernel TUN link');return rows[0]['ifindex']


def bridge(scan,claim):
    rows=[v for v in scan['processes'].values() if v['exe']=='/system/bin/qemu_openvpn_tun']
    need(len(rows)==1 and rows[0]['uid']==1098 and rows[0]['ppid']==claim['client']['pid'] and
        rows[0]['pgrp']==claim['worker']['pgrp'],'one actual forwarding bridge under original client/worker')
    return rows[0]


def replay(e,wire):
    def calls(action):return [(op,rows) for op,rows in e.calls if op['role']=='a' and op['user']==100 and op['request']['action']==action]
    def value(rows,event):
        selected=[r for r in rows if r['event']==event];need(len(selected)==1,'one raw '+event);return loads(selected[0]['value'])
    def kernel(label):
        rows=[(op,s) for op,s in e.kernels if op['label']==label];need(len(rows)==1,'one complete kernel '+label);return rows[0][1]
    def claim_for(variant):
        rows=[(op,c,s) for (op,c),s in zip(e.claims,e.claim_scans) if op['variant']==variant]
        need(rows,'real source-derived connected '+variant);return rows
    def cleanup_links(before,after,name,index):
        need(not any(v['ifname']==name for v in before['datasets']['links']) and
            not any(v['ifname']==name for v in after['datasets']['links']),'fresh owned TUN must disappear after actual destroy')
        for family in ('routes4','routes6'):
            need(not any(attrs(v).get(4)==index for v in after['datasets'][family]),'removed native TUN still owns a real route')
        for family in ('addresses4','addresses6'):
            need(not any(v['ifindex']==index for v in after['datasets'][family]),'removed native TUN still owns a real address')
    wanted=['metric','dnsport','splitdns','dot','doh','badcert','invalid','persist']
    options=calls('option');need([op['request']['payload']['option'] for op,_ in options]==wanted,'exact original positive option requirements plus one genuine invalid boundary')
    for op,rows in options:
        bad=op['request']['payload']['option']=='invalid'
        need(sum(v['event']==('setup-error' if bad else 'setup-returned') for v in rows)==1 and
            not any(v['event']==('setup-returned' if bad else 'setup-error') for v in rows),'required backend option refused or invalid executable option accepted')
        if bad:
            error=next(v for v in rows if v['event']=='setup-error')
            need(type(error['code']) is int and loads(error['value'])['codeType']=='number','real invalid native BusinessError')
    metrics=[];dns_proofs=[]
    for variant in wanted[:6]:
        selected=claim_for(variant);need(len(selected)==1,'one source-normal connected option session')
        op,claim,scan=selected[0];name=interface(claim);live=kernel('connected_'+variant);index=link(live,name)
        cleanup_links(kernel('before_'+variant),kernel('after_'+variant),name,index)
        actual_bridge=bridge(scan,claim)
        if variant=='metric':
            for family in ('routes4','routes6'):
                rows=[v for v in live['datasets'][family] if attrs(v).get(4)==index and attrs(v).get(6)==7]
                need(rows,'nonzero RTA_PRIORITY=7 must actually exist for BOTH real TUN route families')
                metrics.extend(rows)
            continue
        rows=[(o,items) for o,items in e.dns if o['label']==variant]
        need(len(rows)==1 and rows[0][0]['claim']==claim,'native DNS wire tied to this actual source/session claim')
        native=rows[0][1];need(native,'actual private native resolver journal absent')
        for record in native:
            need(set(record)=={'kind','generation','pid','uid','tid','net_id','socket_mark','local_address','local_port','ifindex','transport','address','port','sni','question_hex','answer_hex','error','start_ns','end_ns'} and
                record['kind']=='dns' and record['generation']==claim['generation'] and record['pid']==actual_bridge['pid'] and
                record['uid']==1098 and type(record['tid']) is int and record['tid']>0 and record['ifindex']==index and
                type(record['net_id']) is int and record['net_id']>0 and record['socket_mark']&0xffff==record['net_id'] and
                record['net_id'] in e.public_net_ids and ipaddress.ip_address(record['local_address']) in ipaddress.ip_network('10.73.0.0/24') and
                0<record['local_port']<65536 and 0<record['start_ns']<=record['end_ns'],
                'actual native DNS UID/PID/TID/generation/TUN/netId/socket mark and bounded transaction time')
        matching_calls=[]
        for call,values in e.calls:
            if call['request']['action'] not in ('dns','dns-outside','dns-bad-cert'):continue
            names=[v for v in values if v['event']=='dns-question']
            if not names:continue
            domain=loads(names[0]['value'])
            hits=[v for v in native if question(bytes.fromhex(v['question_hex']))[0]==domain]
            if not hits:continue
            matching_calls.append(call['request']['action'])
            need({question(bytes.fromhex(v['question_hex']))[1] for v in hits}=={1,28},'actual native dual-stack DNS queries required')
            if variant=='badcert':
                need(any(v['event']=='dns-error' and type(v['code']) is int for v in values) and
                    not any(v['event']=='dns-answer' for v in values) and all(v['transport']=='DoT' and v['sni']=='wrong-whole579-peer' and
                    v['answer_hex']=='' and v['error'].startswith('tls-handshake:') and not v['error'].startswith('tls-handshake:0:') for v in hits),
                    'actual wrong TLS identity must fail, return no answer and NEVER downgrade')
                need(not any(question(bytes.fromhex(v['request_hex']))[0]==domain for v in wire if v['kind'] in ('dns','dns-port','dns-reconfigured') and v['request_hex']),
                    'encrypted negative query leaked as plaintext to the peer')
                for hit in hits:
                    failed=[v for v in wire if v['kind']=='dot' and v['remote']==[hit['local_address'],hit['local_port']] and
                        v['sni']=='wrong-whole579-peer']
                    need(failed and all(v['complete'] is False and v['error'] and v['request_hex']=='' and v['response_hex']=='' and
                        len(bytes.fromhex(v['tls_rx_hex']))>20 and len(bytes.fromhex(v['tls_tx_hex']))>20 for v in failed),
                        'actual negative native socket must reach the real peer TLS handshake and send no DNS plaintext')
                continue
            addresses={v['address'] for v in value(values,'dns-answer')}
            kind='dot' if variant=='dot' else 'doh' if variant=='doh' else 'dns-port' if variant=='dnsport' or variant=='splitdns' and call['request']['action']=='dns-outside' else 'dns'
            port=853 if kind=='dot' else 443 if kind=='doh' else 5353 if kind=='dns-port' else 53
            transport='DoT' if kind=='dot' else 'DoH' if kind=='doh' else 'plain'
            expected={'10.73.0.254','fd73:579::fe'} if port==5353 else {'10.73.0.1','fd73:579::1'}
            need(expected<=addresses,'real OS resolver must consume the port/domain/transport-specific independent answer')
            for item in hits:
                q=bytes.fromhex(item['question_hex']);a=bytes.fromhex(item['answer_hex'])
                need(item['error']=='' and item['transport']==transport and item['address']=='10.73.0.1' and item['port']==port,
                    'actual policy chose a different transport/upstream endpoint')
                answer_matches(q,a)
                peers=[v for v in wire if v['kind']==kind and v['request_hex']==q.hex() and v['response_hex']==a.hex() and v['complete'] is True and v['remote']==[item['local_address'],item['local_port']]]
                need(peers,'matching real independent peer question and response bytes absent')
                if kind in ('dot','doh'):
                    need(item['sni']=='qemu-owned-peer' and all(v['sni']=='qemu-owned-peer' and v['tls_version'] in ('TLSv1.2','TLSv1.3') and
                        v['cipher'] and len(bytes.fromhex(v['tls_rx_hex']))>20 and len(bytes.fromhex(v['tls_tx_hex']))>20 and
                        re.fullmatch('[a-f0-9]{64}',v['certificate_sha256']) and v['error'] is None for v in peers),
                        'real peer TLS identity/cipher/ciphertext missing')
                    if kind=='doh':
                        for peer in peers:
                            header=bytes.fromhex(peer['http_header_hex']).decode('ascii')
                            need(header.startswith('POST /dns-query HTTP/1.1\r\n') and '\r\nContent-Type: application/dns-message\r\n' in header and
                                '\r\nContent-Length: '+str(len(q))+'\r\n' in header,'actual encrypted DoH HTTP method/type/length')
            dns_proofs.append(dict(variant=variant,domain=domain,transport=transport,port=port))
        need(set(matching_calls)==({'dns','dns-outside'} if variant=='splitdns' else {'dns-bad-cert'} if variant=='badcert' else {'dns'}),
            'required actual domain branch/certificate negative request missing')
    persisted=claim_for('persist');need(len(persisted)==3,'initial/reconfigured/restored actual persistent snapshots')
    native=[c for _,c,_ in persisted];scans=[s for _,_,s in persisted]
    need(len({(c['generation'],c['client']['pid'],c['client']['start'],c['worker']['pid'],c['worker']['start']) for c in native})==1,
        'persist must retain the original real session, client AND worker identities')
    name=interface(native[0]);cuts=[kernel(label) for label in ('persist_before','persist_after','persist_restored')]
    indices=[link(c,name) for c in cuts];need(len(set(indices))==1,'persist recreated the kernel TUN instead of retaining it')
    bridges=[bridge(scan,c) for scan,c in zip(scans,native)]
    need(len({(v['pid'],v['start']) for v in bridges})==3,'changed OpenVPN pull policy must end the old bridge and create a real successor')
    for old,new in zip(bridges,scans[1:]):
        need(old['pid'] not in new['stats'] or new['stats'][old['pid']]['start']!=old['start'], 'old native forwarding worker not actually reaped before new takeover')
    def changed_route(c):return [v for v in c['datasets']['routes4'] if attrs(v).get(4)==indices[0] and attrs(v).get(1)=='10.74.0.1' and v['dst_len']==32]
    need(not changed_route(cuts[0]) and changed_route(cuts[1]) and not changed_route(cuts[2]),'actual renegotiation/restore route change not installed/removed')
    configs=[loads(v['value']) for op,rows in e.calls if op['request']['action']=='state' for v in rows if v['event']=='connected-config']
    need(any(c.get('dnsAddresses')==['10.73.0.254'] for c in configs),'public connected config never consumed renegotiated DNS')
    cleanup_links(kernel('before_metric'),kernel('persist_destroyed'),name,indices[0])
    admin=[v for v in wire if v['kind'] in ('reconfigure','restore')]
    need([v['kind'] for v in admin]==['reconfigure','restore'],'real original peer management change/restore both required')
    for record in admin:
        need(record['complete'] is True and re.fullmatch('[A-Za-z0-9_.-]{1,128}',record['client_cn']) and
            record['client_id'].isdigit() and bytes.fromhex(record['request_hex'])==('client-kill '+record['client_id']+'\n').encode() and
            b'SUCCESS:' in bytes.fromhex(record['response_hex']) and b'ERROR:' not in bytes.fromhex(record['response_hex']),
            'actual existing peer management/CN transaction failure')
        need(bytes.fromhex(record['status_request_hex'])==b'status 3\n' and bytes.fromhex(record['status_hex']).rstrip().endswith(b'END'),'actual fresh synchronous management status command/completion')
        lines=[line.split('\t') for line in bytes.fromhex(record['status_hex']).decode().splitlines()]
        headers=[row[2:] for row in lines if row[:2]==['HEADER','CLIENT_LIST']]
        clients=[row[1:] for row in lines if row[:1]==['CLIENT_LIST']]
        need(len(headers)==len(clients)==1 and len(headers[0])==len(clients[0]) and len(set(headers[0]))==len(headers[0]),'actual complete status-v3 CN/client identity')
        client=dict(zip(headers[0],clients[0]));need(client['Common Name']==record['client_cn'] and client['Client ID']==record['client_id'],
            'management selected a different real authenticated peer client')
        action='reconfigure' if record['kind']=='reconfigure' else 'restore-peer'
        matching=[(o,rows) for o,rows in calls(action) if any(v['event']=='peer-reconfigure-requested' for v in rows)]
        need(len(matching)==1,'actual public typed nonce-bound peer administration request')
        request=value(matching[0][1],'peer-reconfigure-requested').split(' ')
        need(request[0]==('VPNR' if action=='reconfigure' else 'VPNQ') and len(request)==5 and request[1]==e.value['parameters']['peer_run'] and
            request[2]==record['operation'] and any(v['kind']=='ipv4' and v['complete'] and bytes.fromhex(v['response_hex']).decode()=='VPN3 '+' '.join(request[1:]) for v in wire),
            'peer administrative mutation was not preceded by this real challenge completion')
        completed=[v for v in wire if v['kind']=='ipv4' and v['complete'] and bytes.fromhex(v['response_hex']).decode()=='VPN3 '+' '.join(request[1:])]
        need(len(completed)==1 and client['Virtual Address']==completed[0]['remote'][0], 'actual management CID belongs to this data-path client virtual address')
    return dict(metric_routes=metrics,dns_transactions=dns_proofs,persist_kernel_ifindex=indices[0],
        persist_generation=native[0]['generation'],actual_bridge_identities=[{k:v[k] for k in ('pid','start','ppid','pgrp')} for v in bridges],
        not_claimed=['DNSSEC validating resolver','DNS-over-TCP fallback','external Internet or third-party endpoints'])
