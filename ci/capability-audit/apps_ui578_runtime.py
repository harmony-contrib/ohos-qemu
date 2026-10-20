"""Additional same-guest apps UI cases for the original root-owned stage.

No main, VM boot, SDK/compile/sign command, permission grant or arbitrary source
path interface. Root's fixed callbacks own original build/sign/install/cleanup.
Every operation label is safe for the original RootExecutor label grammar.
"""
import json
from pathlib import Path
import re
import secrets
import shlex
import time

from apps_ui578_contract import (CASES, IDS, ROLES, bundle, decode, journal, json_ref,
    load_ref, nonce, permissions, action_node, provider_boundary_classification, require, returned, sha)
from apps_ui578_project import validate_prepared
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, command_exit, select_node
from guest_process_identity import identity_shell
from hap_identity_binding import bms_application_identity


def read_plan(ref, kind, run=None):
    value = decode(load_ref(ref))
    require(set(value) == {'schema','kind','source_files','provider_bundle','actions','visible'} and
        value['schema'] in ('actual-packaged-apps578-ui/v1','actual-apps578-missing-provider-boundary/v1') and value['kind'] == kind and
        isinstance(value['source_files'], list) and value['source_files'],
        'actual source-backed packaged UI plan required; no default selector')
    for source in value['source_files']:
        load_ref(source)
    expected = ('com.ohos.sceneboard' if kind in ('notification-settings','notification-subscription')
        else 'com.ohos.certmanager' if kind=='certificate-dialog'
        else 'com.ohos.adminprovisioning' if kind=='enterprise'
        else 'com.huawei.hmos.callsetting' if kind=='apn'
        else 'com.ohos.communicationsetting' if kind=='network-policy'
        else 'com.ohos.intelligentscene' if kind=='intelligent-scene'
        else 'com.ohos.settings' if kind in ('shortkey','accessibility-settings')
        else None)
    require(expected is not None and value['provider_bundle'] == expected,
        'fixed API target provider required; a UI plan cannot redirect ANS to SystemUI')
    if value['schema']=='actual-apps578-missing-provider-boundary/v1':
        require(kind in ('notification-subscription','network-policy','apn','intelligent-scene') and value['actions']=={} and value['visible'] is None,
            'only fixed source-missing targets permit a boundary plan; no fabricated selector')
        return value
    require(isinstance(value['actions'],dict) and isinstance(value['visible'],dict), 'actual UI selectors required')
    def selector(row, visible=False):
        require(type(row) is dict,'actual finite UI selector required')
        if set(row)=={'key'}:
            require(not visible and row['key']=='Back','only the real provider cancellation key is permitted')
            return
        base=set(row)-{'ancestor','sibling_type','set_checked','card_title','swipe_to','within_card','within_mode'}
        require(base in ({'bundle','identifier'},{'bundle','text'}) and
            all(isinstance(row[k],str) and 0<len(row[k])<=256 for k in base) and
            row['bundle'] in ({'com.ohos.settings','com.ohos.systemui'} if kind=='accessibility-settings' else {'com.ohos.intelligentscene','com.ohos.settings'} if kind=='intelligent-scene' else {value['provider_bundle']}) and not row['bundle'].startswith('org.harmonycontrib.'),
            'exact real provider node required; caller button is not a system action')
        require('within_mode' not in row or (kind == 'intelligent-scene' and
            set(row) == {'bundle','text','within_mode'} and row['bundle'] == 'com.ohos.intelligentscene' and
            row['within_mode'] == 'Do not disturb' and row['text'] in ('Turn on','Turn off')),
            'only the actual DND mode card Button relation is allowed')
        require('ancestor' not in row or (row['ancestor'] is True and 'sibling_type' not in row),
            'only the nearest actual clickable ancestor may receive input')
        require('sibling_type' not in row or row['sibling_type']=='Toggle','only source Row sibling Toggle is permitted')
        require('within_card' not in row or (kind=='accessibility-settings' and isinstance(row['within_card'],str) and
            0<len(row['within_card'])<=256 and set(row)=={'bundle','text','within_card'}),
            'notification action must stay inside the actual source-related card')
        require('card_title' not in row or (kind=='accessibility-settings' and row['card_title'] is True and
            not ({'ancestor','sibling_type','set_checked','swipe_to'}&set(row))), 'only the actual source notification title Row may expand a card')
        require('swipe_to' not in row or (kind=='accessibility-settings' and row['bundle']=='com.ohos.systemui' and
            row.get('identifier')=='systemui-statusbar-swipe' and row['swipe_to']=={'bundle':bundle('a'),'identifier':'apps578-surface'}),
            'only actual source statusbar/owned caller geometry may open the notification drawer')
        require('set_checked' not in row or (type(row['set_checked']) is bool and row.get('sibling_type')=='Toggle'),
            'explicit desired state requires the actual source Toggle')
        require(not visible or set(row)==base,'visible selector cannot contain an action relation')
    selector(value['visible'],True)
    for name, sequence in value['actions'].items():
        require(re.fullmatch('[a-z][a-z0-9-]{0,40}',name) and isinstance(sequence,list) and 1 <= len(sequence) <= 12,
                'bounded fixed UI sequence required')
        for row in sequence:selector(row)
    if run is not None:
        nonce(run)
        for row in [value['visible']]+[s for rows in value['actions'].values() for s in rows]:
            if row.get('text')=='{{certificate_alias}}':row['text']='apps_'+run[:16]
            require(not any('{{' in x or '}}' in x for x in row.values() if isinstance(x,str)), 'unknown UI selector data placeholder')
    return value


class Session:
    def __init__(self, guest, callbacks, parameters):
        require(set(parameters) == {'case','output','ui_plan','full_blink'}, 'explicit bounded apps578 stage parameters required')
        self.kind = parameters['case']
        require(self.kind in CASES and type(parameters['full_blink']) is bool, 'fixed apps578 case required')
        self.run = secrets.token_hex(16)
        self.plan = None if self.kind in ('blink','accessibility-input') else read_plan(parameters['ui_plan'],self.kind,self.run)
        self.full_blink = parameters['full_blink']
        self.guest, self.callbacks = guest, callbacks
        require(set(callbacks) == {'prepare_apps578','cleanup_apps578','verify_provider_image',
            'account_boundary','display_boundary','business_boundary'}, 'only the fixed root callback surface is permitted')
        require(callable(callbacks['prepare_apps578']) and callable(callbacks['cleanup_apps578']) and
            callable(callbacks['verify_provider_image']), 'original fixed compile/sign/install/image/cleanup callbacks required')
        if self.kind == 'blink' and self.full_blink:
            require(callable(callbacks['account_boundary']) and callable(callbacks['display_boundary']),
                'full blink requires actual nonce account and owned display callbacks; unknown inputs fail')
        self.output = Path(parameters['output'])
        require(self.output.is_absolute(), 'fresh absolute owned stage output required')
        self.output.mkdir(parents=True,exist_ok=False)
        env = guest.report['test_environment']
        require(guest.args.purpose == 'acceptance' and env.get('external_keepalive') is not True and
            guest.report.get('diagnostic_assistance') is None and
            re.fullmatch('[0-9a-f-]{36}',env.get('boot_id','')) and env.get('udid'),
            'original unassisted same-package acceptance guest required')
        self.boot, self.udid = env['boot_id'], env['udid']
        self.value = {'schema':'actual-apps578-runtime/v1','run':self.run,'case':self.kind,
            'original_ids':list(IDS[self.kind]),'archive_sha256':guest.report['archive_sha256'],
            'boot_id':self.boot,'udid':self.udid,'target':guest.target,'commands':[], 'actions':[],
            'roles':{},'journal_reads':[],'pixels':[],'boundaries':{},'failures':[],
            'observer_reads':[],
            'cleanup_verified':False,'status':'fail','formally_closed':[],
            'first_artifact_behavior_gate_passed':False,'full_blink':self.full_blink,
            'ui_plan':parameters['ui_plan']}
        self.previous = {}
        self.prepared = {}
        self.ui = GuestUi(self.command,guest.args.hdc,guest.target,self.output/'ui')

    def save(self):
        (self.output/'evidence.json').write_text(json.dumps(self.value,indent=2)+'\n')

    def command(self, argv, label, **kwargs):
        # Ignore UI-generated descriptive labels for RootExecutor; preserve them
        # only as metadata. Commands themselves stay in the original owner log.
        require(isinstance(label,str) and len(label) <= 256, 'bounded observation label required')
        safe = 'apps578_'+str(len(self.value['commands'])).zfill(5)
        index = len(self.guest.report['commands'])
        before = time.monotonic_ns()
        stdout = self.guest.command(argv,safe,**kwargs)
        after = time.monotonic_ns()
        raw = self.guest.report['commands'][index]
        require(raw['argv'] == list(map(str,argv)) and raw['exit_code'] == 0 and
            sha(raw['log']) == raw['sha256'], 'original owned command/raw/exit differs')
        self.value['commands'].append({'owner_index':index,'observation':label,'argv':raw['argv'],
            'log':json_ref(raw['log']),'started_ns':before,'finished_ns':after})
        return stdout

    def shell(self, script, label):
        marker = '__APPS578_EXIT_'+secrets.token_hex(16)+'__='
        raw = self.command([self.guest.args.hdc,'-t',self.guest.target,'shell',
            script+'; apps578_rc=$?; printf "\\n'+marker+'%s\\n" "$apps578_rc"'],label)
        body, code = command_exit(raw,marker)
        require(code == 0, 'actual guest operation failed: '+label)
        return body

    def same_guest(self):
        self.guest.healthy()
        require(self.shell('cat /proc/sys/kernel/random/boot_id','same_boot').strip() == self.boot,
                'apps stage escaped the actual packaged boot')

    def bind(self, role):
        raw = self.shell('bm dump -n '+bundle(role),'bms_'+role)
        identity = bms_application_identity(raw,bundle(role))
        document = decode(raw[raw.index('{'):]); app = document['applicationInfo']
        require(app.get('isSystemApp') is (role != 'normal') and
            app.get('appPrivilegeLevel') == ('normal' if role == 'normal' else 'system_core') and
            sorted(document.get('reqPermissions',[])) == permissions(self.kind,role),
            'actual installed caller APL/permission surface differs')
        paths = {m['hapPath'] for m in document.get('hapModuleInfos',[]) if m.get('hapPath')}
        require(len(paths) == 1,'one actual installed caller entry HAP required')
        path = paths.pop()
        require(path.startswith('/data/app/') and '..' not in path.split('/') and '\n' not in path,
                'only the newly installed caller HAP may be hashed')
        value = self.shell('sha256sum '+shlex.quote(path),'installed_hap_'+role)
        require(value.strip() == self.prepared[role]['signed']['sha256']+'  '+path,
                'guest installed caller bytes differ from original same-boot signed artifact')
        self.value['roles'][role] = {'identity':identity,'bms_command':len(self.value['commands'])-2,
            'hash_command':len(self.value['commands'])-1,'prepared':self.prepared[role]}
        return identity

    def launch(self, role, operation, argument='', number=0):
        require(role in self.prepared and re.fullmatch('[a-z][a-z0-9.-]{0,63}',operation) and
            isinstance(argument,str) and len(argument) <= 1024 and type(number) is int and abs(number) < 2**31,
            'fixed prepared role/bounded operation required')
        self.same_guest()
        argv = ['aa','start','-b',bundle(role),'-a','EntryAbility','--ps','run',self.run,
            '--ps','kind',self.kind,'--ps','operation',operation,'--ps','argument',argument,
            '--pi','numberArgument',str(number)]
        raw = self.shell(shlex.join(argv),'launch_'+role)
        require('start ability successfully' in raw.lower(), 'actual caller was not started')
        self.wait(role,lambda rows:any(r['operation']==operation and r['event']=='request' for r in rows),'request')

    def rows(self, role):
        base = '/data/app/el2/100/base/'+bundle(role)+'/files/'
        listing = self.shell('for p in '+base+'apps578-'+self.run+'-*.jsonl; do '
            'if test -f "$p" && test ! -L "$p"; then printf "%s\\n" "$p"; fi; done','journal_list')
        paths = listing.splitlines()
        require(len(paths) <= 16 and len(paths) == len(set(paths)), 'bounded distinct process-generation journals required')
        all_rows = []
        for path in paths:
            require(re.fullmatch(re.escape(base+'apps578-'+self.run+'-')+'[1-9][0-9]*'+r'\.jsonl',path),
                    'actual caller journal path differs')
            text = self.shell('test ! -L '+path+' && cat '+path,'actual_journal')
            # Preserve raw reads even if the latest fs.write was observed mid-row.
            self.value['journal_reads'].append({'role':role,'path':path,'command':len(self.value['commands'])-1})
            if text and not text.endswith('\n'):
                continue
            prior = self.previous.get(path,'')
            require(text.startswith(prior), 'actual process journal was truncated or replaced')
            current = journal(text,self.run,self.kind,role)
            require(all(r['uid'] == self.value['roles'][role]['identity']['uid'] for r in current),
                    'journal UID is not the independently observed installed UID')
            self.previous[path] = text
            all_rows.extend(current)
        return all_rows

    def wait(self, role, predicate, label, seconds=35):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            rows = self.rows(role)
            if predicate(rows): return rows
            time.sleep(.1)
        raise ValueError('actual apps578 boundary timed out: '+label)

    def observers(self,role):
        require(role in ('a','b') and self.kind in ('enterprise','notification-subscription'), 'fixed actual extension observer required')
        base='/data/app/el2/100/base/'+bundle(role)+'/files/apps578-observer-'+self.run+'-'
        listing=self.shell('for p in '+base+'*.jsonl; do if test -f "$p" && test ! -L "$p"; then printf "%s\\n" "$p"; fi; done',
            'actual_extension_observers')
        names=listing.splitlines();require(len(names)==len(set(names)) and len(names)<=16,'bounded real extension journals required')
        result=[]
        for name in names:
            require(re.fullmatch(re.escape(base)+r'[1-9][0-9]*\.jsonl',name),'actual extension journal escaped current nonce')
            text=self.shell('test ! -L '+name+' && cat '+name,'real_extension_callbacks')
            self.value['observer_reads'].append({'role':role,'path':name,'command':len(self.value['commands'])-1})
            if text and not text.endswith('\n'):continue
            require(text.startswith(self.previous.get(name,'')),'actual extension journal replaced/truncated')
            self.previous[name]=text
            rows=[decode(line) for line in text.splitlines()]
            require(len(rows)<10000 and all(set(r)=={'run','kind','role','bundle','uid','pid','activeMs','event','value'} and
                r['run']==self.run and r['kind']==self.kind and r['role']==role and r['bundle']==bundle(role) and
                r['uid']==self.value['roles'][role]['identity']['uid'] and name.endswith('-'+str(r['pid'])+'.jsonl') and
                type(r['activeMs']) in (int,float) and r['activeMs']>=0 and isinstance(r['event'],str) and
                isinstance(r['value'],str) for r in rows), 'real extension nonce/UID/PID/event framing differs')
            result.extend(rows)
        return result

    def wait_observer(self,role,event):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            rows=self.observers(role)
            if any(r['event']==event for r in rows):return rows
            time.sleep(.1)
        raise ValueError('actual public extension callback missing: '+event)

    def invoke(self, role, operation, action, *, wait=True, number=0, argument=''):
        if self.kind=='intelligent-scene' and action=='read':
            require(argument=='' and number==0,'fixed DND query request only')
            begin=len(self.value['commands'])
            self.launch(role,operation,argument='read-current-dnd')
            self.value['actions'].append({'role':role,'operation':operation,'action':'read',
                'source_dispatch':'dnd-onrequest-read','commands':list(range(begin,len(self.value['commands'])))})
            rows=self.wait(role,lambda v:any(r['operation']==operation and r['event']=='call.read' for r in v),'actual_dnd_query_call')
            if not wait:return rows
            return self.wait(role,lambda v:any(r['operation']==operation and r['event']=='return.read' for r in v),'actual_dnd_query_return')
        self.launch(role,operation,number=number,argument=argument)
        deadline=time.monotonic()+20
        while True:
            try:
                start = len(self.value['commands'])
                click = self.ui.click(bundle(role),identifier='apps578-'+action,label='caller_control')
                break
            except (NodeNotReady,LayoutNotReady):
                if time.monotonic()>=deadline:raise
                time.sleep(.1)
        self.value['actions'].append({'role':role,'operation':operation,'action':action,
            'selection':click,'commands':list(range(start,len(self.value['commands'])))})
        rows = self.wait(role,lambda v:any(r['operation']==operation and r['event']=='call.'+action for r in v),'call')
        if not wait: return rows
        return self.wait(role,lambda v:any(r['operation']==operation and r['event']=='return.'+action for r in v),'return')

    def api(self, role, operation, action, code=0, *, number=0, argument=''):
        return returned(self.invoke(role,operation,action,number=number,argument=argument),operation,action,code)

    def system(self, name):
        require(self.plan is not None and name in self.plan['actions'], 'actual packaged system action missing: '+name)
        for selector in self.plan['actions'][name]:
            if set(selector)=={'key'}:
                start=len(self.value['commands'])
                self.ui.shell('uitest uiInput keyEvent '+selector['key'],'system_cancel_key')
                self.value['actions'].append({'system':name,'selector':selector,'key':True,
                    'commands':list(range(start,len(self.value['commands'])))})
                continue
            if 'swipe_to' in selector:
                start=len(self.value['commands'])
                selection=self.ui.swipe_down(selector['bundle'],identifier=selector['identifier'],
                    swipe_to=selector['swipe_to'],label='actual_notification_drawer')
                self.value['actions'].append({'system':name,'selector':selector,'gesture':'swipe',
                    'selection':selection,'commands':list(range(start,len(self.value['commands'])))})
                continue
            deadline=time.monotonic()+20
            while True:
                try:
                    start=len(self.value['commands'])
                    tree,path=self.ui.layout(bundle=selector['bundle'],label='system_control')
                    node,matched=action_node(tree,selector)
                    clicked=True
                    if 'set_checked' in selector:
                        checked=node['attributes'].get('checked')
                        require(checked in ('true','false'),'actual Toggle checked state missing')
                        clicked=(checked=='true') is not selector['set_checked']
                    if clicked:
                        x,y,w,h=node['rect']
                        self.ui.shell('uitest uiInput click '+str(x+w//2)+' '+str(y+h//2),'actual_system_node_center')
                    self.value['actions'].append({'system':name,'selector':selector,'clicked':clicked,
                        'selection':{'layout':str(path),'selected_node':node,'matched_node':matched},
                        'commands':list(range(start,len(self.value['commands'])))})
                    break
                except (NodeNotReady,LayoutNotReady):
                    if time.monotonic()>=deadline:raise
                    time.sleep(.1)

    def visible(self, role, operation):
        require(self.plan is not None,'real provider plan required')
        deadline = time.monotonic()+20
        while True:
            try:
                start = len(self.value['commands'])
                tree,path = self.ui.layout(bundle=self.plan['provider_bundle'],label='real_provider')
                node = select_node(tree,**self.plan['visible'])
                current_rows=self.rows(role)
                require(self.kind in ('intelligent-scene','network-policy') or not any(r['operation']==operation and r['event'].startswith('return.') for r in current_rows),
                    'with-result API resolved before its real provider UI closed')
                self.value['actions'].append({'visible':operation,'role':role,'layout':json_ref(path),'node':node,
                    'commands':list(range(start,len(self.value['commands'])))})
                return
            except (NodeNotReady,LayoutNotReady):
                if time.monotonic() >= deadline: raise
                time.sleep(.1)

    def bind_provider(self, auxiliary=None):
        kind=auxiliary or self.kind
        require(auxiliary is None or auxiliary=='intelligent-scene-settings', 'fixed additional DND Settings provider only')
        proof=self.callbacks['verify_provider_image'](self.guest,kind)
        require(set(proof)=={'archive_sha256','bundle','modules'} and
            proof['archive_sha256']==self.value['archive_sha256'] and proof['bundle']==('com.ohos.settings' if auxiliary else self.plan['provider_bundle']) and
            isinstance(proof['modules'],dict) and proof['modules'],
            'original actual-archive provider compiler/signature guard required; pass JSON refused')
        raw=self.shell('bm dump -n '+proof['bundle'],'actual_provider_bms')
        doc=decode(raw[raw.index('{'):]); app=doc['applicationInfo']
        require(app['bundleName']==proof['bundle'] and app['isSystemApp'] is True and
            type(app['uid']) is int and app['uid']//200000==100,
            'real preinstalled provider owner differs')
        commands=[len(self.value['commands'])-1]
        modules={m['moduleName']:m for m in doc['hapModuleInfos']}
        expected = ('NotificationManangerUIExtensionAbility' if kind=='notification-settings'
            else 'NotificationAccessGrantUIExtensionAbility' if kind=='notification-subscription'
            else 'CertPickerUIExtAbility' if kind=='certificate-dialog'
            else 'ByodAdminProvisionAbility' if kind=='enterprise' else 'IntelligentSceneUIExtSettingAbility' if kind=='intelligent-scene' else 'UIExtensionProvider' if kind=='network-policy' else 'IntelligentSceneAppSelectExtensionAbility' if kind=='intelligent-scene-settings' else 'com.ohos.settings.MainAbility')
        declared=doc.get('extensionAbilityInfo',[])+doc.get('abilityInfos',[])
        target=[a for a in declared if a.get('name')==expected and a.get('moduleName') in proof['modules']]
        require(len(target)==1 and ((kind in ('enterprise','accessibility-settings') and target[0].get('visible') is True) or
            (target[0].get('type')==500 and target[0].get('visible') is True)),
            'actual BMS literal provider entry/type/export boundary missing')
        if kind=='accessibility-settings':
            services=[a for a in doc.get('extensionAbilityInfo',[]) if a.get('name')=='IgnoreRepeatClickExtService' and
                a.get('moduleName') in proof['modules'] and a.get('type')==0]
            require(len(services)==1,'actual Settings service extension declaration missing')
        for name,checksum in proof['modules'].items():
            require(re.fullmatch('[a-f0-9]{64}',checksum) and name in modules,'actual provider module missing')
            path=modules[name]['hapPath']
            require(path.startswith(('/system/','/data/app/')) and '..' not in path.split('/') and '\n' not in path,
                    'actual installed system provider path required')
            require(self.shell('sha256sum '+shlex.quote(path),'actual_provider_hap').strip()==checksum+'  '+path,
                    'guest provider bytes differ from this archive compiled source provider')
            commands.append(len(self.value['commands'])-1)
        stored={'proof':proof,'commands':commands}
        if auxiliary:
            self.value.setdefault('provider_aux',{})[auxiliary]=stored
        else:
            self.value['provider_image']=stored

    def bind_aux_provider(self, kind):
        return self.bind_provider(kind)

    def pixels(self, name, role, mode, seconds=4):
        from verify_screen_blink_results import verify_frames
        tree,path = self.ui.layout(bundle=bundle(role),label='blink_surface')
        rect = select_node(tree,bundle(role),identifier='blink-pixel-surface')['rect']
        frames = []
        deadline = time.monotonic()+seconds
        while len(frames) < 3 or time.monotonic() < deadline:
            before = time.monotonic(); picture = self.ui.screenshot(label='blink_pixels'); after = time.monotonic()
            frames.append({'path':str(picture),'sha256':sha(picture),'before':before,'after':after})
            time.sleep(.08)
        verify_frames(frames,rect,mode)
        self.value['pixels'].append({'name':name,'role':role,'layout':json_ref(path),'rect':rect,'frames':frames,'mode':mode})

    def stop(self, role):
        require(role in self.prepared,'only the prepared audit bundle may be stopped')
        begin=len(self.value['commands'])
        raw = self.shell(identity_shell(bundle(role),all_uids=False),'own_process_before')
        fields = raw.split()
        require(len(fields)==3 and all(re.fullmatch('[1-9][0-9]*',x) for x in fields) and
            int(fields[2]) == self.value['roles'][role]['identity']['uid'], 'exact current owned PID/starttime/UID required')
        old = list(map(int,fields))
        self.shell('aa force-stop '+bundle(role),'stop_only_owned_caller')
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            absent = self.shell('if test -d /proc/'+str(old[0])+'; then printf PRESENT; else printf ABSENT; fi','owned_process_absence')
            if absent == 'ABSENT':
                self.value['boundaries'].setdefault('death',[]).append({'role':role,'identity':old,
                    'commands':list(range(begin,len(self.value['commands'])))})
                return old[0]
            time.sleep(.1)
        raise ValueError('actual owned caller did not exit')

    def provider_gone(self):
        # A failed dump is not absence. Require two valid complete global trees
        # with the actual provider selector absent after the caller dies.
        consecutive=0;deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            begin=len(self.value['commands'])
            tree,path=self.ui.layout(label='after_caller_death')
            require(bool(tree),'empty hierarchy cannot prove provider disappearance')
            try:
                select_node(tree,**self.plan['visible'])
                consecutive=0
            except NodeNotReady:
                consecutive+=1
            self.value['actions'].append({'provider_gone':True,'layout':json_ref(path),
                'commands':list(range(begin,len(self.value['commands']))),'absent':consecutive>0})
            if consecutive>=2:return
            time.sleep(.2)
        raise ValueError('actual modal provider survived caller death')

    def frame_sequence(self, seconds):
        frames=[];started=time.monotonic()
        while len(frames)<3 or time.monotonic()-started<seconds:
            before=time.monotonic();path=self.ui.screenshot(label='actual_background');after=time.monotonic()
            frames.append({'path':str(path),'sha256':sha(path),'before':before,'after':after})
            time.sleep(.13)
        return frames

    def owner_death_boundary(self):
        from verify_screen_blink_results import verify_background_restored
        observed=time.monotonic();frames=self.frame_sequence(4)
        baseline=self.value['before_callers']
        verify_background_restored(baseline,frames,observed)
        return {'kind':'actual-owner-death/v1','baseline':baseline,'frames':frames,'exit_observed':observed}

    def account_program_boundary(self):
        """Actual API caller/ack protocol for root's fixed account callback.

        This does not create an account from root shell. The signed account
        program invokes every real osAccount API and owns its own finally.
        """
        from verify_screen_blink_results import verify_background_restored
        self.invoke('account','acct.program','account-program',wait=False)
        def wait_phase(phase):
            self.wait('account',lambda v:any(r['event']=='account.wait.'+phase for r in v),'account_phase',seconds=45)
        def ack(phase):
            require(phase in ('baseline','active','away','return'),'fixed account phase input only')
            path='/data/app/el2/100/base/'+bundle('account')+'/files/account578-'+self.run+'-ack'
            uid=self.value['roles']['account']['identity']['uid']
            self.shell('test ! -L '+path+' && printf %s '+shlex.quote(self.run+':'+phase)+' > '+path+
                ' && chown '+str(uid)+':'+str(uid)+' '+path+' && chmod 0600 '+path,'own_account_ack')
        wait_phase('baseline')
        baseline_frames=self.frame_sequence(3)
        baseline={k:baseline_frames[0][k] for k in ('path','sha256')}
        verify_background_restored(baseline,baseline_frames[1:]+self.frame_sequence(1))
        ack('baseline');wait_phase('active')
        require(self.api('a','acct.active','start')==0,'account baseline switch left stale ownership')
        self.pixels('account-active','a','continuous');ack('active')
        wait_phase('away');observed=time.monotonic();away=self.frame_sequence(4)
        verify_background_restored(baseline,away,observed);ack('away')
        wait_phase('return')
        self.launch('a','acct.returned')
        self.pixels('account-return-quiet','a','off');quiet=self.value['pixels'][-1]
        require(self.api('a','acct.reacquire','start')==0,'real account switch did not clear owner')
        self.pixels('account-reacquired','a','continuous');active=self.value['pixels'][-1]
        require(self.api('a','acct.stop','stop')==0,'account active pulse did not stop')
        ack('return')
        self.wait('account',lambda v:any(r['operation']=='acct.program' and r['event']=='return.account-program' for r in v),
            'actual_account_finally',seconds=45)
        returned(self.rows('account'),'acct.program','account-program')
        return {'kind':'nonce-account-switch/v1','new_account_baseline':baseline,'after_switch':away,
            'switch_observed':observed,'after_return':quiet,'reacquired':active}

    def notification_case(self):
        role='normal' if self.kind=='notification-settings' else 'a'
        baseline = self.api(role,'baseline','read')
        self.value['baseline']=baseline
        if self.kind=='notification-subscription':
            self.api('system-denied','denied','invoke',201)
            self.api('normal','normal-denied','invoke',201)
        self.api(role,'invalid','invalid',401)
        # Both calls are issued by one real UI click before either async native
        # window dispatch completes. A second HDC start must not dismiss the
        # first modal and accidentally turn this into a sequential test.
        self.launch(role,'two')
        start=len(self.value['commands'])
        click=self.ui.click(bundle(role),identifier='apps578-duplicate',label='duplicate_requests')
        self.value['actions'].append({'role':role,'operation':'two','action':'duplicate',
            'selection':click,'commands':list(range(start,len(self.value['commands'])))})
        self.wait(role,lambda v:any(r['operation']=='two.duplicate' and r['event']=='return.invoke' for r in v),'duplicate_rejected')
        returned(self.rows(role),'two.duplicate','invoke',1600018)
        self.visible(role,'two');self.system('cancel')
        self.wait(role,lambda v:any(r['operation']=='two' and r['event']=='return.invoke' for r in v),'original_request_closed')
        for name,wanted in (('enable',True),('disable',False)):
            self.invoke(role,name,'invoke',wait=False); self.visible(role,name)
            self.system(name); self.system('close')
            rows=self.wait(role,lambda v:any(r['operation']==name and r['event']=='return.invoke' for r in v),'settings_closed')
            result=returned(rows,name,'invoke')
            current=self.api(role,name+'.read','read')
            if self.kind=='notification-settings':
                require(isinstance(result,dict) and result==current['settings'] and current['enabled'] is wanted and
                    ('notificationEnabled' not in result or result['notificationEnabled'] is wanted),
                    'real notification user result/getter/UI choice differ')
            else:
                require(isinstance(result,dict) and result.get('userGrantEnabled') is wanted and current is wanted,
                    'real notification subscriber grant/result/getter differ')
        self.invoke(role,'cancel','invoke',wait=False); self.visible(role,'cancel'); self.system('cancel')
        self.wait(role,lambda v:any(r['operation']=='cancel' and r['event']=='return.invoke' for r in v),'cancel_closed')
        cancelled=self.api(role,'cancel.read','read')
        require(cancelled is False if self.kind=='notification-subscription' else cancelled['enabled'] is False,
                'cancel changed real user authorization')
        self.invoke(role,'death','invoke',wait=False); self.visible(role,'death')
        old=self.stop(role)
        self.provider_gone()
        restarted=self.api(role,'restart.read','read')
        require(restarted==cancelled,'caller death/restart changed persisted provider state')
        require(any(r['pid']!=old and r['operation']=='restart.read' for r in self.rows(role)),
            'actual caller restart generation missing')
        # Restore through the same real provider UI, never a root store write.
        wanted=baseline['enabled'] if self.kind=='notification-settings' else baseline
        require(type(wanted) is bool,'actual initial provider switch missing')
        self.invoke(role,'restore','invoke',wait=False); self.visible(role,'restore')
        self.system('enable' if wanted else 'disable'); self.system('close')
        self.wait(role,lambda v:any(r['operation']=='restore' and r['event']=='return.invoke' for r in v),'restored')
        require(self.api(role,'restored.read','read')==baseline,'provider settings were not restored exactly')

    def missing_provider_case(self):
        # Collect the real public call/return and BMS streams before failing the
        # missing-selector boundary. A void return (notably APN without SIM)
        # cannot become a UI pass. An unexpectedly present target is retained
        # for parent review, never labeled unsupported by this caller.
        require(self.plan['schema']=='actual-apps578-missing-provider-boundary/v1','fixed missing-target source plan required')
        observed=[]
        actions=(('normal','read'),('system-denied','read'),('a','read'),('a','open-settings')) if self.kind=='intelligent-scene' else (
            ('normal','invoke'),('system-denied','invoke'),('a','read'),('a','invalid'),('a','invoke'))
        for role,action in actions:
            operation='boundary.'+role+'.'+action
            try:
                rows=self.invoke(role,operation,action)
                result=[r for r in rows if r['operation']==operation and r['event']=='return.'+action]
                require(len(result)==1,'actual boundary API result missing')
                observed.append({'role':role,'operation':operation,'action':action,'code':result[0]['code'],'value':decode(result[0]['value'])})
            except Exception as error:
                observed.append({'role':role,'operation':operation,'action':action,'error':str(error)})
        proof=self.callbacks['business_boundary'](self.guest,self,'provider-probe',{})
        self.value['boundary_observations']={'api':observed,'provider':proof,
            'classification':provider_boundary_classification(self.kind,proof,observed)}
        raise ValueError('pending actual public provider/UI protocol: source-bound target lacks usable selector; actual API/BMS retained')

    def blink_case(self):
        require(self.api('a','baseline','read')=='0','fresh guest blink must initially be disabled; existing user state is not owned')
        self.value['original_setting']='0'
        for role,code in (('normal',202),('system-denied',201)):
            for action in ('start','stop','invalid-mode','invalid-scenario'):
                self.api(role,role+'.'+action,action,code)
        require(self.api('a','enable','enable')=={'written':True,'read':'1'},'real settings grant did not commit')
        time.sleep(1)
        require(self.api('a','start','start')==0,'real public start failed')
        self.pixels('a-continuous','a','continuous')
        require(self.api('a','already','start')==1,'same owner repeat start differs')
        self.api('a','invalid-mode','invalid-mode',401);self.api('a','invalid-scenario','invalid-scenario',401)
        for action in ('start','stop','wrong-stop'):
            require(self.api('b','foreign.'+action,action)==2,'another real BMS token must not acquire/stop the owner')
            self.pixels('foreign-'+action,'b','continuous')
        require(self.api('a','wrong-stop','wrong-stop')==2,'wrong scenario must not stop the owner')
        self.pixels('wrong-scenario-retains','a','continuous')
        require(self.api('a','stop','stop')==0 and self.api('a','stop.again','stop')==0,'stop/repeated stop differ')
        self.pixels('a-stopped','a','off')
        require(self.api('b','takeover','start')==0,'released owner was not acquirable by real second token')
        self.stop('a');self.pixels('nonowner-death-retains','b','continuous')
        self.stop('b')
        # Real owner death must remove the overlay; root original pixel oracle
        # uses its pre-caller compositor background, never an empty window title.
        self.value['boundaries']['owner_death']=self.callbacks['display_boundary'](
            self.guest,self,'owner-death') if callable(self.callbacks['display_boundary']) else None
        require(self.api('a','restart.stop','stop')==0,'new process could not stop after prior owner death')
        self.pixels('new-process-off','a','off')
        require(self.api('a','restart.start','start')==0,'new process could not acquire after prior owner death')
        if self.full_blink:
            self.value['boundaries']['account']=self.callbacks['account_boundary'](self.guest,self)
            self.value['boundaries']['display']=self.callbacks['display_boundary'](self.guest,self,'display-recreate')
        require(self.api('a','disable','disable')=={'written':True,'read':'0'},'owned blink setting was not restored')
        self.pixels('disabled-clears','a','off')
        require(self.api('a','disabled.start','start')==5,'disabled public start must report FEATURE_DISABLED')

    def intelligent_case(self):
        self.value['baseline']={r:self.api(r,'baseline','read') for r in ('a','b')}
        for role in ('normal','system-denied'):
            self.api(role,'denied','read',201)
        for state,expected in (('allowed',[True,True]),('denied',[True,False]),('disabled',None)):
            self.api('a',state+'.open','open-settings')
            # All actions below are actual pinned Settings controls. They must
            # identify the fresh role labels/bundles; a stored default is not a
            # replacement for these real operations.
            self.system('dnd-enable' if state!='disabled' else 'dnd-disable')
            if state!='disabled':
                self.system('allow-caller' if state=='allowed' else 'deny-caller')
                self.system('deny-peer')
            a=self.api('a',state+'.read','read');b=self.api('b',state+'.read','read')
            require(isinstance(a,list) and len(a)==2 and all(type(x) is bool for x in a) and
                isinstance(b,list) and len(b)==2 and all(type(x) is bool for x in b),
                'both actual DND queries must return real booleans for two independent bundles')
            if expected is not None:
                require(a==expected and b==[True,False],'DND global state or per-caller whitelist result differs')
            else:require(a[0] is False and b[0] is False,'real DND disable did not commit')
        old=self.stop('a');self.api('a','restart.read','read')
        require(any(r['operation']=='restart.read' and r['pid']!=old for r in self.rows('a')),
                'DND caller restart lacks a new process generation')
        self.api('a','restore.open','open-settings');self.system('restore')
        for role in ('a','b'):
            require(self.api(role,'restored.read','read')==self.value['baseline'][role],
                    'actual original DND/user-bundle state was not restored')

    def run(self):
        self.same_guest()
        roles=('normal','system-denied','a','b','account') if self.kind=='blink' else (
            ('normal','system-denied','a','b') if self.kind in
                ('intelligent-scene','certificate-dialog','network-policy','enterprise','accessibility-input') else ('normal','system-denied','a'))
        try:
            self.prepared=self.callbacks['prepare_apps578'](self.guest,self.kind,self.run,roles)
            require(set(self.prepared)==set(roles),'original build/sign/install must provide every exact role')
            for role in roles:
                validate_prepared(self.prepared[role],self.run,self.kind,role,self.udid);self.bind(role)
            if self.plan is not None and self.plan['schema']=='actual-apps578-missing-provider-boundary/v1':
                self.missing_provider_case()
            if self.kind=='blink':
                from run_application_home_probe import system_screen
                self.ui.shell('uitest uiInput keyEvent Home','actual_home_before_callers')
                tree,_=self.ui.layout(label='actual_home')
                require(system_screen(tree)[0]=='home','actual default home must be visible before caller pixels')
                baseline=self.ui.screenshot(label='before_callers')
                self.value['before_callers']={'path':str(baseline),'sha256':sha(baseline)}
                ids=[self.value['roles'][r]['identity'] for r in ('a','b')]
                require(ids[0]['uid']!=ids[1]['uid'] and ids[0]['token_id']!=ids[1]['token_id'],
                        'competing callers must have distinct actual BMS UIDs and access tokens')
                self.blink_case()
            elif self.kind in ('notification-settings','notification-subscription'):
                self.bind_provider()
                self.notification_case()
            elif self.kind=='intelligent-scene':
                from apps_ui578_followup import intelligent_scene
                intelligent_scene(self)
            elif self.kind=='network-policy':
                from apps_ui578_followup import network_policy
                network_policy(self)
            elif self.kind=='accessibility-settings':
                from apps_ui578_extra import settings_case
                settings_case(self)
            elif self.kind in ('shortkey','accessibility-input','certificate-dialog','enterprise'):
                from apps_ui578_extra import run
                run(self)
            else:
                # These caller slices are supplied for the next real provider
                # stage. They are not silently accepted as aggregate UI plans.
                raise ValueError('additional actual provider/backend stage still required: '+self.kind)
            self.same_guest();self.value['status']='observed'
        except Exception as error:
            self.value['failures'].append(str(error))
        finally:
            try:
                self.value['cleanup']=self.callbacks['cleanup_apps578'](self.guest,self.kind,self.run,self.prepared,self)
                self.same_guest()
                self.value['cleanup_verified']=True
            except Exception as error:
                self.value['failures'].append('original stage cleanup failed: '+str(error))
            if self.value['failures']:self.value['status']='fail'
            self.save()
        return self.value


def run(guest, root_callbacks, parameters):
    return Session(guest,root_callbacks,parameters).run()
