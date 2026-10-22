"""Root's fixed full L22 joins after original owners have actually closed.

The finite transaction oracle stays unchanged in meaning. Whole supported
obligations also require full original RTT/5A replay, full native compilation
identity and the exact source-qualified carrier IMS boundary. No resource or
DATA-selected code is launched here.
"""
from pathlib import Path
import json
import re
import shlex

from final579_contract import ROOT,HERE,COMMIT,checked,doc,ref,save,need,fixed,api_source_root
from telephony579_tun import SONAME,BASE,NATIVE_SOURCES,product_input

IDENTIFIER='behavior:telephony-no-modem-or-sim'
FACTS=ROOT/'ci/capability-audit/policy579/execution-20261021/ims-provider-source-facts579.json'
FACTS_SHA='c73a5f73e5b85cebd57ecd2477adaf49b29e75fe6e8b85b400d604e8e6fefc01'


def data_ref(value):return {k:value[k] for k in ('path','sha256','bytes') if k in value}


def native_product(inputs,archive):
    row=inputs['telephony579'];value=doc(row['product_export'])
    need(value['source_commit']==COMMIT and value['archive']==archive,'actual current normal native product identity')
    product_input(inputs,archive['sha256'],value['product'])
    source=doc(value['source_export']);library=doc(value['library']);profile=doc(value['installed_runtime_profile'])
    need(source['source_commit']==COMMIT and source['archive_sha256']==archive['sha256'] and
        source['source_kind']=='actual_shared_source_and_out_readonly_export' and source['resources_executed'] is True and
        source['cleanup_verified'] is True and source['failures']==[] and library['schema']=='telephony579-whole-product-DSO/v1' and
        library['source_export']==value['source_export'] and library['installed_runtime_profile']==value['installed_runtime_profile'] and
        library['source_commit']==COMMIT and library['archive_sha256']==archive['sha256'] and library['soname']==SONAME,
        'actual completed full source/out/native product production')
    for logical,digest in NATIVE_SOURCES.items():
        need(value['native_sources'][logical]==source['files'][logical] and
            ref(checked(value['native_sources'][logical]))['sha256']==digest,'complete fixed normal product native sources')
    helper=fixed('batch_system_build_runtime_helpers',ROOT/'ci/capability-audit')
    helper.validate_installed_profile(profile,archive_sha256=archive['sha256'])
    image=checked(library['image_file']);linked=checked(library['linked_output'])
    need(image.read_bytes()==linked.read_bytes() and library['image_file']==profile['dsos'][SONAME]['image_file'] and
        helper.elf_soname(image,product=value['product'])==SONAME,'actual native ELF and independent image SONAME/full bytes')
    root,build=Path(library['source_root']),Path(library['build_directory'])
    need(root==Path('/ohos') and build==root/'out'/value['product'],'actual selected normal source/build roots')
    graphics=fixed('graphics579_replay',HERE/'media579')
    ninja_log=checked(library['complete_ninja_log']).read_text().splitlines()
    link=graphics.replay_solink(library['link'],export=source,root=root,build=build,target=library['ninja_target'],
        helper=helper,ninja_log=ninja_log)
    need(link['effective_CFI'] is True,'actual original normal native DSO link must retain cross-DSO CFI')
    driver=link['actual_driver'];database=doc(library['complete_compile_commands'])
    query=library['complete_compile_query']
    need(query in source['commands'] and query['exit_code']==0 and query['timed_out'] is False and
        query['stdout']==library['complete_compile_commands'] and query['argv'][1:6]==['-C',str(build),'-t','compdb','-x'],
        'full actual expanded normal product compile database')
    checked(query['stdout']);need(checked(query['stderr']).read_bytes()==b'','complete compile query success')
    units=library['translation_units'];direct={str((build/token).resolve()) for token in driver if token.endswith('.o')}
    need(units and {u['object_logical'] for u in units.values()}==direct and
        {BASE+'src/qemu_modem_tun.cpp',BASE+'src/netsys_native_service.cpp'}<=set(units),
        'every full original native DSO translation unit, including module and lifecycle')
    for logical,unit in units.items():
        for name in ('source','object','dependency_file'):checked(unit[name])
        need(unit['source']==source['files'][logical],'actual complete native TU source')
        candidates=[entry for entry in database if (Path(entry['directory'])/entry['file']).resolve()==root/logical and
            str((Path(entry['directory'])/((entry.get('arguments') or shlex.split(entry['command']))[
                (entry.get('arguments') or shlex.split(entry['command'])).index('-o')+1])).resolve())==unit['object_logical']]
        need(len(candidates)==1,'one actual full source/object compile command in original database')
        argv=candidates[0].get('arguments') or shlex.split(candidates[0]['command'])
        need(argv==unit['command'] and helper.effective_cfi(argv) and unit['effective_CFI'] is True and
            '-fno-exceptions' in argv and '-O0' not in argv and '-flto=thin' in argv,
            'preserve actual normal full-TU optimization/ThinLTO/platform ABI/cross-DSO CFI')
        dependency=unit['dependency_query']
        need(dependency in source['commands'] and dependency['exit_code']==0 and dependency['timed_out'] is False and
            dependency['stdout']==unit['dependency_file'] and unit['dependency_kind']=='original_ninja_deps/v1' and
            dependency['argv'][1:]==['-C',str(build),'-t','deps',unit['dependency_object']],
            'actual complete exact-object native dependency query')
        need(checked(dependency['stderr']).read_bytes()==b'','complete native dependency stderr')
        lines=checked(unit['dependency_file']).read_text().splitlines()
        match=re.fullmatch(re.escape(unit['dependency_object'])+r': #deps ([0-9]+), deps mtime [0-9]+ \(VALID\)',lines[0] if lines else '')
        dependencies=[line[4:] for line in lines[1:] if line.startswith('    ')]
        need(match and len(dependencies)==int(match[1]) and all(not line or line.startswith('    ') for line in lines[1:]) and
            root/logical in {(build/p).resolve() for p in dependencies},'complete actual native source/object dependency record')
        token=str(Path(unit['object_logical']).relative_to(build))
        need(any(len(line.split('\t'))==5 and line.split('\t')[3]==token for line in ninja_log),
            'actual original complete Ninja log must contain every normal native object')
    return dict(product_export=row['product_export'],library=value['library'],actual_normal_link=link,
        complete_translation_unit_count=len(units),same_image_library=library['image_file'])


def ims_boundary(inputs,archive,actual_source):
    from release_scope import partial_provider_policy
    device=doc(inputs['telephony579']['product_export'])['product']
    value=doc(inputs['telephony579']['product_export']);profile=doc(value['installed_runtime_profile'])
    policy=partial_provider_policy(profile['device'])['QemuCarrierIMSTransport579']
    need(policy['id']==IDENTIFIER and policy['whole_id_unsupported'] is False and
        ref(FACTS)['sha256']==FACTS_SHA and policy['source_facts']==dict(path=str(FACTS.relative_to(ROOT)),sha256=FACTS_SHA,bytes=FACTS.stat().st_size),
        'explicit exact user-authorized partial IMS provider policy; whole L22 remains mandatory')
    facts=doc(ref(FACTS));fresh=doc(value['rtt_source_facts'])
    need(value['rtt_source_facts']['sha256']==actual_source['source']['sha256'],'same current source as complete original RTT/5A actor')
    rows=[r for r in fresh['projects'] if r['path']=='base/telephony/cellular_call']
    need(len(rows)==1 and rows[0]['head_matches_fixed7'] is True and
        rows[0]['actual_head']==facts['selected_release_project_head'] and rows[0]['complete_ims_vendor_source_tree'] is True and
        rows[0]['complete_ims_working_source_tree'] is True,'complete actual current release IMS provider source and fixed HEAD')
    expected=facts['current_release_complete_vendor_sources']
    prefix='base/telephony/cellular_call/'
    need({prefix+p for p in rows[0]['complete_ims_vendor_source_paths']}==set(expected) and
        {prefix+p for p in rows[0]['complete_ims_working_source_paths']}==set(expected),
        'new or untracked provider source must reopen the precise IMS boundary')
    mappings={r['original_container_ref']['path']:r['actual_host_ref'] for r in actual_source['actual_host_mapping']}
    source_files={r['source_path']:r['raw'] for r in fresh['files']}
    for logical,pin in expected.items():
        raw=source_files[logical]
        need(raw['sha256']==pin['sha256'] and raw['bytes']==pin['bytes'],'changed IMS demo body requires source review')
        checked(mappings[raw['path']])
    inventory=doc(value['ims_image_inventory']);producer=doc(value['original_profile_receipt'])
    need(inventory['schema']=='telephony579-actual-native-provider-image-inventory/v1' and
        inventory['source_commit']==producer['source_commit']==COMMIT and
        data_ref(inventory['archive'])==data_ref(producer['package']) and inventory['archive']['sha256']==archive['sha256'] and
        inventory['images']==producer['images'] and producer['exit_code']==0 and
        inventory['complete_selected_native_library_profile_init_trees'] is True,
        'all actual new package images must be independently read by original profile producer')
    def actual_command(argv):
        need(argv[0]==str(checked(producer['debugfs'])),'actual admitted original profile debugfs only')
        found=[r for r in producer['commands'] if r['argv']==argv]
        need(len(found)==1 and found[0]['exit_code']==0 and found[0]['timed_out'] is False,'one completed original image-read command')
        checked(found[0]['stderr']);return found[0]
    # Reconstruct complete trees from root entries and original raw directory
    # reads. A listed new provider invalidates this boundary even if unused.
    from telephony579_image_inventory import verify as verify_inventory
    images=verify_inventory(inventory,actual_command,selected_profile=value['installed_runtime_profile'])
    for row in inventory['service_configurations']:
        record=actual_command(row['argv']);checked(record['stdout'])
        raw=checked(row['file']).read_bytes()
        need(not re.search(rb'(?<![0-9])4014(?![0-9])',raw) and b'libtel_ims.z.so' not in raw,
            'installed SA4014/IMS provider config invalidates the source-qualified absent-provider scope')
    return dict(policy=policy,source_facts=ref(FACTS),fresh_source=value['rtt_source_facts'],
        actual_new_image_inventory=value['ims_image_inventory'],independently_replayed_images=images,
        IMS_positive_unsupported_only=True,whole_id_unsupported=False,counts_as_fixed=False)


def collect(packet,inputs,output):
    need(packet['api']['kind']=='raw_assembly','original actual API main record index required')
    index=doc(packet['api']['main_index']);boot=doc(packet['main_boot'])
    need(index['schema']=='api26-main-closedio-index579/v1' and index['archive_sha256']==packet['archive']['sha256'] and
        index['boot_id']==boot['test_environment']['boot_id'],'original current main communications record index')
    records=index['records']
    def original(name):
        row=records['communications/'+name]
        return dict(retained=row['retained'],boot=row['boot'])
    api=api_source_root();bundle=fixed('api26_579_bundles',api)
    # This is the original complete raw RTT10 and explicit5A oracle, including
    # its real independent input, role denials, queued off/reset, death, quiet
    # and cleanup. No passed flag or getter-only replacement is accepted.
    replay=bundle.rtt_observer(archive=packet['archive'],lifecycle=original('observer-lifecycle'),
        observer_denied=original('observer-denied'),rtt=original('rtt'),rtt_denied=original('rtt-denied'),
        rtt_ordinary=original('rtt-ordinary'),no_modem=original('no-modem'),rtt_source_facts=index['rtt_source_receipt'],
        output=output/'original-rtt-and-5a')
    actual=doc(replay)
    need(actual['family']=='rtt578' and actual['producer_kind']=='rtt_observer_bundle' and
        actual['archive_sha256']==packet['archive']['sha256'] and actual['boot_id']==index['boot_id'],
        'full original raw RTT and explicit5A replay must belong to this new boot/package')
    source=fixed('api26_579_source_receipt',api).verify(index['rtt_source_receipt'],packet['archive'])
    native=native_product(inputs,packet['archive'])
    ims=ims_boundary(inputs,packet['archive'],source)
    return save(output/'full-supported-obligations.json',dict(schema='actual-L22-full-supported-obligations579/v1',
        archive=packet['archive'],boot=packet['main_boot'],original_main_index=packet['api']['main_index'],
        original_full_RTT10_and_explicit5A=replay,actual_current_source=source,native_product=native,
        precise_carrier_IMS_boundary=ims,supported_obligations_replayed=True,
        actual_IMS_session_or_messages_claimed=False,whole_ID_excluded=False,runtime_pass=False,
        original_owner_finish_still_required=True,first_artifact_behavior_gate_passed=False))
