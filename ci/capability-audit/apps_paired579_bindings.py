"""Finite paired business binding on two original root-held IO instances.

No VM/Owner/Runner/socket/server/process or lease is created. The only host
mutation is nonce evidence/media files; guest operations use original IO.
"""
import hashlib
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import re
import shlex
import time

from apps_providers579_bindings import raw, objects, bms_json
from apps_paired579_project import ACTIONS, EXTERNAL_ROLES, bundle, require
from apps_paired579_capture import HeldCapture
from apps_paired579_media import prepare as prepare_media, assess
from apps_paired579_mic import prepare as prepare_mic, inspect_segment, PHASES as MIC_PHASES
from guest_ui import NodeNotReady, LayoutNotReady, select_node, bounds


def bind(root_io):
    io=root_io;peer=io.apps579_peer_io;run=io.run_id
    require(re.fullmatch('[a-f0-9]{32}',run) and peer is not io and peer.archive_sha256==io.archive_sha256 and
            peer.boot_id!=io.boot_id and peer.udid.lower()!=io.udid.lower(),'independently held same-archive peers required')
    endpoints={'source':io,'sink':peer};plan_ref=io.apps579_peer_plan;plan=json.loads(raw(plan_ref))
    require(plan['run_id']==run and plan['archive_sha256']==io.archive_sha256 and set(plan['instances'])=={'listener','connector'},'actual original peer plan required')
    network=ipaddress.IPv4Network(plan['network']);require(network.is_private and network.prefixlen==30 and not network.overlaps(ipaddress.IPv4Network('10.0.2.0/24')),'independent private data subnet')
    instances={}
    for endpoint,owned in endpoints.items():
        matches=[row for row in plan['instances'].values() if row['target']==owned.target]
        require(len(matches)==1,'actual held target must match one original launcher instance');instances[endpoint]=matches[0]
    require(len({value['peer_mac'] for value in instances.values()}|{value['management_mac'] for value in instances.values()})==4,'four distinct actual configured NIC identities')
    endpoint_outputs={e:Path(o.output)/('apps_paired579_'+run) for e,o in endpoints.items()}
    for path in endpoint_outputs.values():path.mkdir(exist_ok=False)
    output=endpoint_outputs['source']
    remote='/data/local/tmp/paired579_'+run
    state={'serial':0,'prepared':False,'callers':{},'installed':set(),'identities':{},'prefix':{},'created':set(),
           'closed':False,'capture':None,'challenge':None,'locals':{},'last':{},'network_changed':set(),'pcap_prefix':{},'interfaces_before':None,'mic_challenge':None,'mic_injector':None,'mic_marks':{}}

    def split(role):
        require(role in EXTERNAL_ROLES,'fixed paired endpoint/local role');return role.split('_',1)
    def directory(role):
        _,local=split(role);return '/data/app/el2/100/base/'+bundle('pair',local)+'/files'
    def save(label,value):
        state['serial']+=1;p=output/('%05d_'%state['serial']+label)
        p.write_bytes(value if type(value) is bytes else (value.encode() if type(value) is str else (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()))
        return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    def shell(endpoint,script,label,**options):
        require(endpoint in endpoints and re.fullmatch('[a-zA-Z0-9_-]+',label),'fixed endpoint/shell label')
        return endpoints[endpoint].shell('set -eu\n'+script,'paired579_'+label,**options)
    def begin(label):
        marks={e:(len(o.receipts),len(o.qmp_receipts)) for e,o in endpoints.items()}
        for endpoint,owned in endpoints.items():
            require(shell(endpoint,'cat /proc/sys/kernel/random/boot_id',label+'_'+endpoint)['stdout'].strip()==owned.boot_id,'actual paired boot changed')
        return marks
    def result(mark,**data):
        return {'run_id':run,'archive_sha256':io.archive_sha256,'plan':plan_ref,
            'endpoints':{e:{'boot_id':o.boot_id,'udid':o.udid,'commands':[o.ref_receipt(row) for row in o.receipts[mark[e][0]:]],
              'qmp_records':o.qmp_receipts[mark[e][1]:]} for e,o in endpoints.items()},**data}
    def request_check(role,action,request):
        split(role)
        require(role in state['installed'] and action in ACTIONS and set(request)=={'run_id','request_id','action','payload'} and
            request['run_id']==run and request['action']==action and re.fullmatch('[a-z0-9_-]{1,64}',request['request_id']) and type(request['payload']) is dict,'fixed actual dispatched request')
        keys={'network-before':{'interface'},'network-config':{'address','route'},'dm-select':{'deviceId'},
            'dm-unbind':{'networkId'},'cast-select':{'networkId','address'},'mic-start':{'networkId'},'camera-start':{'deviceName'}}.get(action,set())
        require(set(request['payload'])==keys and all(type(value) is str and 0<len(value)<=255 for value in request['payload'].values()),'data-only finite action payload')
        if action=='network-before':require(request['payload']['interface']=='eth0','actual MAC-mapped data NIC only')
        if action=='network-config':
            endpoint,_=split(role);require(request['payload']=={'address':instances[endpoint]['address'],'route':str(network.network_address)},'actual launcher private address only')
        if action in ('cast-select','mic-start','dm-unbind'):
            endpoint,_=split(role);other='sink' if endpoint=='source' else 'source'
            require(other in state['locals'] and request['payload']['networkId']==state['locals'][other]['networkId'],'actual independently observed peer network ID only')
            if action=='cast-select':require(request['payload']['address']==instances[other]['address'],'actual independent peer data IP only')
        if action=='camera-start':require(split(role)[0]=='source' and request['payload']['deviceName']==state['locals']['sink']['deviceName'],'actual independent peer camera name only')
    def launch(role,action,request):
        request_check(role,action,request);endpoint,local=split(role)
        argv=['aa','start','-b',bundle('pair',local),'-a','EntryAbility','-m','entry','-u','100']
        for key in ('run_id','request_id','action'):argv+=['--ps',key,request[key]]
        argv+=['--ps','payload',json.dumps(request['payload'],separators=(',',':'))]
        row=shell(endpoint,shlex.join(argv),'start_'+role+'_'+request['request_id'])
        require('start ability successfully' in row['stdout'].lower(),'actual AMS rejected paired caller');state['last'][role]=request
    def pull(role):
        endpoint,_=split(role);owned=endpoints[endpoint];base=directory(role)
        listing=shell(endpoint,'ls '+base+'/apps-paired579-'+run+'-*.jsonl','journal_list_'+role,allow_failure=True)
        require(listing['exit_code'] in (0,1,2),'actual journal listing failed');data=[];events=[];files=[]
        for remote_file in sorted(listing['stdout'].splitlines() if listing['exit_code']==0 else []):
            require(re.fullmatch(re.escape(base+'/apps-paired579-'+run+'-')+r'[1-9][0-9]*\.jsonl',remote_file),'actual fixed caller journal path')
            for attempt in range(8):
                state['serial']+=1;path=endpoint_outputs[endpoint]/('journal_%05d.jsonl'%state['serial']);owned.receive(remote_file,path,'paired579_journal_'+str(state['serial']))
                body=path.read_bytes();ref={'path':str(path),'sha256':hashlib.sha256(body).hexdigest()}
                require(body.startswith(state['prefix'].get((endpoint,remote_file),b'')),'actual journal replaced/truncated')
                if body.endswith(b'\n'):break
                require(attempt<7,'actual journal remains partial');time.sleep(.05)
            state['prefix'][(endpoint,remote_file)]=body
            values=[json.loads(line) for line in body.decode().splitlines() if line]
            for index,row in enumerate(values):
                require(row['run_id']==run and row['kind']=='paired' and row['role']==role and row['endpoint']==endpoint and
                    row['bundle']==bundle('pair',split(role)[1]) and row['seq']==index and type(row['uid']) is int and
                    remote_file.endswith('-'+str(row['pid'])+'.jsonl'),'actual caller identity/sequence')
                if role in state['identities']:require(row['uid']==state['identities'][role]['uid'],'actual caller UID changed')
            files.append({'endpoint':endpoint,'remote':remote_file,'raw':ref});data.append(body);events.extend(values)
        return b''.join(data),events,files
    def collect(role,request_id):
        mark=begin('collect_'+role);require(re.fullmatch('[a-z0-9_-]{1,64}',request_id),'fixed request id')
        deadline=time.monotonic()+30
        while True:
            body,events,files=pull(role);selected=[row for row in events if row['request_id']==request_id]
            if any(row['event'] in ('done','error','request-error','page-error') for row in selected):break
            require(time.monotonic()<deadline,'actual paired operation did not return');time.sleep(.2)
        require(not any(row['event']=='actual-remote-mic-storage-error' for row in events),'actual callback PCM storage/frame failure retained')
        for row in selected:
            if row['event']=='actual-local-device':state['locals'][split(role)[0]]=json.loads(row['value'])
        binaries=[]
        for row in selected:
            if row['event']=='actual-remote-camera-photo':
                from PIL import Image
                value=json.loads(row['value']);path=value['file']
                require(re.fullmatch(re.escape(directory(role)+'/paired579-camera-'+run+'-')+r'[a-z0-9_-]{1,64}\.jpg',path),'actual remote camera JPEG only')
                state['serial']+=1;target=endpoint_outputs[split(role)[0]]/('camera_%05d.jpg'%state['serial'])
                endpoints[split(role)[0]].receive(path,target,'paired579_camera_'+str(state['serial']));data=target.read_bytes()
                require(4<len(data)<=32*1024*1024 and len(data)==value['bytes'],'actual remote photo byte count differs')
                with Image.open(BytesIO(data)) as decoded:
                    require(decoded.format=='JPEG','actual remote camera output must decode as JPEG');size=decoded.size;decoded.verify()
                binaries.append({'event':'actual-remote-camera-photo','raw':{'path':str(target),'sha256':hashlib.sha256(data).hexdigest()},'bytes':len(data),'decoded_size':list(size)})
                continue
            if row['event'] not in ('actual-mic-state','actual-mic-stopped'):continue
            value=json.loads(row['value']);path=value['file']
            if not value['bytes']:continue
            require(re.fullmatch(re.escape(directory(role)+'/paired579-mic-'+run+'-')+r'[a-z0-9_-]{1,64}\.pcm',path),'actual owned microphone output only')
            state['serial']+=1;target=endpoint_outputs[split(role)[0]]/('mic_%05d.pcm'%state['serial']);endpoints[split(role)[0]].receive(path,target,'paired579_mic_'+str(state['serial']))
            data=target.read_bytes();require(0<value['bytes']<=len(data)<=16*1024*1024 and value['bytes']%4==0,'actual bounded captured bytes and complete native prefix')
            binaries.append({'raw':{'path':str(target),'sha256':hashlib.sha256(data).hexdigest()},'bytes':len(data),'native_journal_bytes':value['bytes']})
        return result(mark,journal=save('journal_'+role+'_'+request_id+'.jsonl',body),journal_files=files,binaries=binaries)
    def internal(role,action,payload=None):
        state['serial']+=1;rid='binding_'+str(state['serial'])+'_'+action
        launch(role,action,{'run_id':run,'request_id':rid,'action':action,'payload':payload or {}})
        value=collect(role,rid);events=[row for row in [json.loads(line) for line in raw(value['journal']).decode().splitlines()] if row['request_id']==rid]
        require(any(row['event']=='done' for row in events) and not any(row['event'] in ('error','request-error','page-error') for row in events),'actual bound native action failed: '+action)
        return value,events
    def prepare_callers(case,nonce,roles):
        mark=begin('prepare');require(case=='pair' and nonce==run and tuple(roles)==EXTERNAL_ROLES and not state['prepared'],'fixed single paired preparation')
        spec=io.package_inputs['native_helpers']['apps_paired579'];require(set(spec)=={'binary','build','source','abi'},'actual fixed observer build input')
        for key in ('binary','build','source'):raw(spec[key])
        source=Path(__file__).with_name('apps_paired579')/'paired_net.c';require(hashlib.sha256(source.read_bytes()).hexdigest()==spec['source']['sha256'],'actual fixed observer source differs')
        preparations={};identities={}
        for endpoint,owned in endpoints.items():
            udid=shell(endpoint,'bm get --udid','actual_udid_'+endpoint)['stdout'].strip().splitlines()
            require(len(udid)==2 and udid[0]=='udid of current device is :' and udid[1].lower()==owned.udid.lower(),'actual BMS UDID differs from held boot')
            env=owned.test_environment if hasattr(owned,'test_environment') else owned.guest.report['test_environment']
            require({'arm':'armv7a','armv7a':'armv7a','arm64':'arm64','x86_64':'x86_64'}.get(spec['abi'])==env['guest_arch'],'actual helper ABI differs')
            shell(endpoint,'test ! -e '+remote+'\nmkdir -m 700 '+remote,'fresh_owned_directory_'+endpoint);state['created'].add(endpoint)
            owned.send(spec['binary']['path'],remote+'/paired_net','paired579_observer_send_'+endpoint)
            digest=shell(endpoint,'chmod 700 '+remote+'/paired_net\nsha256sum '+remote+'/paired_net','actual_observer_'+endpoint)
            require(digest['stdout'].split()==[spec['binary']['sha256'],remote+'/paired_net'],'actual guest observer binary differs')
            local_roles=('normal','grant','denied') if endpoint=='source' else ('grant',)
            built=owned.prepare_callers('apps_paired579','pair',run,local_roles,{'profile':env['device_type'],'udid':owned.udid,'endpoint':endpoint})
            preparations[endpoint]=built
            for local,row in built['callers'].items():state['callers'][endpoint+'_'+local]=row
            identities[endpoint]=owned.udid.lower()
        require(identities['source']!=identities['sink'],'distinct actual BMS identities required');state['prepared']=True
        return result(mark,prepared=preparations,native_helper=spec,profile=(io.test_environment if hasattr(io,'test_environment') else io.guest.report['test_environment'])['device_type'])
    def install(role):
        mark=begin('install_'+role);endpoint,local=split(role);owned=endpoints[endpoint]
        require(state['prepared'] and role in state['callers'] and role not in state['installed'],'actual prepared unique role')
        caller=state['callers'][role];raw(caller['signed']);target=remote+'/'+local+'.hap'
        owned.send(caller['signed']['path'],target,'paired579_hap_send_'+role)
        installed=shell(endpoint,shlex.join(['bm','install','-r','-p',target,'-u','100']),'install_'+role,timeout=600)
        require('install bundle successfully.' in installed['stdout'],'actual BMS install failed');state['installed'].add(role)
        bms=shell(endpoint,shlex.join(['bm','dump','-n',bundle('pair',local),'-u','100']),'bms_'+role)
        identity,events=internal(role,'identity');self_rows=[row for row in events if row['event']=='self-identity']
        require(len(self_rows)==1,'actual identity self-query required');value=dict(json.loads(self_rows[0]['value']),uid=self_rows[0]['uid'])
        require(value['fingerprint']==caller['identity']['fingerprint'] and value['bundle']==bundle('pair',local) and
            any(row.get('bundleName')==value['bundle'] and row.get('uid')==value['uid'] and row.get('fingerprint')==value['fingerprint'] for row in objects(bms_json(bms['stdout']))),'actual BMS/native/sign certificate identity mismatch')
        applications=[row for row in objects(bms_json(bms['stdout'])) if row.get('bundleName')==value['bundle'] and row.get('uid')==value['uid'] and 'appPrivilegeLevel' in row and 'isSystemApp' in row]
        require(len(applications)==1 and value['uid']//200000==100,'actual user100 BMS application identity required')
        application=applications[0];expected_apl='normal' if local=='normal' else 'system_core'
        require(application['appPrivilegeLevel']==expected_apl and application['isSystemApp']==(local!='normal'),'actual ordinary/system denied/grant identity differs from signed role')
        value.update(user_id=100,apl=application['appPrivilegeLevel'],isSystemApp=application['isSystemApp'])
        state['identities'][role]=value
        return result(mark,identity=value,self_query=identity,bms=bms['stdout_ref'])
    def start(role,action,request):
        mark=begin('start_'+role);launch(role,action,request);return result(mark,request=save('request.json',request))
    def nodes(layout,bundle_name):
        found=[]
        def visit(node,inherited=''):
            attrs=node['attributes'];owner=attrs.get('bundleName') or inherited
            if owner==bundle_name:found.append(attrs)
            for child in node.get('children',[]):visit(child,owner)
        for root in (layout if type(layout) is list else [layout]):visit(root)
        return found
    def snapshot(endpoint,label):
        owned=endpoints[endpoint];layout,path=owned.ui.layout(label='paired579_'+label)
        return {'endpoint':endpoint,'layout':save(label+'_layout.json',layout),'original_layout':str(path),
            'frame':owned.frame('paired579_'+label),'ams':shell(endpoint,'aa dump -a -u 100',label+'_ams')['stdout_ref']}
    def click_text(endpoint,provider,texts,pattern=None):
        deadline=time.monotonic()+35
        while True:
            try:
                layout,path=endpoints[endpoint].ui.layout(label='paired579_real_provider_control');matches=[]
                def visit(node,inherited='',ancestors=()):
                    attrs=node['attributes'];owner=attrs.get('bundleName') or inherited;chain=ancestors+((attrs,owner),)
                    text=attrs.get('text','')
                    if owner==provider and (text in texts or (pattern and re.fullmatch(pattern,text))) and attrs.get('visible')=='true':
                        targets=[a for a,b in reversed(chain) if b==provider and a.get('visible')=='true' and a.get('enabled')=='true' and a.get('clickable')=='true']
                        if targets:matches.append(targets[0])
                    require(len(chain)<=256,'bounded actual hierarchy')
                    for child in node.get('children',[]):visit(child,owner,chain)
                for root in (layout if type(layout) is list else [layout]):visit(root)
                matches=list({attrs['bounds']:attrs for attrs in matches}.values())
                require(len(matches)<=1,'ambiguous actual provider control')
                if not matches:raise NodeNotReady('actual source-defined provider control absent')
                selected=matches[0];x,y,w,h=bounds(selected['bounds']);before=save('control_layout.json',layout)
                endpoints[endpoint].ui.shell('uitest uiInput click '+str(x+w//2)+' '+str(y+h//2),'paired579_actual_provider_click')
                return {'endpoint':endpoint,'bundle':provider,'node':selected,'layout':before,'original_layout':str(path),'frame':endpoints[endpoint].frame('paired579_clicked')}
            except (NodeNotReady,LayoutNotReady):
                require(time.monotonic()<deadline,'actual provider control not ready');time.sleep(.25)
    def input(action,payload):
        mark=begin('input_'+action);require(type(payload) is dict,'finite UI data')
        if action in ('snapshot','back','force-stop'):
            require(set(payload)<= {'endpoint','label','role'} and payload['endpoint'] in endpoints,'finite original endpoint input')
            endpoint=payload['endpoint']
            if action=='snapshot':return result(mark,snapshot=snapshot(endpoint,payload['label']))
            if action=='back':endpoints[endpoint].ui.shell('uitest uiInput keyEvent Back','paired579_real_back');return result(mark,frame=endpoints[endpoint].frame('paired579_back'))
            role=payload['role'];require(split(role)[0]==endpoint,'exact caller endpoint');shell(endpoint,shlex.join(['aa','force-stop',bundle('pair',split(role)[1]),'-u','100']),'force_stop_'+role)
            return result(mark,frame=endpoints[endpoint].frame('paired579_caller_stopped'))
        if action=='permissions':
            require(set(payload)=={'endpoint'} and payload['endpoint'] in endpoints,'finite permission endpoint');endpoint=payload['endpoint'];role=endpoint+'_grant';trace=[];deadline=time.monotonic()+45
            while True:
                _,values,_=pull(role)
                completed=[row for row in values if row['request_id']==state['last'][role]['request_id'] and row['event']=='permission-result']
                if completed:return result(mark,native_permission=save('permission_rows.json',completed),ui_actions=trace)
                try:
                    layout,path=endpoints[endpoint].ui.layout(label='paired579_actual_permission')
                    label='Pair579 '+endpoint+' grant '+run[:8]
                    if not any(label in value for attrs in nodes(layout,'com.ohos.permissionmanager') for value in attrs.values() if type(value) is str):
                        raise NodeNotReady('actual nonce-named permission dialog not ready')
                    trace.append(click_text(endpoint,'com.ohos.permissionmanager',('Allow','Allow while using the app','允许','仅使用期间允许')))
                except (NodeNotReady,LayoutNotReady):pass
                require(time.monotonic()<deadline,'actual permission workflow not finished');time.sleep(.2)
        if action=='dm-confirm':
            require(payload in ({'decision':'allow'},{'decision':'reject'}),'finite native authentication choice')
            selected=click_text('sink','com.ohos.devicemanagerui',('Always trust','始终信任') if payload['decision']=='allow' else (),
                None if payload['decision']=='allow' else r"Don't trust \([0-9]+\)|不信任 \([0-9]+ 秒\)")
            return result(mark,actual_choice=selected)
        if action=='dm-pin-cancel':
            require(payload=={},'finite actual PIN cancel');return result(mark,actual_cancel=click_text('source','com.ohos.devicemanagerui',('Cancel','取消')))
        if action=='dm-pin-enter':
            require(payload=={},'PIN must come from actual peer UI, never caller input');deadline=time.monotonic()+35
            while True:
                try:
                    layout,path=peer.ui.layout(label='paired579_actual_peer_pin');attributes=nodes(layout,'com.ohos.devicemanagerui');codes=[]
                    for attrs in attributes:
                        if attrs.get('visible')!='true':continue
                        for key in ('text','description','accessibilityText'):
                            match=re.fullmatch(r'\[n1\]([0-9]{6})\[n0\]',attrs.get(key,''))
                            if match:codes.append(match[1])
                    if not codes:
                        digits=[(bounds(attrs['bounds']),attrs['text']) for attrs in attributes if attrs.get('visible')=='true' and re.fullmatch('[0-9]',attrs.get('text',''))]
                        require(len(digits)<=6,'ambiguous actual PIN digits')
                        if len(digits)==6:
                            require(len({item[0][1] for item in digits})==1,'actual PIN digits must form one visible source-defined row');codes=[''.join(item[1] for item in sorted(digits))]
                    require(len(set(codes))<=1,'conflicting actual PIN accessibility/visible text')
                    if not codes:raise NodeNotReady('actual peer PIN absent')
                    code=codes[0];break
                except (NodeNotReady,LayoutNotReady):require(time.monotonic()<deadline,'actual generated peer PIN did not appear');time.sleep(.2)
            source_layout,source_path=io.ui.layout(label='paired579_actual_pin_input')
            require(any(attrs.get('id')=='inputpin' for attrs in nodes(source_layout,'com.ohos.devicemanagerui')),'actual InputPinDialog hidden focused input required')
            evidence={'peer_pin_layout':save('peer_pin_layout.json',layout),'peer_original_layout':str(path),
                'source_input_layout':save('source_pin_input_layout.json',source_layout),'source_original_layout':str(source_path),
                'actual_pin':save('actual_peer_pin.txt',code),'peer_frame':peer.frame('paired579_actual_pin')}
            # The source's actual InputPinDialog gives this invisible TextInput
            # default focus and validates onChange at six digits; no direct DM
            # callback or private PIN registry is invoked.
            io.ui.shell('uitest uiInput inputText '+code,'paired579_type_actual_peer_pin')
            return result(mark,actual_pin_entry=evidence,source_frame=io.frame('paired579_pin_entered'))
        if action=='cast-picker-peer':
            require(payload=={} and 'sink' in state['locals'],'actual discovered peer label only')
            return result(mark,selection=click_text('source','com.hmos.mediacontroller',(state['locals']['sink']['deviceName'],)))
        if action=='dhardware-absent':
            require(payload=={},'finite actual hardware provider disappearance');deadline=time.monotonic()+30
            while True:
                try:
                    observed=snapshot('sink','actual_hardware_provider_closed');layout=json.loads(raw(observed['layout']))
                    if not any(attrs.get('visible')=='true' for attrs in nodes(layout,'com.ohos.dhardwareui')):
                        return result(mark,actual_disappearance=observed)
                except (NodeNotReady,LayoutNotReady):pass
                require(time.monotonic()<deadline,'actual DHardware UI did not disappear after hardware release');time.sleep(.25)
        if action=='dhardware-control':
            require(payload in ({'control':'pause'},{'control':'resume'},{'control':'stop'}),'finite real DHardware control')
            texts={'pause':('Pause','暂停'),'resume':('Resume','继续'),'stop':('Disconnect','断开连接')}[payload['control']]
            return result(mark,selection=click_text('sink','com.ohos.dhardwareui',texts))
        raise ValueError('unknown fixed paired UI action')
    def inspect(endpoint):
        row=shell(endpoint,shlex.join([remote+'/paired_net',run]),'actual_kernel_interfaces_'+endpoint)
        actual=[json.loads(line) for line in row['stdout'].splitlines()]
        require(len(actual)==2 and all(item['run_id']==run and item['uid']==0 for item in actual),'actual fixed native interface records')
        by_name={item['interface']:item for item in actual};instance=instances[endpoint]
        require(by_name['eth0']['mac']==instance['peer_mac'] and by_name['eth1']['mac']==instance['management_mac'],'actual data-first NIC mapping differs; do not infer from launcher order')
        return {'interfaces':actual,'native':row['stdout_ref'],'route':shell(endpoint,'cat /proc/net/route','actual_kernel_routes_'+endpoint)['stdout_ref']}
    def network_action(action,parameters):
        mark=begin('network_'+action);require(type(parameters) is dict,'finite paired network parameters')
        if action=='pair-inspect':
            require(parameters=={},'actual pair observation only')
            observed={endpoint:inspect(endpoint) for endpoint in endpoints}
            if state['interfaces_before'] is None:state['interfaces_before']=observed
            return result(mark,actual=observed)
        if action=='media-prepare':
            require(parameters=={} and state['challenge'] is None and 'source_grant' in state['identities'],'one actual source-only challenge')
            challenge=prepare_media(output,run);uid=state['identities']['source_grant']['uid'];target=directory('source_grant')+'/cast-'+run+'.wav'
            io.send(challenge['wav']['path'],target,'paired579_source_only_media_send')
            row=shell('source','chown '+str(uid)+':'+str(uid)+' '+target+'\nsha256sum '+target,'actual_source_only_media')
            require(row['stdout'].split()==[challenge['wav']['sha256'],target],'actual source media bytes differ');state['challenge']=challenge
            sink_absent=shell('sink','test ! -e '+directory('sink_grant')+'/cast-'+run+'.wav','actual_sink_has_no_target_asset')
            return result(mark,challenge=save('actual_media_challenge.json',challenge),source_guest_bytes=row['stdout_ref'],
                actual_sink_asset_absence=peer.ref_receipt(sink_absent),provisioned_endpoints=['source'])
        if action=='capture-start':
            require(set(parameters)=={'phase'} and state['challenge'] is not None,'actual challenge precedes sink capture')
            if state['capture'] is None:state['capture']=HeldCapture(peer,run)
            return result(mark,capture=state['capture'].start(parameters['phase']))
        if action=='capture-stop':
            require(set(parameters)=={'audible'} and type(parameters['audible']) is bool and state['capture'],'finite actual sink observation expectation')
            capture=state['capture'].stop();analysis=assess(capture['wav'],state['challenge'],audible=parameters['audible'])
            return result(mark,capture=capture,analysis=save('actual_sink_pcm_analysis.json',analysis))
        if action=='mic-prepare':
            require(parameters=={} and state['mic_challenge'] is None,'one fresh independent sink microphone challenge')
            spec=io.package_inputs['native_helpers']['apps_paired579_alsa'];require(set(spec)=={'binary','build','source','abi'},'actual fixed existing ALSA injector build')
            for key in ('binary','build','source'):raw(spec[key])
            source=Path(__file__).with_name('batch_media_alsa_inject.c')
            require(hashlib.sha256(source.read_bytes()).hexdigest()==spec['source']['sha256'],'existing actual injector source differs')
            env=peer.test_environment if hasattr(peer,'test_environment') else peer.guest.report['test_environment']
            require({'arm':'armv7a','armv7a':'armv7a','arm64':'arm64','x86_64':'x86_64'}.get(spec['abi'])==env['guest_arch'],'actual injector ABI differs')
            challenge=prepare_mic(output,run);target=remote+'/remote-mic-'+run+'.pcm'
            peer.send(spec['binary']['path'],remote+'/alsa_inject','paired579_actual_alsa_injector')
            peer.send(challenge['pcm']['path'],target,'paired579_sink_only_mic_challenge')
            installed=shell('sink','chmod 700 '+remote+'/alsa_inject\nsha256sum '+remote+'/alsa_inject '+target,'actual_sink_only_mic_bytes')
            require(installed['stdout'].split()==[spec['binary']['sha256'],remote+'/alsa_inject',challenge['pcm']['sha256'],target],'actual sink injector/input bytes differ')
            absent=shell('source','test ! -e '+target+'\ntest ! -e '+remote+'/alsa_inject','source_never_receives_mic_challenge')
            state['mic_challenge']=challenge
            return result(mark,challenge=save('actual_mic_challenge.json',challenge),helper=spec,actual_sink_bytes=installed['stdout_ref'],source_asset_absence=io.ref_receipt(absent))
        if action=='mic-inject-start':
            require(parameters=={} and state['mic_challenge'] and state['mic_injector'] is None,'one bounded original held ALSA producer')
            alsa=shell('sink','cat /proc/asound/cards\ncat /proc/asound/pcm\ncat /proc/asound/card1/id','actual_sink_alsa_before')
            require('QemuCapture' in alsa['stdout'] and alsa['stdout'].strip().splitlines()[-1]=='QemuCapture','actual independent sink loopback card identity required')
            challenge=state['mic_challenge'];argv=[remote+'/alsa_inject','--input',remote+'/remote-mic-'+run+'.pcm','--rate','48000','--channels','2','--repeat',str(challenge['repeat']),'--timeout-ms',str(challenge['timeout_ms'])]
            key=peer.spawn_guest('exec '+shlex.join(argv),'paired579_independent_sink_mic_producer')
            state['mic_injector']={'key':key,'started_ns':time.monotonic_ns(),'waited':False}
            return result(mark,key=key,actual_argv=argv,alsa_before=alsa['stdout_ref'],deadline_ms=challenge['timeout_ms'])
        if action=='mic-inject-wait':
            require(parameters=={} and state['mic_injector'] and not state['mic_injector']['waited'],'original held finite producer wait')
            actual=peer.wait(state['mic_injector']['key'],timeout=75);state['mic_injector']['waited']=True
            retained=save('actual_sink_mic_injector.json',actual)
            events=[]
            for line in (actual['stdout']+'\n'+actual['stderr']).splitlines():
                if line.startswith('{'):events.append(json.loads(line))
            challenge=state['mic_challenge'];played=[row for row in events if row.get('event')=='played'];feeding=[row for row in events if row.get('event')=='feeding'];drained=[row for row in events if row.get('event')=='drained']
            valid=actual['exit_code']==0 and not actual['timed_out'] and actual['boot_id']==peer.boot_id and len(played)==len(feeding)==len(drained)==1
            if valid:
                valid=played[0]=={'event':'played','frames':challenge['frames']*challenge['repeat'],'rate':48000,'channels':2,'repeats':challenge['repeat'],'source_bytes':challenge['frames']*4} and feeding[0]=={'event':'feeding','device':'hw:CARD=QemuCapture,DEV=1,SUBDEV=0','rate':48000,'channels':2,'bytes':challenge['frames']*4} and drained[0]['status_rc']==0 and drained[0]['state']==1 and drained[0]['delay_frames']==0 and drained[0]['written_frames']==played[0]['frames']
            return result(mark,actual_process=retained,events=save('actual_sink_mic_injector_events.json',events),prerequisite_errors=[] if valid else ['actual finite ALSA write/drain/exit did not complete exactly'])
        if action in ('mic-phase-begin','mic-phase-end'):
            require(set(parameters)=={'phase'} and parameters['phase'] in MIC_PHASES and state['mic_challenge'],'finite actual remote-PCM phase')
            phase=parameters['phase'];observed,events=internal('source_grant','mic-state')
            values=[json.loads(row['value']) for row in events if row['event']=='actual-mic-state'];require(len(values)==1,'actual native microphone position required');value=values[0]
            require(all(value['stream'].get(key)==expected for key,expected in {'samplingRate':48000,'channels':2,'sampleFormat':1,'encodingType':0}.items()) and value['devices'] and all(device['networkId']==state['locals']['sink']['networkId'] for device in value['devices']),'actual stereo remote microphone route/format required')
            if action=='mic-phase-begin':
                require(phase not in state['mic_marks'],'fresh phase byte boundary');state['mic_marks'][phase]={'native':value,'record':observed}
                return result(mark,phase=phase,actual_begin=observed,native=value)
            require(phase in state['mic_marks'] and 'end' not in state['mic_marks'][phase],'one actual end per phase')
            previous=state['mic_marks'][phase];require(value['file']==previous['native']['file'] and value['bytes']>previous['native']['bytes'],'real microphone bytes must progress during this phase')
            binaries=[item for item in observed['binaries'] if item.get('native_journal_bytes')==value['bytes']];require(len(binaries)==1,'actual byte-anchored captured PCM required')
            data=raw(binaries[0]['raw'])[previous['native']['bytes']:value['bytes']];segment=save('actual_remote_mic_'+phase+'.pcm',data)
            try:analysis=inspect_segment(data,state['mic_challenge'],phase);failures=[]
            except Exception as error:analysis={'phase':phase,'type':type(error).__name__,'message':str(error)};failures=[analysis]
            previous['end']=observed
            return result(mark,phase=phase,actual_begin=previous['record'],actual_end=observed,actual_pcm=segment,analysis=save('actual_remote_mic_'+phase+'_analysis.json',analysis),semantic_errors=failures)
        if action=='services':
            require(parameters=={},'actual service/raw observations only');records={}
            for endpoint in endpoints:
                records[endpoint]={}
                for name,script in {'services':'hidumper -ls','ams':'aa dump -a -u 100','hilog':'hilog -x','route':'cat /proc/net/route','arp':'cat /proc/net/arp'}.items():
                    records[endpoint][name]=shell(endpoint,script,'services_'+endpoint+'_'+name,allow_failure=True)['stdout_ref']
                for name in ('com.ohos.devicemanagerui','com.ohos.dhardwareui','com.hmos.mediacontroller'):
                    records[endpoint][name]=shell(endpoint,shlex.join(['bm','dump','-n',name,'-u','100']),'provider_'+endpoint+'_'+name.replace('.','_'),allow_failure=True)['stdout_ref']
                # Exact SA IDs come from the complete actual DAUDIO profiles,
                # not guessed services; dump help/state is retained unchanged.
                for identifier in (4802,4805,4806):
                    records[endpoint]['sa_'+str(identifier)]=shell(endpoint,'hidumper -s '+str(identifier),'actual_sa_'+endpoint+'_'+str(identifier),allow_failure=True)['stdout_ref']
            pcaps={}
            for endpoint in endpoints:
                path=Path(instances[endpoint]['environment']['QEMU_PEER_CAPTURE_FILE'])
                require(path.is_absolute() and path.is_file() and not path.is_symlink(),'actual root-held QEMU wire capture required')
                body=path.read_bytes();require(body.startswith(state['pcap_prefix'].get(endpoint,b'')),'actual peer wire capture truncated/replaced')
                state['pcap_prefix'][endpoint]=body;pcaps[endpoint]={'original_path':str(path),'raw':save(endpoint+'_actual_wire.pcap',body)}
            return result(mark,actual=records,pcap_snapshots=pcaps)
        raise ValueError('unknown fixed paired network action')
    def cleanup():
        if state['closed']:return {'already_closed':True,'failures':[]}
        mark=begin('cleanup');failures=[];records=[]
        if state['capture']:
            try:records.append(state['capture'].cleanup())
            except Exception as error:failures.append({'capture':str(error)})
        if state['mic_injector'] and not state['mic_injector']['waited']:
            try:
                records.append(peer.wait(state['mic_injector']['key'],timeout=75));state['mic_injector']['waited']=True
            except Exception as error:failures.append({'owned_mic_producer':str(error)})
        # Unbind only the independently observed peer; cleanup never deletes
        # authentication databases or changes account/device identity.
        if 'source_grant' in state['installed'] and 'sink' in state['locals']:
            try:
                records.append(internal('source_grant','dm-unbind',{'networkId':state['locals']['sink']['networkId']})[0])
                deadline=time.monotonic()+30
                while True:
                    observed,values=internal('source_grant','dm-trusted');records.append(observed)
                    lists=[json.loads(row['value']) for row in values if row['event']=='actual-trusted-list']
                    require(len(lists)==1,'actual cleanup trust table required')
                    if not any(device.get('networkId')==state['locals']['sink']['networkId'] for device in lists[0]):break
                    require(time.monotonic()<deadline,'actual owned peer trust remains after public unbind');time.sleep(.5)
            except Exception as error:failures.append({'owned_peer_unbind':str(error)})
        for role in sorted(list(state['installed'])):
            endpoint,local=split(role)
            try:
                if local=='grant':records.append(internal(role,'cleanup')[0])
                shell(endpoint,shlex.join(['aa','force-stop',bundle('pair',local),'-u','100']),'cleanup_stop_'+role)
                uninstalled=shell(endpoint,shlex.join(['bm','uninstall','-n',bundle('pair',local),'-u','100']),'cleanup_uninstall_'+role)
                require('uninstall bundle successfully.' in uninstalled['stdout'],'actual owned paired uninstall failed');state['installed'].remove(role)
            except Exception as error:failures.append({'role':role,'error':str(error)})
        if not failures:
            if state['interfaces_before'] is not None:
                try:
                    deadline=time.monotonic()+30
                    while True:
                        restored={e:inspect(e) for e in endpoints};records.append({'actual_restored_interfaces':restored})
                        matches=True
                        for endpoint in endpoints:
                            before={row['interface']:row for row in state['interfaces_before'][endpoint]['interfaces']}
                            after={row['interface']:row for row in restored[endpoint]['interfaces']}
                            for name in ('eth0','eth1'):
                                if any(after[name][key]!=before[name][key] for key in ('mac','address','netmask')):matches=False
                        if matches:break
                        require(time.monotonic()<deadline,'actual Ethernet addresses/MACs not restored to original observations');time.sleep(.5)
                except Exception as error:failures.append({'actual_network_restore':str(error)})
        if not failures:
            for endpoint in sorted(state['created']):
                owned_files=[remote+'/paired_net']+[remote+'/'+local+'.hap' for local in (('normal','grant','denied') if endpoint=='source' else ('grant',))]
                if endpoint=='sink' and state['mic_challenge']:owned_files += [remote+'/alsa_inject',remote+'/remote-mic-'+run+'.pcm']
                for path in owned_files:shell(endpoint,'rm '+path,'remove_owned_'+endpoint+'_'+Path(path).name.replace('.','_'))
                shell(endpoint,'rmdir '+remote,'remove_owned_directory_'+endpoint)
            state['closed']=True
        return result(mark,records=records,failures=failures,restored=not failures)
    io.register_cleanup(cleanup)
    return {'prepare_callers':prepare_callers,'install':install,'start':start,'input':input,'collect':collect,'network':network_action,'cleanup':cleanup}
