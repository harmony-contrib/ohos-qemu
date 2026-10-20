"""Independent raw replay for additional apps578 observations on one new guest.

No HDC/QMP/build/SDK calls. Invoked by the original package ledger/gate with the
original enclosing Owner command log and its admitted archive/boot/HDCTest path.
"""
from pathlib import Path
import re
import shlex

from apps_ui578_contract import (IDS, SLICE_ONLY, bundle, decode, journal, load_ref,
    nonce, permissions, qmp_wire, action_node, provider_boundary_classification, require, returned, sha)
from apps_ui578_project import validate_prepared
from apps_ui578_runtime import read_plan
from guest_ui import command_exit, select_node, swipe_down_points, NodeNotReady
from hap_identity_binding import bms_application_identity


def commands(value, owner, hdc, target):
    records=[]
    previous=-1
    for entry in value['commands']:
        require(set(entry)=={'owner_index','observation','argv','log','started_ns','finished_ns'} and
            type(entry['owner_index']) is int and entry['owner_index']>previous and
            type(entry['started_ns']) is int and type(entry['finished_ns']) is int and
            entry['finished_ns']>=entry['started_ns'], 'exact ordered original command records required')
        previous=entry['owner_index']; original=owner['commands'][previous]
        require(original['argv']==entry['argv'] and original['exit_code']==0 and not original.get('timed_out') and
            original['log']==entry['log']['path'] and original['sha256']==entry['log']['sha256'],
            'apps observation does not refer to the original successful owner command')
        text=load_ref(entry['log']).replace('\r','');argv=entry['argv']
        require(argv[:3]==[str(hdc),'-t',target], 'actual original HDC guest endpoint differs')
        if argv[3]=='shell':
            require(len(argv)==5,'one original framed guest shell command required')
            match=re.fullmatch(r'(.*); (apps578_rc|task_ui_rc)=\$\?; printf "\\n(__[A-Z0-9_]+_EXIT_[a-f0-9]{32}__=)%s\\n" "\$\2"',argv[4],re.S)
            require(match is not None,'original guest exit footer missing')
            text,code=command_exit(text,match[3]);require(code==0,'actual guest command failed')
            records.append({'script':match[1],'body':text,'entry':entry})
        else:
            require(len(argv)==7 and argv[3:5]==['file','recv'],'only original UI artifact transfer is admitted here')
            records.append({'transfer':argv[5:],'body':text,'entry':entry})
    boots=[r for r in records if r.get('script')=='cat /proc/sys/kernel/random/boot_id']
    require(len(boots)>=2 and all(r['body'].strip()==value['boot_id'] for r in boots),
            'same actual boot was not retained through stage and cleanup')
    return records


def role_rows(value, records):
    seen={};parsed={r:[] for r in value['roles']}
    for item in value['journal_reads']:
        role,path,index=item['role'],item['path'],item['command']
        require(role in value['roles'] and records[index].get('script')=='test ! -L '+path+' && cat '+path,
                'actual caller journal was not read from its own guest file')
        prefix='/data/app/el2/100/base/'+bundle(role)+'/files/apps578-'+value['run']+'-'
        require(re.fullmatch(re.escape(prefix)+r'[1-9][0-9]*\.jsonl',path), 'actual journal path escaped nonce owner')
        text=records[index]['body']
        if text and not text.endswith('\n'):
            # In-flight final partial rows remain in the original command log.
            # Every completed prior row is still checked on the next full read.
            require(text.startswith(seen.get(path,'')),'partial read replaced prior complete observations')
            continue
        require(text.startswith(seen.get(path,'')),'actual caller journal was replaced/truncated')
        rows=journal(text,value['run'],value['case'],role)
        require(path.endswith('-'+str(rows[0]['pid'])+'.jsonl') and
            all(r['uid']==value['roles'][role]['identity']['uid'] for r in rows), 'real PID/UID journal binding differs')
        seen[path]=text
    for path,text in seen.items():
        for role in parsed:
            if '/'+bundle(role)+'/' in path:
                parsed[role].extend(journal(text,value['run'],value['case'],role))
    return parsed


def click(entry, records, selector):
    indexes=entry['commands']
    if set(selector)=={'key'}:
        require(entry.get('key') is True and len(indexes)==1 and
            records[indexes[0]].get('script')=='uitest uiInput keyEvent Back','real provider cancellation key differs')
        return None
    if 'swipe_to' in selector:
        require(entry.get('gesture')=='swipe' and len(indexes)==3,'actual notification drawer swipe triple missing')
        dump,read,actual=[records[i] for i in indexes]
        match=re.fullmatch(r'test ! -e (\S+) && uitest dumpLayout -p (\S+)',dump.get('script',''))
        require(match is not None and match[1]==match[2] and read.get('script')=='cat '+match[1],
            'actual unfiltered drawer hierarchy required')
        tree=decode(read['body']);saved=decode(Path(entry['selection']['layout']).read_text())
        node=select_node(tree,selector['bundle'],identifier=selector['identifier'])
        destination=select_node(tree,**selector['swipe_to']);points=swipe_down_points(node,destination)
        require(saved==tree and node==entry['selection']['selected_node'] and
            destination==entry['selection']['destination_node'] and points==entry['selection']['swipe_points'] and
            actual.get('script')=='uitest uiInput swipe '+' '.join(map(str,points)),
            'drawer input must derive from actual statusbar/caller rectangles')
        return node
    clicked=entry.get('clicked',True)
    require(type(clicked) is bool and len(indexes)==(3 if clicked else 2) and
        indexes==list(range(indexes[0],indexes[0]+len(indexes))), 'actual UITest dump/read/input sequence required')
    dump,read=[records[i] for i in indexes[:2]]
    match=re.fullmatch(r'test ! -e (\S+) && uitest dumpLayout -p (\S+) -b (\S+)',dump.get('script',''))
    require(match is not None and match[1]==match[2] and match[3]==selector['bundle'] and
        read.get('script')=='cat '+match[1], 'real provider hierarchy command differs')
    tree=decode(read['body']); stored=Path(entry['selection']['layout'])
    require(stored.is_absolute() and stored.is_file() and not stored.is_symlink() and decode(stored.read_text())==tree,
            'saved UI tree is not the original actual guest hierarchy')
    node,matched=action_node(tree,selector)
    require(node==entry['selection']['selected_node'],'selected real UI node differs')
    if 'matched_node' in entry['selection']:
        require(matched==entry['selection']['matched_node'],'actual source-related action anchor differs')
    if 'set_checked' in selector:
        require(node['attributes'].get('checked') in ('true','false') and
            clicked is ((node['attributes']['checked']=='true') is not selector['set_checked']),
            'real Toggle must be clicked exactly when its actual state differs')
    else:require(clicked,'only an already-correct actual Toggle can omit input')
    if clicked:
        x,y,w,h=node['rect'];actual=records[indexes[-1]]
        require(actual.get('script')=='uitest uiInput click '+str(x+w//2)+' '+str(y+h//2),
                'input was not dispatched at the actual visible enabled node center')
    return node


def ui(value,records,rows):
    plan=None if value['case'] in ('blink','accessibility-input') else read_plan(value['ui_plan'],value['case'],value['run'])
    for entry in value['actions']:
        if 'provider_gone' in entry:
            require(entry['provider_gone'] is True and len(entry['commands'])==2,
                'provider disappearance must retain actual full dump/read')
            dump,read=[records[i] for i in entry['commands']]
            match=re.fullmatch(r'test ! -e (\S+) && uitest dumpLayout -p (\S+)',dump.get('script',''))
            require(match is not None and match[1]==match[2] and read.get('script')=='cat '+match[1],
                'failed/filtered hierarchy cannot prove actual modal disappearance')
            tree=decode(read['body']);require(tree and tree==decode(load_ref(entry['layout'])), 'actual full hierarchy bytes differ')
            try:
                select_node(tree,**plan['visible']);absent=False
            except NodeNotReady:absent=True
            require(absent is entry['absent'], 'actual provider disappearance result differs')
        elif 'source_dispatch' in entry:
            role=entry['role'];operation=entry['operation'];action=entry['action']
            require(role in rows and entry['commands'] and ((value['case']=='intelligent-scene' and
                entry['source_dispatch']=='dnd-onrequest-read' and action=='read') or
                (value['case']=='apn' and action in ('read','environment') and
                entry['source_dispatch']=='apn-onrequest-'+action)), 'fixed compiled public onRequest query required')
            argument=('read-current-dnd' if value['case']=='intelligent-scene' else
                'read-current-apn' if action=='read' else 'get-apn-environment')
            expected=shlex.join(['aa','start','-b',bundle(role),'-a','EntryAbility','--ps','run',value['run'],
                '--ps','kind',value['case'],'--ps','operation',operation,'--ps','argument',argument,
                '--pi','numberArgument','0'])
            require(len([records[i] for i in entry['commands'] if records[i].get('script')==expected])==1,
                'actual fixed AA Want did not dispatch this public query')
            requests=[r for r in rows[role] if r['operation']==operation and r['event']=='request']
            require(len(requests)==1 and decode(requests[0]['value'])['argument']==argument and
                any(r['operation']==operation and r['event']=='call.'+action for r in rows[role]),
                'real typed onRequest query/caller journal missing')
        elif 'system' in entry:
            require(entry['system'] in plan['actions'] and entry['selector'] in plan['actions'][entry['system']],
                    'system UI choice is not from the pinned actual packaged selector plan')
            click(entry,records,entry['selector'])
        elif 'visible' in entry:
            first=entry['commands'][0];dump,read=records[first:first+2]
            tree=decode(read['body']);saved=decode(load_ref(entry['layout']))
            require(saved==tree and select_node(tree,**plan['visible'])==entry['node'] and
                dump.get('script','').endswith(' -b '+plan['provider_bundle']),
                'real provider visibility/node is not independently replayable')
            # Use the read taken immediately after the UI observation, not the
            # completed final journal, to enforce deferred callback semantics.
            snapshots=[s for s in value['journal_reads'] if s['role']==entry['role'] and
                s['command'] in entry['commands']]
            require(snapshots,'provider visibility lacks simultaneous raw caller observations')
            require(value['case'] in ('intelligent-scene','network-policy','apn') or not any(r['operation']==entry['visible'] and r['event'].startswith('return.')
                for s in snapshots for r in journal(records[s['command']]['body'],value['run'],value['case'],entry['role'])),
                'with-result callback completed before user closed its actual provider')
        else:
            require(entry['role'] in value['roles'] and re.fullmatch('[a-z][a-z0-9.-]{0,63}',entry['operation']),
                    'actual caller control metadata differs')
            click(entry,records,{'bundle':bundle(entry['role']),'identifier':'apps578-'+entry['action']})


def verify_provider(value,records,original_image_guard, auxiliary=None):
    kind=auxiliary or value['case']
    require(auxiliary is None or auxiliary=='intelligent-scene-settings', 'fixed DND auxiliary provider only')
    require(callable(original_image_guard),'original source->compiled HAP->archive provider guard required')
    stored=value['provider_aux'][auxiliary] if auxiliary else value['provider_image'];proof=original_image_guard(kind,value['archive_sha256'])
    require(proof==stored['proof'] and set(proof)=={'archive_sha256','bundle','modules'} and
        proof['archive_sha256']==value['archive_sha256'] and proof['modules'],
        'provider pass summary cannot replace original actual package replay')
    observations=[records[i] for i in stored['commands']]
    require(observations[0].get('script')=='bm dump -n '+proof['bundle'], 'actual provider BMS observation missing')
    raw=observations[0]['body'];doc=decode(raw[raw.index('{'):]);app=doc['applicationInfo']
    require(app['bundleName']==proof['bundle'] and app['isSystemApp'] is True,'actual provider BMS identity differs')
    modules={m['moduleName']:m for m in doc['hapModuleInfos']}
    expected=('NotificationManangerUIExtensionAbility' if kind=='notification-settings' else
        'NotificationAccessGrantUIExtensionAbility' if kind=='notification-subscription' else
        'CertPickerUIExtAbility' if kind=='certificate-dialog' else
        'ByodAdminProvisionAbility' if kind=='enterprise' else 'IntelligentSceneUIExtSettingAbility' if kind=='intelligent-scene' else 'UIExtensionProvider' if kind=='network-policy' else 'GeneralCallSettingDialogAbility' if kind=='apn' else 'IntelligentSceneAppSelectExtensionAbility' if kind=='intelligent-scene-settings' else 'com.ohos.settings.MainAbility')
    targets=[a for a in doc.get('extensionAbilityInfo',[])+doc.get('abilityInfos',[])
        if a.get('name')==expected and a.get('moduleName') in proof['modules']]
    require(len(targets)==1 and ((kind in ('enterprise','accessibility-settings') and targets[0].get('visible') is True) or
        (targets[0].get('type')==500 and targets[0].get('visible') is True)),
        'actual BMS target extension/type/export does not match the fixed public API')
    if kind=='accessibility-settings':
        require(len([a for a in doc.get('extensionAbilityInfo',[]) if a.get('name')=='IgnoreRepeatClickExtService' and
            a.get('moduleName') in proof['modules'] and a.get('type')==0])==1,
            'actual original Settings service declaration missing')
    require(len(observations)==1+len(proof['modules']),'every used provider module must be hashed')
    for obs,(name,checksum) in zip(observations[1:],proof['modules'].items()):
        path=modules[name]['hapPath']
        require(obs.get('script')=='sha256sum '+shlex.quote(path) and obs['body'].strip()==checksum+'  '+path,
                'actual installed provider is not the exact same archive compiled module')


def notification(value,rows):
    kind=value['case'];role='normal' if kind=='notification-settings' else 'a';actual=rows[role]
    require(returned(actual,'baseline','read')==value['baseline'],'real initial provider state differs')
    returned(actual,'invalid','invalid',401)
    returned(actual,'two.duplicate','invoke',1600018)
    returned(actual,'two','invoke')
    if kind=='notification-subscription':
        returned(rows['normal'],'normal-denied','invoke',201)
        returned(rows['system-denied'],'denied','invoke',201)
    for action,wanted in (('enable',True),('disable',False)):
        result=returned(actual,action,'invoke');current=returned(actual,action+'.read','read')
        if kind=='notification-settings':
            require(isinstance(result,dict) and result==current['settings'] and current['enabled'] is wanted and
                ('notificationEnabled' not in result or result['notificationEnabled'] is wanted),
                    'real notification switch result and independent getter do not match actual choice')
        else:
            require(isinstance(result,dict) and result.get('userGrantEnabled') is wanted and current is wanted,
                    'real extension authorization/getter/callback do not match actual choice')
    result=returned(actual,'cancel','invoke');cancel=returned(actual,'cancel.read','read')
    require((result==cancel['settings'] and cancel['enabled'] is False) if kind=='notification-settings' else
        (isinstance(result,dict) and result.get('userGrantEnabled') is False and cancel is False),
        'cancel must return current real user state without silently enabling it')
    require(returned(actual,'restart.read','read')==cancel and returned(actual,'restored.read','read')==value['baseline'],
            'provider persistence/exit/restart/restore differ')
    before=[r for r in actual if r['operation']=='death' and r['event']=='call.invoke']
    after=[r for r in actual if r['operation']=='restart.read' and r['event']=='return.read']
    require(len(before)==len(after)==1 and before[0]['pid']!=after[0]['pid'] and
        not any(r['operation']=='death' and r['event']=='return.invoke' for r in actual),
        'caller death is not the actual pending UI generation boundary')
    required={'enable','disable','close','cancel'}
    require(required <= {r['system'] for r in value['actions'] if 'system' in r}, 'actual system user choices are incomplete')
    visible={r['visible'] for r in value['actions'] if 'visible' in r}
    require({'two','enable','disable','cancel','death','restore'} <= visible, 'one lifecycle window was not actually observed')
    disappeared=[r for r in value['actions'] if 'provider_gone' in r]
    require(len(disappeared)>=2 and all(r['absent'] is True for r in disappeared[-2:]),
        'two valid full UI hierarchies must prove actual pending modal teardown after caller death')


def deaths(value,records,rows):
    from guest_process_identity import identity_shell
    for boundary in value['boundaries'].get('death',[]):
        role=boundary['role'];pid,start,uid=boundary['identity']
        require(role in value['roles'] and uid==value['roles'][role]['identity']['uid'] and pid>1 and start>0,
            'death boundary must retain the actual owned PID generation')
        selected=[records[i] for i in boundary['commands']]
        require(len(selected)>=3 and selected[0].get('script')==identity_shell(bundle(role),all_uids=False) and
            selected[0]['body'].split()==list(map(str,(pid,start,uid))) and
            selected[1].get('script')=='aa force-stop '+bundle(role), 'actual scoped caller death commands differ')
        expected='if test -d /proc/'+str(pid)+'; then printf PRESENT; else printf ABSENT; fi'
        require(all(s.get('script')==expected and s['body'] in ('PRESENT','ABSENT') for s in selected[2:]) and
            selected[-1]['body']=='ABSENT', 'actual stopped PID did not disappear')
        require(any(r['pid']==pid and r['uid']==uid for r in rows[role]), 'stopped PID was not a real caller generation')


def certificate(value,rows):
    import hashlib
    actual=rows['a'];baseline=returned(actual,'baseline','read');current=value['certificate']
    require(baseline==value['baseline'] and type(baseline['supportsCA']) is bool and
        baseline['own'].get('credentialList')==[] and isinstance(baseline['trusted'].get('certList'),list),
        'actual fresh certificate inventory/support result differs')
    for role in ('normal','system-denied'):returned(rows[role],'denied','ca',201)
    returned(actual,'invalid','invalid',401);returned(actual,'empty','invoke',29700007)
    fixture=current['input'];descriptor=decode(load_ref(fixture['input']))
    require(fixture['schema']==descriptor['schema']=='actual-apps578-certificate-input/v1' and
        descriptor['run']==value['run'] and descriptor['boot_id']==fixture['boot_id']==value['boot_id'] and
        descriptor['archive_sha256']==fixture['archive_sha256']==value['archive_sha256'], 'actual nonce certificate inputs differ')
    producer=decode(load_ref(descriptor['producer']))
    require(producer['run']==value['run'] and producer['p12']==descriptor['p12'] and producer['der']==descriptor['der'] and
        producer['commands'], 'original actual nonce certificate producer/source refs required')
    for key in ('p12','der'):require(sha(descriptor[key]['path'])==descriptor[key]['sha256'],'actual producer certificate bytes changed')
    require(len(fixture['transfers'])==4,'all actual owned certificate input transfers required')
    for row in fixture['transfers']:
        key='p12' if row['suffix']=='.p12' else 'der'
        require(row['role'] in ('a','b') and row['suffix'] in ('.p12','.der') and row['source']==descriptor[key] and
            row['remote']=='/data/app/el2/100/base/'+bundle(row['role'])+'/files/apps578-'+value['run']+row['suffix'],
            'actual certificate fixture escaped current nonce caller')
    imported=returned(actual,'import','import');selected=returned(actual,'select','invoke')
    require(selected['keyUri']==selected['reference']['keyUri']==imported['uri'] and
        selected['alias']=='apps_'+value['run'][:16] and selected['certNum']==selected['keyNum']==1 and selected['bytes'] and
        hashlib.sha256(bytes(selected['der'])).hexdigest()==descriptor['der']['sha256'],
        'actual UI-selected credential URI/public X509 consumer did not match current nonce DER')
    require(returned(rows['b'],'peer.empty','read')['own'].get('credentialList')==[], 'private credential leaked across actual UIDs')
    returned(rows['b'],'peer.authorize','invoke',29700007);returned(actual,'cancel','invoke',29700002)
    after=returned(actual,'restarted.read','read')
    require(any(c['keyUri']==imported['uri'] and c['alias']==selected['alias'] for c in after['own']['credentialList']),
        'actual certificate did not persist through caller recreation')
    if baseline['supportsCA']:
        returned(actual,'ca.cancel','install-ca',29700002)
        require(returned(actual,'ca.after-cancel','read')['trusted']==baseline['trusted'],'cancel mutated actual trusted certificate inventory')
        uri=returned(actual,'ca.install','install-ca');consumed=returned(actual,'ca.consume','read-ca')
        require(uri==consumed['uri'] and hashlib.sha256(bytes(consumed['bytes'])).hexdigest()==descriptor['der']['sha256'],
            'actual installed CA URI/consumer DER bytes differ')
        returned(actual,'ca.remove','remove-ca')
    else:returned(actual,'ca.unsupported','install-ca',29700004)
    returned(actual,'remove','remove')
    require(returned(actual,'restored.read','read')==baseline and current['private_installed'] is False and
        current['ca_installed'] is False, 'actual owned certificate inventory was not restored')
    choices={r['system'] for r in value['actions'] if 'system' in r}
    require({'select-own','authorize','cancel'}<=choices and (not baseline['supportsCA'] or
        {'confirm-install','confirm-uninstall'}<=choices), 'actual selection/cancel/install/uninstall UI actions missing')
    gone=[r for r in value['actions'] if 'provider_gone' in r]
    require(len(gone)>=2 and all(r['absent'] is True for r in gone[-2:]), 'actual dialog did not disappear on pending caller death')


def observers(value,records):
    latest={}
    for row in value['observer_reads']:
        role,path,index=row['role'],row['path'],row['command']
        require(role in ('a','b') and role in value['roles'] and
            re.fullmatch(re.escape('/data/app/el2/100/base/'+bundle(role)+'/files/apps578-observer-'+value['run']+'-')+
                r'[1-9][0-9]*\.jsonl',path) and records[index].get('script')=='test ! -L '+path+' && cat '+path,
            'actual extension callback journal ownership differs')
        text=records[index]['body'];require(len(text.encode())<=2**20 and text.startswith(latest.get(path,'')), 'actual extension journal replaced/excessive')
        if text and not text.endswith('\n'):continue
        latest[path]=text
    result={r:[] for r in value['roles']}
    for path,text in latest.items():
        previous=-1
        for line in text.splitlines():
            row=decode(line);role=row['role']
            require(set(row)=={'run','kind','role','bundle','uid','pid','activeMs','event','value'} and
                row['run']==value['run'] and row['kind']==value['case'] and role in ('a','b') and
                row['bundle']==bundle(role) and row['uid']==value['roles'][role]['identity']['uid'] and
                path.endswith('-'+str(row['pid'])+'.jsonl') and row['activeMs']>=previous and isinstance(row['event'],str),
                'real extension UID/PID/nonce/callback frame differs')
            decode(row['value']);previous=row['activeMs'];result[role].append(row)
    return result


def enterprise(value,rows,callback_rows):
    a=rows['a'];b=rows['b']
    require(returned(a,'baseline','read') is False and returned(b,'peer.baseline','read') is False,'initial real admin state differs')
    for action in ('read','invoke','super'):returned(rows['normal'],'normal.'+action,action,202)
    for action in ('invoke','super'):returned(rows['system-denied'],'denied.'+action,action,201)
    returned(a,'invalid','invalid',9200003);returned(a,'enable','invoke');returned(a,'disable','disable')
    require(returned(a,'enabled.read','read') is returned(a,'restart.read','read') is True and
        returned(b,'peer.read','read') is False and returned(a,'disabled.read','read') is False and
        value['admin_owned'] is False, 'normal admin activation/peer isolation/persistence/deactivation differs')
    events=[r['event'] for r in callback_rows['a']]
    require('admin.enabled.callback' in events and 'admin.disabled.callback' in events and
        events.index('admin.enabled.callback')<events.index('admin.disabled.callback'),
        'actual independent EnterpriseAdmin extension enable/disable callbacks missing')
    for operation in ('byod.cancel','byod.agree'):
        returned(a,operation,'byod');require(returned(a,operation+'.read','read') is False,'unsupported/cancelled BYOD changed real admin state')
    require(value['product_boundaries']==['fixed-public-BYOD-provider-has-no-activation-implementation'] and
        {'byod-cancel','byod-agree','byod-unsupported-confirm'} <= {x['system'] for x in value['actions'] if 'system' in x},
        'fixed provider unsupported/cancel UI branch must remain explicit, not a full enterprise pass')


def blink(value,rows,records):
    from verify_screen_blink_results import verify_frames
    identities=[value['roles'][r]['identity'] for r in ('a','b')]
    require(len({v['uid'] for v in identities})==2 and len({v['token_id'] for v in identities})==2,
            'competing blink callers do not have distinct real BMS tokens')
    a,b=rows['a'],rows['b']
    require(returned(a,'baseline','read')=='0' and returned(a,'enable','enable')=={'written':True,'read':'1'},
            'actual blink original/enabled settings differ')
    for role,code in (('normal',202),('system-denied',201)):
        for action in ('start','stop','invalid-mode','invalid-scenario'):
            returned(rows[role],role+'.'+action,action,code)
    for op,action,wanted in [('start','start',0),('already','start',1),('wrong-stop','wrong-stop',2),
        ('stop','stop',0),('stop.again','stop',0),('restart.stop','stop',0),('restart.start','start',0),
        ('disabled.start','start',5)]:
        require(returned(a,op,action)==wanted,'actual blink owner/scenario/lifecycle result differs')
    returned(a,'invalid-mode','invalid-mode',401);returned(a,'invalid-scenario','invalid-scenario',401)
    for action in ('start','stop','wrong-stop'):
        require(returned(b,'foreign.'+action,action)==2,'real foreign token stopped/acquired the active owner')
    require(returned(b,'takeover','start')==0 and returned(a,'disable','disable')=={'written':True,'read':'0'},
            'real second token takeover or original setting restoration failed')
    require({p['name'] for p in value['pixels']} >= {'a-continuous','foreign-start','foreign-stop','foreign-wrong-stop',
        'wrong-scenario-retains','a-stopped','nonowner-death-retains','new-process-off','disabled-clears'},
        'one actual framebuffer ownership/lifecycle case is missing')
    for phase in value['pixels']:
        tree=decode(load_ref(phase['layout']))
        require(phase['role'] in ('a','b') and phase['rect']==select_node(tree,bundle(phase['role']),
            identifier='blink-pixel-surface')['rect'], 'pixel ROI is not the actual visible caller accessibility node')
        verify_frames(phase['frames'],phase['rect'],phase['mode'])
        for frame in phase['frames']:
            transfers=[r for r in records if r.get('transfer',[None,None])[1]==frame['path']]
            require(len(transfers)==1 and sha(frame['path'])==frame['sha256'],
                    'actual framebuffer bytes have no unique original guest transfer')


def intelligent(value,rows):
    for role in ('normal','system-denied'):returned(rows[role],'denied','read',201)
    for role in ('a','b'):
        require(returned(rows[role],'baseline','read')==value['baseline'][role], 'actual initial DND state differs')
        for state in ('allowed','denied','disabled'):
            actual=returned(rows[role],state+'.read','read')
            require(isinstance(actual,list) and len(actual)==2 and all(type(x) is bool for x in actual),
                    'actual DND API boolean shapes differ')
            if state=='disabled':require(actual[0] is False,'global DND disable was not reflected by independent queries')
            else:require(actual==[True,state=='allowed' and role=='a'],'actual per-caller DND UI/grant result differs')
        require(returned(rows[role],'restored.read','read')==value['baseline'][role], 'DND state restoration differs')
    before=[r for r in rows['a'] if r['operation']=='disabled.read' and r['event']=='return.read']
    after=[r for r in rows['a'] if r['operation']=='restart.read' and r['event']=='return.read']
    require(len(before)==len(after)==1 and before[0]['pid']!=after[0]['pid'] and
        decode(before[0]['value'])==decode(after[0]['value']), 'DND restart did not preserve the real getter state')
    require({'dnd-enable','dnd-disable','allow-caller','deny-caller','deny-peer','restore'} <=
        {r['system'] for r in value['actions'] if 'system' in r}, 'actual DND UI transitions incomplete')


def transferred_frames(value,records):
    def walk(node):
        if isinstance(node,list):
            for item in node:walk(item)
        elif isinstance(node,dict):
            if isinstance(node.get('path'),str) and node['path'].endswith('.png') and 'sha256' in node:
                transfers=[r for r in records if r.get('transfer',[None,None])[1]==node['path']]
                require(len(transfers)==1 and sha(node['path'])==node['sha256'],
                    'boundary framebuffer is not unique actual guest transfer bytes')
            for item in node.values():walk(item)
    walk(value.get('before_callers'));walk(value['boundaries']);walk(value['pixels']);walk(value.get('shortcut'));walk(value.get('input'))


def extra(value,rows,original_qmp_replay):
    require(callable(original_qmp_replay),'actual original held QMP socket raw replay required')
    for boundary in value['boundaries']['business']:
        require(boundary['schema']=='actual-apps578-input/v1' and boundary['archive_sha256']==value['archive_sha256'] and
            boundary['boot_id']==value['boot_id'], 'actual physical input belongs to another package/boot')
        original_qmp_replay(boundary,value['archive_sha256'],value['boot_id'])
        for row in boundary['qmp']:
            require(row['boot_id']==value['boot_id'], 'physical input QMP belongs to another boot')
            qmp_wire(row)
    if value['case']=='shortkey':
        from apps_ui578_extra import SHORTCUT
        require(value['shortcut']['config'].get('Shortkeys')==[SHORTCUT], 'actual packaged shortcut differs')
        returned(rows['normal'],'normal.delay','invoke',202)
        returned(rows['a'],'invalid.key','invalid',401);returned(rows['a'],'invalid.delay','invoke',401)
        for operation in ('duration.long','duration.short','restart.delay','duration.restore','cleanup.duration'):
            returned(rows['a'],operation,'invoke')
        expected=[('early-release','meta_l',1000,'home'),('wrong-modifier','ctrl',1800,'home'),
            ('long-accepted','meta_l',1800,'settings'),('changed-delay','meta_l',800,'settings'),
            ('restarted-caller','meta_l',800,'settings'),('restored-early','meta_l',100,'home'),
            ('restored-valid','meta_l',800,'settings')]
        require(len(value['shortcut']['cycles'])==len(expected),'all actual duration/permission/restart boundaries required')
        for row,(name,modifier,duration,screen) in zip(value['shortcut']['cycles'],expected):
            require(row['name']==name and row['expected']==screen and row['qmp'] in value['boundaries']['business'] and
                row['qmp']['action']=='shortcut-key' and row['qmp']['parameters']=={'modifier':modifier,'hold_ms':duration},
                'actual shortcut boundary QMP sequence differs')
            sent=row['qmp']['qmp'][-1]
            require(sent['execute']=='send-key' and sent['arguments']=={'keys':[{'type':'qcode','data':modifier},
                {'type':'qcode','data':'i'}],'hold-time':duration}, 'actual physical shortcut keys differ')
            tree=decode(load_ref(row['layout']))
            if screen=='home':
                from run_application_home_probe import system_screen
                require(system_screen(tree)[0]=='home','short/wrong key activated a provider')
            else:
                from run_shortkey_keyboard_diagnostic import title_node
                from settings_navigation_ui import require_painted_title
                require_painted_title(row['frame']['path'],title_node(tree))
        before=[r for r in rows['a'] if r['operation']=='duration.short' and r['event']=='return.invoke']
        after=[r for r in rows['a'] if r['operation']=='restart.delay' and r['event']=='return.invoke']
        require(len(before)==len(after)==1 and before[0]['pid']!=after[0]['pid'],'actual privileged duration caller did not recreate')
    else:
        require(len(value['input']['steps'])==3,'actual normal/system/two-token physical inputs required')
        for step,role in zip(value['input']['steps'],('normal','a','b')):
            actual=rows[role];typed=value['run'][:8]
            require(step['role']==role and step['pointer'] in value['boundaries']['business'] and
                step['keyboard'] in value['boundaries']['business'], 'actual input producer records missing')
            require(returned(actual,role+'.empty','read')=={'text':'','count':0} and
                returned(actual,role+'.clicked','read')=={'text':'','count':1} and
                returned(actual,role+'.typed','read')==returned(actual,role+'.resume','read')=={'text':typed,'count':1} and
                returned(actual,role+'.recreated','read')=={'text':'','count':0}, 'actual input callback/background/recreate states differ')
            require(any(r['event']=='input.clicked' and decode(r['value'])==1 for r in actual) and
                any(r['event']=='input.changed' and decode(r['value'])==typed for r in actual), 'real independent public input callbacks missing')
            tree=decode(load_ref(step['typed_layout']))
            require(select_node(tree,bundle(role),identifier='apps578-input')==step['typed_node'] and
                step['typed_node']['attributes']['text']==typed, 'actual accessibility text consumer differs')


def cleanup(actual,value,records,rows):
    """Default fixed raw cleanup replay for the original root gate callback.

    Root additionally binds these root_io raw logs to its enclosing command
    receipts. No cleanup boolean or unbound expected stdout is accepted here.
    """
    from apps_ui578_bindings import absent
    require(set(actual)=={'schema','archive_sha256','boot_id','case','run','state','callers','records'} and
        actual['schema']=='actual-apps578-cleanup/v1' and actual['archive_sha256']==value['archive_sha256'] and
        actual['boot_id']==value['boot_id'] and actual['case']==value['case'] and actual['run']==value['run'],
        'raw cleanup must belong to the same actual archive/boot/case/nonce')
    raw=actual['records'];stdout=[]
    for entry in raw:
        text=load_ref(entry['stdout_ref'])
        not_installed=(entry['argv'][3]=='shell' and entry['argv'][4].startswith('aa force-stop ') and
            'error: failed to force stop process.' in text and 'Error Code:10104002' in text and
            'The application corresponding to the specified package name is not installed.' in text)
        boundary_probe=value.get('boundary_observations',{}).get('provider',{}).get('bms')
        own_probe=(value['status']=='fail' and boundary_probe is not None and
            all(entry.get(k)==boundary_probe.get(k) for k in ('argv','exit_code','stdout_ref','stderr_ref','log','boot_id','timed_out')))
        require(entry['boot_id']==value['boot_id'] and (entry['exit_code']==0 or not_installed or own_probe) and entry['timed_out'] is False,
            'actual fixed root cleanup command failed')
        stdout.append(text);load_ref(entry['stderr_ref']);load_ref(entry['log'])
    require(raw and raw[0]['argv'][:4]==raw[-1]['argv'][:4] and
        raw[0]['argv'][3]=='shell' and raw[-1]['argv'][3]=='shell' and
        stdout[0].strip()==stdout[-1].strip()==value['boot_id'],'root binding cleanup escaped actual boot')
    roles=[c['role'] for c in actual['callers']]
    require(set(roles)==set(value['roles']) and len(roles)==len(set(roles)), 'all exact current caller roles must be uninstalled')
    for item in actual['callers']:
        role=item['role'];index=item['uninstall'];argv=raw[index]['argv']
        require(argv==raw[0]['argv'][:3]+['uninstall',bundle(role)] and
            re.search(r'uninstall bundle successfully',stdout[index],re.I) and
            not re.search(r'\[Fail\]|failed',stdout[index],re.I), 'actual owned same-guest uninstall missing')
        for phase in ('before','after'):
            selected=item[phase]
            require(len(selected)>=5 and selected==list(range(selected[0],selected[-1]+1)), 'actual drain observation sequence differs')
            for pid_index,ams_index in ((selected[-4],selected[-3]),(selected[-2],selected[-1])):
                require('pidof '+bundle(role) in raw[pid_index]['argv'][4] and
                    raw[ams_index]['argv'][4].startswith('aa dump -a -u 100') and
                    absent(bundle(role),stdout[pid_index],stdout[ams_index]), 'two actual PID/AMS absent snapshots missing')
    if value['case']=='blink':
        require(actual['state'].get('blink')=='0' and returned(rows['a'],'cleanup.disable','disable')=={'written':True,'read':'0'},
            'actual original blink setting cleanup failed')
        if value['full_blink']:
            require(actual['state'].get('account')==returned(rows['account'],'acct.before','account-read')==
                returned(rows['account'],'acct.after','account-read'), 'actual nonce account cleanup changed original inventory')
    elif value['case'] in ('notification-settings','notification-subscription') and 'baseline' in value:
        role='normal' if value['case']=='notification-settings' else 'a'
        require(actual['state'].get('provider')==value['baseline']==returned(rows[role],'cleanup.read','read'),
            'real provider user state was not restored during finally')
    elif value['case']=='intelligent-scene' and 'baseline' in value:
        require(actual['state'].get('provider')==value['baseline']==
            {r:returned(rows[r],'cleanup.read','read') for r in ('a','b')}, 'real DND/caller user state was not restored')
    elif value['case']=='apn' and 'baseline' in value.get('apn',{}):
        require(actual['state'].get('apn')==value['apn']['baseline'], 'actual APN finally state differs')
    elif value['case']=='shortkey':
        require(actual['state'].get('duration')==500 and returned(rows['a'],'cleanup.duration','invoke') is None,
            'real shortcut duration finally restoration failed')
    elif value['case']=='certificate-dialog':
        require(actual['state'].get('certificate')==value['baseline']==returned(rows['a'],'cleanup.cert.read','read'),
            'actual certificate cleanup did not restore original current-user/private inventory')
    elif value['case']=='accessibility-settings':
        require(actual['state'].get('settings')==value['baseline']==returned(rows['a'],'cleanup.settings','settings-restore'),
            'actual Settings finally config/preferences restoration failed')
    elif value['case']=='enterprise':
        require(actual['state'].get('admin') is False and returned(rows['a'],'cleanup.admin.read','read') is False,
            'real normal administrator finally cleanup failed')


def settings(value,rows,records):
    from apps_ui578_extra import settings_lifecycle
    baseline=returned(rows['a'],'settings.baseline','settings-save')
    require(baseline==value['baseline'] and baseline['ignoreRepeat'] is False and baseline['animationOff'] is False and
        baseline['ignoreNotification'] in ('0','1') and baseline['animationNotification'] in ('0','1'),
        'actual inactive/restorable Settings baseline differs')
    returned(rows['normal'],'normal.config.denied','ignore-enable',202)
    returned(rows['system-denied'],'system-denied.config.denied','ignore-enable',201)
    returned(rows['a'],'settings.invalid','invalid',401)
    expected=[('ignore-disable','ignore-enable','disableIgnoreRepeatClick','ignoreRepeat','ignoreNotification',False),
        ('ignore-cancel','ignore-enable','disableNotificaiton','ignoreRepeat','ignoreNotification',True),
        ('animation-enable','animation-enable','reOpenTransitionAnimations','animationOff','animationNotification',False),
        ('animation-cancel','animation-enable','disableTransitionAnimationsNotification','animationOff','animationNotification',True)]
    actual=value['settings']
    require(actual['saved'] is True and actual['restored'] is True and len(actual['cycles'])==4,
        'all four real notification action/service lifecycles are mandatory')
    ids=[]
    for cycle,(name,enable,action,field,flag,wanted) in zip(actual['cycles'],expected):
        require((cycle['name'],cycle['service_action'],cycle['field'],cycle['flag'],cycle['expected'])==
            (name,action,field,flag,wanted) and len(cycle['observations'])==2,
            'actual fixed Settings action/consumer/idle sequence differs')
        state=returned(rows['a'],name+'.setup',enable)
        require(cycle['setup']==state and state[field] is True and state[flag]=='1' and
            returned(rows['a'],name+'.recreated','read')==state and returned(rows['a'],name+'.dismissed','read')==state,
            'actual NAPI setup/caller recreation/drawer dismissal semantics differ')
        require(records[cycle['before']].get('script')=='hilog -x','original pre-action hilog snapshot missing')
        before=records[cycle['before']]['body']
        seen=[]
        for observation in cycle['observations']:
            h=records[observation['after']];a=records[observation['ams']]
            require(h.get('script')=='hilog -x' and a.get('script')=='aa dump -a -u 100' and
                cycle['before']<observation['after']<observation['ams'], 'actual hilog/complete AMS order differs')
            lifecycle=settings_lifecycle(before,h['body'],a['body'],action)
            require(lifecycle==observation['lifecycle'],'original raw service action/decision/destruction differs')
            current=returned(rows['a'],observation['read'],'read')
            require(current[field] is wanted and current[flag]==('0' if wanted else '1'),
                'real independent configuration/preference consumer differs from actual user action')
            seen.append(lifecycle['record_id'])
        require(seen[0]==seen[1],'two idle observations refer to different real service generations')
        ids.append(seen[0])
    require(len(set(ids))==4,'idle actions did not recreate the actual Settings service records')
    choices={x['system'] for x in value['actions'] if 'system' in x}
    require({'drawer','back','expand-ignore','expand-animation','ignore-disable','ignore-cancel','animation-enable','animation-cancel'}<=choices,
        'actual source-backed Settings notification UI choices missing')
    require(returned(rows['a'],'settings.restore','settings-restore')==baseline,
        'real public Settings state restoration differs')
    require(not any('aa force-stop com.ohos.settings' in r.get('script','') for r in records),
        'force-stopping Settings cannot prove conditional idle completion')


def verify_observations(value, owner, *, archive_sha256, boot_id, hdc, target,
           original_image_guard, original_cleanup_replay,
           original_qmp_replay=None, original_blink_replay=None):
    require(value['schema']=='actual-apps578-runtime/v1' and value['case'] in IDS and
        value['archive_sha256']==archive_sha256==owner['archive_sha256'] and value['boot_id']==boot_id and
        owner['test_environment']['boot_id']==boot_id and value['target']==target and
        value['failures']==[] and value['status']=='observed' and value['cleanup_verified'] is True and
        value['first_artifact_behavior_gate_passed'] is False and value['formally_closed']==[],
        'actual same-new-package apps stage or cleanup failed')
    nonce(value['run'])
    records=commands(value,owner,hdc,target)
    for role,record in value['roles'].items():
        validate_prepared(record['prepared'],value['run'],value['case'],role,value['udid'])
        bms=records[record['bms_command']]
        require(bms.get('script')=='bm dump -n '+bundle(role) and
            bms_application_identity(bms['body'],bundle(role))==record['identity'],
            'installed UID/access token must be independently replayed from original BMS raw')
        doc=decode(bms['body'][bms['body'].index('{'):]);app=doc['applicationInfo']
        require(app.get('isSystemApp') is (role!='normal') and
            app.get('appPrivilegeLevel')==('normal' if role=='normal' else 'system_core') and
            sorted(doc.get('reqPermissions',[]))==permissions(value['case'],role),
            'actual installed role permission/APL differs from exact signer profile')
        installed=records[record['hash_command']]
        paths=[m['hapPath'] for m in doc['hapModuleInfos'] if m.get('hapPath')]
        require(len(paths)==1 and installed.get('script')=='sha256sum '+shlex.quote(paths[0]) and
            installed['body'].strip()==record['prepared']['signed']['sha256']+'  '+paths[0],
            'actual installed caller HAP bytes differ from this original signed SDK artifact')
    rows=role_rows(value,records);callback_rows=observers(value,records)
    ui(value,records,rows);deaths(value,records,rows);transferred_frames(value,records)
    if value['case']=='blink':
        blink(value,rows,records)
        require(value['full_blink'] is True and callable(original_blink_replay),
            'full blink requires original single/stop/death and new real account/display raw replay')
        original_blink_replay(archive_sha256,boot_id)
        from apps_ui578_boundaries import account,display
        from verify_screen_blink_results import verify_background_restored
        account(value['boundaries']['account'],value,rows)
        died=value['boundaries']['owner_death']
        require(set(died)=={'kind','baseline','frames','exit_observed'} and died['kind']=='actual-owner-death/v1',
                'actual new owner death frames/baseline missing')
        verify_background_restored(died['baseline'],died['frames'],died['exit_observed'])
        display(value['boundaries']['display'],value,rows,original_qmp_replay)
    elif value['case'] in ('notification-settings','notification-subscription'):
        verify_provider(value,records,original_image_guard);notification(value,rows)
    elif value['case']=='intelligent-scene':
        verify_provider(value,records,original_image_guard)
        verify_provider(value,records,original_image_guard,'intelligent-scene-settings')
        from apps_ui578_followup_verify import dnd
        dnd(value,rows,records,original_qmp_replay)
    elif value['case']=='network-policy':
        verify_provider(value,records,original_image_guard)
        from apps_ui578_followup_verify import network
        network(value,rows)
    elif value['case']=='apn':
        verify_provider(value,records,original_image_guard)
        from apps_ui578_apn_verify import verify_apn
        verify_apn(value,rows,records,read_plan(value['ui_plan'],'apn',value['run']),original_qmp_replay)
    elif value['case'] in ('shortkey','accessibility-input'):
        extra(value,rows,original_qmp_replay)
    elif value['case']=='certificate-dialog':
        verify_provider(value,records,original_image_guard);certificate(value,rows)
        from apps_ui578_ca_verify import verify_ca
        verify_ca(value,rows,records,read_plan(value['ui_plan'],value['case'],value['run']))
    elif value['case']=='accessibility-settings':
        verify_provider(value,records,original_image_guard);settings(value,rows,records)
    elif value['case']=='enterprise':
        verify_provider(value,records,original_image_guard);enterprise(value,rows,callback_rows)
    else:
        raise ValueError('full original-ID UI/backend oracle is not implemented for this supplied API slice')
    require(callable(original_cleanup_replay),'original owned cleanup raw replay is mandatory')
    original_cleanup_replay(value['cleanup'],value,records,rows)
    return {'schema':'apps578-independent-raw-result/v1','original_ids':list(IDS[value['case']]),
        'archive_sha256':archive_sha256,'boot_id':boot_id,'run':value['run'],
        'runtime_observations_verified':True,'whole_id_closure':False,'formally_closed':[],
        'first_artifact_behavior_gate_passed':False}



def verify(value, owner, *, archive_sha256, boot_id, hdc, target,
           original_image_guard, original_cleanup_replay,
           original_qmp_replay=None, original_blink_replay=None):
    result=verify_observations(value,owner,archive_sha256=archive_sha256,boot_id=boot_id,hdc=hdc,target=target,
        original_image_guard=original_image_guard,original_cleanup_replay=original_cleanup_replay,
        original_qmp_replay=original_qmp_replay,original_blink_replay=original_blink_replay)
    require(value['case'] not in SLICE_ONLY,'narrow API observations cannot close the broader original aggregate')
    # Preserve the existing verify contract: it still rejects all original
    # SLICE_ONLY IDs. Parent aggregate composition calls verify_observations.
    return {key:item for key,item in result.items() if key not in ('whole_id_closure','formally_closed')}


def verify_negative(value, owner, *, archive_sha256, boot_id, hdc, target, original_cleanup_replay, original_boundary_replay):
    """Retain an actual bounded failure; this never returns runtime pass/closure.

    The parent must independently bind every RootIO BMS Ref to its same-boot
    actual receipts. This can support a later bounded unsupported decision, but
    cannot authorize one from an input schema or a failed shell command.
    """
    require(value['schema']=='actual-apps578-runtime/v1' and value['case'] in
        ('notification-subscription','intelligent-scene','network-policy','apn') and
        value['archive_sha256']==archive_sha256==owner['archive_sha256'] and value['boot_id']==boot_id and
        owner['test_environment']['boot_id']==boot_id and value['target']==target and
        value['status']=='fail' and value['failures'] and value['formally_closed']==[] and
        value['first_artifact_behavior_gate_passed'] is False and value['cleanup_verified'] is True,
        'actual same-new-package failed provider boundary/cleanup required')
    nonce(value['run']);read_plan(value['ui_plan'],value['case'],value['run'])
    records=commands(value,owner,hdc,target);rows=role_rows(value,records)
    for role,record in value['roles'].items():
        validate_prepared(record['prepared'],value['run'],value['case'],role,value['udid'])
        bms=records[record['bms_command']]
        require(bms.get('script')=='bm dump -n '+bundle(role) and
            bms_application_identity(bms['body'],bundle(role))==record['identity'],
            'actual failed-boundary caller UID/token identity differs')
        doc=decode(bms['body'][bms['body'].index('{'):]);app=doc['applicationInfo']
        require(app.get('isSystemApp') is (role!='normal') and
            app.get('appPrivilegeLevel')==('normal' if role=='normal' else 'system_core') and
            sorted(doc.get('reqPermissions',[]))==permissions(value['case'],role),
            'actual negative caller role permission/APL differs')
        installed=records[record['hash_command']]
        paths=[m['hapPath'] for m in doc['hapModuleInfos'] if m.get('hapPath')]
        require(len(paths)==1 and installed.get('script')=='sha256sum '+shlex.quote(paths[0]) and
            installed['body'].strip()==record['prepared']['signed']['sha256']+'  '+paths[0],
            'actual negative caller is not this signed same-boot artifact')
    ui(value,records,rows);deaths(value,records,rows)
    observed=value['boundary_observations']
    for result in observed['api']:
        if 'error' in result:continue
        actual=[r for r in rows[result['role']] if r['operation']==result['operation'] and r['event']=='return.'+result['action']]
        require(len(actual)==1 and actual[0]['code']==result['code'] and decode(actual[0]['value'])==result['value'],
            'public API failure/void result is not the actual nonce-bound journal')
    require(value['cleanup']['state']=={},'missing-provider observation must not claim an unobserved state mutation/restore')
    proof=observed['provider']
    require(proof['archive_sha256']==archive_sha256 and proof['boot_id']==boot_id and callable(original_boundary_replay),
        'actual BMS probe must use the original same-boot RootIO receipts')
    original_boundary_replay(proof,archive_sha256,boot_id)
    result=provider_boundary_classification(value['case'],proof,observed['api'])
    require(result==observed['classification'] and callable(original_cleanup_replay),
        'actual raw negative classification or original cleanup replay differs')
    original_cleanup_replay(value['cleanup'],value,records,rows)
    return result
