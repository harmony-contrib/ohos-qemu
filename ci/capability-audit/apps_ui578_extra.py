"""Actual additional public-API/UI/physical-input cases on the held guest.

No new Owner or resource primitive. Successful command return alone is never
the business oracle; each action has a separate real UI/caller consumer.
"""
import time

from apps_ui578_contract import bundle, decode, json_ref, require, returned, load_ref, sha
from guest_ui import select_node


SHORTCUT = {'businessId':'qemu.settings','preKey':[2076],'finalKey':2025,
    'trigger':'key_down','keyDownDuration':500,'statusConfig':'',
    'ability':{'bundleName':'com.ohos.settings','abilityName':'com.ohos.settings.MainAbility'}}


def physical(session,action,parameters):
    require(callable(session.callbacks['business_boundary']),'original actual physical-input callback required')
    result=session.callbacks['business_boundary'](session.guest,session,action,parameters)
    session.value['boundaries'].setdefault('business',[]).append(result)
    return result


def home(session,label):
    from run_application_home_probe import system_screen
    session.ui.shell('uitest uiInput keyEvent Home','actual_home')
    tree,path=session.ui.layout(label=label)
    require(system_screen(tree)[0]=='home','actual packaged default home required before shortcut')
    return {'layout':json_ref(path),'frame':json_ref(session.ui.screenshot(label='actual_home_painted'))}


def shortkey(session):
    actual=decode(session.shell('cat /system/etc/multimodalinput/ability_launch_config.json','packaged_shortcut'))
    require(actual.get('Shortkeys')==[SHORTCUT],'actual packaged businessId/config differs')
    dump=session.shell('hidumper -s 3101 -a "-k"','actual_shortcut_registration')
    import re
    require(re.findall(r'ShortcutKey: count = (\d+)',dump)==['1'],'MMI did not register the actual packaged shortcut')
    session.value['shortcut']={'config':actual,'registration':len(session.value['commands'])-1,'cycles':[]}
    session.api('normal','normal.delay','invoke',202,number=1500)
    session.api('a','invalid.key','invalid',401,number=500)
    session.api('a','invalid.delay','invoke',401,number=-1)
    def press(name,modifier,milliseconds,expected):
        before=home(session,'shortcut_home_before')
        io=physical(session,'shortcut-key',{'modifier':modifier,'hold_ms':milliseconds})
        time.sleep((milliseconds+400)/1000)
        tree,path=session.ui.layout(label='shortcut_actual_result')
        picture=session.ui.screenshot(label='shortcut_actual_pixels')
        if expected=='home':
            from run_application_home_probe import system_screen
            require(system_screen(tree)[0]=='home','short/wrong shortcut unexpectedly activated Settings')
        else:
            from run_shortkey_keyboard_diagnostic import title_node
            from settings_navigation_ui import require_painted_title
            node=title_node(tree);require_painted_title(picture,node)
        row={'name':name,'expected':expected,'before':before,'qmp':io,
            'layout':json_ref(path),'frame':json_ref(picture)}
        session.value['shortcut']['cycles'].append(row)
        if expected=='settings':
            session.ui.shell('uitest uiInput keyEvent Back','ordinary_shortcut_cancel')
            home(session,'shortcut_returned_home')
    session.api('a','duration.long','invoke',number=1500)
    press('early-release','meta_l',1000,'home');press('wrong-modifier','ctrl',1800,'home')
    press('long-accepted','meta_l',1800,'settings')
    session.api('a','duration.short','invoke',number=200)
    press('changed-delay','meta_l',800,'settings')
    session.stop('a');session.api('a','restart.delay','invoke',number=200)
    press('restarted-caller','meta_l',800,'settings')
    session.api('a','duration.restore','invoke',number=500)
    press('restored-early','meta_l',100,'home');press('restored-valid','meta_l',800,'settings')


def input_case(session):
    # Real QMP pointer+keyboard feed the packaged input stack. Public ArkUI
    # callbacks and UITest accessibility nodes are separate consumers.
    session.value['input']={'steps':[]}
    for role in ('normal','a','b'):
        require(session.api(role,role+'.empty','read')=={'text':'','count':0},'fresh real caller input state differs')
        tree,path=session.ui.layout(bundle=bundle(role),label='actual_input_target')
        button=select_node(tree,bundle(role),identifier='apps578-increment',clickable=True)
        io=physical(session,'input-click',{'role':role,'layout':json_ref(path),'identifier':'apps578-increment'})
        session.wait(role,lambda rows:any(r['event']=='input.clicked' for r in rows),'real_physical_click')
        require(session.api(role,role+'.clicked','read')=={'text':'','count':1},'real physical click did not reach public onClick')
        session.ui.click(bundle(role),identifier='apps578-input',label='focus_actual_input')
        typed=session.run[:8]
        keyboard=physical(session,'input-type',{'role':role,'text':typed})
        session.wait(role,lambda rows:any(r['event']=='input.changed' and decode(r['value'])==typed for r in rows),'real_physical_text')
        require(session.api(role,role+'.typed','read')=={'text':typed,'count':1},'real physical keyboard text differs')
        tree,path=session.ui.layout(bundle=bundle(role),label='actual_typed_accessibility_node')
        text=select_node(tree,bundle(role),identifier='apps578-input')
        require(text['attributes'].get('text')==typed,'actual accessibility node did not expose real typed text')
        session.ui.shell('uitest uiInput keyEvent Back','cancel_actual_input')
        session.ui.shell('uitest uiInput keyEvent Home','background_actual_input')
        require(session.api(role,role+'.resume','read')=={'text':typed,'count':1},'background/resume lost real input state')
        old=session.stop(role)
        require(session.api(role,role+'.recreated','read')=={'text':'','count':0},'recreated process retained stale UI state')
        require(any(r['pid']!=old and r['operation']==role+'.recreated' for r in session.rows(role)), 'input process recreation missing')
        session.value['input']['steps'].append({'role':role,'button':button,'pointer':io,'keyboard':keyboard,
            'typed_layout':json_ref(path),'typed_node':text})
    # Account/default-display/Settings actions are required by the wider
    # original ID. The full blink and settings records must be joined by the
    # parent gate; this narrow real input case deliberately cannot close it.


def certificate_case(session):
    session.bind_provider()
    baseline=session.api('a','baseline','read');session.value['baseline']=baseline
    require(type(baseline['supportsCA']) is bool and baseline['own'].get('credentialList')==[] and
        isinstance(baseline['trusted'].get('certList'),list), 'fresh actual caller certificate inventory required')
    session.value['certificate']={'private_installed':False,'ca_installed':False,'supportsCA':baseline['supportsCA']}
    for role in ('normal','system-denied'):session.api(role,'denied','ca',201)
    session.api('a','invalid','invalid',401)
    session.api('a','empty','invoke',29700007)
    inputs=session.callbacks['business_boundary'](session.guest,session,'certificate-input',{})
    session.value['certificate']['input']=inputs
    imported=session.api('a','import','import')
    require(isinstance(imported.get('uri'),str) and imported['uri'], 'actual imported credential URI missing')
    session.value['certificate']['private_installed']=True
    # A second signed bundle has the same permission but cannot see this app's
    # private credential. This checks actual per-UID storage, not label text.
    peer=session.api('b','peer.empty','read')
    require(peer['own'].get('credentialList')==[],'private credential leaked into real peer UID')
    session.api('b','peer.authorize','invoke',29700007)
    session.invoke('a','select','invoke',wait=False);session.visible('a','select')
    session.system('select-own');session.system('authorize')
    selected=session.wait('a',lambda rows:any(r['operation']=='select' and r['event']=='return.invoke' for r in rows),'actual_certificate_selected')
    actual=returned(selected,'select','invoke')
    descriptor=decode(load_ref(inputs['input']))
    import hashlib
    require(actual['keyUri']==imported['uri']==actual['reference']['keyUri'] and
        actual['alias']=='apps_'+session.run[:16] and actual['certNum']==1 and actual['keyNum']==1 and actual['bytes'],
        'actual selected URI was not consumed as the exact nonce credential')
    require(hashlib.sha256(bytes(actual['der'])).hexdigest()==descriptor['der']['sha256'],
        'independent public X509 consumer did not decode the exact current nonce certificate')
    session.invoke('a','cancel','invoke',wait=False);session.visible('a','cancel');session.system('cancel')
    session.wait('a',lambda rows:any(r['operation']=='cancel' and r['event']=='return.invoke' for r in rows),'certificate_cancel')
    returned(session.rows('a'),'cancel','invoke',29700002)
    session.invoke('a','death','invoke',wait=False);session.visible('a','death');old=session.stop('a');session.provider_gone()
    after=session.api('a','restarted.read','read')
    require(any(x['keyUri']==imported['uri'] and x['alias']=='apps_'+session.run[:16]
        for x in after['own']['credentialList']) and
        any(r['pid']!=old and r['operation']=='restarted.read' for r in session.rows('a')),
        'actual credential did not persist across caller death/recreation')
    if baseline['supportsCA']:
        session.value['certificate']['product_gap']='fixed CertPicker/CertificateInstallPage lacks operationType UNINSTALL dispatch'
        raise ValueError('pending actual CA install/uninstall product protocol; refuse creating a global CA without its real dialog cleanup path')
    else:
        # Real generic-device support branch is a required observation. It does
        # not turn a missing HAP, unrelated error or absent input into success.
        session.api('a','ca.unsupported','install-ca',29700004)
    session.api('a','remove','remove');session.value['certificate']['private_installed']=False
    require(session.api('a','restored.read','read')==baseline,'nonce private/trusted certificate inventory did not restore')


def enterprise(session):
    # The backend and real extension callbacks are exercised even though fixed
    # public BYOD UI currently implements only an unsupported-device dialog.
    # A backend success must not close that unimplemented provider protocol.
    session.bind_provider();session.value['admin_owned']=False
    require(session.api('a','baseline','read') is False and session.api('b','peer.baseline','read') is False,
        'fresh nonce caller admins must initially be disabled')
    for action in ('read','invoke','super'):session.api('normal','normal.'+action,action,202)
    for action in ('invoke','super'):session.api('system-denied','denied.'+action,action,201)
    session.api('a','invalid','invalid',9200003)
    session.api('a','enable','invoke');session.value['admin_owned']=True
    require(session.api('a','enabled.read','read') is True and session.api('b','peer.read','read') is False,
        'real normal administrator activation/UID isolation differs')
    session.wait_observer('a','admin.enabled.callback')
    old=session.stop('a')
    require(session.api('a','restart.read','read') is True and
        any(r['pid']!=old and r['operation']=='restart.read' for r in session.rows('a')),
        'actual normal admin did not persist through caller death/recreation')
    session.api('a','disable','disable')
    require(session.api('a','disabled.read','read') is False, 'real normal administrator did not deactivate')
    session.wait_observer('a','admin.disabled.callback');session.value['admin_owned']=False
    session.invoke('a','byod.cancel','byod',wait=False);session.visible('a','byod.cancel');session.system('byod-cancel')
    session.wait('a',lambda r:any(x['operation']=='byod.cancel' and x['event']=='return.byod' for x in r),'real_byod_cancel')
    returned(session.rows('a'),'byod.cancel','byod')
    require(session.api('a','byod.cancel.read','read') is False,'actual BYOD cancel activated an administrator')
    session.invoke('a','byod.agree','byod',wait=False);session.visible('a','byod.agree');session.system('byod-agree')
    # This is the fixed provider's real unsupported branch. The actual dialog
    # must be selected/clicked, not synthesized as a caller success response.
    session.system('byod-unsupported-confirm')
    session.wait('a',lambda r:any(x['operation']=='byod.agree' and x['event']=='return.byod' for x in r),'actual_byod_unsupported_result')
    returned(session.rows('a'),'byod.agree','byod')
    require(session.api('a','byod.agree.read','read') is False,'fixed unsupported BYOD branch unexpectedly changed admin state')
    session.value['product_boundaries']=['fixed-public-BYOD-provider-has-no-activation-implementation']


def run(session):
    if session.kind=='shortkey':shortkey(session)
    elif session.kind=='accessibility-input':input_case(session)
    elif session.kind=='certificate-dialog':certificate_case(session)
    elif session.kind=='enterprise':enterprise(session)
    else:raise ValueError('fixed actual extra case required')


def settings_lifecycle(before, after, ams, action):
    """Actual Settings onCreate/request/conditional decision/onDestroy sequence.

    AMS absence excludes the active/cache maps only. It is deliberately paired
    with the actual same-PID onDestroy callback; Settings' shared process may
    remain alive. No force-stop of Settings is part of this protocol.
    """
    import re
    require(before.endswith('\n') and after.endswith('\n') and len(before.encode())<=16*2**20 and
        len(after.encode())<=16*2**20, 'bounded complete actual hilog snapshots required')
    old=[line for line in before.splitlines() if re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+[1-9][0-9]*\s+[1-9][0-9]*\s+[DIWEF]\b',line)]
    new=after.splitlines()
    require(old and new.count(old[-1])==1,'actual pre-action hilog anchor was lost/duplicated')
    delta=new[new.index(old[-1])+1:]
    parsed=[]
    for index,line in enumerate(delta):
        match=re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([1-9][0-9]*)\s+[1-9][0-9]*\s+[DIWEF]\b',line)
        if match:parsed.append((index,int(match[1]),line))
    requests=[r for r in parsed if 'IgnoreRepeatClickService' in r[2] and 'onRequest' in r[2] and 'action:'+action in r[2]]
    require(len(requests)==1,'exact new original WantAgent service action missing/duplicated')
    request=requests[0];pid=request[1]
    created=[r for r in parsed if r[0]<request[0] and r[1]==pid and 'IgnoreRepeatClickService' in r[2] and 'onCreate' in r[2]]
    native=[]
    for row in parsed:
        m=re.search(r'conditional stop accepted, startId=([1-9][0-9]*) record=([1-9][0-9]*)\b',row[2])
        if row[0]>request[0] and m:native.append((row,int(m[1]),int(m[2])))
    require(created and len(native)==1,'actual new service/native conditional stop decision missing or ambiguous')
    native_row,start,record=native[0]
    destroyed=[r for r in parsed if r[0]>native_row[0] and r[1]==pid and 'IgnoreRepeatClickService' in r[2] and 'onDestroy' in r[2]]
    # The JS promise may settle after onDestroy invalidates its context, so
    # Settings intentionally suppresses its late JS decision log. Never require
    # that callback or invent it in place of native decision + actual destroy.
    decisions=[]
    for row in parsed:
        m=re.search(r'IgnoreRepeatClickService conditional idle stop startId:([1-9][0-9]*) accepted:(true|false)\b',row[2])
        if row[0]>request[0] and row[1]==pid and m:
            require(int(m[1])==start and m[2]=='true','actual Settings conditional-stop result differs')
            decisions.append(row[2])
    require(destroyed and not any('IgnoreRepeatClickService' in r[2] and
        ('action:'+action+' failed' in r[2] or 'conditional idle stop failed' in r[2]) for r in parsed),
        'actual service onDestroy/error semantics differ')
    require(re.search(r'^User ID #100\s*$',ams,re.M) and 'AppRunningRecords:' in ams and '  ExtensionRecords:' in ams,
        'actual complete account-100 AMS active/cache extension dump missing')
    require('main name [IgnoreRepeatClickExtService]' not in ams,'original Settings service remains in actual active/cache records')
    return {'pid':pid,'start_id':start,'record_id':record, 'created':created[-1][2],
        'request':request[2],'decisions':decisions,'native_decision':native_row[2],'destroyed':destroyed[-1][2]}


def settings_case(session):
    session.bind_provider()
    session.value['settings']={'saved':False,'cycles':[]}
    baseline=session.api('a','settings.baseline','settings-save')
    session.value['baseline']=baseline;session.value['settings']['saved']=True
    require(baseline['ignoreRepeat'] is False and baseline['animationOff'] is False,
        'only inactive actual fresh Settings state is owned')
    for role,code in (('normal',202),('system-denied',201)):
        session.api(role,role+'.config.denied','ignore-enable',code)
    session.api('a','settings.invalid','invalid',401)
    for name,enable,button,service_action,field,flag,expect in (
        ('ignore-disable','ignore-enable','ignore-disable','disableIgnoreRepeatClick','ignoreRepeat','ignoreNotification',False),
        ('ignore-cancel','ignore-enable','ignore-cancel','disableNotificaiton','ignoreRepeat','ignoreNotification',True),
        ('animation-enable','animation-enable','animation-enable','reOpenTransitionAnimations','animationOff','animationNotification',False),
        ('animation-cancel','animation-enable','animation-cancel','disableTransitionAnimationsNotification','animationOff','animationNotification',True)):
        state=session.api('a',name+'.setup',enable)
        require(state[field] is True and state[flag]=='1','real NAPI config/preference setup did not commit')
        # Caller exit/recreate must not dispose of a service-owned reminder.
        old=session.stop('a');observed=session.api('a',name+'.recreated','read')
        require(observed==state and any(r['operation']==name+'.recreated' and r['pid']!=old for r in session.rows('a')),
            'actual reminder/config state did not survive the caller generation')
        session.system('drawer');session.system('back')
        require(session.api('a',name+'.dismissed','read')==state,'dismissing actual drawer changed the business state')
        before=session.shell('hilog -x','service_before');before_index=len(session.value['commands'])-1
        session.system('drawer');session.system('expand-'+('ignore' if field=='ignoreRepeat' else 'animation'))
        session.system(button)
        deadline=time.monotonic()+35;attempt=0;completed=[]
        while time.monotonic()<deadline:
            attempt+=1
            current=session.api('a',name+'.read.'+str(attempt),'read')
            after=session.shell('hilog -x','service_after');after_index=len(session.value['commands'])-1
            ams=session.shell('aa dump -a -u 100','settings_service_active_cache');ams_index=len(session.value['commands'])-1
            wanted_flag='0' if expect else '1'
            try:
                lifecycle=settings_lifecycle(before,after,ams,service_action)
                require(current[field] is expect and current[flag]==wanted_flag,
                    'actual notification action did not change its independent public config/preference consumer')
                completed.append({'after':after_index,'ams':ams_index,'read':name+'.read.'+str(attempt),'lifecycle':lifecycle})
                if len(completed)==2:break
            except ValueError:completed=[]
            time.sleep(.25)
        require(len(completed)==2,'actual notification action/config/service idle completion did not close')
        session.value['settings']['cycles'].append({'name':name,'setup':state,'before':before_index,
            'service_action':service_action,'field':field,'flag':flag,'expected':expect,'observations':completed})
    require(session.api('a','settings.restore','settings-restore')==baseline,'actual Settings state did not restore exactly')
    session.value['settings']['restored']=True
