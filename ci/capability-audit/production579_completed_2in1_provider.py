"""Finite actual five-target Contacts/Wallpaper provider lineage; pure raw replay only.

The original ARM64 phone/v17/F18 contract remains in its original checker.
Two fixed kinds bind the actual selected Contacts or phone/pad Wallpaper
source/HAP/graph/image to one later normal target. No profile is relabelled.
"""
from pathlib import Path, PurePosixPath
import re, shlex
from batch_apps_completed_provider_binding import (
    ROOT, SOURCE, RUNNERS, archive_inputs, checkout_head, classify_action,
    public_commands, record, require, sha, regular, checked, decode, tree_digest,
    native376_resources, EXECUTED_EXPORT_SOURCE_SHA256, NATIVE376_IMAGE,
    ENGINE376, raw_ok, exact_absent, local_endpoint, inspected, host_mount_options)
from production579_target import archive_manifest
from batch_apps_production_provider_binding import ninja_decode, option

KIND='completed_same_source_2in1_wallpaper_provider579/v1'
PHONE_KIND='completed_same_source_nondefault_phone_provider579/v1'
FIELDS={'schema_version','kind','expected_source_commit','qa_root','producer_sources','archive',
        'native_evidence','native_launcher_log','native_build_log','exports','export_receipt','historical_reuse','target'}
PROVIDERS={'theme':('applications/standard/theme','wallpaper_pad_hap','Wallpaper','pad_wallpaper',
    'product/pad/build/default/outputs/default/pad_wallpaper-default-unsigned.hap','product/pad/src/main/module.json5')}
CONTACTS=('applications/standard/contacts','contacts_hap','Contacts','entry',
    'entry/build/default/outputs/default/entry-default-unsigned.hap','entry/src/main/module.json5')
PHONE_THEME=('applications/standard/theme','wallpaper_phone_hap','Wallpaper','phone_wallpaper',
    'product/phone/build/default/outputs/default/phone_wallpaper-default-unsigned.hap','product/phone/src/main/module.json5')
PRODUCER_SOURCE_SHA256={'exporter': 'c0edee5c205aece4b87542306098e05d02dbcc77931dc4fc4ed4ff101b4a8d51', 'collector': '03588ee15787b86e61761680441f39aa59a90b34d424e5663498cbdf28e51898'}


def canonical_context(config):
    require(type(config)is dict and set(config)==FIELDS and type(config.get('schema_version'))is int and
        config['schema_version']==1 and config.get('kind')in(KIND,PHONE_KIND),'exact later-target provider contract required')
    root=Path(config['qa_root']);expected=config['expected_source_commit']
    require(root==ROOT and root.is_absolute() and root.is_dir() and not any(p.is_symlink()for p in(root,*root.parents)) and
        re.fullmatch('[a-f0-9]{40}',expected or '') and checkout_head(root)==expected,
        'actual canonical clean-source HEAD/root must match this new package')
    require(type(config['producer_sources'])is dict and set(config['producer_sources'])==set(PRODUCER_SOURCE_SHA256),
        'both fixed actual later-target producer source descriptors required')
    for name,row in config['producer_sources'].items():
        require(sha(checked(row))==PRODUCER_SOURCE_SHA256[name],'unreviewed later-target producer source: '+name)
    actual=archive_manifest(checked(config['archive']))['context']
    require(config['target']==actual,'actual remaining archive target required')
    if config['kind']==KIND:
        require(actual['device']=='2in1','actual pad kind requires true2in1 archive')
    else:
        require(actual['device']=='phone'and actual['product']in('x86_64_virt','armv7a_virt'),
            'exact nondefault phone kind never replaces original ARM64 phone contract')
    return {'source_commit':expected,'tools_root':str(root),'target':actual}


def selected_unsigned_path(value,project,unsigned_relative):
    require((project,unsigned_relative)in{(r[0],r[4])for r in(PROVIDERS['theme'],CONTACTS,PHONE_THEME)},'only actual selected remaining provider output')
    canonical=SOURCE+'/'+project+'/'+unsigned_relative;project_dot=SOURCE+'/'+project+'/./'+unsigned_relative
    require(type(value)is dict and set(value)=={'unsigned_hap_path_list'} and
        type(value['unsigned_hap_path_list'])is list and len(value['unsigned_hap_path_list'])==1 and
        value['unsigned_hap_path_list'][0]in(canonical,project_dot),'actual selected unsigned production output differs')
    token=value['unsigned_hap_path_list'][0]
    return {'raw_token':token,'canonical_source_path':canonical,'allowed_form':'project_dot'if token==project_dot else'canonical'}


def native_completion(evidence,launcher,expected,archive,tree,*,target):
    value=decode(checked(evidence).read_bytes());launcher=checked(launcher)
    require(value.get('schema')=='remaining579-one-target-source-owner/v1' and checked(value['package'])==archive,
        'actual one later normal completed archive required')
    resources=native376_resources(value,launcher,expected,tree)
    require(resources['target']['product']==target['product'] and resources['target']['device']==target['device'],
        'actual raw Owner and archive target differs')
    lines=re.sub(r'\x1b\[[0-9;]*m','',launcher.read_text()).splitlines()
    starts=[i for i,line in enumerate(lines)if line.startswith('Build args: ')];selected=[]
    for n,start in enumerate(starts):
        argv=shlex.split(lines[start][len('Build args: '):]);end=starts[n+1]if n+1<len(starts)else len(lines)
        if '--build-only-load=false'not in argv:continue
        require([v for v in argv if v.startswith('--build-only-load=')]==['--build-only-load=false'] and
            option(argv,'--product-name')==target['product'] and option(argv,'--device-type')==target['device'] and
            option(argv,'--build-target')=='images','actual native frontend belongs to another target/stage')
        hits=[i for i in range(start+1,end)if re.fullmatch(r'\[OHOS INFO\]\s+'+re.escape(target['product'])+r' build success\s*',lines[i])]
        require(len(hits)==1,'one actual selected product images success required')
        footer=lines[hits[0]+1]if hits[0]+1<end else''
        require(re.fullmatch(r'\[OHOS INFO\]\s+Cost Time:\s+[0-9]+:[0-9]{2}:[0-9]{2}\s*',footer),'actual native cost footer missing')
        selected.append(dict(build_args_line=start+1,success_line=hits[0]+1,cost_footer=footer,resource_observation=resources))
    require(len(selected)==1,'unique actual normal target native images phase required')
    return value,selected[0]


def witness_phase_binding(text,witness,frontend,*,target):
    matches={'prepared':[],'completed':[]}
    for index,line in enumerate(re.sub(r'\x1b\[[0-9;]*m','',text).splitlines(),1):
        if not line.startswith('{'):continue
        try:row=decode(line)
        except(ValueError,TypeError):continue
        if type(row)is dict and row.get('nonce')==witness['nonce']and row.get('phase')in matches:
            require(row.get('product')==target['product'],'actual witness belongs to another product')
            matches[row['phase']].append(index)
    require(len(matches['prepared'])==len(matches['completed'])==1 and
        matches['prepared'][0]<frontend['build_args_line']<frontend['success_line']<matches['completed'][0],
        'actual packaged witness nonce is not inside this launcher native phase')
    return dict(prepared_line=matches['prepared'][0],completed_line=matches['completed'][0])


def exports_checked(path, native_evidence, producer_sources,*,target):
    document=decode(path.read_bytes());require(document.get('schema_version')==2 and document.get('source_root')==SOURCE and
        document.get('product')==target['product'] and document.get('device')==target['device'] and checked(document.get('native_evidence'))==checked(native_evidence) and
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


def graph_actions(path, project, target, *, product):
    """Read exact inline rules and their actual edges from the whole raw graph."""
    toolchain = {'arm64_virt':'arm64','armv7a_virt':'arm','x86_64_virt':'x86_64'}[product]
    labels = {part: 'ACTION //' + project + ':' + target + suffix + '(//build/toolchain/ohos:ohos_clang_' + toolchain + ')'
              for part, suffix in (('compile', '_compile_app'), ('sign', ''), ('info', '_info'))}
    found = {}; names = {}; edges = {}; rule = command = None
    with Path(path).open() as stream:
        for line in stream:
            if line.startswith('rule '):
                rule = line[5:].strip(); command = None
            elif rule and line.startswith('  command = '):
                command = line.removeprefix('  command = ').rstrip('\n')
            elif rule and line.startswith('  description = '):
                description = line.removeprefix('  description = ').rstrip('\n')
                for part, label in labels.items():
                    if description == label:
                        require(part not in found and command is not None, 'duplicate/missing production action')
                        found[part] = shlex.split(ninja_decode(command)); names[rule] = part
            elif line.startswith('build '):
                for name, part in names.items():
                    token = ': ' + name + ' '
                    if token in line:
                        require(part not in edges, 'duplicate production action edge')
                        output, dependencies = line[6:].split(token, 1)
                        edges[part] = {'output': output, 'dependencies': shlex.split(ninja_decode(dependencies))}
    require(set(found) == set(labels) == set(edges), 'actual compile/sign/module-info edges missing')
    stem = 'obj/' + project + '/' + target
    require(edges['compile']['output'] == stem + '/unsigned_hap_path_list.json' and
            edges['sign']['output'] == stem + '.stamp' and edges['info']['output'] == stem + '_module_info.json',
            'production action outputs differ')
    for part, script in (('compile', 'compile_app.py'), ('sign', 'app_sign.py')):
        require(found[part][:2] == ['/usr/bin/env', '../../build/scripts/' + script], 'production runner differs')
    for name, value in {'--cwd': '../../' + project + '/', '--build-profile': '../../' + project + '/build-profile.json5',
                        '--sdk-home': SOURCE + '/prebuilts/ohos-sdk/linux', '--product': 'default',
                        '--assemble-type': 'assembleHap', '--build-level': 'module',
                        '--output-file': stem + '/unsigned_hap_path_list.json'}.items():
        require(option(found['compile'], name) == value, 'wrong selected production compile input')
    require('--hvigor-obfuscation' in found['compile'], 'actual selected production obfuscation option missing')
    require(stem + '_compile_app.stamp' in edges['sign']['dependencies'] and
            stem + '_info.stamp' in edges['sign']['dependencies'], 'sign action is disconnected from production compile/info')
    return found, edges


def verify_completed_provider(config, *, provider_name, device, signed_hap, system_image_sha256):
    """Capture and independent replay call this exact new API; old F schema is rejected."""
    base=canonical_context(config);target_ctx=base['target']
    require(isinstance(config,dict) and set(config)==FIELDS and type(config['schema_version']) is int and
        config['schema_version']==1 and config['kind']in(KIND,PHONE_KIND) and provider_name in('contacts','theme') and
        device==target_ctx['device'] and(provider_name!='contacts'or device=='phone') and
        config['expected_source_commit']==base['source_commit'],'explicit new same-source production15 configuration required')
    paths={key:checked(config[key]) for key in ('archive','native_evidence','native_launcher_log','native_build_log','exports')}
    metadata,hashes=archive_inputs(paths['archive']);inputs=metadata['build-inputs.json']
    from snapshot_build_inputs import digest_files
    require(inputs.get('source_git_revision')==config['expected_source_commit'] and
        tree_digest(inputs['files_sha256'])==inputs['tree_sha256'] and
        inputs['files_sha256']==digest_files(Path(base['tools_root'])),
        'actual canonical new F build-inputs identity or exact current frozen tree differs')
    require(hashes['images/system.img']==system_image_sha256,'actual current image differs from new archive')
    native,phase=native_completion(config['native_evidence'],config['native_launcher_log'],config['expected_source_commit'],paths['archive'],inputs['tree_sha256'],target=target_ctx)
    verify_export_receipt(config, paths, inputs)
    export,files=exports_checked(paths['exports'],config['native_evidence'],config['producer_sources'],target=target_ctx)
    def artifact(relative):
        require(SOURCE+'/'+relative in files,'actual new producer export missing: '+relative)
        return files[SOURCE+'/'+relative][1]
    provider_row=CONTACTS if provider_name=='contacts'else PHONE_THEME if device=='phone'else PROVIDERS['theme']
    project,target,title,module,unsigned_relative,module_relative=provider_row
    inventory=export['providers'][provider_name]['source_inventory']
    require(inventory and all(row['path']==SOURCE+'/'+project+'/'+name for name,row in inventory.items()),'actual complete source inventory paths differ')
    for name,row in inventory.items():require(sha(artifact(project+'/'+name))==row['sha256'],'actual current complete source bytes changed: '+name)
    heads=metadata['openharmony-project-heads.json'];selected=[row for row in heads['projects'] if row['path']==project]
    require(heads['status']=='pass' and len(selected)==1 and re.fullmatch('[a-f0-9]{40}',selected[0].get('revision','')) and selected[0]['revision']==selected[0]['observed_head']=={'theme':'a436a43f1c0948fa12df6d520ec695ae4388a057','contacts':'65de33df8d6d7aaa5797a5625ed0e5938e5cb050'}[provider_name],
            'actual new package project source HEAD not pinned')
    prefix='out/'+target_ctx['product']+'/obj/'+project+'/'+target;stem='obj/'+project+'/'+target
    unsigned_list=decode(artifact(prefix+'/unsigned_hap_path_list.json').read_bytes())
    unsigned_selection=selected_unsigned_path(unsigned_list,project,unsigned_relative)
    unsigned=artifact(project+'/'+unsigned_relative);produced=artifact(prefix+'/'+title+'.hap')
    bundle='com.ohos.contacts' if provider_name=='contacts' else 'com.ohos.wallpaper'
    staged=artifact('out/'+target_ctx['product']+'/packages/phone/system/app/'+bundle+'/'+title+'.hap')
    guard=metadata['contacts-theme-provider-evidence.json'];signed_hap=regular(signed_hap)
    require(guard['status']=='pass' and guard['failures']==[] and guard['device']==device and
        guard['system_image_sha256']==system_image_sha256 and sha(produced)==sha(staged)==sha(signed_hap)==guard['providers'][provider_name]['hap_sha256'],
        'actual new produced/staged/image signed provider chain differs')
    info=decode(artifact(prefix+'_module_info.json').read_bytes());install=decode(artifact(prefix+'_install_info.json').read_bytes())
    toolchain='//build/toolchain/ohos:ohos_clang_'+{'arm64_virt':'arm64','armv7a_virt':'arm','x86_64_virt':'x86_64'}[target_ctx['product']]
    label='//'+project+':'+target+'('+toolchain+')'
    require(info['source']==stem and info['dest']==['system/app/'+bundle+'/'] and info['install_enable'] is True and
        info['label']==label and info['label_name']==target and info['part_name']=='prebuilt_hap' and info['type']=='app' and
        install==[{'module_def':label,'module_info_file':stem+'_module_info.json','part_name':'prebuilt_hap',
                   'subsystem_name':'applications','toolchain':toolchain,'toolchain_out_dir':'.'}],
        'actual compiled-to-sign-to-staging installation mapping differs')
    graph=artifact('out/'+target_ctx['product']+'/toolchain.ninja');commands,edges=graph_actions(graph,project,target,product=target_ctx['product'])
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
        require(inv['product']==target_ctx['product'] and inv['recipe']==guard_module.recipe() and witness['phase']=='completed' and
            re.fullmatch('[a-f0-9]{32}',witness.get('nonce','')) and type(witness.get('start_ns')) is int and type(witness.get('finished_ns')) is int and 0<witness['start_ns']<witness['finished_ns'],
            'actual current native recipe/fresh completed witness required')
        expected={family+'-native/'+name:digest for name,digest in inv['files_sha256'].items()}
        actual={name:digest for name,digest in hashes.items() if name.startswith(family+'-native/') and name!=family+'-native/inventory.json'}
        require(expected==actual,'complete packaged native witness payload map differs')
        image=metadata[family+'-native-image-evidence.json'];require(image['status']=='pass' and
            image['system_image_sha256']==system_image_sha256 and image['inventory_sha256']==hashes[family+'-native/inventory.json'],
            'native witness image binding differs')
        ordered=witness_phase_binding(paths['native_launcher_log'].read_text(),witness,phase,target=target_ctx)
        witness_records[family]={'inventory_sha256':hashes[family+'-native/inventory.json'],'nonce':witness['nonce'],
            'launcher_order':ordered,'scope':inv['scope'],'HAP_ArkTS_compile_claimed':False}
    require(hashes['contacts-native/graph/toolchain.ninja']==sha(graph),'actual provider graph is not the graph of this packaged native attempt')
    require(hashes['contacts-native/execution-log.txt']==sha(paths['native_build_log']), 'actual detailed product log differs from this package witness')
    text=paths['native_build_log'].read_text()
    action=classify_action(text,project,module,'ACTION //'+project+':'+target+'_compile_app(', 'ACTION //'+project+':'+target+'(')
    require(config['historical_reuse']is None,'original ARM64 phone history cannot establish another target native producer lineage')
    reuse=None
    if action['mode'] in ('current_ninja_incremental_reuse','current_hvigor_action_cached_ArkTS'):
        raise ValueError('actual later-target native action reused cached HAP without an admitted complete same-target producer history; preserve raw failure and obtain actual current selected Hvigor action')
    from batch_apps_contact_picker_coordinator import verify_signed_payload
    verify_signed_payload(unsigned,signed_hap)
    return {'schema_version':1,'kind':config['kind'],'scope':'actual completed current incremental native/images/package + honest producer HAP source lineage; NOT guest',
        'source_commit':config['expected_source_commit'],'target':target_ctx,'archive':record(paths['archive']),'system_image_sha256':system_image_sha256,
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



def export379_resources(config,paths,inputs,receipt):
    target_ctx=config['target']
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
             '--output',str(output/'public-source'),'--public-input','vendor/ohemu/virt/virt_'+target_ctx['device']+'_full.meta.json','--product',target_ctx['product'],'--device',target_ctx['device']]
    require(paths['exports']==output/'public-source/exports.json' and entry.get('command')==command and
            ledger.get('output')==str(output) and entry.get('cidfile')==str(output/'container.cid') and
            regular(entry['cidfile']).read_text().strip()==cid,'actual exporter command/output/CID file differs')
    mounts={dest:dict(Type='volume',Name=identity['volumes'][dest]['Name'],RW=False) for dest in (SOURCE,SOURCE+'/out')}
    private=checked(receipt['private_manifest']).parent
    mounts.update({'/work':dict(Type='bind',Source=str(root),RW=False),str(output):dict(Type='bind',Source=str(output),RW=True),
                   str(private):dict(Type='bind',Source=str(private),RW=False),
                   str(exporter.parent):dict(Type='bind',Source=str(exporter.parent),RW=False),
                   str(paths['native_evidence']):dict(Type='bind',Source=str(paths['native_evidence']),RW=False)})
    require(len(mounts)==7 and entry.get('mounts')==mounts,'collector planned mounts do not join actual native source/out and input descriptors')
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
        OomKillDisable=False,Ulimits=[],
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
        inspected(rows[cursor],cid,name,NATIVE376_IMAGE,cfg,dict(host,OomKillDisable={'created':False,'exited':None}[status]),actual_mounts,running=False,status=status);cursor+=1
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
    expected_anchor=SOURCE+'/vendor/ohemu/virt/virt_'+config['target']['device']+'_full.meta.json'
    anchors=[r for r in doc['files'] if r.get('path')==expected_anchor]
    require(len(anchors)==1 and anchor.get('metadata')==anchors[0] and
            anchor.get('native_source_revision')==config['expected_source_commit'] and
            anchors[0].get('resolved')==expected_anchor and
            anchors[0].get('export_relative')=='files/vendor/ohemu/virt/virt_'+config['target']['device']+'_full.meta.json',
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
