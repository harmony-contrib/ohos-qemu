"""Pure exact after-project411 overlay; no SDK, signer, process or resources."""
from pathlib import Path
import hashlib, json, math, re, stat, zipfile
from pathlib import PurePosixPath
HERE=Path(__file__).resolve().parent
PREFIX='entry/src/main/ets/entryability/'
ORIGINAL={'EntryAbility.ets': '0b098db225c309752fca0f020ffae35b89cc1b146487edea87feb0c95c43d888', 'LegacyNapiNumberProbe.js': 'e912c4fdd00e14608758db3ea74f141f77746fe33f62d8193854b34c498de0d3', 'LegacyNapiNumberProbe.d.ts': '61ea303494c6d174b967f1920af7f481e5ea521378e7ed19018de79064098c47', 'NapiProbe411.ets': 'cea07fd0826e01e764b2dbae182f52d73228f47395129291ba9e6d6a1a92163a', 'NapiToken411.ets': '46ceffe6b9f66b3a6bba83da462ae7af11cc9a0b0c890fe7036d1e263b7ef21d', 'NumberLocalProbe.ets': 'f38f269b218f60499994f5d62d949bcea98852481c4fe12cffd9959dc3f6b73b', 'TokenObservation.ets': '8b37bc3744e55748baf92f98b23e4934d8711d005196983336a5cbea0993292c'}
ADDED={'LegacyNumberCorpus580.d.ts': 'f723230fbfdfb3cb97566b813db36c6f730c9f620f9ab5c2bb9cda29e04ed3eb', 'LegacyNumberCorpus580.js': '19d5122209d0df9dd6fca3af43eb1941b23122b71ffa366284c72483de93d670', 'NumberCorpus580.ets': '060a748d4c264f30b67974e41e04ac1e80f2c171059d85b44e9715a0bb6446d4'}
CUTS=[{'before': "import { NapiProbe411 } from './NapiProbe411';\n", 'after': "import { NapiProbe411 } from './NapiProbe411';\nimport { NumberCorpus580 } from './NumberCorpus580';\n", 'required_occurrences_before': 1, 'required_occurrences_after': 1}, {'before': "    if (phase === 'napi-read') {\n", 'after': "    if (phase === 'corpus580') {\n      const ownerRun = String(want.parameters?.['ownerRun'] ?? '');\n      const caseId = String(want.parameters?.['caseId'] ?? '');\n      const role = String(want.parameters?.['role'] ?? '');\n      const corpus = new NumberCorpus580(this.context, run, ownerRun, caseId, number, role);\n      corpus.run().finally(() => this.context.terminateSelf());\n      return;\n    }\n    if (phase === 'napi-read') {\n", 'required_occurrences_before': 1, 'required_occurrences_after': 1}]

def need(value,message):
    if not value:raise ValueError(message)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def augment(files):
    need(type(files) is dict,'exact original411 completed source dictionary required')
    for name,expected in ORIGINAL.items():
        need(PREFIX+name in files and type(files[PREFIX+name]) is str and
             digest(files[PREFIX+name].encode())==expected,'unknown/partial original411 caller: '+name)
    need(not any(PREFIX+n in files for n in ADDED),'partial/repeated corpus overlay refused')
    result=dict(files);entry=files[PREFIX+'EntryAbility.ets']
    for cut in CUTS:
        need(entry.count(cut['before'])==1,'Entry source preimage not unique')
        entry=entry.replace(cut['before'],cut['after'],1)
    inverse=entry
    for cut in reversed(CUTS):
        need(inverse.count(cut['after'])==1,'Entry source inverse not unique')
        inverse=inverse.replace(cut['after'],cut['before'],1)
    need(inverse==files[PREFIX+'EntryAbility.ets'],'Entry full inverse differs')
    result[PREFIX+'EntryAbility.ets']=entry
    for name,expected in ADDED.items():
        path=HERE/'caller'/name;raw=path.read_bytes()
        need(path.is_file() and not path.is_symlink() and digest(raw)==expected,'new corpus source changed')
        result[PREFIX+name]=raw.decode('utf-8')
    need(all(result[PREFIX+n]==files[PREFIX+n] for n in ORIGINAL if n!='EntryAbility.ets'),
         'old fivephase/token/NAPI sources changed')
    return result


def source_materials():
    """Actual fixed overlay source Refs for Root's existing SDK producer."""
    result={}
    for name,expected in ADDED.items():
        path=HERE/'caller'/name;raw=path.read_bytes()
        need(path.resolve()==path and not path.is_symlink() and digest(raw)==expected,'overlay source changed: '+name)
        result[name]=dict(path=str(path),sha256=digest(raw),bytes=len(raw))
    path=Path(__file__).resolve();raw=path.read_bytes()
    return dict(project=dict(path=str(path),sha256=digest(raw),bytes=len(raw)),
                caller_sources=result,original_caller_sha256=dict(ORIGINAL),entry_cuts=list(CUTS),
                scope='pure fixed source overlay only; Root retains actual SDK/tool/compile/sign/UID receipts')


def sdk_role_artifacts(item, role, commit, *, original_collector):
    """Replay the real Number SDK schema; no synthetic haps compatibility view."""
    c = original_collector
    checked, record, decode = c.checked, c.record, c.decode
    ROLES, GET, SET = c.ROLES, c.GET, c.SET
    SDK_SCHEMA = 'number-local580-actual-SDK/v1'
    NAPI_MANIFEST_SHA, CALLER_MANIFEST_SHA, TOKEN_MANIFEST_SHA = c.NAPI_MANIFEST_SHA, c.CALLER_MANIFEST_SHA, c.TOKEN_MANIFEST_SHA
    ADMISSION_TOOLS, SDK_SHAS, ACCESS_CTRL_SHA = c.ADMISSION_TOOLS, c.SDK_SHAS, c.ACCESS_CTRL_SHA
    CLI, NODE, CPU_CAP_SHA = c.CLI, c.NODE, c.CPU_CAP_SHA
    PROJECT_FILES = c.PROJECT_FILES | frozenset(PREFIX+n for n in ADDED)
    expected_materials = source_materials()
    materials = {}
    def source(descriptor):
        path = checked(descriptor)
        materials[str(path)] = record(path)
        return path
    def parsed(descriptor):
        return decode(source(descriptor).read_bytes())
    evidence = parsed(item['sdk_evidence'])
    need(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit) and
         evidence.get('schema') == SDK_SCHEMA and evidence.get('source_commit') == commit and
         type(evidence.get('exit_code')) is int and evidence['exit_code'] == 0 and
         evidence.get('failures') == [] and evidence.get('signed') is False and
         evidence.get('guest_executed') is False and
         evidence.get('first_artifact_behavior_gate_passed') is False,
         'actual Number SDK schema/source/complete compile required')
    need(evidence['source_materials']==expected_materials and
         evidence['original_driver']['sha256']==c.SDK_DRIVER_SHA,
         'exact new overlay plus immutable original SDK driver lineage required')
    normal=parsed(evidence['archive_binding']['normal_source'])
    need(normal['source_commit']==commit and type(normal.get('number_local')) is dict,
         'actual fixed normal source Number closure required')
    driver=normal['number_local']['sources']['produce580.py']
    need(driver['path']==str(HERE/'produce580.py') and evidence['driver']==driver,
         'normal SOURCE selects only the fixed sibling producer identity')
    SDK_DRIVER_SHA=driver['sha256']
    source(evidence['original_driver']); source(evidence['driver'])
    need(evidence['target']['device']=='phone' and evidence['target']['arch'] in ('arm64','x86_64','armv7a'),
         'finite actual phone target')
    for row in evidence['archive_binding'].values():source(row)
    need(set(evidence['archive_binding'])=={'inputs','archive','image','profile','normal_source','sdk_declaration','manifest','build_inputs'},
         'complete source/archive/normal SDK binding vector')
    archive_inputs=parsed(evidence['archive_binding']['build_inputs'])
    need(archive_inputs['source_git_revision']==commit,'SDK belongs to another actual archive HEAD')
    source(evidence['selected_device_profile'])
    need(type(evidence['run']) is str and re.fullmatch('[0-9a-f]{32}',evidence['run']), 'actual normal SDK nonce')
    need(evidence['driver']['sha256'] == SDK_DRIVER_SHA, 'reviewed Number SDK driver required')
    # The closed receipt includes a large cache inventory. Parse it with an
    # explicit bound, consuming only its actual source/SDK/tool admission;
    # none of its fields is accepted as resource ownership or runtime success.
    admission_raw = source(evidence['input_admission']).read_bytes()
    need(0 < len(admission_raw) <= 64 * 1024 * 1024, 'bounded actual SDK admission required')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'duplicate SDK admission field')
            value[key] = item
        return value
    admission = json.loads(admission_raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite SDK admission')))
    need(admission['schema'] == 'F-SDK-batch29-input-admission/v1' and
         admission['source_commit'] == commit and admission['status'] == 'input_admitted' and
         type(admission['exit_code']) is int and admission['exit_code'] == 0 and
         admission['failures'] == [] and all(admission[k] is False for k in
             ('sdk_started', 'docker_started', 'resource_commands_started')),
         'actual SDK pre-launch source/input admission differs')
    for name, (literal, expected_sha) in ADMISSION_TOOLS.items():
        tool = admission['tools'][name]
        need(tool['requested'] == tool['resolved'] == literal and tool['sha256'] == expected_sha,
             'reviewed actual SDK executor input differs: ' + name)
    caller = parsed(evidence['caller_manifest']); supplement = parsed(evidence['token_supplement'])
    need(evidence['caller_manifest']['sha256'] == CALLER_MANIFEST_SHA and
         evidence['token_supplement']['sha256'] == TOKEN_MANIFEST_SHA,
         'reviewed Number caller and Token377 manifest pins required')
    sdk = evidence['sdk']
    need(type(sdk) is dict and set(sdk) == set(SDK_SHAS), 'complete actual SDK declaration set required')
    for name, expected_sha in SDK_SHAS.items():
        need(sdk[name]['sha256'] == expected_sha, 'reviewed SDK105 input differs: ' + name)
        source(sdk[name])
    meta = parsed(sdk['metadata'])
    need((meta['apiVersion'], meta['version'], meta['platformVersion'], meta['releaseType']) ==
         ('26', '26.0.0.105', '26.0.0', 'Release'), 'actual SDK105 metadata required')
    ets = admission['metadata']['ets']
    need(ets['requested'] == sdk['metadata']['path'] and
         ets['sha256'] == sdk['metadata']['sha256'] and ets['value'] == meta,
         'SDK admission metadata differs from compile source manifest')
    access = admission['declarations']['@ohos.abilityAccessCtrl.d.ts']
    need(access['sha256'] == ACCESS_CTRL_SHA and access['requested'] ==
         str(Path(sdk['metadata']['path']).parent / 'api/@ohos.abilityAccessCtrl.d.ts'),
         'actual Token377 AccessToken declaration differs')
    source(dict(path=access['requested'], sha256=access['sha256'], bytes=access['bytes']))
    def frozen(manifest, descriptor, relative):
        files = manifest['files']
        if type(files) is list:
            rows = [row for row in files if row['path'] == relative]
            need(len(rows) == 1, 'unique frozen caller source required')
            row = rows[0]
        else:
            need(type(files) is dict and relative in files, 'frozen Token377 source required')
            row = files[relative]
        path = str(Path(descriptor['path']).parent / relative)
        return source(dict(path=path, sha256=row['sha256'], bytes=row['bytes'])).read_bytes()
    napi = parsed(evidence['napi_supplement'])
    need(evidence['napi_supplement']['sha256'] == NAPI_MANIFEST_SHA and
         napi['schema'] == 'number411-fixed-source-extension/v1', 'exact reviewed NAPI source extension required')
    napi_sources = {name: frozen(napi, evidence['napi_supplement'], 'caller/' + name) for name in
        ('EntryAbility.ets','LegacyNapiNumberProbe.js','LegacyNapiNumberProbe.d.ts','NapiProbe411.ets','NapiToken411.ets')}
    frozen(napi, evidence['napi_supplement'], 'project411.py')
    probe = frozen(caller, evidence['caller_manifest'], 'caller/NumberLocalProbe.ets')
    token_sources = {name: frozen(supplement, evidence['token_supplement'],
        'candidate/caller/entry/src/main/ets/entryability/' + name)
        for name in ('EntryAbility.ets', 'TokenObservation.ets')}
    rows = evidence['roles']
    need(type(rows) is list and len(rows) == 3 and
         [row.get('role') for row in rows] == list(ROLES), 'exact three Number SDK roles required')
    roots = {}; selected_role = None
    for row in rows:
        need(set(row) == {'role', 'bundle', 'exit_code', 'source_manifest', 'unsigned_hap', 'permissions'},
             'actual Number SDK role record shape required')
        name = row['role']; bundle, system, get, set_ = ROLES[name]
        permissions = [p for p, value in [(GET, get), (SET, set_)] if value == 0]
        need(type(row['exit_code']) is int and row['exit_code'] == 0 and
             row['bundle'] == bundle and row['permissions'] == permissions,
             'compiled Number SDK role/bundle/permission differs')
        root = Path(row['source_manifest']['path']).parent; roots[name] = root
        manifest = parsed(row['source_manifest'])
        need(manifest['source_commit'] == commit and manifest['role'] == name and
             manifest['caller_manifest'] == evidence['caller_manifest'] and
             manifest['token_supplement'] == evidence['token_supplement'] and manifest['napi_supplement'] == evidence['napi_supplement'] and manifest['sdk'] == sdk and
             manifest['schema']=='number-local580-source/v1' and
             manifest['source_materials']==expected_materials and manifest['run']==evidence['run'] and
             manifest['archive_binding']==evidence['archive_binding'] and manifest['target']==evidence['target'] and
             manifest['selected_device_profile']==evidence['selected_device_profile'] and
             type(manifest['files_sha256']) is dict and set(manifest['files_sha256']) == PROJECT_FILES,
             'actual Number project/source/SDK lineage differs')
        project = {}
        for relative, expected_sha in manifest['files_sha256'].items():
            need(str(PurePosixPath(relative)) == relative and not relative.startswith('/') and
                 '..' not in PurePosixPath(relative).parts, 'canonical SDK project source required')
            project[relative] = source(dict(path=str(root / relative), sha256=expected_sha)).read_bytes()
        token_sources['EntryAbility.ets'] = napi_sources['EntryAbility.ets']
        full_original=dict(token_sources, **{'NumberLocalProbe.ets': probe}, **napi_sources)
        need({name:digest(raw) for name,raw in full_original.items()}==ORIGINAL, 'complete original411 seven-source identity')
        expected_overlay=augment({PREFIX+name:raw.decode() for name,raw in full_original.items()})
        for filename, expected in {name:expected_overlay[PREFIX+name].encode() for name in (*ORIGINAL,*ADDED)}.items():
            need(project['entry/src/main/ets/entryability/' + filename] == expected,
                 'actual compiled caller/Token377 source differs')
        original_module = decode(frozen(caller, evidence['caller_manifest'], 'caller/' + name + '.module.json5'))
        original_module['module']['deviceTypes'] = ['default']
        original_module['module']['abilities'][0].update(label='$string:app_name', icon='$media:app_icon',
            startWindowIcon='$media:app_icon', startWindowBackground='$color:background')
        need(decode(project['entry/src/main/module.json5']) == original_module and
             decode(project['AppScope/app.json5'])['app']['bundleName'] == bundle,
             'compiled source bundle/module/permissions differs from reviewed caller')
        hap = source(row['unsigned_hap'])
        with zipfile.ZipFile(hap) as archive:
            members = archive.infolist(); names = [m.filename for m in members]
            need(len(names) == len(set(names)) and all(not n.startswith('/') and
                 '..' not in PurePosixPath(n).parts and str(PurePosixPath(n)) == n for n in names) and
                 all(stat.S_IFMT(m.external_attr >> 16) != stat.S_IFLNK for m in members),
                 'safe unique actual unsigned HAP members required')
            need('module.json' in names and 'ets/modules.abc' in names and
                 0 < archive.getinfo('module.json').file_size < 1024 * 1024 and
                 archive.getinfo('ets/modules.abc').file_size > 0, 'actual compiled HAP/ABC required')
            module = decode(archive.read('module.json'))
        app, entry = module['app'], module['module']
        need(app['bundleName'] == bundle and app['debug'] is False and
             (app['compileSdkVersion'], app['minAPIVersion'], app['targetAPIVersion']) ==
             ('26.0.0.105', 26, 26) and entry['name'] == 'entry' and entry['type'] == 'entry' and
             entry['deviceTypes'] == ['default'] and entry['mainElement'] == 'EntryAbility' and
             entry.get('extensionAbilities', []) == [] and
             entry.get('requestPermissions', []) == [{'name': p} for p in permissions] and
             len(entry['abilities']) == 1 and entry['abilities'][0]['name'] == 'EntryAbility' and
             entry['abilities'][0]['exported'] is True and
             entry['abilities'][0]['srcEntry'] == './ets/entryability/EntryAbility.ets',
             'actual compiled HAP role/API/entry/permission contract differs')
        if name == role:
            need(all(row['unsigned_hap'][k] == item['unsigned_hap'][k] for k in ('path', 'sha256')),
                 'selected unsigned HAP is not this actual SDK role output')
            selected_role = row
    sdk_root = Path(item['sdk_evidence']['path']).parent
    need(all(roots[name] == sdk_root / name for name in ROLES), 'SDK output/source roots differ')
    cpu = sdk_root / 'cpu-cap.cjs'; source(dict(path=str(cpu), sha256=CPU_CAP_SHA))
    commands = evidence['commands']; labels = [(name, phase) for name in ROLES
                                              for phase in ('dependencies', 'compile')]
    need(type(commands) is list and len(commands) == 6, 'six actual serial SDK commands required')
    previous_end = None
    for command, (name, phase) in zip(commands, labels):
        tail = ([CLI + '/ohpm/bin/pm-cli.js', 'install', '--all', '--registry',
                 'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0']
                if phase == 'dependencies' else [CLI + '/6.x/hvigor/bin/hvigorw.js', 'assembleHap',
                '--mode', 'module', '-p', 'product=default', '-p', 'module=entry', '-p',
                'debuggable=false', '-p', 'hvigor-obfuscation=false', '--no-daemon', '--no-parallel',
                '--no-incremental', '--max-old-space-size', '2048'])
        need(command['argv'] == [NODE, '--max-old-space-size=2048', '--require', str(cpu), *tail] and
             command['label'] == name + '-' + phase and command['project'] == name and
             command['cwd'] == str(roots[name]) and type(command['exit_code']) is int and
             command['exit_code'] == 0 and command['timed_out'] is False and
             command['owned_outer_leader_reaped'] is True and
             all(type(command[k]) is int and command[k] > 0 for k in ('owned_pid', 'owned_initial_pgid')),
             'actual fixed serial SDK argv/exit/owned completion differs')
        start, seconds = command['started_monotonic'], command['seconds']
        need(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (start, seconds)) and
             (previous_end is None or start >= previous_end), 'actual SDK command ordering differs')
        previous_end = start + seconds
        need(command['log'] == str(sdk_root / (name + '-' + phase + '.log')), 'actual SDK command log path differs')
        log = source(dict(path=command['log'], sha256=command['sha256'])).read_bytes()
        if phase == 'compile':
            need(b'BUILD SUCCESSFUL' in log and b'BUILD FAILED' not in log, 'actual Hvigor success log required')
    need(selected_role is not None, 'selected actual SDK role missing')
    return dict(scope='actual_SDK_source_chain_ONLY_NOT_signature_install_or_runtime', source_commit=commit,
                role=role, unsigned_hap=selected_role['unsigned_hap'],
                source_manifest=selected_role['source_manifest'], sdk_evidence=item['sdk_evidence'],
                materials=list(materials.values()), guest_executed=False,
                first_artifact_behavior_gate_passed=False)



def account_sdk_artifacts(controller,commit,*,number_sdk,original_collector):
    """Pure proof of normally compiled account-only four-source projection."""
    c=original_collector;materials={}
    def source(row):
        path=c.checked(row);materials[str(path)]=c.record(path);return path
    def parsed(row):return c.decode(source(row).read_bytes())
    top=parsed(number_sdk);expected=top['account_controller'];receipt=parsed(controller['sdk_evidence'])
    need(receipt['schema']=='number-local580-account-SDK/v1' and receipt['source_commit']==commit and
         receipt['exit_code']==0 and receipt['failures']==[] and receipt['signed'] is False and
         receipt['guest_executed'] is False and receipt['first_artifact_behavior_gate_passed'] is False and
         expected['sdk_evidence']==controller['sdk_evidence'] and expected['unsigned_hap']==controller['unsigned_hap'] and
         receipt['driver']==top['driver'] and receipt['run']==controller['run']==top['run'] and
         receipt['archive_binding']==top['archive_binding'] and receipt['target']==top['target'],
         'actual separately compiled account role, same normally admitted source/nonce/archive')
    row=receipt['role'];name='org.ohos.qemu.networkwhole579.account'
    permissions=['ohos.permission.MANAGE_LOCAL_ACCOUNTS','ohos.permission.GET_LOCAL_ACCOUNTS',
                 'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']
    need(set(row)=={'role','bundle','exit_code','source_manifest','unsigned_hap','permissions'} and row['role']=='account' and
         row['bundle']==name and row['exit_code']==0 and row['permissions']==permissions,'exact original account role contract')
    manifest=parsed(row['source_manifest']);root=Path(row['source_manifest']['path']).parent
    need(manifest['schema']=='number-local580-source/v1' and manifest['source_commit']==commit and manifest['run']==receipt['run'] and
         manifest['target']==top['target'] and manifest['archive_binding']==top['archive_binding'] and manifest['sdk']==top['sdk'] and
         manifest['source_materials']==top['source_materials'] and manifest['source_references']==receipt['source_references'],
         'actual account source manifest/SDK lineage')
    refs=receipt['source_references'];normal=parsed(top['archive_binding']['normal_source']);snapshot=parsed(normal['canonical_snapshot'])
    need(set(refs)=={'project','Journal.ets','AccountDriver.ets','EntryAbility.ets','Index.ets'},'complete original canonical account-source references')
    canonical_root=Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
    for key,ref in refs.items():
        path=source(ref);relative=path.relative_to(canonical_root).as_posix()
        matches=[v for v in snapshot['files'] if v['path']==relative]
        need(len(matches)==1 and matches[0]['sha256']==ref['sha256'] and matches[0]['bytes']==ref['bytes'],
             'account source must be in the same actual normal canonical snapshot')
    wanted=(c.PROJECT_FILES-frozenset(n for n in c.PROJECT_FILES if n.startswith('entry/src/main/ets/')))|frozenset(
        'entry/src/main/ets/'+n for n in ('common/Journal.ets','common/Driver.ets','entryability/EntryAbility.ets','pages/Index.ets'))
    need(set(manifest['files_sha256'])==wanted,'complete account project files, no unknown/source omission')
    files={}
    for relative,expected_sha in manifest['files_sha256'].items():
        need(str(PurePosixPath(relative))==relative and not relative.startswith('/') and '..' not in PurePosixPath(relative).parts,
             'safe original scaffold source')
        files[relative]=source(dict(path=str(root/relative),sha256=expected_sha)).read_bytes()
    substitutions={'__APPS579_RUN__':receipt['run'],'__APPS579_CASE__':'systemvpn','__APPS579_ROLE__':'account','__APPS579_BUNDLE__':name}
    for before,relative in {'Journal.ets':'common/Journal.ets','AccountDriver.ets':'common/Driver.ets',
                            'EntryAbility.ets':'entryability/EntryAbility.ets','Index.ets':'pages/Index.ets'}.items():
        text=source(refs[before]).read_text()
        for old,new in substitutions.items():text=text.replace(old,new)
        need(files['entry/src/main/ets/'+relative]==text.encode() and not re.search(r'__[A-Z0-9_]+__',text),
             'account-only original four-source substitution exact')
    module=c.decode(files['entry/src/main/module.json5'])['module'];app=c.decode(files['AppScope/app.json5'])['app']
    need(app['bundleName']==name and module['deviceTypes']==['default'] and
         module['requestPermissions']==[dict(name=p) for p in permissions] and module.get('extensionAbilities',[])==[] and
         len(module['abilities'])==1 and module['abilities'][0]['name']=='EntryAbility' and module['abilities'][0]['exported'] is True,
         'actual source account bundle/module/permissions')
    hap=source(row['unsigned_hap'])
    with zipfile.ZipFile(hap) as archive:
        members=archive.infolist();names=[m.filename for m in members]
        need(len(names)==len(set(names)) and 'module.json' in names and 'ets/modules.abc' in names and
             not any(n.startswith('libs/') and n.endswith('.so') for n in names) and
             all(not n.startswith('/') and '..' not in PurePosixPath(n).parts and str(PurePosixPath(n))==n for n in names) and
             all(stat.S_IFMT(m.external_attr>>16)!=stat.S_IFLNK for m in members),'safe compiled ArkTS-only account HAP')
        compiled=c.decode(archive.read('module.json'))
    need(compiled['app']['bundleName']==name and compiled['app']['debug'] is False and compiled['app']['compileSdkVersion']=='26.0.0.105' and
         compiled['module']['requestPermissions']==[dict(name=p) for p in permissions] and compiled['module']['deviceTypes']==['default'],
         'compiled API26 account HAP role/permissions')
    commands=receipt['commands'];need(len(commands)==2,'two actual independent account SDK commands')
    previous=None;cpu=Path(number_sdk['path']).parent/'cpu-cap.cjs'
    for cmd,phase in zip(commands,('dependencies','compile')):
        tail=([c.CLI+'/ohpm/bin/pm-cli.js','install','--all','--registry','http://127.0.0.1:9','--fetch_timeout','10000','--retry_times','0']
          if phase=='dependencies' else [c.CLI+'/6.x/hvigor/bin/hvigorw.js','assembleHap','--mode','module','-p','product=default',
          '-p','module=entry','-p','debuggable=false','-p','hvigor-obfuscation=false','--no-daemon','--no-parallel','--no-incremental','--max-old-space-size','2048'])
        need(cmd['argv']==[c.NODE,'--max-old-space-size=2048','--require',str(cpu),*tail] and cmd['cwd']==str(root) and
             cmd['label']=='account-'+phase and cmd['project']=='account' and cmd['exit_code']==0 and cmd['timed_out'] is False and
             cmd['owned_outer_leader_reaped'] is True and all(type(cmd[k]) is int and cmd[k]>0 for k in ('owned_pid','owned_initial_pgid')),
             'actual original account SDK command/owned group closure')
        need(previous is None or cmd['started_monotonic']>=previous,'account SDK serial ordering')
        previous=cmd['started_monotonic']+cmd['seconds'];log=source(dict(path=cmd['log'],sha256=cmd['sha256'])).read_bytes()
        if phase=='compile':need(b'BUILD SUCCESSFUL' in log and b'BUILD FAILED' not in log,'actual account compile log')
    return dict(schema='number580-account-SDK-source-replay/v1',role='account',run=receipt['run'],
        sdk_evidence=controller['sdk_evidence'],source_manifest=row['source_manifest'],unsigned_hap=row['unsigned_hap'],materials=list(materials.values()))
