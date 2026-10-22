"""Pure completed original499/local580 replay. No resources or DATA-selected code.

complete() consumes the six post-finish Refs before the child can exit. replay()
additionally requires the seventh actual parent Popen.wait receipt; a completed
child cannot manufacture its own parent exit/lease receipt. Old pending is kept.
"""
from pathlib import Path
import hashlib
import json
import re
import shlex
import posixpath

LOCAL_ID='number580:phone-supported-local'
COMPLETED={'owner_report','corpus','owner_closure','config','spec','observer_proof'}
NUMBER_MEMBERS={'owner499.py','corpus580.py','protocol580.py','register580.py','project580.py',
 'caller/NumberCorpus580.ets','caller/LegacyNumberCorpus580.js','caller/LegacyNumberCorpus580.d.ts','CONTRACT580.json','produce580.py'}


def need(value,message):
    if not value:raise ValueError(message)

def decode(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            need(k not in result,'duplicate raw JSON key');result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read(row,protocol,maximum=16*1024*1024):
    return protocol.decode(protocol.checked(row,maximum).read_bytes())


def actual_file(path,protocol,maximum=16*1024*1024):
    path=Path(path);raw=path.read_bytes()
    row=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    protocol.checked(row,maximum);return row


def exact_call(ref,entries,protocol,argv=None,zero=True):
    row=read(ref,protocol)
    need(type(row) is dict and set(row)=={'argv','exit_code','stdout_hex','stderr_hex','transport_failure','held_index'} and
         type(row['held_index']) is int and entries.get(row['held_index'])==row and
         (argv is None or row['argv']==argv) and row['transport_failure'] is False and
         type(row['exit_code']) is int and (not zero or row['exit_code']==0),'actual registered original Bridge command required')
    return row,bytes.fromhex(row['stdout_hex'])


def owner_replay(completed,*,protocol,original,admitted):
    report=read(completed['owner_report'],protocol);corpus=read(completed['corpus'],protocol)
    root=protocol.checked(completed['owner_report']).parent
    closure=read(completed['owner_closure'],protocol)
    need(completed['owner_closure']==report['actual_resource_close'] and
         protocol.checked(completed['owner_closure']).parent==root and closure['cleanup_verified'] is True,
         'same original post-finish resource-close report')
    held=read(closure['held_processes'],protocol)
    need(protocol.checked(closure['held_processes']).parent==root and held['unknown_creation'] is False and held['children'],
         'unknown/empty original direct-child authority')
    for child in held['children']:
        need(child['reaped'] is True and child['last_signal_boundary'] is True and
             type(child['exit_code']) is int and type(child['pid']) is int and child['pid']>0 and
             type(child['argv']) is list and child['argv'],'unsettled original owned group')
    collector=report['collector'];c,napi,ui,native=original.original_modules()
    need(collector['failures']==[] and collector['cleanup_pending'] is False and
         collector['runtime_ready'] is False and collector['original_aggregate_finding_closed'] is False,
         'original business/cleanup failures cannot be waived')
    spec=read(completed['spec'],protocol);config=read(completed['config'],protocol)
    boot=read(report['actual_guest_boot'],protocol)
    clocks=boot['watchdog_clocks'];environment=boot['test_environment']
    need(protocol.checked(report['actual_guest_boot'])==root/'boot/boot.json' and
         clocks['cleanup_complete'] is True and clocks['cleanup_errors']==[] and
         clocks['boot_id']==environment['boot_id'],'original initial-boot clock/guest cleanup required')
    need(config['archive']['sha256']==spec['archive_sha256']==corpus['archive_sha256']==admitted.profile['archive']['sha256'] and
         spec['source_commit']==corpus['source_commit'],'actual independent package/source join')
    protocol.checked(config['archive'],maximum=16*1024*1024*1024)
    t=collector['controlled_reboot'];c.reboot_join(t['before_vm'],t['after_vm'],t['before_boot_id'],t['after_boot_id'])
    vm=[]
    for name in ('initial','pre-reset','post-reset'):
        row=read(actual_file(root/'number-owner'/(name+'-held-vm.json'),protocol),protocol)
        need(row['purpose']=='number-only' and row['package_sha256']==spec['archive_sha256'] and row['lease_held'] is True,
             'actual original VM purpose/archive/held lease')
        vm.append(row)
    invariant=('qemu_pid','qemu_start_ticks','writable_image','image_dev','image_inode','kernel_birth','actual_disks','actual_qemu_argv','socket')
    need(all(all(v[k]==vm[0][k] for k in invariant) for v in vm),'actual QEMU incarnation/disk/argv changed across reset')
    need(vm[0]['kernel_birth']['api']=='proc_pidinfo.PROC_PIDTBSDINFO' and
         vm[0]['kernel_birth']['incarnation']==vm[0]['qemu_start_ticks'],'Darwin birth must not be called Linux ticks')
    need(environment['boot_id']==t['before_boot_id'] and t['before_boot_id']!=t['after_boot_id'],
         'true different kernel boots, not caller/provider restart')
    reset=read(actual_file(root/'number-owner/controlled-reset.json',protocol),protocol)
    need(reset['transport_failure_indices']==[] and reset['transition_all_calls_zero_required_by_original_collector'] is True and
         all(r['exit_code']==0 for r in reset['actual_calls']),'original reset/reconnect failures retained and blocking')
    calls={}
    for path in sorted((root/'number-owner').glob('call-*.json')):
        row=read(actual_file(path,protocol),protocol);index=row['held_index']
        need(type(index) is int and 0<=index<len(held['children']) and index not in calls and
             row['argv']==held['children'][index]['argv'] and row['exit_code']==held['children'][index]['exit_code'],
             'every Bridge command belongs to the final actual held table')
        calls[index]=row
    need(calls,'original actual Bridge commands absent')
    # Rejoin every original Collector raw stream to its original held command.
    for row in collector['calls']:
        out=protocol.checked(row['stdout']).read_bytes();err=protocol.checked(row['stderr']).read_bytes()
        need(any(v['argv']==row['argv'] and v['exit_code']==row['exit_code'] and
             v['stdout_hex']==out.hex() and v['stderr_hex']==err.hex() for v in calls.values()),
             'original collector raw not in actual held ledger')
    expected=['cycle','prepare-persist','verify-persist','system-denied','ordinary-denied']
    need([r['phase'] for r in collector['phases']]==expected,'all original five strict phases required')
    for row in collector['phases']:
        raw=protocol.checked(row['journal']).read_bytes()
        proof=original_journal_review(raw,row['run'],row['phase'],spec['number'])
        need(proof==row['journal_review'] and row['run']==spec['runs'][row['role']] and
             row['boot_id']==(t['before_boot_id'] if row['phase'] in ('cycle','prepare-persist') else t['after_boot_id']),
             'original strict journal/run/boot differs')
        bundle=c.ROLES[row['role']][0]
        queries=[(index,v) for index,v in calls.items() if v['argv'][-5:]==
            ['shell',c.TOKEN_QUERY,row['run'],row['phase'],bundle] or
            len(v['argv'])>=6 and v['argv'][-6:-1]==['shell',c.TOKEN_QUERY,row['run'],row['phase'],bundle]]
        need(len(queries)==1,'one actual independent phase AccessToken query')
        query_index,query=queries[0]
        bms_calls=sorted((index,v) for index,v in calls.items() if v['argv'][-5:]==['shell','bm','dump','-n',bundle])
        previous=[v for index,v in bms_calls if index<query_index];following=[v for index,v in bms_calls if index>query_index]
        need(previous and following,'phase BMS before/after independent query')
        fields=spec['roles'][row['role']]['bms']['fields']
        bms=c.bms_fields(bytes.fromhex(previous[-1]['stdout_hex']),bundle,fields)
        need(bms==c.bms_fields(bytes.fromhex(following[0]['stdout_hex']),bundle,fields),'phase BMS identity changed')
        access=c.query_access(bytes.fromhex(query['stdout_hex']),row['role'],row['run'],row['phase'],row['boot_id'],bms)
        joined=c.token_join(protocol.checked(row['token']).read_bytes(),row['role'],row['run'],row['phase'],bms,access)
        need(joined==row['token_join'],'original phase Token raw/independent BMS/query identity differs')
    need([r['role'] for r in collector['napi_phases']]==list(protocol.ROLES),'all three original NAPI phases')
    for row in collector['napi_phases']:
        proof=napi.review(protocol.checked(row['files'][0]).read_bytes(),role=row['role'],run=row['run'],
            owner=row['owner_run'],number=spec['number'],actual_context=row['actual_file_binding']['actual_context'])
        need(proof==row['review'] and row['boot_id']==t['before_boot_id'],'original NAPI proof/raw rewritten')
    index=read(collector['native_chain496_reviews'],protocol)
    need(index['schema']=='number-native496-independent-index/v1' and set(index['roles'])==set(protocol.ROLES),
         'original complete496 index')
    for role,ref in index['roles'].items():
        row=read(ref,protocol)
        need(row.get('failures',[])==[],'original actual496 failure blocks')
        if role!='ordinary':
            bindings=read(row['bindings'],protocol)
            proof=protocol.review_original496(bindings,admitted=admitted,original=original)
            need(row['status']=='checked_native_chain_ONLY' and read(row['proof'],protocol)==proof,
                 'complete original native-chain replay required')
    return dict(root=str(root),source_commit=spec['source_commit'],archive_sha256=spec['archive_sha256'],
        two_boot_ids=[t['before_boot_id'],t['after_boot_id']],held=closure['held_processes'],
        vm=vm,bridge_calls=calls,original_pending_retained=list(collector['pending']))


def source_replay(completed,*,corpus,protocol,original,admitted,project):
    spec=read(completed['spec'],protocol);config=read(completed['config'],protocol)
    source=spec['number580']['sources'];normal=read(source['normal_source'],protocol)
    need(normal['source_commit']==spec['source_commit']==corpus['source_commit'],
         'actual normal source same new clean source HEAD')
    rows=normal['number_local']['sources']
    need(type(rows) is dict and set(rows)=={'produce580.py','project580.py','caller/NumberCorpus580.ets','caller/LegacyNumberCorpus580.js','caller/LegacyNumberCorpus580.d.ts'},'exact normal SDK Number5 physical source closure; other5 protected by original Owner pins/Final authority')
    for name,row in rows.items():
        need(protocol.checked(row)==Path(project.__file__).parent/name,'only fixed normal Number source path')
    need(rows['project580.py']==project.source_materials()['project'],'actual fixed SDK overlay module')
    c=original.original_modules()[0];sdk=[]
    for role in protocol.ROLES:
        item=spec['roles'][role];proof=project.sdk_role_artifacts(item,role,spec['source_commit'],original_collector=c)
        sign=read(item['signing_receipt'],protocol);profile=sign['verified_profile'];bundle,system,get,set_=c.ROLES[role]
        permissions=[name for name,result in ((c.GET,get),(c.SET,set_)) if result==0]
        need(sign['status']=='pass' and sign['scope']=='actual_signature_profile_and_codesign_NOT_guest' and
             sign['role']==role and sign['unsigned_sha256']==item['unsigned_hap']['sha256'] and
             sign['signed_sha256']==item['signed_hap']['sha256'] and
             profile['bundle-info']['bundle-name']==bundle and profile['bundle-info']['apl']==('system_core' if system else 'normal') and
             profile['bundle-info']['app-feature']==('hos_system_app' if system else 'hos_normal_app') and
             profile['acls']['allowed-acls']==permissions and profile['permissions']['restricted-permissions']==permissions,
             'actual signed role source/ACL/system identity differs')
        sdk.append(proof)
    need(all(v['sdk_evidence']==spec['roles'][protocol.ROLES[0]]['sdk_evidence'] for v in sdk),'one actual serial normal SDK receipt')
    need(read(spec['roles'][protocol.ROLES[0]]['sdk_evidence'],protocol)['archive_binding']['normal_source']==source['normal_source'],
         'SDK normal source differs from original spec source')
    account_sdk=project.account_sdk_artifacts(spec['number580']['account_controller'],spec['source_commit'],
        number_sdk=spec['roles']['system-granted']['sdk_evidence'],original_collector=c)
    owners=spec['number580']['observer_owners']
    need(type(owners) is dict and set(owners)=={'build_owner','recheck_owner'},'both actual closed normal native Owners')
    native_inputs=read(completed['observer_proof'],protocol)
    for key,kind in (('build_owner','build'),('recheck_owner','recheck')):
        receipt=read(owners[key],protocol)
        need(receipt['source_commit']==spec['source_commit'] and receipt['exit_code']==0 and
             receipt['cleanup_verified'] is True and receipt['owned_container_absent'] is True and
             not receipt.get('must_resolve_owned_resources_before_next_stage') and
             receipt['build_report_sha256']==native_inputs[kind]['sha256'],
             'actual normal native compile/recheck receipt/source/output differs')
        ledger=read(receipt['resource_ledger'],protocol)
        need(ledger['schema']=='owned-resource35/v1' and ledger['phase']=='closed' and
             ledger['cleanup_verified'] is True and ledger['failed'] is False and ledger['errors']==[],
             'actual normal native CID/lease cleanup ledger')
        container_log=Path(owners[key]['path']).parent/'container.log'
        need(hashlib.sha256(container_log.read_bytes()).hexdigest()==receipt['container_log_sha256'],
             'actual original container command/log changed')
    seeds=corpus['sources']['image_report'];packaged=read(seeds,protocol)
    need(packaged['schema']=='number580-actual-packaged-local-seeds/v1' and
         packaged['source_commit']==spec['source_commit'] and packaged['archive']['sha256']==spec['archive_sha256'],
         'normal packaged seed source/archive proof')
    report=read(packaged['packaged_image_evidence'],protocol)
    need(report['status']=='pass' and report['failures']==[] and
         report['system_image_sha256']==admitted.profile['system_image']['sha256'],'same actual image seed extraction proof')
    bindings0=read(corpus['cases'][0]['bindings'],protocol)
    selection=read(corpus['provider_seed_selection'],protocol);frame=read(selection['frame'],protocol)
    need(selection['schema']=='number580-provider-seed-selection/v1' and selection['pid']==frame['process']['pid'] and
         frame['boot_id']==read(completed['owner_report'],protocol)['collector']['controlled_reboot']['after_boot_id'],
         'post-reset actual provider seed namespace generation')
    need(selection['command'] in bindings0['bridge_calls'] and selection['frame']==bindings0['generation_captures'][1],
         'seed namespace observation must be in the original held case ledger/generation')
    call=read(selection['command'],protocol)
    need(call['argv']==[bindings0['hdc'],'-t',bindings0['target'],'shell',protocol.seed_selection_script(selection['pid'])] and
         call['exit_code']==0 and call['transport_failure'] is False and
         bytes.fromhex(call['stdout_hex'])==protocol.seed_selection_output(selection['pid']),
         'actual process namespace override absence, never bundled seed inference alone')
    prior=original.core.structured_events(bytes.fromhex(frame['hilog_raw_hex']))
    need(not any(v.kind=='native' and v.value['pid']==selection['pid'] and v.value['event']=='query-enter' and
         v.value['route']==1 for v in prior),'previous unobserved location cache load is not seed proof')
    for row in corpus['cases']:
        bindings=read(row['bindings'],protocol)
        need(bindings['build_inputs']==spec['native_consumer_inputs496']['build_inputs'] and
             bindings['system_image']['sha256']==report['system_image_sha256'],'case/source/image inputs differ')
    return dict(source_commit=spec['source_commit'],archive_sha256=spec['archive_sha256'],normal_source=source['normal_source'],
                source_members=rows,sdk=sdk,account_sdk=account_sdk,image_seed_report=seeds)


def readonly_error_replay(bindings,*,protocol,original,admitted,completed):
    spec=read(completed['spec'],protocol);proof=read(spec['number580']['sources']['permission_translation'],protocol)
    need(set(proof)=={'schema','source_commit','archive_sha256','source_export','image_report','installed_profile'} and
         proof['schema']=='number580-actual-permission-translation/v1' and
         proof['source_commit']==spec['source_commit'] and proof['archive_sha256']==spec['archive_sha256'],
         'exact actual source/compile/image permission wrapper')
    raw=read(proof['source_export'],protocol,256*1024*1024);profile=read(proof['installed_profile'],protocol)
    image=read(proof['image_report'],protocol)
    need(raw['schema']=='number580-actual-source-compile-export/v1' and raw['source_commit']==spec['source_commit'] and
         raw['archive_sha256']==spec['archive_sha256'] and raw['source_ro'] is True and raw['out_ro'] is True and
         raw['device']=='phone' and raw['runtime_pass'] is False and
         profile['schema']=='number580-actual-permission-installed-profile/v1' and
         profile['source_export']==proof['source_export'] and profile['source_commit']==spec['source_commit'] and
         profile['archive']['sha256']==spec['archive_sha256'] and
         profile['images']['system']['sha256']==image['system_image_sha256']==admitted.profile['system_image']['sha256'],
         'same actual normal export/new archive/profile/image')
    sources={k:protocol.checked(v).read_bytes() for k,v in raw['sources'].items()}
    need(raw['sources']['number_napi']['sha256']=='36a024778c3057f8f3dbe7ad620e5e8446f47cfe718e71c2d0edf65a92a97582','complete reviewed public201 NAPI product postimage')
    need(set(sources)=={'number_napi','number_errors','mark_ability','core_util','core_errors','js_errors'},'complete precise error-domain source chain')
    need(b'if (errCode == NUMBER_IDENTITY_ERR_PERMISSION_ERR)' in sources['number_napi'] and
         b'errCode = TELEPHONY_ERR_PERMISSION_ERR;' in sources['number_napi'] and
         b'ConverErrorMessageWithPermissionForJs(errCode, funcName, permission)' in sources['number_napi'] and
         b'CHECK_PERMISSION(Permission::SET_TELEPHONY_STATE, NUMBER_IDENTITY_ERR_PERMISSION_ERR)' in sources['mark_ability'] and
         b'if (errorCode == TELEPHONY_ERR_PERMISSION_ERR)' in sources['core_util'] and
         b'error.errorCode = JS_ERROR_TELEPHONY_PERMISSION_DENIED;' in sources['core_util'] and
         re.search(rb'JS_ERROR_TELEPHONY_PERMISSION_DENIED\s*=\s*201\b',sources['js_errors']),
         'actual complete Number-domain to public201 source mapping')
    product=admitted.product
    need(profile['device']=='phone' and profile['profile']['kind']=='installed_number580_permission_dsos' and
         profile['original_profile_unchanged'] is True,'new independent Number permission profile, not runtime15 replacement')
    view=dict(profile['profile'],kind='installed_product_runtime')
    product.validate_installed_profile(view,archive_sha256=spec['archive_sha256'])
    need(set(profile['entries'])=={'libnumber_identity.z.so','libnumberidentity.z.so','libnumberlookup.z.so'}|set(profile['core_util_owners']),
         'Number3 plus actual Core owner exact image roots')
    # Mandatory image roots are independent from TU ownership. Lookup can have
    # no selected permission TU and still requires every real image alias.
    closure={}
    for row in raw['installed_dependency_closure']:
        soname=row['soname'];need(soname not in closure,'duplicate actual installed dependency SONAME')
        closure[soname]=row;file=protocol.checked(row['file'],256*1024*1024)
        need(row['file']['sha256']==row['staged']['sha256'] and row['file']['bytes']==row['staged']['bytes'] and
             product.elf_soname(file,product=profile['product'])==soname and
             set(product.elf_needed(file,product=profile['product']))==set(row['needed']),
             'actual complete staged dependency bytes/SONAME/DT_NEEDED')
    need(set(profile['entries'])<=set(closure) and
         all(set(v['needed'])<=set(closure) for v in closure.values()),'complete closed installed dependency graph')
    for soname,entry in profile['entries'].items():
        row=closure[soname];staged=row['staged']
        need(entry['soname']==soname and entry['staged_file']==row['file'] and entry['aliases'] and
             [v['staged'] for v in entry['aliases']]==row['staged_aliases'] and
             entry['image']==profile['images'][entry['partition']] and
             any(v['image_file']==entry['image_file'] and v['image_member']==entry['image_member'] and
                 v['partition']==entry['partition'] for v in entry['aliases']),
             'every mandatory Number3/Core root canonical image and all aliases, no TU inference')
        for alias in entry['aliases']:
            need(alias['image']==profile['images'][alias['partition']] and type(alias['image_inode']) is int and alias['image_inode']>0 and
                 alias['image_member']==alias['staged']['image_member'] and
                 alias['staged']['sha256']==alias['staged_file']['sha256']==alias['image_file']['sha256']==staged['sha256'] and
                 alias['staged']['bytes']==alias['staged_file']['bytes']==alias['image_file']['bytes']==staged['bytes'],
                 'actual same-archive inode/staged/image alias full byte identities')
            for key in ('image','image_file','staged_file'):protocol.checked(alias[key],16*1024*1024*1024)
            need(product.elf_soname(protocol.checked(alias['image_file'],256*1024*1024),product=profile['product'])==soname,
                 'actual independent image dump SONAME')
        protocol.checked(entry['image_file'],256*1024*1024);protocol.checked(entry['staged_file'],256*1024*1024)
    database=read(raw['complete_compile_commands'],protocol,256*1024*1024)
    ninja_log=protocol.checked(raw['complete_ninja_log'],256*1024*1024).read_text().splitlines()
    query=raw['complete_compile_query']
    need(query['exit_code']==0 and query['timed_out'] is False and query['stdout']==raw['complete_compile_commands'] and
         protocol.checked(query['stderr']).read_bytes()==b'', 'actual complete compdb stdout/stderr/status')
    seen=set()
    required={'number_napi':{'number_napi','number_errors','core_errors','js_errors'},
              'mark_ability':{'mark_ability','number_errors'},'core_util':{'core_util','core_errors','js_errors'}}
    source_root=Path(raw['source_root']);build=source_root/'out'/raw['product']
    def logical_path(value,base):
        need(type(value) is str and value and '\x00' not in value,'actual nonempty command path DATA')
        return posixpath.normpath(value if value.startswith('/') else str(base)+'/'+value)
    need(set(raw['actual_project_heads'])=={'base/telephony/number_identity','base/telephony/core_service'},'exact Number/Core actual project HEAD queries')
    for relative,head in raw['actual_project_heads'].items():
        q=head['query']
        need(q['argv']==['git','-C',str(source_root/relative),'rev-parse','HEAD'] and
             q['exit_code']==0 and q['timed_out'] is False and protocol.checked(q['stderr']).read_bytes()==b'' and
             protocol.checked(q['stdout']).read_text()==head['commit']+'\n' and re.fullmatch('[a-f0-9]{40}',head['commit']),
             'actual full project HEAD command/stdio/status')
        if relative.endswith('number_identity'):need(head['commit']=='50e1330646432ce166e7981c577f25f46c90e7ac','actual fixed Number public revision')
    for record in raw['compile_units']:
        role=record['role'];unit=record['unit'];soname=record['owning_soname']
        need(role in required and unit['source']==raw['sources'][role] and record['source_logical'] in record['dependency_sources'],
             'actual finite source/TU/DSO record')
        command=unit['command'];need(type(command) is list and command.count('-c')==command.count('-o')==1 and
             logical_path(command[command.index('-c')+1],build)==str(source_root/record['source_logical']) and
             logical_path(command[command.index('-o')+1],build)==logical_path(unit['object_logical'],build) and
             logical_path(unit['object_logical'],build)==logical_path(unit['dependency_object'],build),
             'full actual original compiler command DATA; not executed')
        matches=[v for v in database if logical_path(v['file'],v['directory'])==str(source_root/record['source_logical']) and
            (v.get('arguments') if 'arguments' in v else shlex.split(v['command']))==command]
        need(len(matches)==1 and unit['compile_ninja_log_line'] in ninja_log and
             unit['compile_ninja_log_line'].split('\t')[3]==unit['dependency_object'],
             'same original compdb/object/completed Ninja log')
        protocol.checked(unit['object'],256*1024*1024)
        dep=unit['dependency_query'];text=protocol.checked(unit['dependency_file'],64*1024*1024).read_text().splitlines()
        head=re.fullmatch(re.escape(unit['dependency_object'])+r': #deps ([0-9]+), deps mtime [0-9]+ \(VALID\)',text[0] if text else '')
        paths=[v[4:] for v in text[1:] if v.startswith('    ')]
        need(head is not None and len(paths)==int(head[1]) and dep['stdout']==unit['dependency_file'] and
             dep['exit_code']==0 and dep['timed_out'] is False and protocol.checked(dep['stderr']).read_bytes()==b'' and
             dep['argv'][1:]==['-C',str(build),'-t','deps',unit['dependency_object']], 'actual complete VALID Ninja dependency record')
        dependency_bindings=record['dependency_bindings']
        need(type(dependency_bindings) is list and len(dependency_bindings)==len(paths) and
             all(type(v) is dict and set(v)=={'token','logical','file'} for v in dependency_bindings) and
             [v['token'] for v in dependency_bindings]==paths,'full ordered actual Linux dependency token binding, no host symlink rediscovery')
        logical=[v['logical'] for v in dependency_bindings]
        need(all(type(v) is str and not v.startswith('/') and '..' not in Path(v).parts for v in logical) and
             set(logical)==set(record['dependency_sources']) and
             record['compiler_dependencies']==[v['file'] for v in dependency_bindings]==[record['dependency_sources'][v] for v in logical],
             'all dependency paths/Refs exact and ordered, none dropped')
        for row in record['compiler_dependencies']:protocol.checked(row,256*1024*1024)
        for name in required[role]:
            need(raw['sources'][name] in record['compiler_dependencies'],'actual compiled TU does not include exact error source '+name)
        library=raw['libraries'][soname];entry=profile['entries'][soname]
        link=library['link'];q=link['raw_query'];expanded=link['expanded_compdb_query']
        for queryrow in (q,expanded):
            need(queryrow['exit_code']==0 and queryrow['timed_out'] is False and protocol.checked(queryrow['stderr']).read_bytes()==b'',
                 'actual read-only solink query complete split stdout/stderr')
        need(q['argv']==[link['ninja_invoked_path'],'-C',str(build),'-t','query',library['ninja_target']],
             'actual original exact solink query argv')
        lines=protocol.checked(q['stdout']).read_text().splitlines()
        match=re.fullmatch(r'  input: ((?:[A-Za-z0-9_]+_)?solink)',lines[1] if len(lines)>1 else '')
        need(lines and lines[0]==library['ninja_target']+':' and match is not None and
             expanded['argv']==[link['ninja_invoked_path'],'-C',str(build),'-t','compdb','-x',match[1]],
             'actual generated solink rule/expanded query')
        entries=[v for v in read(expanded['stdout'],protocol,256*1024*1024) if v.get('output')==library['ninja_target']]
        need(len(entries)==1 and entries[0]['directory']==str(build),'one actual normal solink entry')
        words=entries[0].get('arguments') if 'arguments' in entries[0] else shlex.split(entries[0]['command'])
        need(words.count('--')==1 and words[words.index('--')+1:]==link['expanded_argv'],'original full wrapper and exact driver DATA')
        for ref in [link['ninja_binary'],link['generated_rule'],*link['grammar_sources'].values()]:protocol.checked(ref,256*1024*1024)
        need(re.search(r'(?m)^rule '+re.escape(match[1])+r'\s*$',protocol.checked(link['generated_rule'],256*1024*1024).read_text()),
             'actual generated product rule source')
        need(unit['effective_CFI'] is True and library['link']['effective_CFI'] is True and
             product.effective_cfi(command) and product.effective_cfi(library['link']['expanded_argv']),
             'actual original permission TU/owning link CFI remains mandatory')
        need(record in library['permission_translation_units'] and
             library['staged']['sha256']==library['linked_output']['sha256']==entry['image_file']['sha256']==record['owning_staged_sha256'],
             'actual linked/staged/independent same-image DSO differs')
        for row in (library['linked_output'],library['installed_file'],entry['image_file']):protocol.checked(row,256*1024*1024)
        need(logical_path(unit['object_logical'],build) in {logical_path(v,build) for v in library['link']['expanded_argv'] if v.endswith('.o')} and
             library['link']['link_ninja_log_line'] in ninja_log,'actual completed solink consumes this exact object')
        seen.add((role,soname))
    need(('number_napi','libnumberidentity.z.so') in seen and ('mark_ability','libnumber_identity.z.so') in seen and
         any(role=='core_util' for role,_ in seen),'all three actual error-domain translation-unit owners')
    events=protocol.rows(protocol.checked(bindings['caller']['journal']).read_bytes(),run=bindings['caller']['run'],
        owner=bindings['caller']['owner_run'],case_id=bindings['caller']['case_id'])
    terminal=[v for v in events if v['step']=='write' and v['event'] in ('rejected','threw','resolved')]
    need(len(terminal)==1 and terminal[0]['event']=='rejected' and terminal[0]['codeKnown'] is True and
         terminal[0]['code']==201 and 'ohos.permission.SET_TELEPHONY_STATE' in terminal[0]['message'],
         'only actual source-bound201 is permission denial;8300999 never passes')
    return dict(schema='number580-permission201-replay/v1',source_export=proof['source_export'],image=proof['image_report'],
        installed_profile=proof['installed_profile'],case_id=bindings['caller']['case_id'],code=201)


def account_replay(ref,*,completed,protocol,original,admitted):
    report=read(ref,protocol);corpus=read(completed['corpus'],protocol);spec=read(completed['spec'],protocol)
    need(report['schema']=='number-account580-raw/v1' and report['source_commit']==spec['source_commit'] and
         report['archive_sha256']==spec['archive_sha256'] and report['owner_run']==corpus['owner_run'] and
         report['number']==spec['number'] and report['failures']==[],'complete actual local account window')
    entries=original.ledger(report['bridge_calls'],report['hdc'],report['target'])
    actions=['accounts','account-create','account-activate','accounts','account-restore','accounts','account-remove','accounts']
    need([v['action'] for v in report['steps']]==actions,'full ordered account lifecycle, not 3roleUID inference')
    created=None;last=0;controller=report['controller'];run=controller['run'];name='org.ohos.qemu.networkwhole579.account'
    role=spec['roles']['system-granted'];number_bundle=original.original_modules()[0].ROLES['system-granted'][0]
    c=original.original_modules()[0]
    need({k:controller[k] for k in ('run','unsigned_hap','signed_hap','signing_receipt','sdk_evidence')}==spec['number580']['account_controller'],
         'same actual signed account controller DATA')
    sign=read(controller['signing_receipt'],protocol);profile=sign['verified_profile']
    permissions=['ohos.permission.MANAGE_LOCAL_ACCOUNTS','ohos.permission.GET_LOCAL_ACCOUNTS',
                 'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']
    root=protocol.checked(completed['owner_report']).parent
    identity=read(actual_file(root/'number-owner/pre-install-profile-UDID.json',protocol),protocol)
    need(sign['status']=='pass' and sign['scope']=='actual_signature_profile_and_codesign_NOT_guest' and
         sign['unsigned_sha256']==controller['unsigned_hap']['sha256'] and sign['signed_sha256']==controller['signed_hap']['sha256'] and
         profile['bundle-info']['bundle-name']==name and profile['bundle-info']['apl']=='system_core' and
         profile['bundle-info']['app-feature']=='hos_system_app' and profile['debug-info']['device-ids']==[identity['udid']] and
         profile['acls']['allowed-acls']==permissions and profile['permissions']['restricted-permissions']==permissions,
         'actual account signature/source/boot UDID permission role')
    actual_owner_calls=owner_replay(completed,protocol=protocol,original=original,admitted=admitted)['bridge_calls']
    for raw in identity['actual_calls']:
        need(any(v['argv']==raw['argv'] and v['exit_code']==raw['exit_code'] and v['stdout_hex']==raw['stdout_hex'] and
             v['stderr_hex']==raw['stderr_hex'] for v in
             actual_owner_calls.values()),
             'original BM UDID raw belongs to the final held ledger')
    def installation(item,bundle,user,hap):
        prefix=[report['hdc'],'-t',report['target']]
        exact_call(item['send'],entries,protocol,prefix+['file','send',hap['path'],item['remote']])
        _,out=exact_call(item['install'],entries,protocol,prefix+['shell','bm','install','-p',item['remote'],'-u',str(user)])
        need(b'install bundle successfully.' in out,'actual user installation acknowledgment')
        _,out=exact_call(item['bms'],entries,protocol,prefix+['shell','bm','dump','-n',bundle,'-u',str(user)])
        bms=c.bms_fields(out,bundle,role['bms']['fields'])
        need(bms['uid']//200000==user and bms['uid']==item['uid'] and bms['token']==item['token'] and bms['systemApp'] is True,
             'independent actual account BMS UID/token/user')
        _,out=exact_call(item['hash'],entries,protocol,prefix+['shell','sha256sum',bms['installedHapPath']])
        need(out.decode().split()==[hap['sha256'],bms['installedHapPath']],'actual installed signed HAP')
    installation(controller,name,100,controller['signed_hap'])
    _,baseline=exact_call(controller['baseline'],entries,protocol,[report['hdc'],'-t',report['target'],'shell','bm','dump','-a'])
    need(name.encode() not in baseline,'no preexisting controller adopted')
    for step in report['steps']:
        argv=[report['hdc'],'-t',report['target'],'shell','aa','start','-b',name,'-a','EntryAbility','-m','entry','-u','100']
        for k in ('run_id','request_id','action'):argv+=['--ps',k,step['request'][k]]
        argv+=['--ps','payload','{}']
        start,_=exact_call(step['start'],entries,protocol,argv)
        need(start['held_index']>last and step['request']['run_id']==run and step['request']['action']==step['action'],
             'actual account actions source nonce/order')
        last=start['held_index'];rows=[]
        for item in step['journals']:
            receive,_=exact_call(item['receive'],entries,protocol)
            need(receive['argv']==[report['hdc'],'-t',report['target'],'file','recv',item['remote'],item['raw']['path']],
                 'actual same-Owner account journal receive')
            values=[protocol.decode(line) for line in protocol.checked(item['raw']).read_bytes().splitlines()]
            need(values and all(v['seq']==i and v['run_id']==run and v['kind']=='systemvpn' and v['role']=='account' and
                 v['bundle']==name and v['uid']==controller['uid'] and str(v['pid']) in Path(item['remote']).name
                 for i,v in enumerate(values)),'actual signed account journal UID/PID/nonce')
            rows.extend(v for v in values if v['request_id']==step['request']['request_id'])
        need(sum(v['event']=='request' for v in rows)==1 and sum(v['event']=='done' for v in rows)==1 and
             not any(v['event'] in ('error','request-error','page-error') for v in rows),'public account action actual success')
        def one(event):
            values=[protocol.decode(v['value']) for v in rows if v['event']==event];need(len(values)==1,'one actual account event '+event);return values[0]
        if step['action']=='account-create':
            created=one('account-created');need(type(created['localId']) is int and created['localId']>100 and
                 created['localName']=='whole579_'+run,'fresh actual Guest account identity')
        elif step['action']=='account-activate':
            v=one('account-activate');need(v['foreground']==created['localId'] and v['owned']['localId']==created['localId'],'actual foreground activation')
        elif step['action'] in ('account-restore','account-remove'):
            v=one(step['action']);need(v['foreground']==100 and v['owned']['localId']==created['localId'],'actual restore/removal owner')
            if step['action']=='account-remove':need(all(v['localId']!=created['localId'] for v in v['accounts']),'owned account really removed')
        else:
            foreground=one('foreground-account');self_id=one('self-account');all_ids=one('accounts')
            need(foreground in (100,created['localId'] if created else 100) and self_id==100,'actual controller self/foreground account')
    installation(report['foreign_install'],number_bundle,created['localId'],role['signed_hap'])
    foreign=protocol.review_account_case(report['foreign_case'],report=report,expected_user=created['localId'],
        protocol=protocol,original=original,admitted=admitted,expected_empty=True)
    restored=protocol.review_account_case(report['restored_case'],report=report,expected_user=100,
        protocol=protocol,original=original,admitted=admitted,expected_empty=False)
    need(report['finally_cleanup']['failures']==[] and report['finally_cleanup']['controller_uninstalled'] is True and
         report['finally_cleanup']['foreign_number_uninstalled'] is True,'actual cleanup must finish before guest reuse')
    for ref in report['finally_cleanup']['calls']:exact_call(ref,entries,protocol)
    scanner=protocol.account_scanner(spec['number580']['sources']['normal_source'],source_commit=spec['source_commit'])
    absence=report['finally_cleanup']['absence']
    need([(v['bundle'],v['uid']) for v in absence]==[(number_bundle,report['foreign_install']['uid']),(name,controller['uid'])],
         'both exact uninstalled identities require raw absence')
    cleanup_indices=[]
    for item in absence:
        need(len(item['series'])==2,'two full independent post-uninstall UID scans')
        for observation in item['series']:
            argv=[report['hdc'],'-t',report['target'],'shell',scanner.snapshot_script(observation['nonce'],report['boot_id'],
                mode='uid',uid=item['uid'],bundle=item['bundle'])]
            call,raw=exact_call(observation['scan'],entries,protocol,argv);cleanup_indices.append(call['held_index'])
            view=scanner.parse_snapshot(raw.decode(),observation['nonce'],report['boot_id'],mode='uid',uid=item['uid'],bundle=item['bundle'])
            need(not any(v['uid']==item['uid'] for v in view['processes'].values()),'uninstalled UID remains alive')
            if item['bundle']==name:need(not view['processes'],'controller process remains alive')
            for key,tail in (('bms',['bm','dump','-a']),('ams',['aa','dump','-a'])):
                call,raw=exact_call(observation[key],entries,protocol,[report['hdc'],'-t',report['target'],'shell',*tail])
                cleanup_indices.append(call['held_index'])
                need(raw.strip() and not re.search(rb'(?<![0-9])'+str(item['uid']).encode()+rb'(?![0-9])',raw),'raw BMS/AMS retains removed UID')
                if item['bundle']==name:need(name.encode() not in raw,'raw BMS/AMS retains controller')
    need(cleanup_indices==sorted(cleanup_indices) and len(set(cleanup_indices))==len(cleanup_indices),'cleanup raw order/independence')
    for item in (controller,report['foreign_install']):
        argv=[report['hdc'],'-t',report['target'],'shell','test ! -e '+item['remote']+' && test ! -L '+item['remote']]
        need(sum(read(v,protocol)['argv']==argv for v in report['finally_cleanup']['calls'])==1,'owned temporary HAP actual absence missing')
    return dict(source_commit=spec['source_commit'],archive_sha256=spec['archive_sha256'],boot_id=report['boot_id'],
        original_user=100,created_user=created['localId'],foreground_restored=100,self_restored=100,
        owned_user_removed=True,cleanup_failures=[],foreign=foreign,restored=restored)


def number580_complete(completed,*,original,admitted,protocol,registration=None,project):
    need(type(completed) is dict and set(completed)==COMPLETED,'six post-finish Refs only; no invented parent wait receipt')
    report=read(completed['owner_report'],protocol);corpus=read(completed['corpus'],protocol);failures=[];proof=None
    try:
        need(corpus['failures']==[] and corpus['cleanup_pending'] is False,'real corpus/uncertain mutation failure')
        owner=owner_replay(completed,protocol=protocol,original=original,admitted=admitted)
        source=source_replay(completed,corpus=corpus,protocol=protocol,original=original,admitted=admitted,project=project)
        expected=[(role,row['id']) for role in protocol.ROLES for row in protocol.cases()]
        need([(v['role'],v['case_id']) for v in corpus['cases']]==expected,'full finite role/corpus mapping')
        cases=[];readonly=[]
        for item in corpus['cases']:
            bindings=read(item['bindings'],protocol)
            need(bindings['archive_sha256']==corpus['archive_sha256'] and bindings['source_commit']==corpus['source_commit'],
                 'actual corpus case belongs to another package/source')
            value=protocol.review_native(bindings,admitted=admitted,original=original)
            need(value==read(item['proof'],protocol),'retained case proof differs from raw replay');cases.append(value)
            if value['public_api_review']['readonly_error_source_replay_still_required']:
                readonly.append(readonly_error_replay(bindings,protocol=protocol,original=original,admitted=admitted,completed=completed))
        account=account_replay(corpus['account'],completed=completed,protocol=protocol,original=original,admitted=admitted)
        proof=dict(owner=owner,source=source,cases=cases,readonly=readonly,account=account)
    except Exception as error:failures.append(type(error).__name__+': '+str(error))
    return dict(schema='number580-local-owner-completion/v1',id=LOCAL_ID,exit_code=int(bool(failures)),failures=failures,
        source_commit=corpus['source_commit'],archive_sha256=corpus['archive_sha256'],
        two_boot_ids=[report['collector']['controlled_reboot']['before_boot_id'],report['collector']['controlled_reboot']['after_boot_id']],
        owner=None if proof is None else dict(root=proof['owner']['root'],held=proof['owner']['held'],
            report=completed['owner_report'],resource_close=completed['owner_closure'],actual_boot=report['actual_guest_boot']),
        proof=proof,original_pending_retained=list(report['collector']['pending']),
        original_failures_retained=list(report['collector']['failures']),required_local_obligations_complete=not failures,
        whole_id_registered=False,aggregate_provider_passed=False,parent_exit_and_lease_release_still_required=True,
        core47_count_changed=False,media48_count_changed=False,first_artifact_behavior_gate_passed=False)


def replay(completed,*,protocol,original,admitted,project):
    need(type(completed) is dict and set(completed)==COMPLETED|{'command_attempt'},'seven final actual Ref inputs')
    before={k:v for k,v in completed.items() if k!='command_attempt'}
    proof=number580_complete(before,original=original,admitted=admitted,protocol=protocol,project=project)
    need(proof['exit_code']==0 and proof['failures']==[],'strict independent local replay failed')
    attempt=read(completed['command_attempt'],protocol)
    need(attempt['schema']=='number580-original499-command-completed/v1' and attempt['source_commit']==proof['proof']['source']['source_commit'] and
         attempt['archive_sha256']==proof['proof']['source']['archive_sha256'] and attempt['exit_code']==0 and
         attempt['timed_out'] is False and attempt['failures']==[] and
         attempt['leader_reaped'] is True and attempt['group_closed'] is True and attempt['lease_released'] is True and
         attempt['marker_absent'] is True and attempt['cleanup_verified'] is True and attempt['must_resolve'] is False,
         'actual parent wait/owned group/lease closure required; staged completion is not final')
    actual=read(attempt['actual_wait'],protocol)
    need(type(actual['pid']) is int and actual['pid']>0 and actual['returncode']==attempt['exit_code'] and
         actual['argv']==attempt['argv'] and actual['reaped'] is True and actual['group_closed'] is True,
         'parent actual Popen.wait receipt/full argv required')
    for k in ('stdout','stderr'):protocol.checked(attempt[k],64*1024*1024)
    need(attempt['completed_input']==before,'final parent command references all exact six completed source/raw Refs')
    proof.update(schema='number580-supported-local-mandatory-replay/v1',parent_exit_and_lease_release_still_required=False,
                 command_attempt=completed['command_attempt'])
    return proof


# Byte-preserved original D2 review function, renamed only; original full source is provenance.
def original_journal_review(raw, run_id, phase, number):
    need(type(raw) is bytes and 0<len(raw)<=1048576,'bounded complete journal required')
    need(re.fullmatch('[a-f0-9]{32}',run_id) and phase in ('cycle','prepare-persist','verify-persist','ordinary-denied','system-denied'),'explicit run/phase required')
    rows=[decode(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    need(1<=len(rows)<=256,'finite actual journal required')
    fields={'scope','run','phase','event','number','detail','code','time','firstArtifactGatePassed','aggregateProviderPassed'}
    for row in rows:
        need(type(row) is dict and set(row)==fields and row['scope']=='local_number_provider_caller_observation_only' and
             (row['run'],row['phase'],row['number'])==(run_id,phase,number) and
             row['firstArtifactGatePassed'] is False and row['aggregateProviderPassed'] is False and
             type(row['code']) is int and type(row['time']) is int and type(row['detail']) is str and type(row['event']) is str,
             'exact actual caller challenge/type/scope binding required')
    events=[row['event'] for row in rows]
    need(events[0]=='begin' and events[-1]=='summary' and events.count('begin')==events.count('summary')==1,'one complete invocation required')
    need(not {'cleanup_failure','close_failure'}&set(events),'caller cleanup/close failure retained; cannot pass content review')
    if phase=='ordinary-denied':
        denied=[r for r in rows if r['event']=='ordinary_system_api_denial_observed']
        failures=[r for r in rows if r['event']=='failure']
        need(len(denied)==len(failures)==1 and denied[0]['code']==failures[0]['code']==202 and
             not {'helper_open','normalized','read','write'}&set(events),'ordinary system-API denial must be exact202 before any provider call')
        boundary='system_API_access_denial_content_only; actual ordinary BMS/UID must be independently proven'
    elif phase=='system-denied':
        evidence=[r for r in rows if r['event']=='system_permission_observation_requires_root_review']
        need(len(evidence)==1 and evidence[0]['code']!=0,'no successful mutation allowed for alleged denied role')
        boundary='unclassified_nonzero_native_result; requires source permission code, actual system-app and denied AccessToken joins'
    else:
        need('failure' not in events and events.count('helper_open')==events.count('helper_closed')==1 and
             rows[-1]['detail']=='observed_requested_local_phase_only','actual successful requested local phase and helper closure required')
        names={'cycle':['created_readback','updated_readback','deleted_readback'],
               'prepare-persist':['created_readback'], 'verify-persist':['persist_readback','persist_deleted_readback']}[phase]
        positions=[events.index(name) for name in names if name in events]
        need(len(positions)==len(names) and positions==sorted(positions),'all actual ordered phase readbacks required')
        writes=[row for row in rows if row['event']=='write'];need(all(row['code']==0 for row in writes),'native business error cannot count as successful mutation')
        normalized=[row['detail'] for row in rows if row['event']=='normalized'];need(len(normalized)==1 and normalized[0],'one real normalization observation required')
        reads=[decode(row['detail']) for row in rows if row['event']=='read']
        for result in reads:
            need(type(result) is dict and set(result)=={'count','number','name','classify','isCloud'} and
                 type(result['count']) is int and result['count'] in (0,1),'exact RDB observation required')
        expected=['created','updated'] if phase=='cycle' else ['persist']
        for suffix in expected:
            matches=[r for r in reads if r['count']==1 and r['number']==normalized[0] and
                     r['name']=='number-local375:'+run_id+':'+suffix and r['classify']=='custom' and
                     type(r['isCloud']) is int and r['isCloud']==0]
            need(matches,'actual challenge-owned local RDB row missing: '+suffix)
        if phase!='prepare-persist':need(reads and reads[-1]['count']==0,'actual final absence required')
        boundary='caller_local_RDB_content_only; genuine same-package/identity/permission/boot/provider evidence remains mandatory'
    return {'journal_structure_valid':True,'scope':boundary,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows),
            'first_artifact_behavior_gate_passed':False,'original_aggregate_finding_closed':False,
            'actual_package_identity_or_runtime_lease_proven_by_this_file':False}



def replay_completed(completed):
    """Final fixed entry: code comes only from the already-admitted siblings.

    No Owner/Authority/guest object is constructed. source_modules() admits and
    loads definitions; admit_normal_observer() replays only existing bytes.
    """
    import importlib.util
    import sys
    need(type(completed) is dict and set(completed)==COMPLETED|{'command_attempt'},'actual final seven Ref inputs')
    path=Path(__file__).resolve().with_name('owner499.py')
    need(path.is_file() and not path.is_symlink() and path.resolve()==path,'fixed sibling original499 source only')
    definition=importlib.util.spec_from_file_location('fixed_number580_final_owner_source',path)
    owner=importlib.util.module_from_spec(definition);definition.loader.exec_module(owner)
    corpus,protocol,registration,project=owner.number580_modules()
    need(Path(registration.__file__).resolve()==Path(__file__).resolve(),'same admitted registration source')
    ownermodule,collector=owner.source_modules()
    config=ownermodule.load_config(completed['config']['path'],completed['config']['sha256'])
    spec=read(completed['spec'],protocol)
    need(spec['source_commit']==owner.SOURCE_COMMIT and spec['archive_sha256']==config['archive']['sha256'],
         'fixed Owner source/new actual archive/spec join')
    profile=dict(path=config['environment']['OHOS_QA_RUNTIME_PROFILE'],
                 sha256=config['environment']['OHOS_QA_RUNTIME_PROFILE_SHA256'],
                 bytes=Path(config['environment']['OHOS_QA_RUNTIME_PROFILE']).stat().st_size)
    product,context,elf_reader=protocol.normal_modules(spec['number580']['sources']['normal_source'],source_commit=owner.SOURCE_COMMIT)
    admitted=protocol.admit_normal_observer(read(completed['observer_proof'],protocol),profile_descriptor=profile,
        archive_sha256=config['archive']['sha256'],product=product,context=context,elf_reader=elf_reader,
        normal_source=spec['number580']['sources']['normal_source'])
    return replay(completed,protocol=protocol,original=owner.native_module496(),admitted=admitted,project=project)
