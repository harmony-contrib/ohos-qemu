"""Completed same-source provider evidence. Pure file replay, no runtime gate.

Historical native08/package09 stays in its original canonical checker. Reuse
requires its real proof; native completion never claims fresh HAP ArkTS epochs.
"""
from pathlib import Path, PurePosixPath
import hashlib,json,re,shlex,tarfile
from batch_apps_production_provider_binding import (SOURCE, PRODUCT, require, sha,
    regular, record, checked, decode, tree_digest, graph_actions, public_commands, option)
ROOT=Path(__file__).resolve().parents[2]
KIND='completed_same_source_native_provider15/v1'
FIELDS={'schema_version','kind','expected_source_commit','qa_root','producer_sources','archive',
        'native_evidence','native_launcher_log','native_build_log','exports','export_receipt','historical_reuse'}
PROVIDERS={
 'contacts':('applications/standard/contacts','contacts_hap','Contacts','entry','entry/build/default/outputs/default/entry-default-unsigned.hap','entry/src/main/module.json5'),
 'theme':('applications/standard/theme','wallpaper_phone_hap','Wallpaper','phone_wallpaper','product/phone/build/default/outputs/default/phone_wallpaper-default-unsigned.hap','product/phone/src/main/module.json5')}
RUNNERS=('build/scripts/compile_app.py','build/scripts/app_sign.py','build/scripts/check_hvigor_hap.py',
 'build/templates/metadata/gen_module_info.py','build/ohos/app/app.gni','build/ohos/app/app_internal.gni')
# Exact reviewed code bodies, not an epoch or output identity. Root selects their
# actual current paths; old private15 bootstrap and retired checkout are unused.
PRODUCER_SOURCE_SHA256={
 'exporter':'6452fb5e2edd2d82a927e44d81c359206fa92e84a91e4a2e48540d4f337f7f4b',
 'collector':'8192272c0a961a6de98eb439b5ea25fac986728b68ebb5343a3770785abb3441'}

def archive_inputs(path):
    """Hash actual archive members, retaining only bounded JSON metadata."""
    from boot_package import members_checked
    root=Path(path).name.removesuffix('.tar.gz');members=[];hashes={};documents={}
    selected={'build-inputs.json','openharmony-project-heads.json','contacts-theme-provider-evidence.json',
              'contacts-native-image-evidence.json','wallpaper-native-image-evidence.json',
              'contacts-native/inventory.json','contacts-native/witness.json',
              'wallpaper-native/inventory.json','wallpaper-native/witness.json','SHA256SUMS','images/system.img'}
    with tarfile.open(path,'r|gz') as archive:
        for item in archive:
            members.append(item);require(len(members)<50000,'bounded actual archive required')
            p=PurePosixPath(item.name)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in item.name and p.parts and p.parts[0]==root,
                    'unsafe current package member')
            name='/'.join(p.parts[1:])
            if item.isdir():continue
            if not (name in selected or name.startswith(('contacts-native/','wallpaper-native/'))):continue
            require(item.isfile() and name not in hashes and item.size <= (8*1024**3 if name=='images/system.img' else 256*1024**2),
                    'duplicate/nonregular/oversized provider archive evidence')
            digest=hashlib.sha256();raw=[];retain=name in selected and name!='images/system.img'
            require(not retain or item.size<=8*1024**2,'bounded selected package JSON/checksums required')
            stream=archive.extractfile(item);count=0
            for block in iter(lambda:stream.read(1048576),b''):
                digest.update(block);count+=len(block)
                if retain:raw.append(block)
            require(count==item.size,'short actual archive evidence');hashes[name]=digest.hexdigest()
            if retain:documents[name]=b''.join(raw)
    members_checked(members,root)
    require(selected <= hashes.keys(),'complete current package/provider/native provenance required')
    sums={}
    for line in documents['SHA256SUMS'].decode().splitlines():
        match=re.fullmatch(r'([a-f0-9]{64}) [ *](?:\./)?(.+)',line)
        require(match and match[2] not in sums,'unambiguous actual package checksum list required');sums[match[2]]=match[1]
    for name,digest in hashes.items():
        if name!='SHA256SUMS':require(sums.get(name)==digest,'archive native/provider member differs from complete checksums')
    return {name:decode(raw) for name,raw in documents.items() if name!='SHA256SUMS'},hashes


def selected_unsigned_path(value,project,unsigned_relative):
    """Accept only the two actual compile_app spellings, without path resolution."""
    require((project,unsigned_relative) in {(row[0],row[4]) for row in PROVIDERS.values()},
            'only the fixed selected provider unsigned output is supported')
    canonical=SOURCE+'/'+project+'/'+unsigned_relative
    project_dot=SOURCE+'/'+project+'/./'+unsigned_relative
    require(type(value) is dict and set(value)=={'unsigned_hap_path_list'} and
        type(value['unsigned_hap_path_list']) is list and len(value['unsigned_hap_path_list'])==1 and
        type(value['unsigned_hap_path_list'][0]) is str and value['unsigned_hap_path_list'][0] in (canonical,project_dot),
        'actual selected unsigned production output differs')
    token=value['unsigned_hap_path_list'][0]
    return {'raw_token':token,'canonical_source_path':canonical,
            'allowed_form':'project_dot' if token==project_dot else 'canonical'}


def native_completion(evidence, launcher, expected, archive, tree):
    value=decode(checked(evidence).read_bytes());text=checked(launcher).read_text()
    require(value.get('source_commit')==expected and type(value.get('exit_code')) is int and value['exit_code']==0 and
            not value.get('timed_out') and not value.get('error') and not value.get('cleanup_error') and
            value.get('owned_launcher_group_closed') is True and value.get('cleanup_verified') is True and
            value.get('resource_lease_held') is False and
            value.get('owned_container_absent') is True and checked(value['launcher_log'])==checked(launcher) and
            value.get('package',{}).get('sha256')==sha(archive) and value.get('tree_sha256')==tree and
            value.get('adopted_complete_host_environment',{}).get('PREPARE_ONLY')=='0' and value['adopted_complete_host_environment'].get('BUILD_ONLY_LOAD')=='0',
            'actual completed-zero same-source native/images/package attempt required')
    resources=native376_resources(value,checked(launcher),expected,tree)
    require(checked(value['package'])==archive, 'actual native archive descriptor differs')
    lines=re.sub(r'\x1b\[[0-9;]*m','',text).splitlines();starts=[i for i,line in enumerate(lines) if line.startswith('Build args: ')]
    selected=[]
    for n,start in enumerate(starts):
        argv=shlex.split(lines[start][len('Build args: '):]);end=starts[n+1] if n+1<len(starts) else len(lines)
        if '--build-only-load=false' not in argv:continue
        require([v for v in argv if v.startswith('--build-only-load=')]==['--build-only-load=false'] and
                option(argv,'--product-name')==PRODUCT and option(argv,'--device-type')=='phone' and
                option(argv,'--build-target')=='images','actual native terminal belongs to another product/device')
        hits=[i for i in range(start+1,end) if re.fullmatch(r'\[OHOS INFO\]\s+arm64_virt build success\s*',lines[i])]
        require(len(hits)==1,'one actual native images success within the selected frontend phase required')
        footer=lines[hits[0]+1] if hits[0]+1<end else ''
        require(re.fullmatch(r'\[OHOS INFO\]\s+Cost Time:\s+[0-9]+:[0-9]{2}:[0-9]{2}\s*',footer),'native success cost footer missing')
        selected.append({'build_args_line':start+1,'success_line':hits[0]+1,'cost_footer':footer})
    require(len(selected)==1,'unique actual native images phase required')
    selected[0]['resource_observation']=resources
    return value,selected[0]



def witness_phase_binding(text,witness,frontend):
    """Join the actual packaged nonce to this launcher's prepare/native/finish order."""
    matches={'prepared':[],'completed':[]}
    for index,line in enumerate(re.sub(r'\x1b\[[0-9;]*m','',text).splitlines(),1):
        if not line.startswith('{'):continue
        try:row=decode(line)
        except (ValueError,TypeError):continue
        if isinstance(row,dict) and row.get('nonce')==witness['nonce'] and row.get('phase') in matches:
            require(row.get('product')==PRODUCT,'native nonce reported for another product')
            matches[row['phase']].append(index)
    require(len(matches['prepared'])==len(matches['completed'])==1 and
        matches['prepared'][0]<frontend['build_args_line']<frontend['success_line']<matches['completed'][0],
        'packaged witness nonce is not prepared/native-success/completed in this actual launcher')
    return {'prepared_line':matches['prepared'][0],'completed_line':matches['completed'][0]}


def exports_checked(path, native_evidence, producer_sources):
    document=decode(path.read_bytes());require(document.get('schema_version')==1 and document.get('source_root')==SOURCE and
        document.get('product')==PRODUCT and checked(document.get('native_evidence'))==checked(native_evidence) and
        document.get('source_out_readonly') is True and document.get('inputs_unchanged') is True,
        'actual completed-build read-only producer export required')
    exporter=document.get('exporter',{})
    require(checked(exporter)==checked(producer_sources['exporter']) and
        exporter['sha256']==PRODUCER_SOURCE_SHA256['exporter'],
        'producer export was not bound to the reviewed private exporter source')
    rows=document['files'];result={}
    for row in rows:
        name=row['path'];require(name.startswith(SOURCE+'/') and row.get('resolved')==name and
            '..' not in PurePosixPath(name).parts and row['export_relative']=='files/'+name.removeprefix(SOURCE+'/'),
            'unaliased producer export with exact original path required')
        actual=regular(path.parent/row['export_relative'])
        require(sha(actual)==row['sha256'] and actual.stat().st_size==row['bytes'],'actual exported bytes changed')
        require(name not in result,'duplicate producer export');result[name]=(row,actual)
    return document,result


def classify_action(text,project,module,compile_label,sign_label):
    lines=text.splitlines();groups={}
    for line in lines:
        match=re.search(r'\[([a-f0-9]{8})\] project dir: (.+)$',line)
        if match and match[2]==SOURCE+'/'+project:groups[match[1]]=[]
    for tag in groups:groups[tag]=[line for line in lines if '['+tag+']' in line]
    require(len(groups)<=1,'ambiguous current production compile trace')
    compile_progress=any(compile_label in line for line in lines);sign_progress=any(sign_label in line for line in lines)
    if not groups:
        require(not compile_progress,'selected compile action has no actual retained Hvigor stdout')
        return {'mode':'current_ninja_incremental_reuse','compile_action_observed':False,
                'sign_action_observed':sign_progress,'fresh_es2abc_claimed':False,'current_CompileArkTS_UP_TO_DATE':None}
    tag,rows=next(iter(groups.items()));commands=[line.split('hvigor cmd: ',1)[1] for line in rows if 'hvigor cmd: ' in line]
    require(len(commands)==1 and compile_progress,'actual current selected Hvigor command/action required')
    argv=shlex.split(commands[0])
    expected=['bash',SOURCE+'/prebuilts/tool/command-line-tools/6.x/hvigor/bin/hvigorw','assembleHap',
        '--mode','module','-p','product=default','-p','module='+module,'-p','debuggable=false',
        '-p','buildMode=release','--no-daemon']
    require(argv==expected,'current selected Hvigor module/options differ')
    require(any('BUILD SUCCESSFUL' in line for line in rows),'current production Hvigor action did not complete')
    cached=any('UP-TO-DATE :'+module+':default@CompileArkTS' in line for line in rows)
    return {'mode':'current_hvigor_action_cached_ArkTS' if cached else 'current_hvigor_action_completed_freshness_unproven',
            'trace_tag':tag,'hvigor_argv':argv,'compile_action_observed':True,'sign_action_observed':sign_progress,
            'current_CompileArkTS_UP_TO_DATE':cached,'fresh_es2abc_claimed':False}


def same_source_inventory(previous,current):
    """Compare the retained full public inventory; do not infer old missing bytes."""
    require(isinstance(previous,dict) and previous and isinstance(current,dict) and set(previous)==set(current),
            'public production source inventory changed since retained historical producer snapshot')
    for name,row in previous.items():
        require(row['sha256']==current[name]['sha256'] and row['bytes']==current[name]['bytes'],
                'current source bytes differ from historical producer input snapshot: '+name)
    return len(previous)


def historical_equivalence(historical,current,source_inventory,commands,unsigned,provider_name,graph):
    """Replay the actual old producer proof without asserting its ArkTS generation epoch."""
    import batch_apps_production_provider_binding as old
    require(isinstance(historical,dict) and set(historical)=={'config','image_signed_hap','system_image_sha256'},
            'incremental unchanged HAP requires the actual retained historical producer configuration')
    previous=old.verify_production_provider(historical['config'],provider_name=provider_name,device='phone',
        signed_hap=checked(historical['image_signed_hap']),system_image_sha256=historical['system_image_sha256'])
    first=old.decode(old.checked(historical['config']['discovery']).read_bytes())
    second=old.decode(old.checked(historical['config']['supplement']).read_bytes())
    inventory=first['source_inventory'][provider_name]
    same_source_inventory(inventory,source_inventory)
    require(sha(unsigned)==previous['production_unsigned_hap']['sha256'],'incremental unsigned HAP differs from actual historical compiled artifact')
    require(public_commands(commands)==previous['commands'],'selected production compile/sign/module graph command changed')
    original=old.retained_exports(second['files'],old.checked(historical['config']['supplement']).parent)
    compared=[];unmeasured=[]
    for name,(row,path) in current.items():
        relative=name.removeprefix(SOURCE+'/')
        if relative.startswith(('build/','developtools/','prebuilts/')) and name in original:
            require(row['sha256']==original[name][0]['sha256'],'retained producer runner/public tool changed: '+relative)
            compared.append(relative)
        elif relative.startswith(('build/','developtools/','prebuilts/')):unmeasured.append(relative)
    require(set(RUNNERS)<=set(compared),'actual historical public runner closure missing from current export')
    return {'scope':'unchanged current source+unsigned artifact reuse against the actual retained historical producer proof',
        'historical_proof':previous,'source_entries_equal':len(inventory),'selected_commands_equal':True,
        'raw_current_graph':record(graph),'historically_recorded_runner_tools_equal':sorted(compared),
        'current_tools_without_historical_byte_measurement':sorted(unmeasured),
        'complete_historical_SDK_or_Node_byte_closure_claimed':False,
        'historical_ArkTS_generation_epoch_established':False,'fresh_es2abc_claimed':False}


def verify_completed_provider(config, *, provider_name, device, signed_hap, system_image_sha256):
    """Capture and independent replay call this exact new API; old F schema is rejected."""
    base=canonical_context(config)
    require(isinstance(config,dict) and set(config)==FIELDS and type(config['schema_version']) is int and
        config['schema_version']==1 and config['kind']==KIND and provider_name in PROVIDERS and device=='phone' and
        config['expected_source_commit']==base['source_commit'],'explicit new same-source production15 configuration required')
    paths={key:checked(config[key]) for key in ('archive','native_evidence','native_launcher_log','native_build_log','exports')}
    metadata,hashes=archive_inputs(paths['archive']);inputs=metadata['build-inputs.json']
    from snapshot_build_inputs import digest_files
    require(inputs.get('source_git_revision')==config['expected_source_commit'] and
        tree_digest(inputs['files_sha256'])==inputs['tree_sha256'] and
        inputs['files_sha256']==digest_files(Path(base['tools_root'])),
        'actual canonical new F build-inputs identity or exact current frozen tree differs')
    require(hashes['images/system.img']==system_image_sha256,'actual current image differs from new archive')
    native,phase=native_completion(config['native_evidence'],config['native_launcher_log'],config['expected_source_commit'],paths['archive'],inputs['tree_sha256'])
    verify_export_receipt(config, paths, inputs)
    export,files=exports_checked(paths['exports'],config['native_evidence'],config['producer_sources'])
    def artifact(relative):
        require(SOURCE+'/'+relative in files,'actual new producer export missing: '+relative)
        return files[SOURCE+'/'+relative][1]
    project,target,title,module,unsigned_relative,module_relative=PROVIDERS[provider_name]
    inventory=export['providers'][provider_name]['source_inventory']
    require(inventory and all(row['path']==SOURCE+'/'+project+'/'+name for name,row in inventory.items()),'actual complete source inventory paths differ')
    for name,row in inventory.items():require(sha(artifact(project+'/'+name))==row['sha256'],'actual current complete source bytes changed: '+name)
    heads=metadata['openharmony-project-heads.json'];selected=[row for row in heads['projects'] if row['path']==project]
    require(heads['status']=='pass' and len(selected)==1 and re.fullmatch('[a-f0-9]{40}',selected[0].get('revision','')) and selected[0]['revision']==selected[0]['observed_head'],
            'actual new package project source HEAD not pinned')
    prefix='out/'+PRODUCT+'/obj/'+project+'/'+target;stem='obj/'+project+'/'+target
    unsigned_list=decode(artifact(prefix+'/unsigned_hap_path_list.json').read_bytes())
    unsigned_selection=selected_unsigned_path(unsigned_list,project,unsigned_relative)
    unsigned=artifact(project+'/'+unsigned_relative);produced=artifact(prefix+'/'+title+'.hap')
    bundle='com.ohos.contacts' if provider_name=='contacts' else 'com.ohos.wallpaper'
    staged=artifact('out/'+PRODUCT+'/packages/phone/system/app/'+bundle+'/'+title+'.hap')
    guard=metadata['contacts-theme-provider-evidence.json'];signed_hap=regular(signed_hap)
    require(guard['status']=='pass' and guard['failures']==[] and guard['device']==device and
        guard['system_image_sha256']==system_image_sha256 and sha(produced)==sha(staged)==sha(signed_hap)==guard['providers'][provider_name]['hap_sha256'],
        'actual new produced/staged/image signed provider chain differs')
    info=decode(artifact(prefix+'_module_info.json').read_bytes());install=decode(artifact(prefix+'_install_info.json').read_bytes())
    label='//'+project+':'+target+'(//build/toolchain/ohos:ohos_clang_arm64)'
    require(info['source']==stem and info['dest']==['system/app/'+bundle+'/'] and info['install_enable'] is True and
        info['label']==label and info['label_name']==target and info['part_name']=='prebuilt_hap' and info['type']=='app' and
        install==[{'module_def':label,'module_info_file':stem+'_module_info.json','part_name':'prebuilt_hap',
                   'subsystem_name':'applications','toolchain':'//build/toolchain/ohos:ohos_clang_arm64','toolchain_out_dir':'.'}],
        'actual compiled-to-sign-to-staging installation mapping differs')
    graph=artifact('out/'+PRODUCT+'/toolchain.ninja');commands,edges=graph_actions(graph,project,target)
    require(option(commands['compile'],'--build-modules')==module,'actual production selected module differs')
    for flag,value in {'--unsigned-hap-path-list':stem+'/unsigned_hap_path_list.json','--hap-out-dir':stem,'--hap-name':title,
        '--hap-list':stem+'/hap_list.json','--profileFile':'../../'+project+'/signature/'+('contacts.p7b' if provider_name=='contacts' else 'wallpaper.p7b'),
        '--hapsigner':'../../developtools/hapsigner/dist/hap-sign-tool.jar'}.items():
        require(option(commands['sign'],flag)==value,'actual producer signing input differs')
    require(SOURCE+'/'+prefix+'/hap_list.json' in export['absent'],'unreviewed production HAP rename/filter selection')
    # Native library witnesses remain native witnesses; they never claim HAP ArkTS freshness.
    witness_records={}
    for family,script in [('contacts','qemu_contacts_build_witness'),('wallpaper','qemu_wallpaper_build_witness')]:
        guard_module=__import__(script);inv=metadata[family+'-native/inventory.json'];witness=metadata[family+'-native/witness.json']
        require(inv['product']==PRODUCT and inv['recipe']==guard_module.recipe() and witness['phase']=='completed' and
            re.fullmatch('[a-f0-9]{32}',witness.get('nonce','')) and type(witness.get('start_ns')) is int and type(witness.get('finished_ns')) is int and 0<witness['start_ns']<witness['finished_ns'],
            'actual current native recipe/fresh completed witness required')
        expected={family+'-native/'+name:digest for name,digest in inv['files_sha256'].items()}
        actual={name:digest for name,digest in hashes.items() if name.startswith(family+'-native/') and name!=family+'-native/inventory.json'}
        require(expected==actual,'complete packaged native witness payload map differs')
        image=metadata[family+'-native-image-evidence.json'];require(image['status']=='pass' and
            image['system_image_sha256']==system_image_sha256 and image['inventory_sha256']==hashes[family+'-native/inventory.json'],
            'native witness image binding differs')
        ordered=witness_phase_binding(paths['native_launcher_log'].read_text(),witness,phase)
        witness_records[family]={'inventory_sha256':hashes[family+'-native/inventory.json'],'nonce':witness['nonce'],
            'launcher_order':ordered,'scope':inv['scope'],'HAP_ArkTS_compile_claimed':False}
    require(hashes['contacts-native/graph/toolchain.ninja']==sha(graph),'actual provider graph is not the graph of this packaged native attempt')
    require(hashes['contacts-native/execution-log.txt']==sha(paths['native_build_log']), 'actual detailed product log differs from this package witness')
    text=paths['native_build_log'].read_text()
    action=classify_action(text,project,module,'ACTION //'+project+':'+target+'_compile_app(', 'ACTION //'+project+':'+target+'(')
    reuse=None
    if action['mode'] in ('current_ninja_incremental_reuse','current_hvigor_action_cached_ArkTS'):
        reuse=historical_equivalence(config['historical_reuse'],files,inventory,commands,unsigned,provider_name,graph)
    from batch_apps_contact_picker_coordinator import verify_signed_payload
    verify_signed_payload(unsigned,signed_hap)
    return {'schema_version':1,'kind':KIND,'scope':'actual completed current incremental native/images/package + honest producer HAP source lineage; NOT guest',
        'source_commit':config['expected_source_commit'],'archive':record(paths['archive']),'system_image_sha256':system_image_sha256,
        'native_evidence':record(paths['native_evidence']),'native_launcher_log':record(paths['native_launcher_log']),
        'native_frontend_phase':phase,'native_build_log':record(paths['native_build_log']),'producer_exports':record(paths['exports']),
        'source_project':project,'source_revision':selected[0]['revision'],'source_module':record(artifact(project+'/'+module_relative)),
        'source_entries_verified':len(inventory),'source_inventory_sha256':tree_digest({k:v['sha256'] for k,v in inventory.items()}),
        'production_unsigned_hap':record(unsigned),'production_signed_hap':record(produced),'staged_signed_hap':record(staged),
        'image_signed_hap_sha256':sha(signed_hap),'unsigned_path_list':record(artifact(prefix+'/unsigned_hap_path_list.json')),
        'unsigned_path_selection':unsigned_selection,
        'module_info':record(artifact(prefix+'_module_info.json')),'install_info':record(artifact(prefix+'_install_info.json')),
        'graph':record(graph),'commands':public_commands(commands),'edges':edges,'public_runners':{p:record(artifact(p)) for p in RUNNERS},
        'current_exported_public_tool_observations':{name:record(path) for name,(row,path) in files.items()
            if name.removeprefix(SOURCE+'/').startswith(('developtools/','prebuilts/'))},
        'current_action_classification':action,'historical_reuse':reuse,'native_library_witnesses':witness_records,
        'build_inputs_tree_sha256':inputs['tree_sha256'],'fresh_es2abc_claimed':False,'runtime_validated':False,
        'first_artifact_behavior_gate_passed':False, 'canonical_checker':record(Path(__file__))}



def checkout_head(qa):
    """Read only the worktree's actual metadata; never invoke Git."""
    dot=Path(qa)/'.git'
    if dot.is_file():
        line=dot.read_text().strip();require(line.startswith('gitdir: '),'actual worktree gitdir metadata required')
        gitdir=Path(line.removeprefix('gitdir: '))
        if not gitdir.is_absolute():gitdir=dot.parent/gitdir
        gitdir=gitdir.resolve()
    else:
        require(dot.is_dir(),'actual QA checkout metadata required');gitdir=dot.resolve()
    head=(gitdir/'HEAD').read_text().strip()
    if head.startswith('ref: '):
        reference=head.removeprefix('ref: ')
        require(re.fullmatch(r'refs/[A-Za-z0-9_./-]+',reference)and '..'not in Path(reference).parts,'safe HEAD ref required')
        common=(gitdir/(gitdir/'commondir').read_text().strip()).resolve()if(gitdir/'commondir').is_file()else gitdir
        candidates=[directory/reference for directory in (gitdir,common)if(directory/reference).is_file()]
        if candidates:
            values={p.read_text().strip()for p in candidates};require(len(values)==1,'ambiguous QA HEAD ref');head=values.pop()
        else:
            packed=common/'packed-refs';matches=[]
            if packed.is_file():
                matches=[line.split()[0]for line in packed.read_text().splitlines()if line and not line.startswith(('#','^'))and line.split()[1:]==[reference]]
            require(len(matches)==1,'actual QA HEAD ref missing');head=matches[0]
    require(re.fullmatch('[a-f0-9]{40}',head),'actual full QA HEAD required')
    return head


# Actual376 PREPARE supplies engine/image defaults only; never native/images success.
ENGINE376={'provenance': {'receipt': {'path': '/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r60-canonical-first-arm64-phone-prepare-376-01/evidence.json', 'sha256': '09fff0558a76687d815a64647270a994964011ddf27329156d1d2f631c23baf4', 'bytes': 14784}, 'inspect_stdout': {'path': '/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r60-canonical-first-arm64-phone-prepare-376-01/0005-discover-build-4-stdout.bin', 'sha256': '9e4406aebd728623276afcfdf490e5b045e64bf753934709c9cb48163e8d4225', 'bytes': 19930}, 'scope': 'engine/image defaults only; actual PREPARE is not a completed native/images/package or runtime positive'}, 'config': {'Domainname': '', 'User': 'root', 'AttachStdin': False, 'AttachStdout': True, 'AttachStderr': True, 'Tty': False, 'OpenStdin': False, 'StdinOnce': False, 'Image': 'sha256:8f7a960c7dc515a597d43a510d6d8a5e634e5c94a55aa5d9e22bfbf6b0f42c55', 'Volumes': None, 'Entrypoint': None}, 'host': {'LogConfig': {'Type': 'json-file', 'Config': {'max-file': '5', 'max-size': '20m'}}, 'PortBindings': {}, 'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'VolumeDriver': '', 'VolumesFrom': None, 'ConsoleSize': [0, 0], 'CapAdd': None, 'CgroupnsMode': 'private', 'Dns': None, 'DnsOptions': [], 'DnsSearch': [], 'ExtraHosts': None, 'GroupAdd': None, 'IpcMode': 'private', 'Cgroup': '', 'Links': None, 'OomScoreAdj': 0, 'PidMode': '', 'Privileged': False, 'PublishAllPorts': False, 'UTSMode': '', 'UsernsMode': '', 'ShmSize': 8409579520, 'Runtime': 'runc', 'Isolation': '', 'CpuShares': 0, 'CgroupParent': '', 'BlkioWeight': 0, 'BlkioWeightDevice': [], 'BlkioDeviceReadBps': [], 'BlkioDeviceWriteBps': [], 'BlkioDeviceReadIOps': [], 'BlkioDeviceWriteIOps': [], 'CpuPeriod': 0, 'CpuQuota': 0, 'CpuRealtimePeriod': 0, 'CpuRealtimeRuntime': 0, 'CpusetCpus': '', 'CpusetMems': '', 'Devices': [], 'DeviceCgroupRules': None, 'DeviceRequests': None, 'MemoryReservation': 0, 'MemorySwappiness': None, 'OomKillDisable': None, 'Ulimits': [{'Name': 'nofile', 'Hard': 1048576, 'Soft': 1048576}], 'CpuCount': 0, 'CpuPercent': 0, 'IOMaximumIOps': 0, 'IOMaximumBandwidth': 0, 'MaskedPaths': ['/proc/acpi', '/proc/asound', '/proc/interrupts', '/proc/kcore', '/proc/keys', '/proc/latency_stats', '/proc/sched_debug', '/proc/scsi', '/proc/timer_list', '/proc/timer_stats', '/sys/devices/virtual/powercap', '/sys/firmware'], 'ReadonlyPaths': ['/proc/bus', '/proc/fs', '/proc/irq', '/proc/sys', '/proc/sysrq-trigger']}, 'native_env': ['ARMV7A_PRODUCT_COMPONENT=1', 'BUILD_JOBS=2', 'BUILD_ONLY_LOAD=0', 'CACHE_ROOT=/Volumes/PSSD/qemu', 'CCACHE_DIR=/Volumes/PSSD/qemu/ccache', 'CCACHE_MAXSIZE=4G', 'CONTAINER_HOME=/Volumes/PSSD/qemu/home', 'DEVICE_TYPE=phone', 'DEVICE_TYPE_BUILD_PROFILE=qemu_phone_full_source', 'HTTPS_PROXY=http://host.docker.internal:7890', 'HTTP_PROXY=http://host.docker.internal:7890', 'JSVM_ENGINE_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/jsvm', 'KERNEL_BUILD_JOBS=2', 'LANG=C.UTF-8', 'LC_ALL=C.UTF-8', 'MANIFEST_REVISION=f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549', 'NOFILE_LIMIT=1048576', 'NO_PREBUILT_SDK=0', 'NO_PROXY=github.com,.github.com,githubusercontent.com,.githubusercontent.com', 'OHOS_BRANCH=OpenHarmony-7.0-Release', 'OHOS_FALLBACK_MIRROR_ROOT=/Volumes/PSSD/qemu/git-mirrors/openharmony-7.0-release', 'OHOS_GITHUB_FALLBACK=1', 'OHOS_LFS_ASSET_ROOT=/Volumes/PSSD/qemu/artifacts/openharmony-7.0-lfs', 'OHOS_PROJECT_MIRROR=https://github.com/openharmony/', 'OHOS_ROOT=/Volumes/PSSD/qemu/openharmony', 'OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE=0', 'PACKAGE_ROOT=/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r60-canonical-first-arm64-phone-prepare-376-01/no-packages-prepare-only', 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'PREPARE_ONLY=1', 'PRUNE_PRODUCT_OUT_AFTER_PACKAGE=0', 'QEMU_2IN1_PROFILE_COMPONENT=0', 'QEMU_ABSOLUTE_POINTER_COMPONENT=1', 'QEMU_ACCESSIBILITY_COMPONENT=1', 'QEMU_ARKWEB_CORE_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/arkweb-m144-7.0/5bce1a80ba4889a189960c57336fd4c400ab684f8ff79ff4dca76bed95b55e37-375-02', 'QEMU_AVC_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/avc', 'QEMU_BUILD_INPUT_MANIFEST=/work/build-inputs.json', 'QEMU_CCACHE_ON_OUT_VOLUME=1', 'QEMU_FIX_ACCESS_TOKENID_ABI=1', 'QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK=1', 'QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION=1', 'QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN=1', 'QEMU_FIX_SYSTEM_COMPAT_SYMLINKS=1', 'QEMU_FIX_VIRTIOFS_KERNEL_COPY=1', 'QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY=1', 'QEMU_HOST_GN_QEMU_USER=1', 'QEMU_JSVM_COMPONENT=1', 'QEMU_KNOWLEDGE_ICS=/qemu-inputs/knowledge/holidays.ics', 'QEMU_MESA_LLVM_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/qemu-mesa-llvm/634e042f0532266d934ad4c6ee9cc52a85695f49f8079e7303ec57f1a0981cdd', 'QEMU_MESA_REVISION_CACHE=/Volumes/PSSD/qemu/git-mirrors/qemu-mesa/third_party_mesa3d.git', 'QEMU_PHONE_PROFILE_COMPONENT=1', 'QEMU_QOS_COMPONENT=1', 'QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR=1', 'QEMU_SERIAL_SOURCE_REPO=/Volumes/PSSD/qemu/git-mirrors/busmanager_serial_manager.c05fbbf.git', 'QEMU_VIBRATOR_COMPONENT=1', 'QEMU_VULKAN_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/swiftshader', 'QEMU_VULKAN_COMPONENT=1', 'REPO_CHECKOUT_JOBS=4', 'REPO_JOBS=16', 'SCENEBOARD_RUNTIME_ASSET_ROOT=/Volumes/PSSD/qemu/artifacts/sceneboard-runtime', 'SCENEBOARD_RUNTIME_NATIVE_REVISION=27befcf82a71047a585d725bb8c7805031472e86', 'SDKMANAGER_COMMON_ARTIFACT=/Volumes/PSSD/qemu/artifacts/npm/sdkmanager-common-2.26.3.tgz', 'SDKMANAGER_COMMON_SHA512=1f20b632c759085d79321f3b95425b4ee7608fdd1911c1c9965ab16d49f96c3384657f92dd16cda5710fdaa95215908a323cb1d629b9eede1edb500664170533', 'SDKMANAGER_COMMON_VERSION=2.26.3', 'SKIP_APT=1', 'SKIP_GIT_LFS=1', 'SKIP_PREBUILTS=1', 'SKIP_REPO_SYNC=1', 'SOURCE_PREPARE_ONLY=0', 'STANDARD_VPN_COMPONENT=1', 'http_proxy=http://host.docker.internal:7890', 'https_proxy=http://host.docker.internal:7890', 'no_proxy=github.com,.github.com,githubusercontent.com,.githubusercontent.com'], 'native_bind_paths': {'/qemu-inputs/knowledge/holidays.ics': {'Type': 'bind', 'Source': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/patches/resources/knowledge/cn-2026/holidays.ics', 'Destination': '/qemu-inputs/knowledge/holidays.ics', 'Mode': '', 'RW': False, 'Propagation': 'rprivate'}, '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/avc': {'Type': 'bind', 'Source': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/avc', 'Destination': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/avc', 'Mode': '', 'RW': False, 'Propagation': 'rprivate'}, '/Volumes/PSSD/qemu': {'Type': 'bind', 'Source': '/Volumes/PSSD/qemu', 'Destination': '/Volumes/PSSD/qemu', 'Mode': '', 'RW': True, 'Propagation': 'rprivate'}, '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/jsvm': {'Type': 'bind', 'Source': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/jsvm', 'Destination': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/jsvm', 'Mode': '', 'RW': False, 'Propagation': 'rprivate'}, '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/swiftshader': {'Type': 'bind', 'Source': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/swiftshader', 'Destination': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/swiftshader', 'Mode': '', 'RW': False, 'Propagation': 'rprivate'}, '/Volumes/PSSD/qemu/artifacts/arkweb-m144-7.0/5bce1a80ba4889a189960c57336fd4c400ab684f8ff79ff4dca76bed95b55e37-375-02': {'Type': 'bind', 'Source': '/Volumes/PSSD/qemu/artifacts/arkweb-m144-7.0/5bce1a80ba4889a189960c57336fd4c400ab684f8ff79ff4dca76bed95b55e37-375-02', 'Destination': '/Volumes/PSSD/qemu/artifacts/arkweb-m144-7.0/5bce1a80ba4889a189960c57336fd4c400ab684f8ff79ff4dca76bed95b55e37-375-02', 'Mode': '', 'RW': False, 'Propagation': 'rprivate'}, '/Volumes/PSSD/qemu/artifacts/qemu-mesa-llvm/634e042f0532266d934ad4c6ee9cc52a85695f49f8079e7303ec57f1a0981cdd': {'Type': 'bind', 'Source': '/Volumes/PSSD/qemu/artifacts/qemu-mesa-llvm/634e042f0532266d934ad4c6ee9cc52a85695f49f8079e7303ec57f1a0981cdd', 'Destination': '/Volumes/PSSD/qemu/artifacts/qemu-mesa-llvm/634e042f0532266d934ad4c6ee9cc52a85695f49f8079e7303ec57f1a0981cdd', 'Mode': '', 'RW': False, 'Propagation': 'rprivate'}}, 'native_config_labels': {'org.opencontainers.image.version': '22.04'}, 'adopted': {'HOME': '/Users/ranger', 'PATH': '/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r59-F-private-docker-cli-97-01/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin', 'CACHE_ROOT': '/Volumes/PSSD/qemu', 'OHOS_ROOT': '/Volumes/PSSD/qemu/openharmony', 'CONTAINER_HOME': '/Volumes/PSSD/qemu/home', 'CCACHE_DIR': '/Volumes/PSSD/qemu/ccache', 'DEVICE_TYPE': 'phone', 'PRODUCTS': 'arm64_virt', 'DOCKER_IMAGE': 'sha256:8f7a960c7dc515a597d43a510d6d8a5e634e5c94a55aa5d9e22bfbf6b0f42c55', 'DOCKER_PLATFORM': 'linux/amd64', 'DOCKER_SOURCE_VOLUME': 'ohos-qemu-7_0-release-source', 'DOCKER_OUT_VOLUME': 'ohos-qemu-7_0-release-out', 'DOCKER_SOURCE_SEED': '0', 'DOCKER_SOURCE_REFRESH': '0', 'QEMU_KNOWLEDGE_ICS': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/patches/resources/knowledge/cn-2026/holidays.ics', 'PACKAGE_ROOT': '/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r60-canonical-first-arm64-phone-prepare-376-01/no-packages-prepare-only', 'LOG_DIR': '/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r60-canonical-first-arm64-phone-prepare-376-01/logs', 'BUILD_JOBS': '2', 'KERNEL_BUILD_JOBS': '2', 'DOCKER_BUILD_CPUS': '2', 'DOCKER_BUILD_MEMORY': '5g', 'SKIP_REPO_SYNC': '1', 'SKIP_PREBUILTS': '1', 'SKIP_GIT_LFS': '1', 'SKIP_APT': '1', 'PREPARE_ONLY': '1', 'BUILD_ONLY_LOAD': '0', 'SOURCE_PREPARE_ONLY': '0', 'OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE': '0', 'JSVM_ENGINE_ARTIFACTS': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/jsvm', 'QEMU_VULKAN_ARTIFACTS': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/swiftshader', 'QEMU_AVC_ARTIFACTS': '/Volumes/PSSD/qemu/artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d/arm64/avc', 'QEMU_ARKWEB_CORE_ARTIFACTS': '/Volumes/PSSD/qemu/artifacts/arkweb-m144-7.0/5bce1a80ba4889a189960c57336fd4c400ab684f8ff79ff4dca76bed95b55e37-375-02', 'LC_ALL': 'C', 'LC_CTYPE': 'C', 'LANG': 'C'}}

def canonical_context(config):
    require(isinstance(config,dict) and set(config)==FIELDS and type(config.get('schema_version')) is int and
            config['schema_version']==1 and config.get('kind')==KIND, 'exact completed provider configuration required')
    root=Path(config['qa_root'])
    require(root.is_absolute() and '..' not in root.parts and root.is_dir() and
            not any(p.is_symlink() for p in (root,*root.parents)) and root==ROOT,
            'explicit actual canonical checkout root required')
    expected=config['expected_source_commit']
    require(isinstance(expected,str) and re.fullmatch('[a-f0-9]{40}',expected) and checkout_head(root)==expected,
            'actual canonical HEAD differs from completed package source')
    sources=config['producer_sources']
    require(isinstance(sources,dict) and set(sources)==set(PRODUCER_SOURCE_SHA256), 'exact actual producer source descriptors required')
    for name,item in sources.items():
        require(sha(checked(item))==PRODUCER_SOURCE_SHA256[name], 'unreviewed actual producer source: '+name)
    return {'source_commit':expected,'tools_root':str(root)}

EXECUTED_EXPORT_SOURCE_SHA256={'F-provider-current-owner237-draft/provider46_common.py': '2051f1e528ae4df8761a6ab732b652fe7f4d5f72ec2c511fb8fab4472f69e6ba', 'F-provider-current-owner237-draft/provider_guard237.py': '257b20a3509643a4c7bb570b04b8cfdbd53db0da287bb477deb203c0f079e8bc', 'F-runtime-support35-draft/owned_resource35.py': '02dcc35db074c625cb070ca7af29446ba917e585d45cb015fc86ff4b8863e4eb', 'F-runtime-support35-draft/support_common35.py': '69c29368c72b503f5fe5165f2796fe5273f84e92098dfb5cc6bf8059770f6a43', 'F-location-inventory-owner227-draft/run_inventory227.py': 'c6b79831f3122b3050ee7074a6b99924591ef95fce359ae7ab38ec8f4d9a8ded'}
# Protocol is deliberately one reviewed success path, not an arbitrary Docker
# journal interpreter. Other producers/stages require their own reviewed protocol.
NATIVE376_MANIFEST_SHA='3c0ed570c30ca44bd9cb3632a3467d0831e1a94e704b8f317e5b051febe070c4'
NATIVE376_WRAPPER_SHA='c33b32e5a4cd44d0d2555f0208412205ceea0b0a1261a7ec67f4296d868e3ee1'
NATIVE376_IMAGE='sha256:8f7a960c7dc515a597d43a510d6d8a5e634e5c94a55aa5d9e22bfbf6b0f42c55'
NATIVE376_NAME='ohos-qemu-phone-build'
NATIVE376_SOURCE='ohos-qemu-7_0-release-source'
NATIVE376_OUT='ohos-qemu-7_0-release-out'


def raw_row(row, *, native=False):
    require(type(row) is dict and type(row.get('argv')) is list and row['argv'] and
            all(type(v) is str and v for v in row['argv']) and
            type(row.get('exit_code')) is int and row.get('timed_out') is False and not row.get('error'),
            'unfinished/unknown raw resource command')
    names=('stdout','stderr') if native else ('stdout_record','stderr_record')
    return checked(row[names[0]]).read_bytes(),checked(row[names[1]]).read_bytes()


def exact_absent(row, subject, *, native=False):
    stdout,stderr=raw_row(row,native=native)
    prefixes=['error: no such object: ','error: no such container: ','error response from daemon: no such container: ']
    if native:prefixes+=['no such object: ','no such container: ','error response from daemon: no such object: ']
    require(row['argv']==['docker','inspect',subject] and row['exit_code']==1 and decode(stdout)==[] and
            stderr.decode().strip().casefold() in [prefix+subject.casefold() for prefix in prefixes],
            'raw exact container absence required; daemon error is not absence')


def raw_ok(row, argv, *, native=False):
    stdout,stderr=raw_row(row,native=native)
    require(row['argv']==argv and row['exit_code']==0 and not stderr.strip(),
            'unknown/foreign/failed command or execution argv differs: '+str(row['argv']))
    return stdout


def local_endpoint(rows, cursor, environment, *, native=False):
    require(type(environment) is dict and set(environment)<= {'DOCKER_HOST','DOCKER_CONTEXT'} and
            all(type(v)is str and v and '\n' not in v and '\r' not in v for v in environment.values()),
            'explicit bounded Docker endpoint environment required')
    if environment.get('DOCKER_HOST') and not environment.get('DOCKER_CONTEXT'):
        endpoint=environment['DOCKER_HOST']
    else:
        context=environment.get('DOCKER_CONTEXT')
        if not context:
            context=raw_ok(rows[cursor],['docker','context','show'],native=native).decode().strip();cursor+=1
        require(re.fullmatch('[A-Za-z0-9_.-]+',context or ''),'simple observed Docker context required')
        endpoint=decode(raw_ok(rows[cursor],['docker','context','inspect',context,'--format',
            '{{json .Endpoints.docker.Host}}'],native=native));cursor+=1
    require(type(endpoint)is str and endpoint.startswith('unix:///') and
            all(c not in endpoint for c in ('@','?','#','\n','\r')),'local Unix daemon endpoint required')
    return endpoint,cursor


def mount_table(observation):
    rows=observation.get('Mounts')
    require(type(rows)is list and all(type(r)is dict and type(r.get('Destination'))is str for r in rows) and
            len({r['Destination'] for r in rows})==len(rows),'complete unique actual mount set required')
    return {r['Destination']:r for r in rows}


def exact_mounts(observation, wanted):
    actual=mount_table(observation)
    require(set(actual) in (set(wanted),set(wanted)|{'/tmp'}),'extra/missing actual container mount or alias')
    for dest,m in wanted.items():
        require(all(actual[dest].get(k)==v for k,v in m.items()),'actual mount identity/access differs: '+dest)
    if '/tmp' in actual:
        require(actual['/tmp'].get('Type')=='tmpfs' and actual['/tmp'].get('RW')is True,'invalid tmpfs observation')
    return actual


def host_mount_options(mounts):
    return [dict(Type=m['Type'],Source=m.get('Name',m.get('Source')),Target=dest,
                 **({'ReadOnly':True} if m['RW'] is False else {})) for dest,m in mounts.items()]


def inspected(row,cid,name,image,config,host,mounts,*,native=False,running=None,status=None):
    stdout=raw_ok(row,['docker','inspect',row['argv'][2]],native=native)
    values=decode(stdout)
    require(type(values)is list and len(values)==1,'one complete raw inspect required')
    obs=values[0]
    require(obs.get('Id')==cid and obs.get('Name')=='/'+name and obs.get('Image')==image and
            obs.get('Config')==config and obs.get('HostConfig')==host,
            'actual complete Config/HostConfig/CID/name/image contradict reviewed command')
    exact_mounts(obs,mounts)
    state=obs.get('State',{})
    require(type(state.get('Running'))is bool and state.get('Paused')is False and state.get('Restarting')is False and
            state.get('OOMKilled')is False and state.get('Dead')is False and not state.get('Error') and
            type(state.get('ExitCode'))is int,'actual container state incomplete/failed')
    require(state.get('Status')==('running' if state['Running'] else state.get('Status')) and
            (state['Running'] or state.get('Status') in ('created','exited')), 'actual state status contradicts running/exit cut')
    if status is not None:require(state['Status']==status, 'actual operation phase/status differs')
    if running is not None:require(state['Running']is running,'unexpected resource lifecycle state')
    if not state['Running']:require(state['ExitCode']==0,'nonzero actual container completion')
    return obs


def native376_resources(value, launcher, expected, tree):
    """Replay actual v17 run--rm/held-Popen protocol; no synthetic Owner35 format."""
    require(value.get('schema')=='F-representative-owner/v17' and value.get('source_commit')==expected and
            type(value.get('exit_code'))is int and value['exit_code']==0 and value.get('tree_sha256')==tree and
            checked(value['launcher_log'])==launcher and value.get('owned_resources_closed_while_lease_held')is True and
            value.get('resource_lease_release_authorized')is True and value.get('resource_lease_released_after_verified_closure')is True and
            value.get('resource_lease_held')is False and value.get('cleanup_verified')is True and
            value.get('owned_container_absent')is True and value.get('owned_launcher_group_closed')is True and
            not any(value.get(k) for k in ('timed_out','error','cleanup_error','postcondition_error','root_settlements',
                'unexpected_leader_reap','foreground_creator_forcibly_stopped_while_still_running','group_signals',
                'must_resolve_owned_resources_before_next_stage')),
            'completed normal v17 native execution and raw closure required')
    require(value.get('resource_lock')=='/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/.representative10-resource.lock' and
            re.fullmatch('[a-f0-9]{32}',value.get('root_run_id','')) and type(value.get('wrapper_pid'))is int and value['wrapper_pid']>1,
            'actual canonical native root owner/lease identity missing')
    manifest_file=checked(value['private_manifest']);manifest=decode(manifest_file.read_bytes())
    require(sha(manifest_file)==NATIVE376_MANIFEST_SHA,'unreviewed native producer manifest')
    require(manifest.get('schema')=='F-representative17-source-draft/v1' and
            manifest['files_sha256'].get('run_F_representative17.py')==NATIVE376_WRAPPER_SHA,
            'reviewed actual376 native producer source required')
    for name,digest in manifest['files_sha256'].items():
        require(Path(name).name==name and sha(regular(manifest_file.parent/name))==digest,'native producer source changed')
    for descriptor in manifest['external_inputs'].values():checked(descriptor)
    inputs_file=checked(value['build_inputs']);frozen=Path(value['actual_frozen_inputs'])
    inputs=decode(inputs_file.read_bytes())
    require(inputs_file==frozen/'build-inputs.json' and frozen.parent==Path('/Volumes/PSSD/qemu/build-inputs') and
            inputs.get('source_git_revision')==expected and inputs.get('tree_sha256')==tree and
            tree_digest(inputs['files_sha256'])==tree,'actual native retained source snapshot differs')
    declarations=re.findall(r'^frozen build inputs: (\S+) sha256=([a-f0-9]{64})$',launcher.read_text(),re.M)
    require(declarations==[(str(frozen),tree)] and value.get('declared_launcher_tree_sha256')==tree and
            checked(value['launcher_snapshot_manifest'])==inputs_file, 'raw native launcher frozen-source declaration differs')
    from snapshot_build_inputs import digest_files
    require(digest_files(frozen)==inputs['files_sha256'],'actual native frozen source bytes changed')
    require(value.get('argv')==['bash',str(ROOT/'scripts/run_2in1_full_build_docker.sh')] and
            inputs['files_sha256'].get('scripts/run_2in1_full_build_docker.sh')==sha(regular(frozen/'scripts/run_2in1_full_build_docker.sh')),
            'actual launcher argv/source pin missing')
    env=value['adopted_complete_host_environment'];out=launcher.parent
    template=dict(ENGINE376['adopted']);template.update(PACKAGE_ROOT=str(out/'packages'),LOG_DIR=str(out/'logs'),
        PREPARE_ONLY='0',DOCKER_BUILD_CPUS='4',DOCKER_BUILD_MEMORY='10g')
    endpoint_env={k:env[k] for k in ('DOCKER_HOST','DOCKER_CONTEXT') if k in env}
    require({k:v for k,v in env.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG')}==
            {k:v for k,v in template.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG')},
            'actual native adopted environment is not reviewed complete build/images stage')
    if 'DOCKER_CONFIG' in env:require(Path(env['DOCKER_CONFIG']).is_absolute(),'native Docker config directory must be absolute')
    # PATH is the real CLI, not a claimed argv shim. Pin the actual held376 CLI.
    require(sha(regular(Path(env['PATH'].split(':')[0])/'docker'))==
            '70d5a06adf388bd09b652f47ddc9ca31663a3e5353d24188bdb0054b3014ab3e','actual native Docker executable changed')
    cid=value.get('container_id');require(re.fullmatch('[a-f0-9]{64}',cid or ''),'native actual full CID missing')
    cfg=dict(ENGINE376['config'],Hostname=cid[:12],WorkingDir='/work',Labels=ENGINE376['native_config_labels'],
        Cmd=['bash','-lc','ulimit -n 1048576 2>/dev/null || true; ulimit -n; exec bash /work/scripts/build_standard_qemu_in_docker.sh arm64_virt '])
    cfg['Env']=sorted(k+'='+(v if k in ('LANG','LC_ALL') else env.get(k,v)) for k,v in (s.split('=',1) for s in ENGINE376['native_env']))
    mounts={dest:{k:v for k,v in row.items() if k in ('Type','Source','RW')} for dest,row in ENGINE376['native_bind_paths'].items()}
    mounts['/work']=dict(Type='bind',Source=str(frozen),RW=False)
    for dest,name in ((SOURCE,NATIVE376_SOURCE),(SOURCE+'/out',NATIVE376_OUT)):
        mounts[dest]=dict(Type='volume',Name=name,Source='/var/lib/docker/volumes/'+name+'/_data',Driver='local',RW=True)
    # Preserve complete engine defaults; dynamic bounds/mounts come from the
    # reviewed launcher's actual build environment and frozen source.
    host=dict(ENGINE376['host'],AutoRemove=True,ContainerIDFile='',ReadonlyRootfs=False,NetworkMode='bridge',
        CapDrop=None,SecurityOpt=None,PidsLimit=None,Memory=10*1024**3,MemorySwap=20*1024**3,NanoCpus=4*10**9,
        Tmpfs={'/tmp':'exec,mode=1777,size=32g'},Binds=['/Volumes/PSSD/qemu:/Volumes/PSSD/qemu',str(frozen)+':/work:ro'])
    host['Mounts']=host_mount_options({dest:m for dest,m in mounts.items() if dest not in ('/work','/Volumes/PSSD/qemu')})
    # HostConfig.Mounts order is launch argv order, separate from unordered Mounts.
    order=['JSVM_ENGINE_ARTIFACTS','QEMU_VULKAN_ARTIFACTS','QEMU_AVC_ARTIFACTS','QEMU_ARKWEB_CORE_ARTIFACTS','QEMU_MESA_LLVM_ARTIFACTS']
    targets=[env.get(k,next((s.split('=',1)[1] for s in ENGINE376['native_env'] if s.startswith(k+'=')),None)) for k in order]
    targets+=['/qemu-inputs/knowledge/holidays.ics',SOURCE,SOURCE+'/out']
    host['Mounts']=host_mount_options({dest:mounts[dest] for dest in targets})
    rows=value.get('commands');require(type(rows)is list and rows,'native actual raw command journal missing')
    endpoint,cursor=local_endpoint(rows,0,endpoint_env,native=True)
    require(endpoint==value.get('actual_local_docker_endpoint'),'native raw endpoint observation differs')
    exact_absent(rows[cursor],NATIVE376_NAME,native=True)
    require(rows[cursor].get('label')=='before-build-name','native initial before-name cut missing');cursor+=1
    observed=[]
    while cursor<len(rows) and re.fullmatch('discover-build-[0-9]+',rows[cursor].get('label','')):
        row=rows[cursor];require(row['argv']==['docker','inspect',NATIVE376_NAME],'foreign native discovery command')
        if row['exit_code']==1:
            require(not observed,'native CID must remain held after discovery');exact_absent(row,NATIVE376_NAME,native=True)
        else:
            require(not observed,'duplicate native adoption')
            observed.append(inspected_native376(row,cid,cfg,host,mounts))
        cursor+=1
    require(len(observed)==1,'actual native adopted complete Config/HostConfig/Mounts required')
    pid=value.get('launcher_pid');pgid=value.get('owned_launcher_pgid');wn=value.get('launcher_wnowait_exit',{})
    require(type(pid)is int and pid>1 and pgid==pid and value.get('launcher_start_new_session')is True and
            value.get('spawn_mask_restored_in_child')is True and value.get('foreground_creator_completed_normally_before_forced_stop')is True and
            wn.get('pid')==pid and type(wn.get('si_code'))is int and wn['si_code']==1 and
            type(wn.get('si_status'))is int and wn['si_status']==0 and type(wn.get('exit_code'))is int and wn['exit_code']==0 and wn.get('reaped')is False and
            value.get('leader_final_wait_completed')is True and value.get('owned_launcher_leader_reaped')is True and
            type(value.get('actual_launcher_exit_code_after_cleanup'))is int and value['actual_launcher_exit_code_after_cleanup']==0,
            'actual held-Popen WNOWAIT/final wait chain missing')
    cuts=value.get('registered_group_cuts');require(type(cuts)is list and cuts,'native raw PS/group cuts missing')
    replayed=[]
    while cursor<len(rows) and rows[cursor].get('label')=='owned-group-members':
        raw=raw_ok(rows[cursor],['ps','-axo','pid=,pgid=,stat='],native=True);members=[];seen=set()
        for line in raw.decode().splitlines():
            fields=line.split();require(len(fields)==3 and fields[0].isdigit() and fields[1].isdigit() and
                re.fullmatch('[A-Za-z][A-Za-z0-9+<>=?-]{0,15}',fields[2]),'invalid actual PS row')
            p,g=int(fields[0]),int(fields[1]);require(p not in seen,'duplicate actual PS PID');seen.add(p)
            if g==pgid:members.append(dict(pid=p,pgid=g,state=fields[2]))
        replayed.append(members);cursor+=1
    require(replayed and len(replayed)==len(cuts) and all(a==b.get('members') for a,b in zip(replayed,cuts)) and
            all(m['pid']==pid or m['state'].startswith('Z') for m in replayed[-1]) and
            type(wn.get('observed_monotonic_ns'))is int and type(value.get('cleanup_started_monotonic_ns'))is int and
            type(value.get('last_group_signal_boundary_monotonic_ns'))is int and
            all(type(cut.get('monotonic_ns'))is int for cut in cuts) and
            0<value['cleanup_started_monotonic_ns']<=wn['observed_monotonic_ns']<=cuts[0]['monotonic_ns'] and
            all(a['monotonic_ns']<=b['monotonic_ns'] for a,b in zip(cuts,cuts[1:])) and
            cuts[-1]['monotonic_ns']<=value['last_group_signal_boundary_monotonic_ns'],
            'raw final original group membership/WNOWAIT order differs')
    require(rows[cursor].get('label')=='cleanup-discover' and rows[cursor]['argv']==['docker','inspect',cid],
            'native cleanup must re-observe original CID after group completion')
    if rows[cursor]['exit_code']==0:
        inspected_native376(rows[cursor],cid,cfg,host,mounts,running=False);cursor+=1
        raw_ok(rows[cursor],['docker','rm','--force',cid],native=True);cursor+=1
        exact_absent(rows[cursor],cid,native=True);cursor+=1
    else:exact_absent(rows[cursor],cid,native=True);cursor+=1
    for label in ('cleanup-name-absence-1','cleanup-name-absence-2'):
        require(rows[cursor].get('label')==label,'native separate post-group name cuts required')
        exact_absent(rows[cursor],NATIVE376_NAME,native=True);cursor+=1
    require(cursor==len(rows),'unknown/foreign native command outside reviewed finite success protocol')
    return dict(endpoint=endpoint,container_id=cid,volumes={dest:observed[0]['MountsByDestination'][dest] for dest in (SOURCE,SOURCE+'/out')})


def inspected_native376(row,cid,config,host,mounts,*,running=None):
    # Docker Env is a set of unique KEY=VALUE strings; order is not semantic.
    raw=raw_ok(row,row['argv'],native=True);values=decode(raw)
    require(type(values)is list and len(values)==1 and type(values[0].get('Config',{}).get('Env'))is list,
            'native complete actual Config/Env missing')
    original=values[0]['Config']['Env'];require(len({v.split('=',1)[0] for v in original})==len(original),'duplicate native environment key')
    require(sorted(original)==config['Env'],'actual native complete environment differs')
    actual_config=dict(config,Env=original)
    obs=inspected(row,cid,NATIVE376_NAME,NATIVE376_IMAGE,actual_config,host,mounts,native=True,running=running)
    return dict(obs,MountsByDestination=mount_table(obs))


def export379_resources(config,paths,inputs,receipt):
    ledger=decode(checked(receipt['resource_ledger']).read_bytes())
    require(ledger.get('schema')=='owned-resource35/v1' and ledger.get('phase')=='closed' and
            ledger.get('failed')is False and ledger.get('cleanup_verified')is True and ledger.get('errors')==[] and
            ledger.get('commands')==receipt.get('commands') and ledger.get('signals')==[] and
            ledger.get('quarantine_attempts')==[] and type(ledger.get('containers'))is list and len(ledger['containers'])==1,
            'actual normal closed exporter raw ledger required')
    entry=ledger['containers'][0];owner=ledger.get('owner_uuid');cid=entry.get('id');name=entry.get('name')
    require(re.fullmatch('[a-f0-9]{32}',owner or '') and re.fullmatch('[a-f0-9]{64}',cid or '') and
            name=='ohos-F-provider-export46-'+owner and entry.get('image')==NATIVE376_IMAGE and
            entry.get('owner')==owner and entry.get('commit')==config['expected_source_commit'] and
            entry.get('absent')is True and entry.get('create_attempted')is True and entry.get('create_outcome')=='known_created' and
            receipt.get('container_id')==cid and receipt.get('run_id')==owner,
            'actual selected exporter create/identity/owner differs')
    native=decode(paths['native_evidence'].read_bytes())
    identity=native376_resources(native,checked(config['native_launcher_log']),config['expected_source_commit'],inputs['tree_sha256'])
    rows=ledger['commands'];require(type(rows)is list and rows,'actual finite export command journal required')
    endpoint,cursor=local_endpoint(rows,0,receipt['docker_endpoint_environment'])
    require(endpoint==receipt.get('actual_local_docker_endpoint')==identity['endpoint'],
            'actual native/export Docker endpoint differs')
    images=decode(raw_ok(rows[cursor],['docker','image','inspect',NATIVE376_IMAGE]));cursor+=1
    require(type(images)is list and len(images)==1 and images[0].get('Id')==NATIVE376_IMAGE and
            type(images[0].get('Config'))is dict,'actual immutable image defaults missing')
    image=images[0]['Config'];env=image.get('Env');labels=image.get('Labels')or{}
    require(image.get('Entrypoint')in (None,[]) and type(env)is list and all(type(v)is str and '='in v for v in env) and
            len({v.split('=',1)[0] for v in env})==len(env) and type(labels)is dict and
            not {'ohos-qemu.root-run','ohos-qemu.source-commit'}&set(labels),'unexpected image entrypoint/environment/owner labels')
    root=Path(config['qa_root']);exporter=checked(config['producer_sources']['exporter']);output=checked(config['export_receipt']).parent
    command=['python3',str(exporter),'--source-root',SOURCE,'--native-evidence',str(paths['native_evidence']),
             '--output',str(output/'public-source'),'--public-input','vendor/ohemu/virt/virt_phone_full.meta.json']
    require(paths['exports']==output/'public-source/exports.json' and entry.get('command')==command and
            ledger.get('output')==str(output) and entry.get('cidfile')==str(output/'container.cid') and
            regular(entry['cidfile']).read_text().strip()==cid,'actual exporter command/output/CID file differs')
    mounts={dest:dict(Type='volume',Name=identity['volumes'][dest]['Name'],RW=False) for dest in (SOURCE,SOURCE+'/out')}
    mounts.update({'/work':dict(Type='bind',Source=str(root),RW=False),str(output):dict(Type='bind',Source=str(output),RW=True),
                   str(exporter.parent):dict(Type='bind',Source=str(exporter.parent),RW=False),
                   str(paths['native_evidence']):dict(Type='bind',Source=str(paths['native_evidence']),RW=False)})
    require(len(mounts)==6 and entry.get('mounts')==mounts,'collector planned mounts do not join actual native source/out and input descriptors')
    actual_mounts={dest:dict(m) for dest,m in mounts.items()}
    for dest in (SOURCE,SOURCE+'/out'):
        actual_mounts[dest].update({k:identity['volumes'][dest][k] for k in ('Source','Driver')})
    cidfile=str(output/'container.cid')
    create=['docker','create','--name',name,'--cidfile',cidfile,'--label','ohos-qemu.root-run='+owner,
            '--label','ohos-qemu.source-commit='+config['expected_source_commit'],'--platform','linux/amd64','--read-only',
            '--cpus','1','--memory','512m','--pids-limit','64','--network','none','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,exec,nosuid,nodev,size=512m']
    for dest,m in mounts.items():
        create+=['--mount','type='+m['Type']+',src='+m.get('Name',m.get('Source'))+',dst='+dest+(',readonly' if not m['RW'] else '')]
    create+=[NATIVE376_IMAGE,*command]
    cfg=dict(ENGINE376['config'],Hostname=cid[:12],Cmd=command,Env=env,WorkingDir=image.get('WorkingDir',''),
             Labels=dict(labels,**{'ohos-qemu.root-run':owner,'ohos-qemu.source-commit':config['expected_source_commit']}))
    require(image.get('User')==cfg['User'],'unexpected actual image user')
    host=dict(ENGINE376['host'],AutoRemove=False,ContainerIDFile=cidfile,ReadonlyRootfs=True,NetworkMode='none',
        CapDrop=['ALL'],SecurityOpt=['no-new-privileges'],PidsLimit=64,Memory=512*1024**2,MemorySwap=1024**3,NanoCpus=10**9,
        Tmpfs={'/tmp':'rw,exec,nosuid,nodev,size=512m'},Binds=None,Mounts=host_mount_options(mounts))
    def git_cut():
        nonlocal cursor
        require(raw_ok(rows[cursor],['git','-C',str(root),'rev-parse','HEAD']).decode().strip()==config['expected_source_commit'],
                'actual export source HEAD differs');cursor+=1
        require(not raw_ok(rows[cursor],['git','-C',str(root),'status','--short']).strip(),'actual export source was dirty');cursor+=1
    def inspect_cut(status='exited'):
        nonlocal cursor
        require(rows[cursor]['argv']==['docker','inspect',cid],'selected exporter CID inspect required')
        inspected(rows[cursor],cid,name,NATIVE376_IMAGE,cfg,host,actual_mounts,running=False,status=status);cursor+=1
    git_cut()
    exact_absent(rows[cursor],name);cursor+=1
    require(raw_ok(rows[cursor],create).decode().strip()==cid,'actual Docker create result/CID differs');cursor+=1
    inspect_cut('created');inspect_cut('created') # create-after and start-before actual identity cuts
    summary_raw=raw_ok(rows[cursor],['docker','start','-a',cid]);cursor+=1
    summaries=[decode(line) for line in summary_raw.splitlines() if line.strip()]
    require(len(summaries)==1 and type(summaries[0])is dict and type(summaries[0].get('exit_code'))is int and
            summaries[0]['exit_code']==0 and summaries[0].get('private_key_bytes_read')is False and
            summaries[0].get('compiler_executed')is False,'actual unique exporter stdout completion required')
    inspect_cut();git_cut();inspect_cut();inspect_cut() # post-start, clean source, cleanup-before/remove-before
    require(raw_ok(rows[cursor],['docker','rm',cid]).decode().strip()==cid,'actual exporter removal result differs');cursor+=1
    exact_absent(rows[cursor],cid);cursor+=1
    exact_absent(rows[cursor],name);cursor+=1
    require(not raw_ok(rows[cursor],['docker','ps','-aq','--no-trunc','--filter','label=ohos-qemu.root-run='+owner]).strip(),
            'actual exporter owner inventory not empty');cursor+=1
    require(cursor==len(rows),'unknown/foreign command outside finite exporter success protocol')
    return summaries[0]

def verify_export_receipt(config, paths, inputs):
    """Replay closed collector raw commands, mounts, output and source audit.

    An argv-only receipt or a status/pass label is never an executed export.
    No Docker/API execution occurs in this verifier.
    """
    receipt=decode(checked(config['export_receipt']).read_bytes())
    require(type(receipt.get('exit_code')) is int and receipt['exit_code']==0 and
            receipt.get('cleanup_verified') is True and receipt.get('owned_container_absent') is True and
            not receipt.get('error') and not receipt.get('cleanup_error') and
            receipt.get('source_commit')==config['expected_source_commit'] and
            checked(receipt['package_build_receipt'])==paths['native_evidence'] and
            checked(receipt['source_export'])==paths['exports'] and receipt.get('export_sha256')==sha(paths['exports']) and
            checked(receipt['private_exporter'])==checked(config['producer_sources']['exporter']) and
            checked(receipt['private_source'])==checked(config['producer_sources']['collector']) and
            checked(receipt['execution_outer379'])==checked(config['producer_sources']['collector']) and
            receipt.get('original46_outer_executed') is False and receipt.get('source_out_written') is False,
            'actual completed RO export receipt/new native package/source identity required')
    identity=receipt['source_identity']
    require(identity.get('schema')=='F-source-identity-observation35/v1' and
            identity.get('source_root')==SOURCE and identity.get('product_commit')==config['expected_source_commit'] and
            identity.get('tree_sha256')==inputs['tree_sha256'] and identity.get('source_ro') is True and
            identity.get('out_ro') is True and identity.get('whole_source_tree_verified') is False and
            identity.get('full_rebuild_claimed') is False,
            'actual RO source recipe/package observation differs')
    require(sha(checked(receipt['docker_cli']))=='70d5a06adf388bd09b652f47ddc9ca31663a3e5353d24188bdb0054b3014ab3e',
            'actual exporter Docker CLI bytes differ from native reviewed CLI')
    summary=export379_resources(config,paths,inputs,receipt)
    doc=decode(paths['exports'].read_bytes())
    require(type(summary.get('exported_files')) is int and type(summary.get('bytes')) is int and
            summary.get('exported_files')==len(doc['files']) and
            summary.get('bytes')==sum(r['bytes'] for r in doc['files']), 'actual exporter stdout/file inventory differs')
    anchor=identity['native_source_recipe_anchor']
    expected_anchor=SOURCE+'/vendor/ohemu/virt/virt_phone_full.meta.json'
    anchors=[r for r in doc['files'] if r.get('path')==expected_anchor]
    require(len(anchors)==1 and anchor.get('metadata')==anchors[0] and
            anchor.get('native_source_revision')==config['expected_source_commit'] and
            anchors[0].get('resolved')==expected_anchor and
            anchors[0].get('export_relative')=='files/vendor/ohemu/virt/virt_phone_full.meta.json',
            'actual exported source recipe/native revision anchor missing')
    copied=regular(paths['exports'].parent/anchors[0]['export_relative'])
    require(sha(copied)==anchors[0]['sha256'] and copied.stat().st_size==anchors[0]['bytes'] and
            decode(copied.read_bytes())['privacycenter_provider']['native_source_revision']==config['expected_source_commit'],
            'actual source recipe bytes belong to another native commit')
    frozen=decode(checked(receipt['retained_launcher_snapshot']).read_bytes())
    require(frozen==inputs,'actual retained native launcher manifest differs from package inputs')
    source_audit=decode(checked(receipt['source_audit']).read_bytes())
    require(source_audit.get('source_commit')==config['expected_source_commit'] and source_audit.get('failures')==[] and
            isinstance(source_audit.get('sources'),dict), 'actual collector source audit incomplete')
    for path,row in source_audit['sources'].items():
        require(row.get('before')==row.get('after') and checked(row['before'])==regular(path),
                'executed producer source changed during or after export')
    for descriptor in config['producer_sources'].values():
        source=checked(descriptor);require(str(source) in source_audit['sources'],'actual executed exporter/collector missing from source audit')
    # The successor retains these exact dependencies, not self-described replacements.
    for relative,digest in EXECUTED_EXPORT_SOURCE_SHA256.items():
        source=regular(ROOT/'.tmp/parallel-capability-20261016'/relative)
        require(sha(source)==digest and str(source) in source_audit['sources'] and
                source_audit['sources'][str(source)]['before']['sha256']==digest,
                'actual unchanged shared collector/guard/Owner source missing from audit: '+relative)
    return receipt
