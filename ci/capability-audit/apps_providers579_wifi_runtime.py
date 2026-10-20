"""Actual WiFi radio/IP/OS-portal flow on the parent's single held image.

No process, socket, Owner or lease is constructed. Unsupported thermal/auto-
idle conclusions remain separate source-bounded dispositions plus VM raw;
UI/absence alone never closes the aggregate. All package gates remain false.
"""
import ipaddress
import json
import re
import struct
import time

from apps_providers579_bindings import raw
from apps_providers579_project import require, ROLES
from apps_providers579_runtime import KEYS, rows, one, permission_boundary


def packet(row):
    return bytes.fromhex(row['hex'])


def dhcp(data):
    require(len(data) >= 240 and data[236:240] == b'\x63\x82\x53\x63', 'real DHCP cookie/header required')
    options = {};index = 240
    while index < len(data):
        code = data[index];index += 1
        if code == 255:
            break
        if code == 0:
            continue
        require(index < len(data), 'actual DHCP option length missing')
        size = data[index];index += 1
        require(index + size <= len(data), 'actual DHCP option truncated')
        options.setdefault(code, []).append(data[index:index+size]);index += size
    require(len(options.get(53, [])) == 1 and len(options[53][0]) == 1, 'one actual DHCP message type')
    return {'type': options[53][0][0], 'xid': data[4:8].hex(), 'mac': ':'.join('%02x' % b for b in data[28:34]),
        'address': str(ipaddress.IPv4Address(data[16:20])), 'options': options}


def native(record, event, namespace=None):
    require(record['native_journals'] and record['native_events'], 'actual retained native wire files required')
    for item in record['native_journals']:
        raw(item['raw'])
    return [row for row in record['native_events'] if row['event'] == event and (namespace is None or row['netns'] == namespace)]


def verify_exchange(record, run):
    require(record['initial_netns'] != record['peer_netns'], 'separate kernel IP stack required')
    initial = [row for row in native(record, 'nonce-initial-tx', record['initial_netns']) if row['pid'] == record['current_exchange_pid']]
    require(len(initial) == 1, 'one current actual client transmission required')
    expected = packet(initial[0])
    require(re.fullmatch(('APPS579:' + run + ':initial-to-independent-peer:[a-f0-9]{32}').encode(), expected),
            'fresh per-exchange random challenge must be recorded before its real send')
    require(any(packet(row) == expected for row in native(record, 'nonce-initial-tx', record['initial_netns'])) and
            any(packet(row) == expected for row in native(record, 'nonce-peer-rx', record['peer_netns'])) and
            any(packet(row) == expected + b':reply' for row in native(record, 'nonce-peer-tx', record['peer_netns'])) and
            any(packet(row) == expected + b':reply' for row in native(record, 'nonce-initial-rx', record['initial_netns'])),
            'nonce must traverse initial radio socket, isolated peer receive/reply and actual initial receive')
    wire = [packet(row) for row in native(record, 'radio-frame', record['peer_netns'])]
    require(any(expected in frame for frame in wire) and any(expected + b':reply' in frame for frame in wire),
            'independent radio AF_PACKET must observe real nonce payload frames in both directions')
    # Kernel IP-address exclusion is enforced by the actual helper before
    # connect, including ALL initial-netns addresses, not merely 127.0.0.1.
    return {'peer_ip': record['peer_ip'], 'interface': record['interface'],
            'initial_netns': record['initial_netns'], 'peer_netns': record['peer_netns']}


def verify_dora(record, client_event, server_event, mac):
    clients = [dhcp(packet(row)) for row in native(record, client_event) if row['pid'] == record['server_pid']]
    servers = [dhcp(packet(row)) for row in native(record, server_event) if row['pid'] == record['server_pid']]
    complete = []
    for discover in clients:
        if discover['type'] != 1 or discover['mac'].lower() != mac.lower():
            continue
        xid = discover['xid']
        offered = [p for p in servers if p['xid'] == xid and p['mac'] == discover['mac'] and p['type'] == 2]
        requested = [p for p in clients if p['xid'] == xid and p['mac'] == discover['mac'] and p['type'] == 3]
        acked = [p for p in servers if p['xid'] == xid and p['mac'] == discover['mac'] and p['type'] == 5]
        if offered and requested and acked:
            ack = acked[-1];offer = offered[-1]
            require(offer['address'] == ack['address'] and ack['address'] not in ('0.0.0.0', '127.0.0.1') and
                    all(len(ack['options'].get(code, [])) == 1 for code in (1, 3, 54)), 'real DHCP OFFER/ACK address/mask/router/server required')
            complete.append({'xid': xid, 'mac': mac, 'address': ack['address'],
                'mask': str(ipaddress.IPv4Address(ack['options'][1][0])),
                'router': str(ipaddress.IPv4Address(ack['options'][3][0][:4])),
                'server': str(ipaddress.IPv4Address(ack['options'][54][0]))})
    require(complete, 'independent source MAC and transaction must complete real DHCP DISCOVER/OFFER/REQUEST/ACK')
    return complete[-1]


def run(guest, root_callbacks, parameters):
    require(type(root_callbacks) is dict and set(root_callbacks) == KEYS and all(callable(v) for v in root_callbacks.values()), 'exact original seven held callbacks')
    require(type(parameters) is dict and set(parameters) == {'case', 'run_id', 'profile'} and parameters['case'] == 'wifi' and
            re.fullmatch('[a-f0-9]{32}', parameters['run_id']) and parameters['profile'] in ('phone', '2in1'), 'fixed WiFi stage data')
    cb = root_callbacks;run = parameters['run_id'];serial = 0
    value = {'schema_version': 1, 'case': 'wifi', 'run_id': run, 'profile': parameters['profile'],
        'requirement_ids': ['behavior:wifi-system-ui-providers-not-activated'], 'operations': [], 'observed_slices': [],
        'failures': [], 'unresolved_requirements': ['source_bounded_auto_idle_and_thermal_provider_dispositions'],
        'runtime_pass': False, 'first_artifact_behavior_gate_passed': False, 'closed_requirement_ids': []}
    def keep(kind, row):
        value['operations'].append({'kind': kind, 'record': row});return row
    def start(action, role='grant'):
        nonlocal serial
        serial += 1;request = {'run_id': run, 'request_id': 'wifi_ip_' + str(serial) + '_' + action.replace('-', '_'), 'action': action, 'payload': {}}
        keep('request', request);keep('start', cb['start'](role, action, request));return request['request_id']
    def finish(request_id, role='grant', errors=False):
        result = keep('collect', cb['collect'](role, request_id));events = rows(result['journal'], run, role, request_id)
        require(events and any(row['event'] == 'request' for row in events), 'actual dispatched typed caller required')
        if not errors:
            require(any(row['event'] == 'done' for row in events) and not any(row['event'] in ('error', 'request-error', 'page-error') for row in events), 'typed native WLAN call failed')
        return events,result
    def call(action, role='grant', errors=False):
        return finish(start(action, role), role, errors)
    def touch(action, payload=None):
        return keep('input_' + action, cb['input'](action, payload or {}))
    def network(action, data=None):
        return keep('network_' + action, cb['network'](action, data or {}))
    def picture(label):
        return touch('snapshot', {'label': label})
    def wifi_network(expect_validated):
        deadline=time.monotonic()+60
        while True:
            values,record=call('networks')
            networks=[json.loads(row['value']) for row in values if row['event']=='actual-wifi-network']
            matching=[row for row in networks if row['properties']['interfaceName']=='wlan0' and
                any(item['address']['address']=='192.0.2.2' for item in row['properties']['linkAddresses'])]
            if len(matching)==1 and ((16 in matching[0]['capabilities']['networkCap']) is expect_validated):
                return matching[0],record
            require(time.monotonic()<deadline, 'actual WiFi NetHandle/IPv4/OS validated state not reached')
            time.sleep(.5)
    try:
        prepared=keep('prepared_callers', cb['prepare_callers']('wifi',run,ROLES['wifi']))
        require(prepared['profile']==parameters['profile'], 'actual profile mismatch')
        value.update(boot_id=prepared['boot_id'],archive_sha256=prepared['archive_sha256'])
        for role in ROLES['wifi']:
            keep('install_'+role,cb['install'](role))
        for role in ('normal','denied'):
            events,_=call('ap-start',role,True);permission_boundary(events)
        permission=start('permissions');touch('wifi-location-permission')
        granted,_=finish(permission);require(one(granted,'permission-result')['authResults']==[0,0], 'actual two native location grants required')
        before,_=call('snapshot');baseline=one(before,'wifi-before')
        require(not baseline['enabled'] and not baseline['hotspot'], 'refuse foreign initial STA/AP')
        fixture=network('wifi-radio-prepare')
        network('wifi-peer-start',{'mode':'ap'});network('wifi-portal-config')
        call('sta-start')
        deadline=time.monotonic()+60
        while True:
            peer=network('wifi-peer-collect')
            if peer['station'] and '[AUTHORIZED]' in raw(peer['station']).decode():
                linked,linked_raw=call('sta-state');info=one(linked,'sta-linked')
                if info['ssid']=='apps579_'+run[:12] and one(linked,'sta-ip-info')['ipAddress']:
                    break
            require(time.monotonic()<deadline,'real OS STA WPA/DHCP did not complete');time.sleep(.5)
        exchange=network('wifi-data-exchange',{'side':'sta'});verify_exchange(exchange,run)
        dora=verify_dora(exchange,'dhcp-server-rx','dhcp-server-tx',info['macAddress'])
        require(dora['address']=='192.0.2.2' and dora['server']==dora['router']=='192.0.2.1', 'actual OS DHCP lease must belong to isolated AP')
        unvalidated,unvalidated_raw=wifi_network(False)
        call('detect');picture('portal_detected_before_cancel');touch('back');picture('portal_after_real_back')
        clicked=touch('wifi-notification-open');picture('portal_notification_opened')
        authorized=touch('wifi-portal-authorize')
        call('detect');validated,validated_raw=wifi_network(True)
        require(validated['netId']==unvalidated['netId'], 'portal authentication must validate the original WiFi NetHandle')
        portal=network('wifi-ip-collect')
        requests=[packet(row) for row in native(portal,'http-peer-request')]
        responses=[packet(row) for row in native(portal,'http-peer-response')]
        require(any(body.startswith(b'HTTP/1.1 302 Found\r\n') for body in responses) and
                any(body.startswith(b'HTTP/1.1 204 No Content\r\n') for body in responses) and
                any(body.startswith(('GET /allow/'+run+' ').encode()) for body in requests) and
                any(body.startswith(('GET /login/'+run+' ').encode()) for body in requests), 'OS detector + actual browser nonce login/allow/dual-HTTP recovery wire required')
        dns_requests = [packet(row) for row in native(portal, 'dns-rx')]
        for domain in ('wifi.apps579.invalid', 'wifi-fallback.apps579.invalid', 'login.apps579.invalid'):
            encoded = b''.join(bytes([len(part)]) + part.encode() for part in domain.split('.')) + b'\x00'
            require(any(encoded in body[12:] for body in dns_requests), 'actual OS detector/browser DNS question missing: ' + domain)
        require(any(b'\xc0\x00\x02\x01' in packet(row) for row in native(portal, 'dns-tx')), 'actual isolated DNS answer must provide peer AP address')
        value['observed_slices'].append({'slice':'real_independent_STA_DHCP_IP_nonce_and_OS_portal_notification_cancel_auth_recovery',
            'fixture':fixture,'dora':dora,'data':exchange,'linked':linked_raw,'before_validation':unvalidated_raw,
            'notification_click':clicked,'browser_auth':authorized,'after_validation':validated_raw,'peer_wire':portal})
        # A restarted ordinary caller must not lose ownership of its saved
        # network ID. Its private nonce marker drives public config removal.
        touch('force-stop',{'role':'grant'});call('identity');call('sta-stop')
        call('sta-start');wifi_network(True);call('sta-stop')
        network('wifi-peer-stop')
        call('ap-start');network('wifi-peer-start',{'mode':'sta'})
        peer=network('wifi-peer-collect');peer_mac=raw(peer['mac']).decode().strip().lower()
        deadline=time.monotonic()+30
        while True:
            ap,ap_raw=call('ap-state');state=one(ap,'ap-state')
            matching=[row for row in state['stations'] if row['macAddress'].lower()==peer_mac]
            if state['active'] and len(matching)==1 and matching[0]['ipAddress']:
                break
            require(time.monotonic()<deadline,'real AP DHCP station enumeration absent');time.sleep(.5)
        ap_data=network('wifi-data-exchange',{'side':'ap'});verify_exchange(ap_data,run)
        ap_dora=verify_dora(ap_data,'dhcp-client-tx','dhcp-client-rx',peer_mac)
        require(ap_dora['address']==ap_data['peer_ip']==matching[0]['ipAddress'], 'public AP station IP must equal independent client DORA lease')
        network('wifi-peer-stop')
        deadline=time.monotonic()+30
        while True:
            left,left_raw=call('ap-state');left_state=one(left,'ap-state')
            if not any(row['macAddress'].lower()==peer_mac for row in left_state['stations']):
                break
            require(time.monotonic()<deadline,'public AP did not remove actual departed station');time.sleep(.5)
        all_events=rows(left_raw['journal'],run,'grant')
        require(any(row['event']=='hotspot-join' and json.loads(row['value'])['macAddress'].lower()==peer_mac for row in all_events) and
                any(row['event']=='hotspot-leave' and json.loads(row['value'])['macAddress'].lower()==peer_mac for row in all_events), 'real public join and leave callbacks required')
        picture('actual_hotspot_after_peer_leave')
        value['observed_slices'].append({'slice':'real_independent_AP_WPA_DHCP_IP_nonce_join_leave_and_restore',
            'station':ap_raw,'dora':ap_dora,'data':ap_data,'leave':left_raw})
        # The fixed official default is ten minutes; the public SDK has no
        # timeout setter. Observe real guest active time without a fabricated
        # timer, broadcast or direct notification-provider invocation.
        idle_start = next(row['active_ms'] for row in left if row['event'] == 'ap-state')
        idle_deadline = time.monotonic() + 660
        idle_records = [];idle_state = left_state;idle_elapsed = 0
        while idle_state['active'] and idle_elapsed < 610000:
            require(not idle_state['stations'], 'unrelated hotspot station appeared during owned idle observation')
            require(time.monotonic() < idle_deadline, 'default idle interval not observed in actual guest active time; no unsupported inference')
            time.sleep(5)
            idle_values,idle_raw = call('ap-state');idle_state = one(idle_values,'ap-state')
            idle_elapsed = next(row['active_ms'] for row in idle_values if row['event'] == 'ap-state') - idle_start
            require(idle_elapsed >= 0, 'actual guest active clock moved backwards')
            idle_records.append(idle_raw)
        idle_boundary = {'default_source_timeout_ms':600000,'actual_guest_active_elapsed_ms':idle_elapsed,
            'state':idle_state,'typed_observations':idle_records,'services':network('wifi-ip-collect'),
            'frame':picture('actual_default_hotspot_idle_boundary'),
            'disposition':'observed_active_after_default_interval' if idle_state['active'] else 'actual_OS_hotspot_closed'}
        if not idle_state['active']:
            idle_boundary['notification_click'] = touch('wifi-hotspot-notification-reenable')
            deadline = time.monotonic() + 30
            while True:
                restored,restored_raw = call('ap-state');restored_state = one(restored,'ap-state')
                if restored_state['active']:
                    break
                require(time.monotonic()<deadline, 'real hotspot notification action did not enable the OS hotspot');time.sleep(.5)
            require(restored_state['config']['ssid']=='apps579_ap_'+run[:12], 'notification recovery changed the actual owned hotspot identity')
            network('wifi-peer-start',{'mode':'sta'})
            rejoined = network('wifi-peer-collect');rejoined_mac = raw(rejoined['mac']).decode().strip().lower()
            require(rejoined_mac==peer_mac, 'same actual independent radio must rejoin recovered hotspot')
            recovered_data = network('wifi-data-exchange',{'side':'ap'});verify_exchange(recovered_data,run)
            recovered_dora = verify_dora(recovered_data,'dhcp-client-tx','dhcp-client-rx',peer_mac)
            require(recovered_dora['address']==recovered_data['peer_ip'], 'actual recovered peer DHCP/IP differs')
            idle_boundary.update(recovered_state=restored_raw,recovered_data=recovered_data,recovered_dora=recovered_dora)
            network('wifi-peer-stop')
        value['observed_slices'].append({'slice':'actual_default_hotspot_idle_boundary_and_available_notification_recovery',**idle_boundary})
        call('ap-stop');call('restore')
    except Exception as error:
        value['failures'].append({'type':type(error).__name__,'message':str(error)})
    finally:
        try:
            cleaned=keep('cleanup',cb['cleanup']());require(not cleaned.get('failures'),'actual WLAN/netns/config cleanup failed')
        except Exception as error:
            value['failures'].append({'cleanup_error':type(error).__name__+': '+str(error)})
    return value
