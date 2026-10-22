"""Finite first-phone DATA successor: actual F18 resources over unchanged 377/379.

No resource, Git subprocess, SDK, signing or owner entry. New files only after
actual canonical native/export replay; complete image-provider/47 checks stay pending.
"""
from pathlib import Path, PurePosixPath
import argparse,copy,hashlib,json,re,stat,sys,types
sys.dont_write_bytecode=True
CANONICAL_SHA256={'ci/capability-audit/batch_apps_completed_provider_binding.py': 'b1b756c95e0680cf638023d130ce7627ba8b605640ff359509bd3d22f224f789', 'ci/capability-audit/batch_apps_production_provider_binding.py': '6b56c13ffbb7ffc7fbb7516303fbb42e42e07903d496599a599dd45576d0df38', 'ci/capability-audit/parallel_runtime_suite.py': 'b898ef5bd86726f4cb9b7cef8bc1c1adc7197553cded6b74e2041242e293c4cb', 'ci/capability-audit/production579_native_resources.py': '46431f1a03de918462249195ffa651c2ca9991ca2c2bebcf33e5311290004104', 'ci/capability-audit/production579_target.py': 'd38b8a7578709e9ca3d16966c5a6bdfe84c7b44b8acc03f74dfaf3e48df97097', 'ci/capability-audit/batch_system_build_runtime_helpers.py': '9c4db163b28e934bb41c7e19806d71b25a9c230cd048ba1d7b6c1a31f1d94ead', 'ci/capability-audit/production579_completed_2in1_provider.py': '5de77e4ad1e59403c5a246a976a07d54cca3631407c76c2eff269507d4fb9283'}

SCHEMA='four-family-completed-provider-inputs391/v1'
FIELDS={'schema','expected_source_commit','qa_root','base_preparation','base_capability_inputs','archive',
        'native_evidence','native_launcher_log','native_build_log','exports','export_receipt',
        'producer_sources','historical_reuse','output'}
DESCRIPTORS=('base_preparation','base_capability_inputs','archive','native_evidence','native_launcher_log',
             'native_build_log','exports','export_receipt')
ROLES=(('contacts-picker','contacts','inputs'),('wallpaper','theme','artifacts'))


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):
    value=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):value.update(block)
    return value.hexdigest()


def regular(raw):
    p=Path(raw)
    require(p.is_absolute()and p.resolve()==p and all(not q.is_symlink()for q in (p,*p.parents)),
            'canonical unaliased input required')
    info=p.stat();require(stat.S_ISREG(info.st_mode)and info.st_nlink==1,'single regular input required')
    return p


def record(p):
    p=regular(p);return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)


def checked(row):
    require(type(row)is dict and set(row)in ({'path','sha256'},{'path','sha256','bytes'})and
            type(row.get('path'))is str and type(row.get('sha256'))is str and
            re.fullmatch('[a-f0-9]{64}',row['sha256']),'real path/SHA descriptor required; pending values reject')
    p=regular(row['path']);require(sha(p)==row['sha256']and('bytes'not in row or
        type(row['bytes'])is int and row['bytes']==p.stat().st_size),'actual descriptor bytes changed')
    return p


def load(p):
    def pairs(rows):
        value={}
        for k,v in rows:require(k not in value,'duplicate JSON key');value[k]=v
        return value
    def invalid(v):raise ValueError('nonfinite JSON value')
    return json.loads(regular(p).read_text(),object_pairs_hook=pairs,parse_constant=invalid)


def shape(intent):
    require(type(intent)is dict and set(intent)==FIELDS and intent.get('schema')==SCHEMA,'exact391 data intent required')
    require(type(intent.get('expected_source_commit'))is str and
            re.fullmatch('[a-f0-9]{40}',intent['expected_source_commit']),'explicit actual full source commit required')
    pending=[name for name in (*DESCRIPTORS,'qa_root','producer_sources','historical_reuse','output')if intent[name]is None]
    require(not pending,'required real inputs still pending: '+','.join(pending))
    require(type(intent['producer_sources'])is dict and set(intent['producer_sources'])=={'exporter','collector'},
            'both actual fixed producer source descriptors required')
    require(type(intent['historical_reuse'])is dict and set(intent['historical_reuse'])=={'contacts','theme'},
            'explicit per-provider historical reuse proof or null required')
    return intent


def canonical(qa):
    qa=Path(qa)
    require(qa.is_absolute()and qa.resolve()==qa and qa.is_dir()and all(not p.is_symlink()for p in (qa,*qa.parents)),
            'explicit real canonical QA directory required')
    for name,digest in CANONICAL_SHA256.items():
        require(sha(regular(qa/name))==digest,'unreviewed canonical source: '+name)
    sys.path[:0]=[str(qa/'ci/capability-audit'),str(qa/'scripts')]
    modules=[]
    for name in ('batch_apps_production_provider_binding','batch_apps_completed_provider_binding','parallel_runtime_suite',
                 'batch_system_build_runtime_helpers','production579_target','production579_completed_2in1_provider'):
        path=regular(qa/'ci/capability-audit'/(name+'.py'));raw=path.read_bytes()
        require(hashlib.sha256(raw).hexdigest()==CANONICAL_SHA256['ci/capability-audit/'+name+'.py'],'canonical bytes changed before load')
        previous=sys.modules.get(name)
        require(previous is None or Path(previous.__file__).resolve()==path,'foreign cached canonical module')
        module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
        exec(compile(raw,str(path),'exec'),module.__dict__) # exact reviewed bytes, no adjacent pyc
        modules.append(module)
    return modules[1],modules[2],modules[4],modules[5]


def profile_roles(environment,suite):
    """Only the actual archive environment selects the original applicable roles."""
    families=suite.applicable_families(environment)
    expected=(('contacts-picker','wallpaper','external-inputs','knowledge-holiday')
              if environment['device_type']=='phone' else ('wallpaper','external-inputs','knowledge-holiday'))
    require(families==expected,'exact applicable phone4 or true2in1-three original families required')
    roles=ROLES if environment['device_type']=='phone' else ROLES[1:]
    require(tuple(row[0]for row in roles)==tuple(name for name in families if name in ('contacts-picker','wallpaper')),
            'all and only applicable original image providers required')
    return families,roles


def retained_later_config(spec,expected,checker):
    """Keep the F15 provider's complete config and prove every original field."""
    provider=spec.get('provider')
    require(type(provider)is dict,'original later-target provider spec required')
    prior=provider.get('production_build')
    require(type(prior)is dict and set(prior)==set(expected)==checker.FIELDS,
            'complete existing F15 later-target provider config required')
    descriptors={'archive','native_evidence','native_launcher_log','native_build_log','exports','export_receipt'}
    for name in checker.FIELDS-descriptors-{'producer_sources'}:
        require(prior[name]==expected[name],'existing later-target provider field differs: '+name)
    for name in descriptors:
        require(checked(prior[name])==checked(expected[name]),'existing later-target provider actual Ref differs: '+name)
    require(type(prior['producer_sources'])is dict and set(prior['producer_sources'])==set(expected['producer_sources'])=={'exporter','collector'},
            'complete existing later-target producer source pair required')
    for name in ('exporter','collector'):
        require(checked(prior['producer_sources'][name])==checked(expected['producer_sources'][name]),
                'existing later-target producer source differs: '+name)
    return copy.deepcopy(prior)


def patch_documents(plan,specs,configs,output,*,environment,suite):
    """Pure data transform only; does not admit a config or claim provider proof."""
    families,roles=profile_roles(environment,suite)
    result=copy.deepcopy(plan);updated={}
    require(plan['product']==environment['product'] and plan['device_type']==environment['device_type'] and
            set(plan['families'])==set(families),'all exact actual-profile original families required')
    require(set(specs)=={family for family,_,_ in roles} and set(configs)=={provider for _,provider,_ in roles},
            'complete actual-profile image provider inputs, without inapplicable Contacts')
    for family,provider,key in roles:
        spec=copy.deepcopy(specs[family]);require(type(spec.get('provider'))is dict,'original provider spec required')
        if suite.representative(environment):
            require('production_build'not in spec['provider'],'use unchanged377 base inputs, not relabelled old provider binding')
            spec['provider']['production_build']=copy.deepcopy(configs[provider])
        else:
            require(spec['provider'].get('production_build')==configs[provider],
                    'fully replayed existing later-target provider config must remain byte-for-byte DATA')
        updated[family]=spec
        result['families'][family][key]=str(output/(family+'-inputs.json'))
    for family in ('external-inputs','knowledge-holiday'):
        require(result['families'][family]==plan['families'][family],'unrelated family changed')
    return result,updated


def write_new(path,value):
    with path.open('x')as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
    return record(path)


def assemble(intent):
    shape(intent);original,suite,targets,later=canonical(intent['qa_root']);expected=intent['expected_source_commit']
    paths={name:checked(intent[name])for name in DESCRIPTORS}
    watched={str(path):record(path)for path in paths.values()}
    target=targets.archive_manifest(paths['archive'])['context']
    environment=dict(product=target['product'],device_type=target['device'],guest_arch=target['arch'])
    families,roles=profile_roles(environment,suite)
    first=suite.representative(environment)
    c=original if first else later
    if target['device']=='2in1':
        require(intent['historical_reuse']['contacts']is None,'true2in1 cannot carry an inapplicable Contacts reuse proof')
    if not first:
        require(all(intent['historical_reuse'][provider]is None for _,provider,_ in roles),
                'original ARM64phone history cannot establish a later-target provider lineage')
    prep=load(paths['base_preparation']);native=load(paths['native_evidence'])
    require(prep.get('status')=='pass_inputs_ONLY'and prep.get('source_commit')==prep.get('package_source_commit')==expected and
        prep.get('package_archive_sha256')==sha(paths['archive'])and prep.get('runtime_ready')is False and
        prep.get('production_binding_pending')is True and type(prep.get('closure_count'))is int and prep['closure_count']==0 and
        prep.get('closed_requirement_ids')==[]and prep.get('failures')==[]and prep.get('first_artifact_behavior_gate_passed')is False and
        checked(prep['plan'])==paths['base_capability_inputs']and checked(prep['original_inputs']['package'])==paths['native_evidence'],
        'actual same-new-package377 inputs-only preparation required')
    require(type(native.get('exit_code'))is int and native['exit_code']==0 and native.get('source_commit')==expected and
        native.get('cleanup_verified')is True and native.get('owned_container_absent')is True and
        native.get('owned_launcher_group_closed')is True and native.get('resource_lease_held')is False and
        native.get('adopted_complete_host_environment',{}).get('PREPARE_ONLY')=='0'and
        native['adopted_complete_host_environment'].get('BUILD_ONLY_LOAD')=='0'and
        checked(native['package'])==paths['archive'],'actual completed0 new native package and closed resources required')
    plan=suite.load_plan(paths['base_capability_inputs'],environment)
    specs={family:load(regular(plan['families'][family][key]))for family,_,key in roles}
    for family,_,key in roles:
        path=regular(plan['families'][family][key]);watched[str(path)]=record(path)
    output=Path(intent['output'])
    require(output.is_absolute()and output.parent.resolve()==output.parent and output.parent.is_dir()and not output.exists()and
        all(not p.is_symlink()for p in output.parents)and not output.is_relative_to(Path(intent['qa_root'])),
        'fresh external output outside canonical/frozen source trees required')
    metadata,hashes=c.archive_inputs(paths['archive'])
    export,files=(c.exports_checked(paths['exports'],intent['native_evidence'],intent['producer_sources']) if first else
                  c.exports_checked(paths['exports'],intent['native_evidence'],intent['producer_sources'],target=target))
    relative=PurePosixPath(export['detailed_log_export_relative'])
    require(not relative.is_absolute()and '..'not in relative.parts and
        regular(paths['exports'].parent/str(relative))==paths['native_build_log'],'actual exported detailed native log required')
    configs={};actions={};native_phase=None
    inputs=metadata['build-inputs.json']
    from snapshot_build_inputs import digest_files
    require(inputs['source_git_revision']==expected and inputs['files_sha256']==digest_files(Path(intent['qa_root']))and
        c.tree_digest(inputs['files_sha256'])==inputs['tree_sha256'],'actual archive/final canonical source tree differs')
    require(hashes['contacts-native/execution-log.txt']==sha(paths['native_build_log']),
            'actual detailed native log differs from new package witness')
    for family,provider,key in roles:
        cfg=dict(schema_version=1,kind=(c.KIND if first or target['device']=='2in1' else c.PHONE_KIND),
            expected_source_commit=expected,qa_root=intent['qa_root'],
            producer_sources=copy.deepcopy(intent['producer_sources']),archive=record(paths['archive']),
            native_evidence=record(paths['native_evidence']),native_launcher_log=record(paths['native_launcher_log']),
            native_build_log=record(paths['native_build_log']),exports=record(paths['exports']),
            export_receipt=record(paths['export_receipt']),historical_reuse=copy.deepcopy(intent['historical_reuse'][provider]))
        if not first:
            cfg['target']=copy.deepcopy(target)
            cfg=retained_later_config(specs[family],cfg,c)
        require(set(cfg)==c.FIELDS,'exact selected canonical twelve/thirteen-field provider contract changed')
        c.canonical_context(cfg) # Actual HEAD and fixed producer source SHA, never old bootstrap.
        if native_phase is None:
            if first:
                _,native_phase=c.native_completion(intent['native_evidence'],intent['native_launcher_log'],expected,
                                                    paths['archive'],inputs['tree_sha256'])
            else:
                _,native_phase=c.native_completion(intent['native_evidence'],intent['native_launcher_log'],expected,
                                                    paths['archive'],inputs['tree_sha256'],target=target)
            c.verify_export_receipt(cfg,paths,inputs)
        provider_row=(c.PROVIDERS[provider] if first else c.CONTACTS if provider=='contacts' else
                      c.PHONE_THEME if target['device']=='phone' else c.PROVIDERS['theme'])
        project,provider_target,_,module,_,_=provider_row
        action=c.classify_action(paths['native_build_log'].read_text(),project,module,
            'ACTION //'+project+':'+provider_target+'_compile_app(', 'ACTION //'+project+':'+provider_target+'(')
        if action['mode']in ('current_ninja_incremental_reuse','current_hvigor_action_cached_ArkTS'):
            require(first,'later-target cached HAP has no admitted complete same-target producer history')
            reuse=cfg['historical_reuse']
            require(type(reuse)is dict and set(reuse)=={'config','image_signed_hap','system_image_sha256'}and
                    type(reuse['config'])is dict and type(reuse['system_image_sha256'])is str and
                    re.fullmatch('[a-f0-9]{64}',reuse['system_image_sha256']),
                    'actual cached/Ninja HAP requires explicit retained historical proof; not a fresh epoch')
            checked(reuse['image_signed_hap'])
        actions[provider]=action
        configs[provider]=cfg
    changed,updated=patch_documents(plan,specs,configs,output,environment=environment,suite=suite)
    for descriptor in watched.values():checked(descriptor)
    for row in intent['producer_sources'].values():checked(row)
    require(c.checkout_head(Path(intent['qa_root']))==expected,'actual canonical commit changed during assembly')
    for name,digest in CANONICAL_SHA256.items():require(sha(regular(Path(intent['qa_root'])/name))==digest,'canonical source changed')
    output.mkdir(mode=0o700)
    for family,spec in updated.items():write_new(output/(family+'-inputs.json'),spec)
    capability=write_new(output/'capability-inputs.json',changed)
    suite.load_plan(Path(capability['path']),environment)
    for descriptor in watched.values():checked(descriptor)
    report=dict(schema='provider-inputs391-data-only/v1',status='assembled_DATA_ONLY',source_commit=expected,
        assembly_source=record(Path(__file__).resolve()),
        normal_owner_source_replay='F18 raw lifecycle via fixed production579_native_resources',
        capability_inputs=capability,base_preparation=record(paths['base_preparation']),base_capability_inputs=record(paths['base_capability_inputs']),
        package_receipt=record(paths['native_evidence']),archive=record(paths['archive']),export_receipt=record(paths['export_receipt']),
        canonical_native_frontend_phase=native_phase,current_action_classification=actions,
        image_provider_HAP_and_signature_replay_pending=True,unchanged_families=['external-inputs','knowledge-holiday'],
        SDK_receipts_modified=False,old_inputs_modified=False,compiled_or_signed=False,runtime_ready=False,
        production_binding_pending=True,runtime_validated=False,closed_requirement_ids=[],closure_count=0,
        first_artifact_behavior_gate_passed=False)
    return write_new(output/'preparation391.json',report)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--intent',type=Path,required=True)
    parser.add_argument('--intent-sha256',required=True);args=parser.parse_args()
    path=checked(dict(path=str(args.intent),sha256=args.intent_sha256))
    result=assemble(load(path));require(sha(path)==args.intent_sha256,'391 intent changed during read-only assembly')
    print(json.dumps(result))

if __name__=='__main__':main()
