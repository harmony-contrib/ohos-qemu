"""Raw semantic Photos/FormHost/provider restart reconstruction; no driver run."""
from pathlib import Path
import json
import re
import shlex

import apps_providers579_project as original_project
import photos579_project as restart_project
from apps_providers579_bindings import bms_json, objects
from apps_providers579_dialog import select as consent_select
from batch_media_verify_wallpaper_runtime import pixels
from photos579_raw import (need, checked, ref, document, loads, PROCESS_SCRIPT,
    processes, extensions, title_hash)
from photos579_receipts import Raw, value, success, denial, nonce_image
from photos579_identity import verify_callers, actor_command
from photos579_provider import inspect_hap, SIGNATURE, SIGNER_JAR_SHA

ID='behavior:photo-provider-not-activated-2in1'
PHASES=('prepare','hidden','unhidden','trashed','recovered','deleted','cleanup')


class Calls:
    def __init__(self, cuts, raw, *, run, archive, project):
        self.raw,self.run,self.archive,self.project=raw,run,archive,project
        self.cuts=[document(row) for row in cuts]
        self.requests,self.results,self.identities,self.prepared={},{},{},{}
        self.inputs=[];self.cleanup=[];self.network=[]
        flattened=[];qmp=[];previous=0
        for cut in self.cuts:
            need(cut['schema']=='actual-photos579-callback-cut/v1' and cut['boot_id']==raw.boot and
                cut['archive_sha256']==archive and cut['error'] is None and
                type(cut['before_monotonic_ns']) is int and cut['before_monotonic_ns']>=previous and
                cut['after_monotonic_ns']>=cut['before_monotonic_ns'],'actual finite callback failed/reordered')
            previous=cut['after_monotonic_ns'];flattened.extend(cut['commands']);qmp.extend(cut['qmp_records'])
            need(all(row in raw.normal for row in cut['commands']),'callback commands not actual original IO')
            semantic_commands=cut['commands']
            if 'collector_commands' in cut:
                semantic_commands=semantic_commands+[raw.collector_normal(row,raw.boot) for row in cut['collector_commands']]
            cut['semantic_commands']=semantic_commands
            case,name,args,result=cut['case'],cut['name'],cut['args'],cut['result']
            need(case in ('photos','photosform') and name in
                ('prepare_callers','install','start','input','collect','network','cleanup'),'fixed callback enum')
            if name=='prepare_callers':
                need(args==[case,run,list(project.ROLES[case])] and result['case']==case and
                    result['run_id']==run and result['boot_id']==raw.boot and case not in self.prepared,
                    'one original actual role preparation')
                self.prepared[case]=result
            elif name=='install':
                role=args[0];identity=document(result['identity'])
                need(identity['bundle']==project.bundle(case,role) and identity['user_id']==100 and
                    type(identity['uid']) is int and identity['uid']>0,'actual BMS/self UID role')
                bms,code=raw.body(identity['bms_raw'],'set -e\nbm dump -n '+identity['bundle']+' -u 100')
                need(code==0 and any(obj.get('bundleName')==identity['bundle'] and obj.get('uid')==identity['uid'] and
                    obj.get('fingerprint')==identity['fingerprint'] for obj in objects(bms_json(bms))),
                    'actual native BMS identity differs')
                rows=raw.combined(identity['self_query_raw'],cut['commands'])
                actual=[row for row in rows if row['event']=='self-identity' and row['request_id']=='identity_'+role]
                need(len(actual)==1 and actual[0]['uid']==identity['uid'] and
                    loads(actual[0]['value'])['fingerprint']==identity['fingerprint'] and
                    loads(actual[0]['value'])['bundle']==identity['bundle'],'actual self identity differs')
                need(identity['fingerprint']==self.prepared[case]['callers'][role]['identity']['fingerprint'],
                    'signed HAP and actual installed self certificate differ')
                self.identities[(case,role)]=identity
            elif name=='start':
                role,action,request=args
                need(request==document(result['request']) and request['run_id']==run and request['action']==action,
                    'actual request data differ')
                key=(case,role,request['request_id']);need(key not in self.requests,'request replay/reuse')
                argv=['aa','start','-b',project.bundle(case,role),'-a','EntryAbility','-m','entry','-u','100']
                for name in ('run_id','request_id','action'): argv+=['--ps',name,request[name]]
                argv+=['--ps','payload',json.dumps(request['payload'],separators=(',',':'))]
                raw.has('set -e\n'+shlex.join(argv),rows=cut['commands'])
                self.requests[key]=request
            elif name=='collect':
                role,request_id=args;key=(case,role,request_id)
                # Internal cleanup/install collections stay inside their outer
                # callback and are independently reconstructed below.
                need(key in self.requests,'collect has no actual public start')
                rows=raw.journal(result,run=run,role=role,bundle=project.bundle(case,role),case=case,
                    uid=self.identities[(case,role)]['uid'],request=request_id)
                emitted=[row for row in rows if row['event']=='request']
                need(len(emitted)==1,'one actual dispatched request')
                p=loads(emitted[0]['value']);request=self.requests[key]
                need(p['run_id']==run and p['request_id']==request_id and p['action']==request['action'] and
                    loads(p['payload'])==request['payload'],'Want and journal actual request differ')
                self.results[key]=(rows,result,cut)
            elif name=='input':
                self.ui(args[0],args[1],result,cut);self.inputs.append((case,args[0],args[1],result,cut))
            elif name=='network': self.network.append((case,args,result,cut))
            elif name=='cleanup':
                need(result.get('restored') is True and result['failures']==[],'actual Photos cleanup failed')
                self.cleanup.append((case,result,cut))
        need(flattened==raw.normal[:len(flattened)] and qmp==raw.qmp[:len(qmp)],
            'all cuts must preserve exact original chronological IO prefix')
        self.covered=len(flattened);self.qmp_covered=len(qmp)
        need(len({identity['uid'] for identity in self.identities.values()})==len(self.identities),
            'separate genuine sandbox UIDs required for all actual roles')

    def actions(self,case,role,action):
        selected=[]
        for key,request in self.requests.items():
            if key[:2]==(case,role) and request['action']==action and key in self.results:
                selected.append(self.results[key])
        return selected

    def only(self,case,role,action,index=0):
        found=self.actions(case,role,action)
        need(len(found)>index,'actual action missing: '+case+'/'+role+'/'+action)
        return found[index]

    def ui(self,action,payload,result,cut):
        raw=self.raw
        commands=cut['semantic_commands']
        if action=='photos-consent':
            layout=raw.layout(result['layout']);node,contract=consent_select(layout,self.run,payload['kind'],'photos')
            need(node==result['selected_node'] and contract==result['contract'],'actual source-defined consent target')
            raw.click(node,result['layout'],commands)
        elif action in ('photos-select-fixture','photoform-select-photo'):
            raw.click(result['selected_node'],result['layout'],commands)
            if action=='photos-select-fixture':
                raw.frame(result['screenshot']);raw.layout(result['after_layout'])
                for completion in result['complete']:
                    layout_ref=ref(completion['layout'])
                    raw.click(completion['selected_node'],layout_ref,commands)
        elif action=='snapshot':
            raw.layout(result['observation']['layout']);raw.frame(result['observation']['frame'])
        elif action=='photoform-pixels':
            need(result['expected']==payload['expected'] and len(result['samples'])>=2,'actual repeated form frames')
            for sample in result['samples']:
                raw.node(sample['selected_node'],sample['layout']);raw.frame(sample['frame'])
        elif action=='recent-nonce-pixels':
            need(result['binary']==payload['binary'] and result['nonce']==payload['nonce'] and len(result['samples'])==2,
                'exact newly returned actual nonce renderer input')
            nonce_image(payload['binary'],payload['nonce'])
            for sample in result['samples']:
                raw.node(sample['selected_node'],sample['layout']);raw.node(sample['host_node'],sample['layout'])
                raw.frame(sample['frame'])
                need(sample['host_node']['attributes']['id']=='apps579-recent' and
                    sample['host_node']['bundle']==self.project.bundle('photos','normal'), 'actual Recent component host')
                hx,hy,hw,hh=sample['host_node']['rect'];x,y,w,h=sample['selected_node']['rect']
                need(x>=hx and y>=hy and x+w<=hx+hw and y+h<=hy+hh,'actual nonce image outside Recent host')
                need(pixels(checked(sample['frame']),checked(payload['binary']),sample['selected_node']['rect'],minimum_fraction=.85)==sample['metrics'],
                    'actual Recent image failed independent new nonce decode')
        elif action=='back': raw.has('uitest uiInput keyEvent Back',rows=commands)
        elif action=='force-stop':
            raw.has('set -e\n'+shlex.join(['aa','force-stop',self.project.bundle(cut['case'],payload['role']),'-u','100']),
                rows=commands)
        elif action=='media-permission':
            if 'permission_journal' in result:
                rows=raw.combined(result['permission_journal'],cut['commands'])
                need(any(row['event']=='permission-result' and loads(row['value'])['authResults']==[0,0] for row in rows),
                    'actual permission result absent')
            else:
                need(len(result['selected'])==1,'one actual caller-named permission approval')
                selected=result['selected'][0]
                raw.click(selected['selected_node'],ref(selected['layout']),commands)
                tree=raw.layout(result['title_layout'])
                label='Apps579 photos janitor '+self.run[:8]
                from guest_ui import select_node, NodeNotReady
                matched=[]
                for title in ('允许“'+label+'”访问图片和视频？','Allow '+label+' to access images and videos on your device?'):
                    try: matched.append(select_node(tree,'com.ohos.permissionmanager',text=title))
                    except NodeNotReady: pass
                need(len(matched)==1,'caller-specific actual permission dialog title')

    def cleanup_calls(self):
        need({case for case,_,_ in self.cleanup}==set(self.prepared),'all prepared callback sets actually cleaned')
        for case,_,cut in self.cleanup:
            for role in self.project.ROLES[case]:
                program='set -e\nbm uninstall -n '+self.project.bundle(case,role)+' -u 100'
                rows=self.raw.has(program,rows=cut['commands'])
                need(any('uninstall bundle successfully.' in row['body'] for row in rows),'actual owned uninstall acknowledgement')
            self.raw.has('set -e\ncat /proc/sys/kernel/random/boot_id',rows=cut['commands'])


def verify_restart(stage,*,archive,boot,actor,output):
    report=document(stage['restart']);env=document(boot)['test_environment']
    need(report['schema']=='actual-photos579-provider-restart/v1' and not report['failures'] and
        report['boot_id']==env['boot_id'] and report['udid']==env['udid'] and
        report['archive_sha256']==archive['sha256'] and env['device_type']=='2in1','actual true2in1 restart failed/foreign')
    io=document(stage['original_io']);need(io['closed'] is True and io['boot_id']==report['boot_id'] and
        io['archive_sha256']==archive['sha256'] and report['target']==env['target'] and
        all(row['reaped'] is True for row in io['held_transports'].values()),'original restart IO not closed')
    raw=Raw(io['commands'],boot=report['boot_id'],target=report['target'],qmp=io['qmp'])
    calls=Calls(report['callback_cuts'],raw,run=report['run'],archive=archive['sha256'],project=restart_project)
    close=document(stage['close_span']);need(document(close['cleanup'])['cleanup_complete'] is True and
        document(close['cleanup'])['errors']==[] and raw.normal[calls.covered:]==close['commands'] and
        raw.qmp[calls.qmp_covered:]==close['qmp_records'],'actual final IO close suffix differs')
    callers=verify_callers(calls.prepared['photos'],raw=raw,case='photos',project=restart_project,
        sdk=calls.prepared['photos']['sdk'],udid=report['udid'],actor=actor,output=output/'restart-identities')
    calls.cleanup_calls()
    permission,_,_=calls.only('photos','janitor','permissions')
    need(value(permission,'permission-result')['authResults']==[0,0],'actual janitor permissions not granted')
    creations=calls.actions('photos','normal','create');need(len(creations)==2,'two actual public nonce creations')
    assets=[]
    for name,(rows,collected,cut) in zip(('before','after'),creations):
        success(rows);fresh=value(rows,'fresh-nonce');created=value(rows,'asset-created')
        nonce=report['nonces'][name]
        need(fresh=={'nonce':nonce,'title':'photos579-'+report['run']+'-'+nonce} and created['nonce']==nonce and
            created['title']==fresh['title'] and value(rows,'creation-dialog-result')==[created['uri']] and
            len(collected['binaries'])==1,'actual consented fresh asset differs')
        nonce_image(collected['binaries'][0]['raw'],nonce)
        info,_,_=calls.only('photos','normal','recent-info',len(assets));success(info)
        recent=value(info,'recent-info')
        need(recent['defaults']==recent['explicit'] and recent['defaults']['identifier']==title_hash(created['title']) and
            recent['defaults']['dateTaken']>0,'public info not linked to newly rendered native asset')
        album,_,_=calls.only('photos','normal','default-album',len(assets));success(album)
        need(type(value(album,'default-album')) is str and value(album,'default-album'),'actual localized default album')
        component,_,_=calls.only('photos','normal','recent-component',len(assets));success(component)
        need(any(row['event']=='recent-component-exists' and loads(row['value']) is True for row in component),
            'actual Recent component positive callback missing')
        assets.append(dict(uri=created['uri'],nonce=nonce,jpeg=collected['binaries'][0]['raw'],created=cut))
    native={};provider_payloads={}
    for name in ('before','stopped','after'):
        snap=report['snapshots'][name]
        text,code=raw.body(snap['processes'],PROCESS_SCRIPT);need(code==0,'actual process scan failed')
        native[name]=processes(text,report['boot_id'])
        need(native[name]==snap['observed_processes'],'actual process scan summary differs')
        compatibility,code=raw.body(snap['app_types'],'param get const.bms.supportAppTypes')
        need(code==0 and {'2in1','phone','default','tablet'}<=set(compatibility.strip().split(',')),
            'actual supported-app-types compatibility missing')
        bms,code=raw.body(snap['bms'],'bm dump -n com.ohos.photos -u 100')
        provider_uids={row['uid'] for row in objects(bms_json(bms)) if row.get('bundleName')=='com.ohos.photos' and
            type(row.get('uid')) is int}
        need(code==0 and len(provider_uids)==1 and all(row['uid'] in provider_uids for row in native[name]),
            'actual provider BMS and kernel UID differ')
        declared={row['hapPath'] for row in objects(bms_json(bms)) if type(row.get('hapPath')) is str and row['hapPath'].endswith('.hap')}
        need(declared=={row['remote'] for row in snap['packages']},'all actual installed provider HAP paths retained')
        selected=[]
        for package in snap['packages']:
            raw.transported(package['raw'],package['remote'])
            import zipfile
            with zipfile.ZipFile(checked(package['raw'])) as hap:
                module=loads(hap.read('module.json').decode())
            need(module['app']['bundleName']=='com.ohos.photos','BMS provider readback has foreign bundle')
            if module['module']['name']=='phone_photos': selected.append((package,inspect_hap(checked(package['raw']))))
        need(len(selected)==1,'one actual installed full phone_photos compatible provider')
        provider_payloads[name]=selected[0]
    need(len({item[0]['raw']['sha256'] for item in provider_payloads.values()})==1,
        'provider restart cannot silently replace its installed signed implementation')
    signature_output=output/'provider-signature';signature_output.mkdir(exist_ok=False)
    command,signature_commands=actor_command(actor,signature_output)
    sign=[row for row in calls.prepared['photos']['callers']['normal']['sign_commands'] if 'sign-app' in row['argv']]
    need(len(sign)==1,'actual signer tool provenance')
    jar=Path(sign[0]['argv'][sign[0]['argv'].index('-jar')+1])
    need(ref(jar)['sha256']==SIGNER_JAR_SHA,'existing source provider verifier fixed signer tool')
    chain=signature_output/'provider-chain.cer';profile=signature_output/'provider-profile.p7b'
    transcript=command(['java','-jar',str(jar),'verify-app','-inFile',str(checked(provider_payloads['after'][0]['raw'])),
        '-outCertChain',str(chain),'-outProfile',str(profile)],'provider-verify-app')
    from batch_apps_contact_picker_coordinator import application_leaf
    application_leaf(transcript)
    need(all(marker in transcript for marker in ('verify codesign success','Digest verify result: true',
        'verify permission sign success','verify-app success')) and checked(ref(chain)).stat().st_size>0 and
        checked(ref(profile)).stat().st_size>0,'actual full installed provider signature/digest/profile verification')
    need(all(any(row.get('bundleName')=='com.ohos.photos' and row.get('fingerprint')==SIGNATURE for row in
        objects(bms_json(raw.body(report['snapshots'][name]['bms'])[0]))) for name in ('before','stopped','after')),
        'actual provider BMS certificate differs from actual signed HAP/root OS leaf')
    stops=[cut for case,args,result,cut in calls.network if args==['provider-stop',{}]]
    need(len(stops)==1,'exactly one actual provider stop')
    raw.has('aa force-stop com.ohos.photos -u 100',rows=stops[0]['commands'])
    old={(row['pid'],row['starttime']) for row in native['before']}
    need(old and native['after'] and not old & {(row['pid'],row['starttime']) for row in native['stopped']+native['after']},
        'provider old PID birth survived or new native instance absent')
    need(all(row['uid'] not in {i['uid'] for i in calls.identities.values()} for row in native['before']+native['after']),
        'caller identity substituted for Photos provider')
    extension_ids=[]
    for name in ('before','after'):
        text,code=raw.body(report['snapshots'][name]['ams'],'aa dump -a -u 100');need(code==0,'actual AMS query failed')
        extension_ids.append(extensions(text,restart_project.bundle('photos','normal')))
    need(extension_ids[0]!=extension_ids[1] and assets[0]['uri']!=assets[1]['uri'] and
        assets[0]['nonce']!=assets[1]['nonce'] and assets[0]['jpeg']['sha256']!=assets[1]['jpeg']['sha256'] and
        assets[0]['created']['after_monotonic_ns']<stops[0]['before_monotonic_ns']<
        stops[0]['after_monotonic_ns']<assets[1]['created']['before_monotonic_ns'],
        'actual stop must separate old/new public content and native extension generations')
    rendered=[(payload,result,cut) for case,action,payload,result,cut in calls.inputs if action=='recent-nonce-pixels']
    need(len(rendered)==2 and all(payload=={'binary':asset['jpeg'],'nonce':asset['nonce']} for (payload,_,_),asset in zip(rendered,assets)) and
        rendered[0][2]['after_monotonic_ns']<stops[0]['before_monotonic_ns'] and
        stops[0]['after_monotonic_ns']<rendered[1][2]['before_monotonic_ns'],
        'actual before/after independent Recent render observations absent/reordered')
    denied,_,_=calls.only('photos','foreign','read-denied');denial(denied)
    cancelled,_,_=calls.only('photos','normal','cancel-select');success(cancelled)
    need(value(cancelled,'select-result')['photoUris']==[],'real cancel returned Photo URI')
    exited,_,_=calls.only('photos','normal','exit');reentered,_,_=calls.only('photos','normal','identity')
    need(len([r for r in exited if r['event']=='exit-request'])==1 and
        not any(r['event'] in ('error','request-error','page-error') for r in exited),
        'actual ordinary terminateSelf request absent/failed')
    success(reentered);value(reentered,'self-identity')
    last_info,_,_=calls.only('photos','normal','recent-info',2);success(last_info)
    need(value(last_info,'recent-info')['defaults']['identifier']==title_hash(
        'photos579-'+report['run']+'-'+report['nonces']['after']), 'public info not recovered after UIAbility exit')
    # Cleanup's internally dispatched janitor requests remain in the final
    # actual per-process files pulled by that very cleanup callback.
    cleaned=set()
    for _,_,cut in calls.cleanup:
        latest={}
        for command in cut['commands']:
            argv=command['argv']
            if len(argv)==7 and argv[1:5]==['-t',raw.target,'file','recv'] and argv[5].endswith('.jsonl'):
                latest[argv[5]]=Path(argv[6]).read_text()
        values=[loads(line) for text in latest.values() for line in text.splitlines() if line]
        for asset in assets:
            for request in {row['request_id'] for row in values if row['action']=='cleanup-owned'}:
                selected=[row for row in values if row['request_id']==request]
                if any(row['event']=='cleanup-active-after' and loads(row['value'])=={'uri':asset['uri'],'count':0} for row in selected):
                    success(selected)
                    need(value(selected,'cleanup-trash-after')=={'uri':asset['uri'],'count':0},'actual TRASH cleanup absent')
                    cleaned.add(asset['uri'])
    need(cleaned=={asset['uri'] for asset in assets},'both fresh assets need actual active/TRASH public absence')
    return dict(boot_id=report['boot_id'],identities=callers,assets=assets,
        native_processes=native,extension_ids=extension_ids,provider_payloads=provider_payloads,
        provider_signature_commands=signature_commands,cleanup_complete=True)


def verify_knowledge(knowledge_ref,*,archive,boot,actor,output):
    from batch_media_knowledge_suite import verify_evidence
    knowledge=document(knowledge_ref);env=document(boot)['test_environment']
    own_boot=knowledge['boot'];own_environment=document(own_boot)['test_environment']
    need(document(own_boot)['archive_sha256']==archive['sha256'] and all(own_environment[key]==env[key] for key in
        ('boot_id','udid','target','device_type','guest_arch')), 'original22 actual owning boot snapshot differs from main')
    original=verify_evidence(checked(knowledge_ref),checked(archive),checked(own_boot))
    need(env['device_type']=='2in1' and knowledge.get('apps579_errors',[])==[] and
        knowledge.get('apps579_form_errors',[])==[] and knowledge.get('apps579_cleanup_errors',[])==[],
        'actual original Photos/FormHost business failed')
    retained=knowledge['photos579_raw_retention'];need(retained,'original Collector actual retention absent')
    rawdoc=document(retained[-1]);need(rawdoc['phase']=='final_cleanup' and rawdoc['boot_id']==env['boot_id'] and
        rawdoc['udid']==env['udid'] and rawdoc['target']==env['target'] and rawdoc['archive_sha256']==archive['sha256'] and
        rawdoc['original_commands']==knowledge['commands'][:len(rawdoc['original_commands'])],
        'actual final Collector retained command prefix')
    for row in rawdoc['commands']:
        need(any(original_row['argv']==row['argv'] and original_row['raw']==row['log'] and
            original_row['exit_code']==row.get('transport_exit_code',row['exit_code']) and
            original_row['timed_out']==row['timed_out'] for original_row in knowledge['commands']),
            'additional actual IO lacks original Collector transport receipt')
    raw=Raw(rawdoc['commands'],boot=rawdoc['boot_id'],target=rawdoc['target'],merged=True,qmp=rawdoc['qmp_records'])
    actual_cuts=[document(row) for row in rawdoc['callback_cuts']]
    ui_commands=[]
    for cut in actual_cuts:
        need('collector_commands' in cut,'actual original GuestUi command cuts absent')
        for command in cut['collector_commands']:
            need(command in knowledge['commands'],'GuestUi cut lacks original full Collector command')
            ui_commands.append(command)
    indices=[knowledge['commands'].index(row) for row in ui_commands]
    need(indices==sorted(set(indices)),'actual callback Collector commands overlap or reverse')
    raw.add_collector_ui(ui_commands)
    calls=Calls(rawdoc['callback_cuts'],raw,run=rawdoc['run_id'],archive=archive['sha256'],project=original_project)
    need(calls.covered==len(raw.normal) and calls.qmp_covered==len(raw.qmp),'uncaptured actual Collector additional IO')
    artifacts=document(knowledge['apps579_artifacts']);production=artifacts['photos579_production']
    production_doc=document(production['receipts'])
    production_raw=Raw(production_doc['commands'],boot=raw.boot,target=raw.target,qmp=production_doc['qmp_records'])
    identities={}
    for case,key in (('photos','callers'),('photosform','form_callers')):
        need(case in calls.prepared and calls.prepared[case]['callers']==artifacts[key],
            'actual original signed caller manifest differs')
        identities[case]=verify_callers(calls.prepared[case],raw=production_raw,case=case,project=original_project,
            sdk=production['sdk'],udid=rawdoc['udid'],actor=actor,output=output/('knowledge-identities-'+case))
    calls.cleanup_calls()
    for name in ('apps579_photo_phases','apps579_form_phases'):
        need(tuple(row['phase'] for row in knowledge[name])==PHASES,'all seven actual original curator phases required')
        for row in knowledge[name]:
            observation=document(row['observations'])
            need(not observation.get('failures') and observation['closed_requirement_ids']==[] and
                observation['runtime_pass'] is False,'old actual slice failed or self-closed')
            fixture=document(row['fixture'])
            need(fixture['phase']==row['phase'] and fixture['boot_id']==raw.boot and
                fixture['archive_sha256']==archive['sha256'],'actual curator fixture ownership')
    prepared=document(knowledge['apps579_photo_phases'][0]['fixture'])
    challenge=prepared['challenge']['cases'][0];uri=prepared['uris'][challenge['case_id']]
    permission,_,_=calls.only('photos','janitor','permissions');success(permission)
    need(value(permission,'permission-result')['authResults']==[0,0],'actual declared cleanup permission grant')
    baseline,_,_=calls.only('photos','normal','recent-info');success(baseline)
    created,_,_=calls.only('photos','normal','create');success(created)
    fresh=value(created,'asset-created');need(value(created,'creation-dialog-result')==[fresh['uri']],'actual ordinary consent creation')
    changed,_,_=calls.only('photos','normal','recent-info',1);success(changed)
    info=value(changed,'recent-info')
    need(info['defaults']==info['explicit'] and info['defaults']['dateTaken']>0 and
        info['defaults']['identifier'] not in ('','0') and info['defaults']!=value(baseline,'recent-info')['defaults'],
        'actual recent info must change after public asset creation')
    album,_,_=calls.only('photos','normal','default-album');success(album)
    need(type(value(album,'default-album')) is str and value(album,'default-album'),'actual localized default album')
    component,_,_=calls.only('photos','normal','recent-component');success(component)
    need(any(row['event']=='recent-component-exists' and loads(row['value']) is True for row in component),
        'actual recent component callback absent')
    deleted,_,_=calls.only('photos','janitor','cleanup-owned');success(deleted)
    need(value(deleted,'cleanup-active-after')=={'uri':fresh['uri'],'count':0} and
        value(deleted,'cleanup-trash-after')=={'uri':fresh['uri'],'count':0},'original fresh active/TRASH asset cleanup')
    selected,collected,_=calls.only('photos','normal','select');success(selected)
    need(value(selected,'select-result')['photoUris']==[uri] and len(collected['binaries'])==1 and
        collected['binaries'][0]['raw']['sha256']==challenge['image']['sha256'],'actual selected nonce URI grant and exact bytes')
    denied,_,_=calls.only('photos','foreign','read-denied');denial(denied)
    cancel,_,_=calls.only('photos','normal','cancel-select');success(cancel)
    need(value(cancel,'select-result')['photoUris']==[],'actual picker cancel leaked a grant')
    need(any(case=='photos' and action=='force-stop' and payload=={'role':'normal'} for case,action,payload,_,_ in calls.inputs),
        'actual caller death boundary absent')
    # Original subsequent phase observations must retain successful public
    # info/default normalization, not merely a phase.status summary.
    for row in knowledge['apps579_photo_phases'][1:]:
        phase=row['phase']
        for action in ('recent-info','default-album'):
            selected=[rows for key,(rows,_,_) in calls.results.items() if key[0:2]==('photos','normal') and
                key[2]=='original_'+phase+'_'+action.replace('-','_')]
            need(len(selected)==1,'actual phase public observation absent');success(selected[0])
            actual=value(selected[0],action)
            need(actual['defaults']==actual['explicit'] if action=='recent-info' else type(actual) is str and bool(actual),
                'actual phase public normalization/album boundary')
    form_ids=set();rendered=[]
    described,_,_=calls.only('photosform','grant','describe');success(described)
    need(value(described,'running-forms')==[] and any(row.get('bundleName')=='com.ohos.photos' and
        row.get('moduleName')=='phone_photos' and row.get('abilityName')=='FormAbility' and row.get('name')=='widget1'
        for row in value(described,'form-provider-info')), 'actual native FMS metadata/provider activation missing')
    acquired,_,_=calls.only('photosform','grant','show');success(acquired)
    need(len(value(acquired,'running-forms'))==1 and value(acquired,'form-acquired')['idString']==
        value(acquired,'running-forms')[0]['formId'],'actual FormComponent callback/FMS identity differ')
    for case,action,payload,record,cut in calls.inputs:
        if action=='photos-select-fixture':
            need(record['uri']==uri and record['case_id']==challenge['case_id'] and
                pixels(checked(record['screenshot']),checked(challenge['image']),record['selected_node']['rect'],minimum_fraction=.85)==record['metrics'],
                'actual picker nonce selection UI differs from original curator challenge')
    for row in knowledge['apps579_form_phases']:
        observation=document(row['observations']);phase=row['phase']
        for op in observation['operations']:
            if op['kind']=='collect':
                collected=op['record']
                matching=[(key,result) for key,result in calls.results.items() if result[1]==collected]
                need(len(matching)==1,'FormHost observation has no original callback')
                key,(rows,_,_)=matching[0];success(rows)
                for event in ('running-forms','form-published'):
                    for event_row in rows:
                        if event_row['event']==event:
                            forms=loads(event_row['value'])
                            if forms:
                                need(len(forms)==1,'one actual owned native form')
                                form=forms[0];form_ids.add(form['formId'])
                                need(form['bundleName']=='com.ohos.photos' and form['hostBundleName']==original_project.bundle('photosform','grant') and
                                    form['moduleName']=='phone_photos' and form['abilityName']=='FormAbility' and form['formName']=='widget1',
                                    'actual native FMS provider identity differs')
                                if event=='form-published' or phase!='prepare': need(form['formLocation']==0,'actual native DESKTOP publication')
            elif op['kind']=='input_photoform-pixels':
                record=op['record'];expected=record['expected']=='visible';need(record['phase']==phase,'actual form phase association')
                matches=[]
                for sample in record['samples']:
                    try:
                        metrics=pixels(checked(sample['frame']),checked(challenge['image']),sample['selected_node']['rect'],minimum_fraction=.85)
                        match=True
                        need(metrics==sample['metrics'],'independent nonce pixel metrics differ')
                    except ValueError as error:
                        need(str(error)=='new challenged wallpaper pixels not independently painted','invalid frame/geometry not absence')
                        match=False
                    need(match==sample['nonce_matches'],'actual nonce pixel summary differs');matches.append(match)
                need(len(matches)>=2 and matches[-2:]==[expected,expected],'two actual consecutive native form observations')
                rendered.append((phase,expected))
    need(len(form_ids)==1 and all(re.fullmatch('[1-9][0-9]*',item) for item in form_ids),'same real retained native form across all phases')
    need(('prepare',True) in rendered and all((phase,phase in ('unhidden','recovered')) in rendered for phase in PHASES[1:]),
        'native FA notifications must reflect every original actual mutation')
    for role,code in (('normal',202),('denied',201)):
        boundary=calls.actions('photosform',role,'boundaries');need(len(boundary)>=2,'initial and final form permission boundaries')
        for rows,_,_ in boundary:
            success(rows)
            for event in ('form-info-error','form-running-error'):
                actual=[r for r in rows if r['event']==event]
                need(len(actual)==1 and actual[0]['code']==code and loads(actual[0]['value'])['codeType']=='number',
                    'actual ordinary/undeclared native form denial')
            need(not any(r['event'].endswith('-returned') for r in rows),'protected native form call returned')
    removed,_,_=calls.only('photosform','grant','delete-form');success(removed)
    need(value(removed,'form-delete-after')==[],'actual owned native form not removed')
    need(any(case=='photosform' and action=='force-stop' and payload=={'role':'grant'} for case,action,payload,_,_ in calls.inputs) and
        calls.actions('photosform','grant','attach'),'real host death/retained-ID reattachment absent')
    return dict(original22=original,identities=identities,form_id=next(iter(form_ids)),
        curator_phases=list(PHASES),rendered=rendered,actual_received_copies=raw.copied_receives,cleanup_complete=True)


def replay_photos(*,archive,main_boot,main_suite,actor,output):
    output=Path(output);output.mkdir(exist_ok=False)
    result=dict(schema='photos579-true2in1-whole-raw-replay/v1',archive=archive,boot=main_boot,
        supported_local_complete=False,cloud_account_complete=False,checks={},retained_failures=[],replay_errors=[],
        unresolved_subscopes=['cloud_userPropertySettings_real_account_and_named_complete_provider'],
        formally_closed=[],runtime_pass=False,first_artifact_behavior_gate_passed=False)
    suite=document(main_suite);stage=suite['supplemental_checks']['photos579']
    result['retained_original_reports']={key:stage[key] for key in
        ('original_knowledge','restart','original_io','close_span')}
    result['retained_original_reports']['main_suite']=main_suite
    result['retained_failures'].extend(stage['failures'])
    if stage['original_knowledge'] is not None:
        original=document(stage['original_knowledge'])
        for key in ('failures','cleanup_errors','apps579_errors','apps579_form_errors','apps579_cleanup_errors'):
            if original.get(key): result['retained_failures'].append(dict(scope='original22/'+key,actual=original[key]))
    need(stage['profile']=='2in1' and document(main_boot)['test_environment']['device_type']=='2in1',
        'phone N/A cannot be replayed as true2in1 positive')
    for name,function in (('original22_and_photos_form',verify_knowledge),('provider_restart',verify_restart)):
        try:
            value=stage['original_knowledge'] if function is verify_knowledge else stage
            result['checks'][name]=function(value,archive=archive,boot=main_boot,actor=actor,output=output)
        except Exception as error:
            result['replay_errors'].append(dict(scope=name,type=type(error).__name__,message=str(error)))
    result['supported_local_complete']=not result['retained_failures'] and not result['replay_errors'] and len(result['checks'])==2
    return result
