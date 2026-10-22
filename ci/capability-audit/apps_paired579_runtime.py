"""Real paired PIN/auth, DHardware UI and Cast+Stream business on held guests.

Source-only. Semantic observations never set the parent's package/ID gates.
"""
import ipaddress
import json
import re
import struct
import time

from apps_providers579_bindings import raw
from apps_paired579_project import EXTERNAL_ROLES,require

KEYS={'prepare_callers','install','start','input','collect','network','cleanup'}


def rows(ref,run,role=None,request_id=None):
    values=[json.loads(line) for line in raw(ref).decode().splitlines() if line]
    require(values and all(row['run_id']==run and row['kind']=='paired' for row in values),'actual paired nonce journal')
    return [row for row in values if (role is None or row['role']==role) and (request_id is None or row['request_id']==request_id)]


def one(values,event):
    selected=[row for row in values if row['event']==event];require(len(selected)==1,'one actual '+event)
    return json.loads(selected[0]['value'])


def direct_route(reference,iface,address,mask):
    dest=ipaddress.IPv4Network(address+'/30',strict=False).network_address
    matches=[]
    for line in raw(reference).decode().splitlines()[1:]:
        words=line.split()
        if len(words)<8 or words[0]!=iface:continue
        actual_dest=ipaddress.IPv4Address(struct.pack('<I',int(words[1],16)))
        actual_gateway=ipaddress.IPv4Address(struct.pack('<I',int(words[2],16)))
        actual_mask=ipaddress.IPv4Address(struct.pack('<I',int(words[7],16)))
        if actual_dest==dest and str(actual_mask)==mask and int(words[3],16)&1:
            matches.append((actual_dest,actual_gateway))
    require(len(matches)==1 and str(matches[0][1])=='0.0.0.0','actual direct peer data subnet must use eth0 with no NAT gateway')


def run(guest,root_callbacks,parameters):
    require(type(root_callbacks) is dict and set(root_callbacks)==KEYS and all(callable(value) for value in root_callbacks.values()),'exact original seven held callbacks')
    require(set(parameters)=={'case','run_id','profile'} and parameters['case']=='pair' and re.fullmatch('[a-f0-9]{32}',parameters['run_id']) and parameters['profile'] in ('phone','2in1'),'fixed paired stage data')
    cb=root_callbacks;nonce=parameters['run_id'];serial=0
    result={'schema_version':1,'case':'pair','run_id':nonce,'profile':parameters['profile'],
      'requirement_ids':['behavior:avcast-media-controller-provider-mismatch','behavior:distributed-hardware-ui-preinstall-path-mismatch'],
      'operations':[],'observed_slices':[],'failures':[],
      'unresolved_requirements':[],
      'runtime_pass':False,'first_artifact_behavior_gate_passed':False,'closed_requirement_ids':[]}
    def keep(kind,row):result['operations'].append({'kind':kind,'record':row});return row
    def start(action,role='source_grant',payload=None):
        nonlocal serial
        serial+=1;request={'run_id':nonce,'request_id':str(serial)+'_'+action.replace('-','_'),'action':action,'payload':payload or {}}
        keep('request',{'role':role,**request});keep('start',cb['start'](role,action,request));return request['request_id']
    def finish(request_id,role='source_grant',errors=False):
        observed=keep('collect',cb['collect'](role,request_id));events=rows(observed['journal'],nonce,role,request_id)
        require(any(row['event']=='request' for row in events),'actual dispatched typed paired operation')
        if not errors:require(any(row['event']=='done' for row in events) and not any(row['event'] in ('error','request-error','page-error') for row in events),'actual paired native operation failed')
        return events,observed
    def call(action,role='source_grant',payload=None,errors=False):return finish(start(action,role,payload),role,errors)
    def touch(action,payload):return keep('input_'+action,cb['input'](action,payload))
    def network(action,data=None):return keep('network_'+action,cb['network'](action,data or {}))
    def snapshot(endpoint,label):return touch('snapshot',{'endpoint':endpoint,'label':label})
    def trusted(role,network_id,present):
        deadline=time.monotonic()+45
        while True:
            values,record=call('dm-trusted',role);devices=one(values,'actual-trusted-list')
            matched=[device for device in devices if device['networkId']==network_id]
            require(len(matched)<=1,'ambiguous actual trusted peer')
            if bool(matched)==present:return record
            require(time.monotonic()<deadline,'actual peer trust state did not reach the native boundary');time.sleep(.4)
    def auth_result(request_id,success):
        deadline=time.monotonic()+90
        while True:
            events,record=finish(request_id,errors=True)
            callbacks=[row for row in events if row['event']=='actual-auth-result']
            if callbacks:
                require(len(callbacks)==1 and ((callbacks[0]['code']==0) is success),'actual native PIN decision/result disagrees')
                if not success:require(callbacks[0]['code'] not in (201,202,401),'user reject/cancel must not be a permission or fabricated argument error')
                return record
            require(time.monotonic()<deadline,'actual bindTarget callback did not finish');time.sleep(.5)
    try:
        prepared=keep('prepared',cb['prepare_callers']('pair',nonce,EXTERNAL_ROLES))
        result['archive_sha256']=prepared['archive_sha256'];result['boot_id']=prepared['endpoints']['source']['boot_id']
        require(prepared['profile']==parameters['profile'],'actual package profile mismatch')
        identities={}
        for role in EXTERNAL_ROLES:identities[role]=keep('install_'+role,cb['install'](role))['identity']
        require(identities['source_grant']['appIdentifier']==identities['sink_grant']['appIdentifier'] and
                identities['source_grant']['fingerprint']==identities['sink_grant']['fingerprint'],'real same-app peer identity must agree across per-UDID signing')
        for role in ('source_normal','source_denied'):
            events,record=call('dm-discover',role,errors=True)
            require(any(row['event']=='error' and row['code'] in (201,202) for row in events) and not any(row['event']=='done' for row in events),'ordinary/denied native discovery permission rejection required')
        for endpoint in ('source','sink'):
            role=endpoint+'_grant';request=start('permissions',role);touch('permissions',{'endpoint':endpoint})
            events,_=finish(request,role);require(one(events,'permission-result')['authResults']==[0,0,0],'actual endpoint permission grants required')
        before=network('pair-inspect');baseline={}
        for endpoint,observed in before['actual'].items():
            by_name={item['interface']:item for item in observed['interfaces']};baseline[endpoint]=by_name
            require(by_name['eth0']['address']=='' and by_name['eth1']['address']!='','paired data NIC must start unaddressed while management remains available')
            call('network-before',endpoint+'_grant',{'interface':'eth0'})
        # The actual original plan supplies each address; no new host network,
        # NAT, namespace, listener or management-interface mutation is created.
        plan=json.loads(raw(prepared['plan']));instances={}
        for endpoint in ('source','sink'):
            target=prepared['prepared'][endpoint]['boot_id']
            require(target==prepared['endpoints'][endpoint]['boot_id'],'actual prepared caller boot mismatch')
            # Network identity is independently constrained again by the native
            # observer's MAC matching in the binding; use the retained plan MAC.
            actual_mac=baseline[endpoint]['eth0']['mac']
            values=[value for value in plan['instances'].values() if value['peer_mac']==actual_mac]
            require(len(values)==1,'actual MAC must map to one original instance');instances[endpoint]=values[0]
            net=ipaddress.IPv4Network(plan['network'])
            call('network-config',endpoint+'_grant',{'address':values[0]['address'],'route':str(net.network_address)})
        deadline=time.monotonic()+60
        while True:
            current=network('pair-inspect');ready=True
            for endpoint,observed in current['actual'].items():
                data={item['interface']:item for item in observed['interfaces']}
                if data['eth0']['address']!=instances[endpoint]['address'] or data['eth0']['netmask']!='255.255.255.252':ready=False
                require(data['eth1']['address']==baseline[endpoint]['eth1']['address'] and data['eth1']['mac']==baseline[endpoint]['eth1']['mac'],'actual management NIC/IP changed')
                if ready:direct_route(observed['route'],'eth0',instances[endpoint]['address'],'255.255.255.252')
            if ready:break
            require(time.monotonic()<deadline,'actual independent peer IPv4/mask did not appear');time.sleep(.5)
        local={}
        for endpoint in ('source','sink'):
            call('network-state',endpoint+'_grant')
            values,_=call('local',endpoint+'_grant');local[endpoint]=one(values,'actual-local-device')
            require(re.fullmatch('[A-Fa-f0-9]{64}',local[endpoint]['networkId']),'actual SoftBus local network ID required')
        require(local['source']['networkId']!=local['sink']['networkId'] and local['source']['deviceId']!=local['sink']['deviceId'],'actual independent SoftBus/app device identities required')
        discover=start('dm-discover');finish(discover)
        deadline=time.monotonic()+90
        while True:
            values,found_raw=call('dm-found');found=one(values,'actual-discovered-list')
            # DeviceBasicInfo.deviceType is a string; getLocalDeviceType is a
            # native numeric enum. Do not equate those different API values.
            # The isolated two-endpoint LAN yields one discovered peer; actual
            # post-auth networkId matching below proves the independent target.
            matches=[device for device in found if device['deviceName']==local['sink']['deviceName'] and device['deviceId']!=local['source']['deviceId']]
            if len(matches)==1:break
            require(len(matches)<=1,'ambiguous independently discovered peer')
            require(time.monotonic()<deadline,'actual Ethernet/CoAP peer not discovered');time.sleep(.5)
        call('dm-select',payload={'deviceId':matches[0]['deviceId']})
        trusted('source_grant',local['sink']['networkId'],False)
        rejected=start('dm-auth');snapshot('sink','actual_pin_reject_before');touch('dm-confirm',{'decision':'reject'})
        reject_raw=auth_result(rejected,False);trusted('source_grant',local['sink']['networkId'],False)
        cancelled=start('dm-auth');touch('dm-confirm',{'decision':'allow'});snapshot('sink','actual_generated_pin_cancel')
        touch('dm-pin-cancel',{});cancel_raw=auth_result(cancelled,False);trusted('source_grant',local['sink']['networkId'],False)
        accepted=start('dm-auth');touch('dm-confirm',{'decision':'allow'});pin=touch('dm-pin-enter',{})
        accept_raw=auth_result(accepted,True);source_trusted=trusted('source_grant',local['sink']['networkId'],True)
        sink_trusted=trusted('sink_grant',local['source']['networkId'],True)
        touch('force-stop',{'endpoint':'source','role':'source_grant'});call('identity')
        restart_trust=trusted('source_grant',local['sink']['networkId'],True)
        result['observed_slices'].append({'slice':'real_independent_ETH_SoftBus_discovery_PIN_reject_cancel_accept_and_app_restart',
            'native_interfaces':current,'discovery':found_raw,'reject':reject_raw,'cancel':cancel_raw,'actual_pin':pin,
            'accept':accept_raw,'source_trust':source_trusted,'sink_trust':sink_trusted,'restart':restart_trust})
        network('owning-services579-held', {'locals':local,
            'source_trust':restart_trust,'sink_trust':sink_trusted})
        network('msdp579-held', {'locals':local,
            'source_trust':restart_trust,'sink_trust':sink_trusted})
        # DHardware_UI is triggered by real remote camera use. Its PIN UI is
        # a different provider; do not manually start either hardware dialog.
        try:
            deadline=time.monotonic()+90
            while True:
                values,cameras=call('camera-devices');devices=one(values,'actual-remote-cameras')
                owned=[device for device in devices if device['hostDeviceName']==local['sink']['deviceName']]
                if owned:break
                require(time.monotonic()<deadline,'actual independent peer camera did not enumerate');time.sleep(.5)
            for denied_role in ('source_normal','source_denied'):
                denied,_=call('camera-start',denied_role,{'deviceName':local['sink']['deviceName']},errors=True)
                require(any(row['event']=='error' and row['code'] in (201,202) for row in denied) and not any(row['event']=='actual-remote-camera-started' for row in denied),'actual ordinary/denied camera access boundary required')
            _,camera_started=call('camera-start',payload={'deviceName':local['sink']['deviceName']})
            snapshot('sink','actual_dhardware_remote_camera')
            def actual_photo(request_id,timeout=20):
                deadline=time.monotonic()+timeout
                while True:
                    values,record=finish(request_id,errors=True)
                    photos=[item for item in record['binaries'] if item.get('event')=='actual-remote-camera-photo']
                    if photos:
                        require(len(photos)==1,'one decoded actual remote JPEG per shutter');return record
                    require(not any(row['event']=='actual-remote-photo-error' for row in values),'actual remote photo failed')
                    require(time.monotonic()<deadline,'actual remote photo callback absent');time.sleep(.25)
            camera_before=actual_photo(start('camera-shutter'))
            touch('dhardware-control',{'control':'pause'});time.sleep(1)
            paused_shutter=start('camera-shutter');finish(paused_shutter,errors=True)
            pause_raw=[];deadline=time.monotonic()+3
            while True:
                values,record=finish(paused_shutter,errors=True);pause_raw.append(record)
                require(not any(row['event']=='actual-remote-camera-photo' for row in values),'paused hardware camera still delivered an actual image')
                if time.monotonic()>=deadline:break
                time.sleep(.25)
            camera_pause_service=network('services');touch('dhardware-control',{'control':'resume'})
            deadline=time.monotonic()+15
            while True:
                state_values,camera_resumed=call('camera-state');camera_state=one(state_values,'actual-remote-camera-state')
                if not camera_state['pending']:break
                require(time.monotonic()<deadline,'actual resumed camera did not settle the pending paused shutter');time.sleep(.25)
            camera_after=actual_photo(start('camera-shutter'))
            touch('dhardware-control',{'control':'stop'});camera_stop_ui=touch('dhardware-absent',{})
            _,camera_stopped=call('camera-state',errors=True);camera_stop_service=network('services');call('camera-stop')
            # A new real session after stop must activate the real provider and
            # return a new native JPEG. No receiver-side target image is seeded.
            _,camera_reentry=call('camera-start',payload={'deviceName':local['sink']['deviceName']})
            camera_reentry_photo=actual_photo(start('camera-shutter'));snapshot('sink','actual_dhardware_camera_reentry')
            call('camera-stop');camera_closed=touch('dhardware-absent',{})
            result['observed_slices'].append({'slice':'real_remote_camera_DHardware_UI_pause_resume_disconnect_reentry_JPEG',
                'devices':cameras,'start':camera_started,'before':camera_before,'paused_actual_requests':pause_raw,
                'pause_services':camera_pause_service,'resumed_native':camera_resumed,'resumed_photo':camera_after,
                'stop_ui':camera_stop_ui,'stop_native':camera_stopped,'stop_services':camera_stop_service,
                'reentry':camera_reentry,'reentry_photo':camera_reentry_photo,'closed_ui':camera_closed,
                'scope':'native remote camera descriptor + real decoded JPEG/lifecycle; no claim of an optical image nonce'})
        except Exception as error:
            result['failures'].append({'scope':'dhardware_camera','type':type(error).__name__,'message':str(error)})
            try:call('camera-stop')
            except Exception as cleanup_error:result['failures'].append({'scope':'dhardware_camera_cleanup','message':str(cleanup_error)})
        # Input belongs exclusively to the independent sink ALSA loopback cable.
        # Source consumes only its actual distributed AudioCapturer route.
        try:
            deadline=time.monotonic()+90
            while True:
                values,mics=call('mic-devices');devices=one(values,'actual-remote-microphones')
                owned=[device for device in devices if device['networkId']==local['sink']['networkId']]
                if len(owned)==1:break
                require(len(owned)<=1,'ambiguous independent microphone descriptor')
                require(time.monotonic()<deadline,'complete remote microphone backend did not enumerate peer');time.sleep(.5)
            for denied_role in ('source_normal','source_denied'):
                denied,_=call('mic-start',denied_role,{'networkId':local['sink']['networkId']},errors=True)
                require(any(row['event']=='error' and row['code'] in (201,202) for row in denied) and not any(row['event']=='actual-remote-mic-started' for row in denied),'actual ordinary/denied remote microphone boundary required')
            network('mic-prepare')
            values,started=call('mic-start',payload={'networkId':local['sink']['networkId']})
            chosen=one(values,'actual-remote-mic-started');require(chosen['current'] and all(device['networkId']==local['sink']['networkId'] for device in chosen['current']),'actual capture input did not route to independent peer')
            producer=network('mic-inject-start');time.sleep(.5)
            network('mic-phase-begin',{'phase':'running'});time.sleep(4.5);running=network('mic-phase-end',{'phase':'running'})
            require(not running['semantic_errors'],'actual remote running PCM did not decode fresh stereo challenge')
            snapshot('sink','actual_dhardware_remote_mic_running');touch('dhardware-control',{'control':'pause'})
            network('mic-phase-begin',{'phase':'paused'});time.sleep(4.5);paused=network('mic-phase-end',{'phase':'paused'})
            require(not paused['semantic_errors'],'actual paused remote microphone did not continue with zero PCM')
            touch('dhardware-control',{'control':'resume'})
            network('mic-phase-begin',{'phase':'resumed'});time.sleep(4.5);resumed=network('mic-phase-end',{'phase':'resumed'})
            require(not resumed['semantic_errors'],'resumed remote microphone did not decode fresh stereo challenge')
            # Let the finite original producer drain while the real capture
            # remains open. Killing it before drain would invalidate input proof.
            injected=network('mic-inject-wait');require(not injected['prerequisite_errors'],'actual sink ALSA production/drain failed')
            touch('dhardware-control',{'control':'stop'});stop_ui=touch('dhardware-absent',{})
            time.sleep(1);stopped_values,stopped=call('mic-state',errors=True);time.sleep(1.5)
            after_values,after_stop=call('mic-state',errors=True)
            first=one(stopped_values,'actual-mic-state');last=one(after_values,'actual-mic-state')
            require(not any(device['networkId']==local['sink']['networkId'] for device in last['devices']) or last['state'] in (3,4) or last['bytes']==first['bytes'],'real hardware disconnect did not remove remote route or stop remote capture bytes')
            stop_service=network('services');released_values,released=call('mic-stop');released_state=one(released_values,'actual-mic-stopped')
            time.sleep(1);final_values,mic_final=call('mic-final');final_state=one(final_values,'actual-mic-final')
            require(final_state['present'] is False and final_state['bytes']==released_state['bytes'],'actual microphone release still delivered callbacks/PCM')
            result['observed_slices'].append({'slice':'real_remote_microphone_DHardware_provider_nonce_PCM_pause_zero_resume_disconnect',
                'remote_devices':mics,'start':started,'actual_sink_producer':producer,'finite_producer_result':injected,
                'running':running,'paused':paused,'resumed':resumed,'after_stop':[stopped,after_stop],'stop_ui':stop_ui,'stop_services':stop_service,'released':released,'after_release':mic_final,
                'content_scope':'fresh independent stereo challenge only sink ALSA; actual remote source Capturer PCM with per-phase native byte boundaries'})
        except Exception as error:
            result['failures'].append({'scope':'dhardware_microphone','type':type(error).__name__,'message':str(error)})
            try:network('mic-inject-wait')
            except Exception as cleanup_error:result['failures'].append({'scope':'dhardware_microphone_producer_cleanup','message':str(cleanup_error)})
            try:call('mic-stop')
            except Exception as cleanup_error:result['failures'].append({'scope':'dhardware_microphone_cleanup','message':str(cleanup_error)})
        # Independent sink DAC consumes only the media sent through the actual
        # Cast+Stream route. The sink never receives the target asset as fixture.
        network('media-prepare');network('capture-start',{'phase':'baseline'});time.sleep(3);baseline_pcm=network('capture-stop',{'audible':False})
        call('sink-observe','sink_grant');call('cast-create');call('cast-discover')
        deadline=time.monotonic()+90
        while True:
            values,cast_found=call('cast-found');outputs=one(values,'actual-cast-devices')
            candidates=[output for output in outputs if any(device.get('networkId')==local['sink']['networkId'] and device.get('ipAddress')==instances['sink']['address'] and device.get('supportedProtocols',0)&2 for device in output['devices'])]
            if candidates:break
            require(time.monotonic()<deadline,'actual authenticated Cast+Stream peer route not discovered');time.sleep(.5)
        call('cast-select',payload={'networkId':local['sink']['networkId'],'address':instances['sink']['address']})
        call('cast-picker');snapshot('source','actual_cast_picker_cancel');touch('back',{'endpoint':'source'})
        call('cast-picker');picker_selection=touch('cast-picker-peer',{})
        # Native controller inspection determines whether that real provider
        # already connected. If it did not, explicitly request the same actual
        # discovered endpoint through the public typed casting API.
        probe,_=call('cast-controller',errors=True)
        if not any(row['event']=='actual-source-controller-ready' for row in probe):call('cast-connect')
        deadline=time.monotonic()+45
        while True:
            controller,controller_raw=call('cast-controller',errors=True)
            if any(row['event']=='actual-source-controller-ready' for row in controller):break
            require(time.monotonic()<deadline,'real source cast controller unavailable after route request');time.sleep(.5)
        deadline=time.monotonic()+45
        while True:
            attached,sink_raw=call('sink-attach','sink_grant',errors=True)
            if any(row['event']=='actual-sink-surface-bound' for row in attached):break
            require(time.monotonic()<deadline,'actual OS sink session/surface not ready');time.sleep(.5)
        network('capture-start',{'phase':'playing'});call('cast-start');time.sleep(8);playing_pcm=network('capture-stop',{'audible':True})
        call('cast-pause');network('capture-start',{'phase':'paused'});time.sleep(3);paused_pcm=network('capture-stop',{'audible':False})
        network('capture-start',{'phase':'resumed'});call('cast-resume');time.sleep(8);resumed_pcm=network('capture-stop',{'audible':True})
        source_state=call('cast-state')[1];sink_state=call('cast-state','sink_grant')[1]
        call('cast-stop');network('capture-start',{'phase':'disconnected'});time.sleep(3);disconnected_pcm=network('capture-stop',{'audible':False})
        services=network('services');call('cast-cleanup');call('cast-cleanup','sink_grant')
        touch('force-stop',{'endpoint':'source','role':'source_grant'});call('identity');trusted('source_grant',local['sink']['networkId'],True)
        call('sink-observe','sink_grant');call('cast-create');call('cast-discover')
        deadline=time.monotonic()+90
        while True:
            discovered,_=call('cast-found');outputs=one(discovered,'actual-cast-devices')
            if any(any(device.get('networkId')==local['sink']['networkId'] and device.get('ipAddress')==instances['sink']['address'] and device.get('supportedProtocols',0)&2 for device in output['devices']) for output in outputs):break
            require(time.monotonic()<deadline,'same independent cast endpoint not rediscovered after source app death');time.sleep(.5)
        call('cast-select',payload={'networkId':local['sink']['networkId'],'address':instances['sink']['address']})
        call('cast-picker');reentry_picker=touch('cast-picker-peer',{})
        reentry_probe,_=call('cast-controller',errors=True)
        if not any(row['event']=='actual-source-controller-ready' for row in reentry_probe):call('cast-connect')
        deadline=time.monotonic()+45
        while True:
            ready,_=call('cast-controller',errors=True)
            if any(row['event']=='actual-source-controller-ready' for row in ready):break
            require(time.monotonic()<deadline,'new source session did not regain a native cast controller');time.sleep(.5)
        deadline=time.monotonic()+45
        while True:
            rebound,reentry_sink=call('sink-attach','sink_grant',errors=True)
            if any(row['event']=='actual-sink-surface-bound' for row in rebound):break
            require(time.monotonic()<deadline,'new actual sink session/surface did not reconnect');time.sleep(.5)
        network('capture-start',{'phase':'reentry'});call('cast-start');time.sleep(8);reentry_pcm=network('capture-stop',{'audible':True})
        call('cast-stop');call('cast-cleanup');call('cast-cleanup','sink_grant')
        result['observed_slices'].append({'slice':'actual_AVCast_provider_selection_OS_sink_decode_nonce_DAC_pause_resume_disconnect',
            'discovered':cast_found,'picker':picker_selection,'source_controller':controller_raw,'sink_surface':sink_raw,
            'baseline':baseline_pcm,'playing':playing_pcm,'paused':paused_pcm,'resumed':resumed_pcm,
            'disconnected':disconnected_pcm,'source_native_state':source_state,'sink_native_state':sink_state,'services_wire':services,
            'actual_reentry_picker':reentry_picker,'new_sink_session':reentry_sink,'reentry_independent_DAC':reentry_pcm})
        call('dm-unbind',payload={'networkId':local['sink']['networkId']});unbound=trusted('source_grant',local['sink']['networkId'],False)
        result['observed_slices'].append({'slice':'actual_owned_peer_unbind_and_native_trust_removal','raw':unbound})
    except Exception as error:
        result['failures'].append({'scope':'pair','type':type(error).__name__,'message':str(error)})
    finally:
        try:keep('final_service_boundary',cb['network']('services',{}))
        except Exception as error:result['failures'].append({'scope':'final_raw','message':str(error)})
        try:
            cleaned=keep('cleanup',cb['cleanup']());require(not cleaned.get('failures'),'actual paired cleanup failed; original Owner retains resources')
        except Exception as error:result['failures'].append({'scope':'cleanup','message':str(error)})
    return result
