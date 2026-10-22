"""Serial Number580 leaf on original499 Bridge; no Owner/IO/transport constructor.

All external actions pass the original held authority. The account window is a
fixed source callable supplied by Root, not a module/command selected in DATA.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
from types import SimpleNamespace


def need(value,message):
    if not value:raise ValueError(message)


def record(path):
    path=Path(path);raw=path.read_bytes()
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')
        stream.flush();__import__('os').fsync(stream.fileno())
    return record(path)


def capture_generation_before(bridge, output, *, original):
    """Passive after true reset/readiness, before first post-reset provider call."""
    _,_,_,native=original.original_modules()
    value=native.capture(bridge,'datashare-cycle-before')
    return save(output,value)


def seed_inputs(data, *, system_image_sha256, protocol):
    # Root's ordinary image exporter supplies this actual report; these are
    # file observations, never expected cities or guest outcomes.
    need(type(data) is dict and set(data)=={'image_report','semantic_sources','normal_source','permission_translation'},'exact local source/image inputs')
    packaged=protocol.decode(protocol.checked(data['image_report']).read_bytes())
    need(packaged['schema']=='number580-actual-packaged-local-seeds/v1' and packaged['target']['device']=='phone' and
         packaged['system_image']['sha256']==system_image_sha256 and packaged['runtime_pass'] is False,
         'actual same-package normal seed export')
    report=protocol.decode(protocol.checked(packaged['packaged_image_evidence']).read_bytes())
    need(report['status']=='pass' and report['failures']==[] and report['system_image_sha256']==system_image_sha256 and
         report['source_revision']=='50e1330646432ce166e7981c577f25f46c90e7ac', 'actual complete source/image receipt')
    table=protocol.contract();seeds={}
    need(set(packaged['files'])==set(table['seeds']), 'exact two actual packaged corpora')
    for name in ('numberlocation.data','yellowpage.data'):
        selected=packaged['files'][name];row=selected['image_proof'];file=selected['file']
        need(row==report['local_seed_files'][name] and row['system_image_sha256']==system_image_sha256 and
             type(row['image_inode']) is int and row['image_inode']>0 and
             row['image_path'] in ('/etc/telephony/'+name,'/system/etc/telephony/'+name) and
             row['image_path'] in row['image_path_aliases'] and row['source_relative']=='base/telephony/number_identity/etc/'+name and
             row['source_sha256']==row['sha256']==file['sha256']==table['seeds'][name]['sha256'] and
             row['bytes']==file['bytes']==table['seeds'][name]['bytes'], 'actual seed inode/source/image/file identity differs')
        protocol.checked(file);seeds[name]=file
    required={name:row for name,row in table['source_files'].items() if not name.endswith(('napi_number_identity.cpp','number_mark_ability.cpp'))}
    need(type(data['semantic_sources']) is dict and set(data['semantic_sources'])==set(required),'complete finite oracle source vector')
    for name,row in data['semantic_sources'].items():
        need({key:row[key] for key in ('sha256','bytes')}==required[name],'unknown oracle source: '+name)
        protocol.checked(row)
    protocol.seed_oracle(seeds)
    return seeds


class CaseView:
    """A file/command adapter over an existing Bridge, not another resource."""
    def __init__(self,bridge,role,run,protocol):
        self.bridge=bridge;self.owner=bridge.owner;self.guest=bridge.guest;self.c=bridge.c
        self.calls=bridge.calls;self.role=role;self.run=run;self.protocol=protocol
        self.spec=dict(bridge.spec,runs=dict(bridge.spec['runs'],**{role:run}))
        self.paths=();self.pid=None;self.context=None;self.actual_pids={}
    def verify_observer(self):return self.bridge.verify_observer()
    def check_observer_file(self):return self.bridge.check_observer_file()
    def leaf(self,*args,**kwargs):return self.bridge.leaf(*args,**kwargs)
    def boot(self):return self.shell(['cat','/proc/sys/kernel/random/boot_id']).decode('ascii').strip()
    def shell(self,argv):
        bundle=self.c.ROLES[self.role][0]
        allowed=argv in (['cat','/proc/sys/kernel/random/boot_id'],['bm','dump','-n',bundle],['pidof',bundle])
        bms=self.bridge.current_bms.get(self.role)
        allowed=allowed or bms is not None and argv in ([self.c.TOKEN_QUERY,self.run,'identity',bundle,str(bms['token'])],
                                                       ['sha256sum',bms['installedHapPath']])
        if self.paths:
            allowed=allowed or any(argv==[self.c.stat_script(path)] for path in self.paths)
        if self.pid:
            allowed=allowed or argv in (['cat','/proc/'+self.pid+'/status'],['cat','/proc/'+self.pid+'/cmdline'],['cat','/proc/'+self.pid+'/stat'])
            if self.context:
                allowed=allowed or any(argv==[self.c.stat_script('/proc/'+self.pid+'/root'+self.context+'/'+Path(path).name,process_root=True)] for path in self.paths)
        need(allowed,'case command outside fixed actual identity/file surface')
        actual=self.leaf([self.owner.hdc,'-t',self.guest.target,'shell',*argv],'number580-identity')
        need(actual['exit_code']==0 and not self.calls[-1]['transport_failure'],'actual case command failed; raw retained')
        if argv==['bm','dump','-n',bundle]:
            self.bridge.current_bms[self.role]=self.c.bms_fields(actual['stdout'],bundle,self.spec['roles'][self.role]['bms']['fields'])
        if argv==['pidof',bundle]:
            self.pid=actual['stdout'].decode('ascii').strip();need(re.fullmatch('[1-9][0-9]*',self.pid),'one actual caller PID')
        return actual['stdout']


def collect(bridge,probe,admitted,*,original,protocol,output,account_window):
    root=Path(output);need(root.is_absolute() and root.parent.resolve()==root.parent and not root.exists(),'fresh corpus output')
    root.mkdir(mode=0o700)
    need(bridge.observer is admitted and probe.spec is bridge.spec and callable(account_window),
         'same original admitted Bridge/Collector and fixed Root account callable required')
    data=bridge.spec.get('number580');need(type(data) is dict and set(data)=={'sources','account_controller','observer_owners'},'exact Number DATA fields')
    seeds=seed_inputs(data['sources'],system_image_sha256=admitted.profile['system_image']['sha256'],protocol=protocol)
    _,_,_,native=original.original_modules();owner_run=secrets.token_hex(16)
    need(hasattr(bridge,'number580_generation_before'),'passive post-reset generation anchor missing')
    generation_before=bridge.number580_generation_before
    generation_after=save(root/'generation-after.json',native.capture(bridge,'datashare-cycle-after'))
    frame=protocol.decode(protocol.checked(generation_after).read_bytes())
    need(frame.get('process_absent') is False, 'actual post-reset mark provider generation must exist')
    # Never infer the selected JSON table from the image alone. The provider's
    # update namespace is observed before any location route in this boot.
    earlier=original.core.structured_events(bytes.fromhex(frame['hilog_raw_hex']))
    need(not any(v.kind=='native' and v.value['pid']==frame['process']['pid'] and
                 v.value['event']=='query-enter' and v.value['route']==1 for v in earlier),
         'location cache may already have loaded before namespace observation')
    pid=frame['process']['pid']
    script=protocol.seed_selection_script(pid)
    observed=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,'shell',script],'number580-provider-seed-selection')
    need(observed['exit_code']==0 and observed['stdout']==protocol.seed_selection_output(pid) and
         not bridge.calls[-1]['transport_failure'], 'actual provider update override absent proof')
    provider_seed_selection=save(root/'provider-seed-selection.json',dict(schema='number580-provider-seed-selection/v1',
        frame=generation_after,command=record(bridge.out/('call-%04d.json'%(len(bridge.calls)-1))),pid=pid,
        selected='same-image-packaged-numberlocation.data',source_only_inference=False))

    completed=[];failures=[];cleanup_pending=False;account_receipt=None
    def run_case(role,case_id,*,label=None):
        nonlocal cleanup_pending
        run=secrets.token_hex(16);folder=root/('%03d-'%len(completed)+role+'-'+case_id)
        folder.mkdir(mode=0o700);view=CaseView(bridge,role,run,protocol);boot=view.boot()
        before_bms,access=original.original_modules()[0].identity395(view,role)
        bms_call=next(record(bridge.out/('call-%04d.json'%i)) for i in reversed(range(len(bridge.calls)))
                      if bridge.calls[i]['argv']==[bridge.owner.hdc,'-t',bridge.guest.target,'shell','bm','dump','-n',bridge.c.ROLES[role][0]])
        query_call=next(record(bridge.out/('call-%04d.json'%i)) for i in reversed(range(len(bridge.calls)))
                        if bridge.calls[i]['argv']==[bridge.owner.hdc,'-t',bridge.guest.target,'shell',bridge.c.TOKEN_QUERY,run,'identity',bridge.c.ROLES[role][0],str(before_bms['token'])])
        before=save(folder/'native-before.json',native.capture(view,role+'-before'))
        argv=['aa','start','-b',bridge.c.ROLES[role][0],'-a','EntryAbility','--ps','run',run,'--ps','phase','corpus580',
              '--ps','number',bridge.spec['number'],'--ps','ownerRun',owner_run,'--ps','caseId',case_id,'--ps','role',role]
        # Mark mutation may have happened even if transport, pull or replay then
        # fails. Set risk BEFORE dispatch, clear only after proved delete+empty.
        if role=='system-granted' and case_id in ('mark-create-read','mark-update-read'):
            cleanup_pending=True
        actual=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,'shell',*argv],'number580-case-start')
        need(actual['exit_code']==0 and not bridge.calls[-1]['transport_failure'],'case start failed')
        deadline=time.monotonic()+bridge.spec['phase_timeout_seconds'];context=None
        while time.monotonic()<deadline:
            raw=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,'shell','hilog','-x'],'number580-summary')
            need(raw['exit_code']==0 and not bridge.calls[-1]['transport_failure'],'actual summary transport failed')
            hits=[];begins=[]
            for line in raw['stdout'].splitlines():
                if b'NUMBER_CORPUS580 ' not in line:continue
                try:row=protocol.decode(line.split(b'NUMBER_CORPUS580 ',1)[1])
                except (ValueError,UnicodeError):continue
                if (row.get('run'),row.get('caseId'))!=(run,case_id):continue
                if row.get('event')=='summary':hits.append(row)
                if row.get('event')=='begin':begins.append(row)
            need(len(hits)<=1 and len(begins)<=1,'duplicate actual case summary/begin')
            if hits:
                need(len(begins)==1,'actual case begin/context absent');context=protocol.decode(begins[0]['valueJSON']);break
            time.sleep(.5)
        need(context is not None,'bounded actual case journal did not complete')
        after=save(folder/'native-after.json',native.capture(view,role+'-after'))
        found=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,'shell',protocol.find_script(run)],'number580-find')
        need(found['exit_code']==0 and not bridge.calls[-1]['transport_failure'],'actual unique find failed')
        view.paths=protocol.discovered(found['stdout'],run);view.context=context
        stats=tuple(bridge.c.file_stat(view.shell([bridge.c.stat_script(path)]),path,before_bms['uid']) for path in view.paths)
        need(len({(v['dev'],v['inode']) for v in stats})==3,'distinct actual case journal/tokens')
        mapping=bridge.c.mapped_context395(view,role,context,view.paths,stats)
        pairs=[]
        for repeat in range(2):
            values=[]
            for index,remote in enumerate(view.paths):
                local=folder/('pull-%d-%d.raw'%(repeat,index))
                result=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,'file','recv',remote,str(local)],'number580-pull')
                need(result['exit_code']==0 and not bridge.calls[-1]['transport_failure'],'actual case pull failed')
                values.append(record(local))
            need(tuple(bridge.c.file_stat(view.shell([bridge.c.stat_script(path)]),path,before_bms['uid']) for path in view.paths)==stats and
                 all(row['sha256']==observed['sha256'] for row,observed in zip(values,stats)),'case raw changed during pull')
            pairs.append(values)
        need([r['sha256'] for r in pairs[0]]==[r['sha256'] for r in pairs[1]],'independent case pulls differ')
        need(view.boot()==boot==probe.current_boot,'case crossed uncontrolled boot')
        package=bridge.spec['native_consumer_inputs496']
        need(type(package) is dict and set(package)==original.PACKAGE_KEYS496,'complete original native image inputs')
        bindings=dict(schema='number580-case-native/v1',hdc=bridge.owner.hdc,target=bridge.guest.target,
            source_commit=bridge.spec['source_commit'],archive_sha256=bridge.spec['archive_sha256'],before=before,after=after,
            generation_captures=[generation_before,generation_after],
            bridge_calls=[record(bridge.out/('call-%04d.json'%i)) for i,row in enumerate(bridge.calls)
                          if row['argv'][:3]==[bridge.owner.hdc,'-t',bridge.guest.target]],
            caller=dict(role=role,run=run,owner_run=owner_run,number=bridge.spec['number'],case_id=case_id,
                        actual_context=context,journal=pairs[0][0],token_before=pairs[0][1],token_after=pairs[0][2],
                        bms_fields=bridge.spec['roles'][role]['bms']['fields'],bms_call=bms_call,query_call=query_call),seeds=seeds,**package)
        bound=save(folder/'bindings.json',bindings)
        proof=protocol.review_native(bindings,admitted=admitted,original=original)
        if role=='system-granted' and case_id=='mark-delete-read':cleanup_pending=False
        item=dict(role=role,case_id=case_id,bindings=bound,proof=save(folder/'proof.json',proof),actual_file_mapping=mapping,label=label)
        completed.append(item);save(folder/'completed.json',item);return item
    try:
        for role in protocol.ROLES:
            for case in protocol.cases():
                # The account window runs with the owned mark still present;
                # only the original100 view deletes it after full restoration.
                if role=='system-granted' and case['id']=='mark-delete-read':
                    account_receipt=account_window(bridge=bridge,controller=data['account_controller'],owner_run=owner_run,
                        owned_number=bridge.spec['number'],generation_captures=[generation_before,generation_after])
                    protocol.checked(account_receipt)
                run_case(role,case['id'])
    except Exception as error:
        failures.append(type(error).__name__+': '+str(error))
    finally:
        report=dict(schema='number580-corpus-retained/v1',source_commit=bridge.spec['source_commit'],
            archive_sha256=bridge.spec['archive_sha256'],owner_run=owner_run,number=bridge.spec['number'],
            sources=data['sources'],provider_seed_selection=provider_seed_selection,generation_captures=[generation_before,generation_after],cases=completed,
            account=account_receipt,failures=failures,cleanup_pending=cleanup_pending,
            status='raw_complete_requires_final_replay' if not failures and not cleanup_pending else 'failed_or_unsettled',
            original_collector_rewritten=False,whole_aggregate_closed=False,first_artifact_behavior_gate_passed=False)
        result=save(root/'corpus.json',report)
    return result


def account_case(bridge,*,user,case_id,owner_run,owned_number,output,protocol,original):
    """Same Bridge only; foreign BMS explicitly uses -u, never old observer100."""
    need(type(user) is int and user>=100 and case_id in ('account-foreign-read','account-restored-read'), 'fixed account read')
    root=Path(output);root.mkdir(mode=0o700,exist_ok=False);run=secrets.token_hex(16)
    c=bridge.c;bundle=c.ROLES['system-granted'][0];at=len(bridge.calls)
    def call(argv,label):
        value=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,*argv],label)
        need(value['exit_code']==0 and not bridge.calls[-1]['transport_failure'],'actual account probe command failed')
        return value,record(bridge.out/('call-%04d.json'%(len(bridge.calls)-1)))
    boot,bref=call(['shell','cat','/proc/sys/kernel/random/boot_id'],'number580-account-boot')
    before_bms,bb=call(['shell','bm','dump','-n',bundle,'-u',str(user)],'number580-account-bms')
    bms=c.bms_fields(before_bms['stdout'],bundle,bridge.spec['roles']['system-granted']['bms']['fields'])
    need(bms['uid']//200000==user and bms['systemApp'] is True,'actual per-user BMS system role')
    hashed,hapref=call(['shell','sha256sum',bms['installedHapPath']],'number580-account-hap')
    need(hashed['stdout'].decode().split()==[bridge.spec['roles']['system-granted']['signed_hap']['sha256'],bms['installedHapPath']],
         'actually installed per-user HAP must be the signed role')
    _,_,_,native=original.original_modules()
    before=save(root/'native-before.json',native.capture(bridge,'account-'+str(user)+'-before'))
    argv=['shell','aa','start','-b',bundle,'-a','EntryAbility','-m','entry','-u',str(user),
        '--ps','run',run,'--ps','phase','corpus580','--ps','number',owned_number,'--ps','ownerRun',owner_run,
        '--ps','caseId',case_id,'--ps','role','system-granted']
    _,start=call(argv,'number580-account-number-start');deadline=time.monotonic()+bridge.spec['phase_timeout_seconds'];context=None
    while time.monotonic()<deadline:
        logs,logref=call(['shell','hilog','-x'],'number580-account-number-journal')
        rows=[]
        for line in logs['stdout'].splitlines():
            if b'NUMBER_CORPUS580 ' not in line:continue
            try:value=protocol.decode(line.split(b'NUMBER_CORPUS580 ',1)[1])
            except (ValueError,UnicodeError):continue
            if (value.get('run'),value.get('caseId'))==(run,case_id):rows.append(value)
        if any(v['event']=='summary' for v in rows):
            begins=[v for v in rows if v['event']=='begin'];need(len(begins)==1,'one actual account case context')
            context=protocol.decode(begins[0]['valueJSON']);break
        time.sleep(.25)
    need(context is not None,'account case raw bounded completion')
    after=save(root/'native-after.json',native.capture(bridge,'account-'+str(user)+'-after'))
    found,findref=call(['shell',protocol.find_script(run)],'number580-account-find');paths=protocol.discovered(found['stdout'],run)
    stats=[];pulls=[]
    for repeat in range(2):
        series=[];current=[]
        for n,path in enumerate(paths):
            raw,sref=call(['shell',c.stat_script(path)],'number580-account-file-stat')
            stat=c.file_stat(raw['stdout'],path,bms['uid']);current.append(dict(stat=stat,call=sref))
            dest=root/('pull-%d-%d.raw'%(repeat,n));_,received=call(['file','recv',path,str(dest)],'number580-account-pull')
            file=record(dest);need(file['sha256']==stat['sha256'] and file['bytes']==stat['bytes'],'actual account file transport differs')
            series.append(dict(file=file,remote=path,receive=received,stat_call=sref))
        need(repeat==0 or [v['stat'] for v in current]==[v['stat'] for v in stats],'actual account files changed across independent pulls')
        stats=current;pulls.append(series)
    need([v['file']['sha256'] for v in pulls[0]]==[v['file']['sha256'] for v in pulls[1]],'account pulls differ')
    journal=Path(pulls[0][0]['file']['path']).read_bytes();jrows=protocol.rows(journal,run=run,owner=owner_run,case_id=case_id)
    pid=str(protocol.caller_pid(logs['stdout'],jrows,original.core));proc={}
    for name in ('status','cmdline','stat'):
        raw,ref=call(['shell','cat','/proc/'+pid+'/'+name],'number580-account-process-'+name);proc[name]=ref
    mapping=[]
    for path in paths:
        mapped='/proc/'+pid+'/root'+context+'/'+Path(path).name
        raw,ref=call(['shell',c.stat_script(mapped,process_root=True)],'number580-account-process-file')
        c.file_stat(raw['stdout'],mapped,bms['uid']);mapping.append(dict(path=mapped,call=ref))
    after_bms,ab=call(['shell','bm','dump','-n',bundle,'-u',str(user)],'number580-account-bms-after')
    need(c.bms_fields(after_bms['stdout'],bundle,bridge.spec['roles']['system-granted']['bms']['fields'])==bms,'per-user BMS changed')
    last,lastref=call(['shell','cat','/proc/sys/kernel/random/boot_id'],'number580-account-boot-after')
    need(last['stdout']==boot['stdout'],'account read crossed kernel boot')
    return save(root/'case.json',dict(schema='number580-account-case/v1',user=user,run=run,case_id=case_id,
        owner_run=owner_run,number=owned_number,boot_id=boot['stdout'].decode().strip(),context=context,
        bms_fields=bridge.spec['roles']['system-granted']['bms']['fields'],bms_before=bb,bms_after=ab,
        installed_hap=hapref,start=start,hilog=logref,before=before,after=after,find=findref,pulls=pulls,
        process=proc,mapping=mapping,boot_before=bref,boot_after=lastref,
        calls=[record(bridge.out/('call-%04d.json'%i)) for i in range(at,len(bridge.calls))]))


# Original496 collection body retained; fixed target-aware image replay call only.
def collect_original_bridge496(*,bridge,probe,admitted,package_inputs,output,original,protocol):
    core=original.core;PACKAGE_KEYS496=original.PACKAGE_KEYS496;original_modules=original.original_modules
    checked=original.checked;descriptor496=original.descriptor496;write496=original.write496
    TOKEN_QUERY=original.TOKEN_QUERY
    """One local-only hook after original probe.collect(), before Owner cleanup.

    The caller is the unchanged original live Owner holding its Bridge, Collector
    and original AdmittedObserver. No command/callback/Owner is created here.
    Incomplete/old-image inputs yield three independent pending receipts. The
    original Collector status/pending/native_callback_proven/47 are untouched.
    """
    root=Path(output)
    core.need(root.is_absolute() and root.parent.resolve()==root.parent and not root.exists() and
        not root.is_symlink(),'one fresh canonical local native-review output required')
    root.mkdir(mode=0o700)
    if package_inputs is None:package_inputs={key:None for key in PACKAGE_KEYS496}
    core.need(type(package_inputs) is dict and set(package_inputs)==PACKAGE_KEYS496,
        'fixed DATA descriptors only; no package claim/callback is execution authority')
    results={}
    for role in ('system-granted','system-readonly','ordinary'):
        item=dict(role=role,status='pending_actual_native_inputs_ONLY',pending=[],
            native_callback_chain_checked=False,original411_verdict_changed=False,
            first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)
        try:
            if admitted is None:raise core.Pending('original admitted observer missing; no JSON admission fallback')
            missing=sorted(key for key,value in package_inputs.items() if value is None)
            if missing:raise core.Pending('actual package/producer descriptors pending: '+','.join(missing))
            c,napi,ui,native=original_modules()
            spec=bridge.spec;hdc=bridge.owner.hdc;target=bridge.guest.target
            core.need(bridge.observer is admitted and probe.spec is spec,
                'original Bridge/Collector must share the actual original admitted object/spec')
            actual_calls=[];call_rows=[]
            for index,retained in enumerate(bridge.calls):
                path=bridge.out/('call-%04d.json'%index)
                descriptor=descriptor496(path);row=core.decode_json(checked(descriptor).read_bytes())
                core.need(row==retained,'registered original Bridge row differs from retained raw file')
                # Controlled reboot QMP/host commands are retained by the Owner;
                # they are not falsely relabeled as target HDC observations.
                if row.get('argv',[])[:3]==[hdc,'-t',target]:
                    actual_calls.append(descriptor);call_rows.append((row,descriptor))
            core.need(actual_calls,'actual original held HDC ledger absent')
            phases=[value for value in probe.napi_phases if value.get('role')==role and value.get('phase')=='napi-read']
            if len(phases)!=1:raise core.Pending('one actual completed original public NAPI phase missing/ambiguous')
            phase=phases[0]
            core.need(len(phase['files'])==3 and phase['run']==spec['runs'][role] and
                phase['owner_run']==spec['runs']['system-granted'],'registered original NAPI file/run triple differs')
            phase_path=probe.output/(role+'-napi-read.json')
            phase_descriptor=descriptor496(phase_path)
            core.need(core.decode_json(checked(phase_descriptor).read_bytes())==phase,
                'registered original completed phase differs from independently retained phase file')
            observations=[]
            for suffix in ('before','after'):
                matches=[value for value in bridge.native_observations if value.get('label')==role+'-'+suffix]
                if len(matches)!=1:raise core.Pending('actual native '+role+'-'+suffix+' capture missing/ambiguous')
                value=core.decode_json(checked(matches[0]['evidence']).read_bytes())
                if any(type(value.get(key)) is not dict or value[key].get('value') is None for key in
                    ('native_clock_before496','native_clock_after496')):
                    raise core.Pending('original/failed clock capture is not a new dual-clock raw observation')
                if any('held_index' not in row for row in value.get('actual_calls',[])):
                    raise core.Pending('old native capture lacks exact original Authority indices')
                observations.append(matches[0]['evidence'])
            generation=[]
            for label in ('datashare-cycle-before','datashare-cycle-after'):
                matches=[value for value in bridge.native_observations if value.get('label')==label]
                if len(matches)!=1:raise core.Pending('actual initial '+label+' generation capture missing/ambiguous')
                generation.append(matches[0]['evidence'])
            bundle=c.ROLES[role][0];fields=spec['roles'][role]['bms']['fields']
            def unique_raw_call(argv,boot=None):
                candidates=[]
                for row,descriptor in call_rows:
                    if row.get('argv')!=argv or row.get('exit_code')!=0 or row.get('transport_failure') is not False:continue
                    if boot is not None:
                        parsed=core.decode_json(bytes.fromhex(row['stdout_hex']))
                        if parsed.get('boot_id')!=boot:continue
                    candidates.append((row,descriptor))
                if not candidates:raise core.Pending('actual registered independent identity command absent')
                # Repeated equal identity snapshots are legal. Divergent raw
                # identity is refused, never chosen by nearest timestamp.
                signatures={(row['stdout_hex'],row['stderr_hex']) for row,_ in candidates}
                if len(signatures)!=1:raise core.Pending('independent identity raw has multiple distinct candidates')
                return min(candidates,key=lambda pair:pair[0]['held_index'])
            bms_row,bms_descriptor=unique_raw_call([hdc,'-t',target,'shell','bm','dump','-n',bundle])
            bms=c.bms_fields(bytes.fromhex(bms_row['stdout_hex']),bundle,fields)
            query_row,query_descriptor=unique_raw_call([hdc,'-t',target,'shell',TOKEN_QUERY,
                phase['run'],'identity',bundle,str(bms['token'])],boot=phase['boot_id'])
            caller=dict(role=role,run=phase['run'],owner_run=phase['owner_run'],number=spec['number'],
                actual_context=phase['actual_file_binding']['actual_context'],journal=phase['files'][0],
                token_before=phase['files'][1],token_after=phase['files'][2],bms_fields=fields,
                bms_call=bms_descriptor,query_call=query_descriptor)
            bindings=dict(schema='number-native-consumer496/v1',hdc=hdc,target=target,
                source_commit=spec['source_commit'],archive_sha256=spec['archive_sha256'],
                before=observations[0],after=observations[1],generation_captures=generation,bridge_calls=actual_calls,caller=caller,**package_inputs)
            item['original_phase']=phase_descriptor
            item['bindings']=write496(root/(role+'-bindings.json'),bindings)
            if role=='ordinary':
                # The original ordinary public-denial oracle and pending error
                # domain remain the authority. It has no permitted Query chain.
                raise core.Pending('ordinary role original denial review retained separately; no permission-granted native Query chain claimed')
            proof=protocol.review_original496(bindings,admitted=admitted,original=original)
            item['proof']=write496(root/(role+'-proof.json'),proof)
            item['native_callback_chain_checked']=proof['native_callback_chain_checked']
            item['status']='checked_native_chain_ONLY'
        except core.Pending as error:item['pending'].append(str(error))
        except (FileNotFoundError,PermissionError) as error:
            item['pending'].append('actual registered local evidence unavailable: '+type(error).__name__+': '+str(error))
        except Exception as error:
            item['status']='rejected_native_evidence_ONLY'
            item['failures']=[type(error).__name__+': '+str(error)]
        results[role]=write496(root/(role+'-review.json'),item)
    return dict(schema='number-native496-independent-index/v1',roles=results,
        scope='local replay of original registered raw only; original Owner verdict and 47 unchanged',
        original411_verdict_changed=False,first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)

