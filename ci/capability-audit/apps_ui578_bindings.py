"""Fixed adapters for the ORIGINAL held-guest Owner; no launcher or subprocess.

Only root_io performs commands, transfers, compiler/signing and QMP. This file
does not select caller source or an executable from a test JSON. Absent actual
package/provider/display inputs fail before mutation. No standalone main.
"""
import re
import shlex
import time
import zipfile
from pathlib import Path, PurePosixPath

from apps_ui578_contract import (CASES, ROLES, bundle, decode, json_ref, load_ref,
    nonce, qmp_wire, require, returned, sha)
from apps_ui578_project import validate_prepared


PROVIDERS = {
    'notification-settings': ('com.ohos.sceneboard', 'NotificationManangerUIExtensionAbility'),
    'notification-subscription': ('com.ohos.sceneboard', 'NotificationAccessGrantUIExtensionAbility'),
    'intelligent-scene': ('com.ohos.intelligentscene', 'IntelligentSceneUIExtSettingAbility'),
    'intelligent-scene-settings': ('com.ohos.settings','IntelligentSceneAppSelectExtensionAbility'),
    'network-policy': ('com.ohos.communicationsetting','UIExtensionProvider'),
    'accessibility-settings': ('com.ohos.settings','com.ohos.settings.MainAbility'),
    'certificate-dialog': ('com.ohos.certmanager', 'CertPickerUIExtAbility'),
    'enterprise': ('com.ohos.adminprovisioning', 'ByodAdminProvisionAbility'),
}


def absent(bundle_name, pids, abilities):
    """Same bounded PID+real AMS rule as stop_previous_probe, own fixed bundle."""
    require(bundle_name in {bundle(r) for r in ROLES}, 'only the fixed audit callers may be drained')
    if pids.strip() != 'ABSENT':
        require(re.fullmatch(r'[1-9][0-9]*(?:\s+[1-9][0-9]*)*', pids.strip()), 'malformed real pidof result')
        return False
    require(re.search(r'^User ID #100\s*$', abilities, re.M) and 'AppRunningRecords:' in abilities,
        'actual complete account-100 AMS process/ability dump required')
    return re.search(r'(?<![A-Za-z0-9_.])'+re.escape(bundle_name)+r'(?=$|[^A-Za-z0-9_.])', abilities) is None


class Bindings:
    def __init__(self, io):
        self.io=io;self.records=[];self.installed=[];self.prepared={};self.session=None
        self.kind=None;self.run_id=None;self.closed=False;self.image_proofs={}
        self.output=Path(io.output)/'apps578-bindings'
        self.output.mkdir(parents=True,exist_ok=False)
        require(io.guest.report['archive_sha256']==io.archive_sha256 and
            io.guest.report['test_environment']['boot_id']==io.boot_id and io.guest.target==io.target,
            'root_io must refer to the same held original package/boot/endpoint')
        # Registered before preparation so partial installs also have a finally.
        io.register_cleanup(self.emergency_cleanup)

    def label(self):return 'apps578_io_'+str(len(self.records)).zfill(5)

    def record(self,row):
        required={'argv','exit_code','stdout','stderr','boot_id','stdout_ref','stderr_ref','log','timed_out'}
        require(isinstance(row,dict) and required<=set(row) and row['boot_id']==self.io.boot_id and
            isinstance(row['argv'],list) and type(row['exit_code']) is int and row['timed_out'] is False and
            isinstance(row['stdout'],str) and isinstance(row['stderr'],str), 'actual root command record required')
        require(load_ref(row['stdout_ref'])==row['stdout'] and load_ref(row['stderr_ref'])==row['stderr'],
            'raw stdout/stderr refs do not contain the actual root command streams')
        load_ref(row['log'])
        self.records.append({k:row[k] for k in required if k not in ('stdout','stderr')})
        return row

    def shell(self,script,*,allow_failure=False):
        row=self.record(self.io.shell(script,self.label(),timeout=60,allow_failure=allow_failure))
        require(row['argv'][:4]==[str(self.io.hdc),'-t',self.io.target,'shell'] and
            len(row['argv'])==5, 'root shell escaped the held actual HDC target')
        require(allow_failure or row['exit_code']==0, 'actual root shell failed')
        return row

    def command(self,argv):
        row=self.record(self.io.command(argv,self.label(),timeout=90))
        require(row['argv']==list(map(str,argv)) and row['exit_code']==0, 'actual fixed root command failed')
        return row

    def boot(self):
        require(self.shell('cat /proc/sys/kernel/random/boot_id')['stdout'].strip()==self.io.boot_id,
            'held guest changed during owned caller stage')

    def drain(self,role):
        name=bundle(role);begin=len(self.records)
        reply=self.shell('aa force-stop '+name,allow_failure=True)['stdout'].strip()
        require(reply=='force stop process successfully.' or
            ('error: failed to force stop process.' in reply and 'Error Code:10104002' in reply and
            'The application corresponding to the specified package name is not installed.' in reply),
            'AA did not confirm the exact owned caller stop/not-installed result')
        deadline=time.monotonic()+30;consecutive=0
        while time.monotonic()<deadline:
            pids=self.shell('apps578_pids=$(pidof '+name+'); if test -n "$apps578_pids"; then '
                'printf "%s\\n" "$apps578_pids"; else echo ABSENT; fi')['stdout']
            ams=self.shell('aa dump -a -u 100')['stdout']
            consecutive=consecutive+1 if absent(name,pids,ams) else 0
            if consecutive==2:return list(range(begin,len(self.records)))
            time.sleep(.25)
        raise ValueError('actual owned caller PID/AMS records did not drain')

    def prepare(self,guest,kind,run,roles):
        require(guest is self.io.guest and kind in CASES and self.kind is None and
            isinstance(roles,tuple) and set(roles)<=set(ROLES), 'one fixed family/case per held stage required')
        nonce(run);self.kind=kind;self.run_id=run;self.boot()
        raw=self.io.prepare_callers('apps_ui578',kind,run,roles,{'source_family':'apps_ui578','case':kind})
        require(isinstance(raw,dict) and set(raw)==set(roles), 'original builder must return all exact roles')
        for role in roles:
            row=raw[role]
            require({'project','unsigned','signed','signing','verified_profile','build_commands',
                'sign_commands','verify_commands','identity'}<=set(row), 'actual original compiler/signer records missing')
            spec={key:row[key] for key in ('project','unsigned','signed','signing')}
            validate_prepared(spec,run,kind,role,self.io.udid)
            require(decode(load_ref(spec['signing']))['verified_profile']==row['verified_profile'],
                'same-boot actual verified profile differs')
            for phase in ('build_commands','sign_commands','verify_commands'):
                require(isinstance(row[phase],list) and row[phase], 'actual compiler/sign/verify commands cannot be empty')
            self.prepared[role]=spec
            self.drain(role)
            # Build/sign intentionally did not install. Install only these exact
            # compiled signed bytes, using the held original HDC primitive.
            self.installed.append(role)
            reply=self.command([str(self.io.hdc),'-t',self.io.target,'install','-r',spec['signed']['path']])['stdout']
            require(re.search(r'install bundle successfully',reply,re.I) and not re.search(r'\[Fail\]|failed',reply,re.I),
                'actual current signed caller was not installed')
        self.boot()
        return self.prepared

    def provider(self,guest,kind):
        require(guest is self.io.guest and kind in PROVIDERS, 'fixed actual provider case required')
        if kind in self.image_proofs:return self.image_proofs[kind]
        descriptor=self.io.package_inputs
        require(set(descriptor)=={'archive','system_image','providers'} and
            sha(descriptor['archive']['path'])==descriptor['archive']['sha256']==self.io.archive_sha256,
            'actual new archive/provider inputs required; old packages/pass JSON are refused')
        image=Path(descriptor['system_image']['path'])
        require(image.resolve()==image and image.is_relative_to(Path(guest.directory).resolve()) and
            sha(image)==descriptor['system_image']['sha256'], 'actual this-archive extracted system image required')
        # Root binds the current package's actual selected build-input HAPs.
        # No extra host image extraction/test is introduced here. Session binds
        # every module below to actual installed HAP bytes and BMS declarations,
        # then performs real UI and independent business-result observations.
        group=descriptor['providers'][kind];wanted,extension=PROVIDERS[kind]
        require(set(group)=={'bundle','modules'} and group['bundle']==wanted and
            isinstance(group['modules'],dict) and group['modules'], 'literal public-API provider target required')
        result={'archive_sha256':self.io.archive_sha256,'bundle':wanted,'modules':{}}
        found=False
        for module,entry in group['modules'].items():
            require(re.fullmatch('[A-Za-z0-9_]{1,80}',module) and set(entry)=={'hap'},
                'fixed actual package build-input HAP required')
            built=entry['hap'];require(sha(built['path'])==built['sha256'], 'actual selected build-input HAP changed')
            with zipfile.ZipFile(built['path']) as archive:
                members=archive.infolist();names=[r.filename for r in members]
                require(len(members)<10000 and len(names)==len(set(names)) and
                    sum(r.file_size for r in members)<256*1024*1024,'bounded actual provider ZIP closure required')
                for item in members:
                    path=PurePosixPath(item.filename)
                    require(not path.is_absolute() and '..' not in path.parts and '\\' not in item.filename and
                        not item.flag_bits&1 and (item.external_attr>>16)&0o170000!=0o120000,
                        'unsafe actual provider HAP member')
                require({'module.json','ets/modules.abc','resources.index'}<=set(names) and
                    archive.read('ets/modules.abc') and archive.read('resources.index'), 'real compiled provider/resources missing')
                info=decode(archive.read('module.json').decode())
                require(info['app']['bundleName']==wanted and info['module']['name']==module,
                    'actual built provider module identity differs')
                for ability in info['module'].get('extensionAbilities',[])+info['module'].get('abilities',[]):
                    if ability['name']==extension:
                        require((kind in ('enterprise','accessibility-settings') and ability.get('exported') is True) or
                            (ability.get('type')=='sys/commonUI' and ability.get('exported') is True),
                            'actual literal ANS target must be an exported sys/commonUI extension')
                        found=True
            result['modules'][module]=built['sha256']
        require(found,'actual image is missing the literal public-API provider; pending, not a UI fallback')
        self.image_proofs[kind]=result
        return result

    def account(self,guest,session):
        require(guest is self.io.guest and session.kind=='blink', 'same held blink session required')
        self.session=session
        return session.account_program_boundary()

    def qmp(self,name,args=None):
        row=self.io.qmp(name,args)
        require(isinstance(row,dict) and {'execute','arguments','reply','request','response','boot_id'}<=set(row) and
            row['execute']==name and row['arguments']==(args or {}) and row['boot_id']==self.io.boot_id,
            'actual owned QMP request/reply/boot record required')
        qmp_wire(row)
        return row

    def business(self,guest,session,action,parameters):
        require(guest is self.io.guest and session.kind in
            ('shortkey','accessibility-input','certificate-dialog','network-policy','apn','notification-subscription','intelligent-scene') and
            action in ('shortcut-key','input-click','input-type','certificate-input','provider-probe','dnd-search'), 'fixed actual same-guest business boundary required')
        self.session=session;self.boot()
        if action=='provider-probe':
            require(session.kind in ('network-policy','apn','notification-subscription','intelligent-scene') and parameters=={},
                'only the fixed missing public-provider targets may be probed')
            targets={'network-policy':('com.ohos.communicationsetting','UIExtensionProvider'),
                'apn':('com.huawei.hmos.callsetting','GeneralCallSettingDialogAbility'),
                'notification-subscription':('com.ohos.sceneboard','NotificationAccessGrantUIExtensionAbility'),
                'intelligent-scene':('com.ohos.intelligentscene','IntelligentSceneUIExtSettingAbility')}
            target,ability=targets[session.kind]
            row=self.shell('bm dump -n '+target,allow_failure=True)
            return {'schema':'actual-apps578-provider-boundary/v1','bundle':target,'ability':ability,
                'archive_sha256':self.io.archive_sha256,'boot_id':self.io.boot_id,
                'bms':{k:row[k] for k in ('argv','exit_code','stdout_ref','stderr_ref','log','boot_id','timed_out')}}
        if action=='certificate-input':
            require(session.kind=='certificate-dialog' and parameters=={},'fixed actual certificate fixture boundary required')
            ref=self.io.environment['apps_ui578_certificate_input']
            value=decode(load_ref(ref))
            require(set(value)=={'schema','run','boot_id','archive_sha256','p12','der','producer'} and
                value['schema']=='actual-apps578-certificate-input/v1' and value['run']==session.run and
                value['boot_id']==self.io.boot_id and value['archive_sha256']==self.io.archive_sha256,
                'actual original nonce certificate producer inputs missing; no fixture fallback')
            producer=decode(load_ref(value['producer']))
            require(producer['run']==session.run and producer['p12']==value['p12'] and producer['der']==value['der'] and
                isinstance(producer['commands'],list) and producer['commands'], 'actual original certificate producer records required')
            transfers=[]
            for suffix,key,limit in (('.p12','p12',20480),('.der','der',8192)):
                source=value[key];require(sha(source['path'])==source['sha256'] and 0<Path(source['path']).stat().st_size<=limit,
                    'bounded actual certificate input bytes changed')
                for role in ('a','b'):
                    remote='/data/app/el2/100/base/'+bundle(role)+'/files/apps578-'+session.run+suffix
                    uid=session.value['roles'][role]['identity']['uid']
                    self.shell('test ! -e '+remote+' && test ! -L '+remote)
                    sent=self.record(self.io.send(source['path'],remote,self.label()))
                    require(sent['exit_code']==0 and sent['argv']==[str(self.io.hdc),'-t',self.io.target,'file','send',source['path'],remote],
                        'actual nonce fixture transfer did not use held guest')
                    self.shell('chown '+str(uid)+':'+str(uid)+' '+remote+' && chmod 0600 '+remote)
                    require(self.shell('sha256sum '+remote)['stdout'].strip()==source['sha256']+'  '+remote,
                        'actual transferred fixture bytes differ')
                    transfers.append({'role':role,'suffix':suffix,'source':source,'remote':remote})
            return {'schema':'actual-apps578-certificate-input/v1','input':ref,'transfers':transfers,
                'boot_id':self.io.boot_id,'archive_sha256':self.io.archive_sha256}
        records=[self.qmp('query-qmp-schema')]
        schema={x['name'] for x in records[0]['reply'] if x.get('meta-type')=='command'}
        result={'schema':'actual-apps578-input/v1','action':action,'parameters':parameters,
            'archive_sha256':self.io.archive_sha256,'boot_id':self.io.boot_id,'qmp':records}
        if action=='shortcut-key':
            require(session.kind=='shortkey' and set(parameters)=={'modifier','hold_ms'} and
                parameters['modifier'] in ('meta_l','ctrl') and parameters['hold_ms'] in (100,800,1000,1800),
                'only bounded actual packaged shortcut key sequences allowed')
            require('send-key' in schema, 'actual owned QEMU keyboard injection unsupported')
            records.append(self.qmp('send-key',{'keys':[{'type':'qcode','data':parameters['modifier']},
                {'type':'qcode','data':'i'}],'hold-time':parameters['hold_ms']}))
        elif action=='dnd-search':
            require(session.kind=='intelligent-scene' and set(parameters)=={'role','text'} and
                parameters['role'] in ('a','b') and
                parameters['text']=='apps578'+parameters['role']+session.run[:8],
                'fixed current-nonce DND caller search only')
            require('send-key' in schema,'actual owned QEMU keyboard injection unsupported')
            # Session clicked the real Settings Search node first. Clear only
            # that focused editor, then feed physical keys through the guest.
            records.append(self.qmp('send-key',{'keys':[{'type':'qcode','data':'ctrl'},{'type':'qcode','data':'a'}],'hold-time':60}))
            records.append(self.qmp('send-key',{'keys':[{'type':'qcode','data':'backspace'}],'hold-time':60}))
            for letter in parameters['text']:
                records.append(self.qmp('send-key',{'keys':[{'type':'qcode','data':letter}],'hold-time':60}))
                time.sleep(.12)
        elif action=='input-type':
            require(session.kind=='accessibility-input' and set(parameters)=={'role','text'} and
                parameters['role'] in ('normal','a','b') and parameters['text']==session.run[:8],
                'only this nonce input text may be injected')
            require('send-key' in schema,'actual owned QEMU keyboard injection unsupported')
            for letter in parameters['text']:
                records.append(self.qmp('send-key',{'keys':[{'type':'qcode','data':letter}],'hold-time':60}))
                time.sleep(.12)
        else:
            from guest_ui import select_node
            from PIL import Image
            require(session.kind=='accessibility-input' and set(parameters)=={'role','layout','identifier'} and
                parameters['role'] in ('normal','a','b') and parameters['identifier']=='apps578-increment',
                'only the actual owned input target may be clicked')
            require('input-send-event' in schema,'actual owned QEMU pointer injection unsupported')
            node=select_node(decode(load_ref(parameters['layout'])),bundle(parameters['role']),
                identifier=parameters['identifier'],clickable=True)
            picture=session.ui.screenshot(label='actual_input_geometry')
            with Image.open(picture) as image:width,height=image.size
            x,y,w,h=node['rect'];require(0<=x<x+w<=width and 0<=y<y+h<=height,'actual input ROI is off the real framebuffer')
            result['geometry']={'frame':json_ref(picture),'width':width,'height':height,'node':node}
            records.append(self.qmp('input-send-event',{'events':[
                {'type':'abs','data':{'axis':'x','value':(x+w//2)*32767//(width-1)}},
                {'type':'abs','data':{'axis':'y','value':(y+h//2)*32767//(height-1)}}]}))
            for down in (True,False):
                records.append(self.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':down}}]}))
                time.sleep(.1)
        self.boot();return result

    def display(self,guest,session,boundary):
        require(guest is self.io.guest and session.kind=='blink' and boundary in ('owner-death','display-recreate'),
            'fixed same-guest real default-display boundary required')
        self.session=session
        if boundary=='owner-death':return session.owner_death_boundary()
        # Product Tick clears when the ACTUAL default display id/width/height
        # changes. Physical GPU hotplug is not a public start/stopBlinking
        # requirement, and the packaged virtio GPU must never be removed here.
        before=session.api('a','display.before','display-read')
        inventory=session.api('a','display.inventory','screen-read')
        from apps_ui578_boundaries import screen_inventory
        actual,original,alternatives=screen_inventory(inventory,before)
        require(alternatives, 'pending: actual default main screen advertises no different-size mode')
        selected=alternatives[0]
        require(session.api('a','display.start','start')==0,'real pulse must be active before default-display change')
        session.pixels('display-before-active','a','continuous');active=session.value['pixels'][-1]
        changed=None;restored=None
        try:
            session.api('a','display.mode.set','screen-mode',number=selected['id'])
            deadline=time.monotonic()+20;attempt=0
            while time.monotonic()<deadline:
                attempt+=1
                current=session.api('a','display.observe.'+str(attempt),'display-read')
                if current['id']==before['id'] and (current['width'],current['height'])==(selected['width'],selected['height']):
                    changed=current;break
                time.sleep(.2)
            require(changed is not None,
                'pending: main-screen API returned without actual default display mode/dimension change')
            after=session.api('a','display.after','display-read')
            require(after==changed,'actual default display did not stabilize')
            mode_after=session.api('a','display.mode.after','screen-read')
            observed,_,_=screen_inventory(mode_after,after)
            require(observed['id']==actual['id'] and observed['activeModeIndex']==selected['id'],
                'actual main screen did not retain the selected advertised mode')
            # Actual source Tick can run up to750ms later; the original off
            # frame oracle observes a longer real window and is not an API stub.
            time.sleep(1)
            session.pixels('display-return-quiet','a','off');quiet=session.value['pixels'][-1]
            require(session.api('a','display.reacquire','start')==0,'default display change retained stale ownership')
            session.pixels('display-reacquired','a','continuous');resumed=session.value['pixels'][-1]
            require(session.api('a','display.stop','stop')==0,'changed display pulse did not stop')
        finally:
            session.api('a','display.mode.restore','screen-mode',number=original['id'])
            deadline=time.monotonic()+20;attempt=0
            while time.monotonic()<deadline:
                attempt+=1
                current=session.api('a','display.restore.'+str(attempt),'display-read')
                if current==before:restored=current;break
                time.sleep(.2)
            require(restored==before,'actual main screen/default-display original mode restoration failed')
            restored_inventory=session.api('a','display.inventory.restored','screen-read')
            restored_screen,_,_=screen_inventory(restored_inventory,before)
            require(restored_screen==actual,'actual main screen inventory/mode was not restored exactly')
        return {'kind':'actual-default-display-change/v1','before':before,'after':after,
            'inventory':inventory,'selected':selected,'mode_after':mode_after,'restored_inventory':restored_inventory,
            'restored':restored,'active':active,'quiet':quiet,'resumed':resumed}

    def cleanup(self,guest,kind,run,prepared,session):
        require(guest is self.io.guest and kind==self.kind and run==self.run_id and
            (prepared==self.prepared or (prepared=={} and not session.value['roles'])),
            'cleanup must retain the exact same prepared stage ownership')
        self.session=session
        return self.finish()

    def finish(self):
        require(not self.closed,'stage cleanup already completed');self.boot()
        state={};session=self.session
        if session is not None:
            if self.kind=='accessibility-settings' and session.value.get('settings',{}).get('saved'):
                actual=session.api('a','cleanup.settings','settings-restore')
                require(actual==session.value['baseline'],'actual Settings config/preferences did not restore')
                state['settings']=actual
            if self.kind=='blink' and 'account' in session.value['roles']:
                actor=session.rows('account')
                if any(r['operation']=='acct.program' and r['event']=='call.account-program' for r in actor):
                    actor=session.wait('account',lambda r:any(x['operation']=='acct.after' and x['event']=='return.account-read'
                        for x in r),'account_finally_before_uninstall',seconds=45)
                    original=returned(actor,'acct.before','account-read');final=returned(actor,'acct.after','account-read')
                    require(final==original and final['foreground']==100,'actual account finally did not restore original inventory')
                    state['account']=final
            if self.kind=='blink' and session.value.get('original_setting')=='0':
                require(session.api('a','cleanup.disable','disable')=={'written':True,'read':'0'},'owned setting cleanup failed')
                state['blink']='0'
            elif self.kind in ('notification-settings','notification-subscription') and 'baseline' in session.value:
                role='normal' if self.kind=='notification-settings' else 'a'
                wanted=session.value['baseline']['enabled'] if self.kind=='notification-settings' else session.value['baseline']
                session.invoke(role,'cleanup.restore','invoke',wait=False);session.visible(role,'cleanup.restore')
                session.system('enable' if wanted else 'disable');session.system('close')
                session.wait(role,lambda r:any(x['operation']=='cleanup.restore' and x['event']=='return.invoke' for x in r),'cleanup_ui')
                state['provider']=session.api(role,'cleanup.read','read')
                require(state['provider']==session.value['baseline'],'actual provider user setting cleanup failed')
            elif self.kind=='intelligent-scene' and 'baseline' in session.value:
                from apps_ui578_followup import restore_dnd
                state['provider']=restore_dnd(session)
            elif self.kind=='network-policy' and 'network_policy' in session.value:
                from apps_ui578_followup import restore_network
                state['network_policy']=restore_network(session)
            elif self.kind=='shortkey':
                session.api('a','cleanup.duration','invoke',number=500)
                state['duration']=500
            elif self.kind=='certificate-dialog' and 'certificate' in session.value:
                # Use only URIs created by this nonce. The typed program checks
                # private alias/CA exact input bytes before any removal.
                if session.value['certificate'].get('ca_installed') is True:
                    session.invoke('a','cleanup.ca','remove-ca',wait=False);session.visible('a','cleanup.ca')
                    session.system('confirm-uninstall')
                    session.wait('a',lambda rows:any(r['operation']=='cleanup.ca' and r['event']=='return.remove-ca' for r in rows),'cleanup_ca')
                    session.value['certificate']['ca_installed']=False
                if session.value['certificate'].get('private_installed') is True:
                    session.api('a','cleanup.private','remove')
                    session.value['certificate']['private_installed']=False
                state['certificate']=session.api('a','cleanup.cert.read','read')
                require(state['certificate']==session.value['baseline'],'actual certificate inventory was not restored')
            elif self.kind=='enterprise' and 'admin_owned' in session.value:
                if session.value['admin_owned'] is True:session.api('a','cleanup.admin.disable','disable')
                require(session.api('a','cleanup.admin.read','read') is False, 'actual owned normal administrator cleanup failed')
                if any(r['event']=='admin.enabled.callback' for r in session.observers('a')):
                    session.wait_observer('a','admin.disabled.callback')
                session.value['admin_owned']=False
                state['admin']=False
            for role in session.value['roles']:
                session.rows(role)
                if self.kind in ('enterprise','notification-subscription') and role in ('a','b'):session.observers(role)
        callers=[]
        for role in reversed(self.installed):
            drain=self.drain(role)
            index=len(self.records)
            reply=self.command([str(self.io.hdc),'-t',self.io.target,'uninstall',bundle(role)])['stdout']
            require(re.search(r'uninstall bundle successfully',reply,re.I) and not re.search(r'\[Fail\]|failed',reply,re.I),
                'actual owned caller uninstall failed')
            after=self.drain(role)
            callers.append({'role':role,'before':drain,'uninstall':index,'after':after})
        self.boot();self.closed=True
        result={'schema':'actual-apps578-cleanup/v1','archive_sha256':self.io.archive_sha256,
            'boot_id':self.io.boot_id,'case':self.kind,'run':self.run_id,'state':state,'callers':callers,
            'records':self.records}
        return result

    def emergency_cleanup(self):
        if self.closed or self.kind is None:return
        # On partial build/install failure there may be no Session yet. Drain
        # only successful installs. Account failure deliberately raises before
        # uninstall; original Owner teardown still discards the fresh guest.
        return self.finish()


def bind(root_io):
    bound=Bindings(root_io)
    return {'prepare_apps578':bound.prepare,'cleanup_apps578':bound.cleanup,
        'verify_provider_image':bound.provider,'account_boundary':bound.account,'display_boundary':bound.display,
        'business_boundary':bound.business}
