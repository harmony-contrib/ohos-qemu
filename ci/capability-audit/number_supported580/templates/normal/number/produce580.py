"""Normal serial unsigned Number580 callers; no signer, guest or new Owner.

Runs only under the original SDK batch's fixed command/lease protocol. The
three Number permission roles and the independent account controller never
share permission declarations. Actual image/archive and SDK inputs are data.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import tarfile

HERE = Path(__file__).resolve().parent
SDK_DIRECTORY = HERE.parent / 'sdk'
_common = sys.modules.get('sdk26_common')
if _common is not None and Path(_common.__file__).resolve() != SDK_DIRECTORY / 'sdk26_common.py':
    raise ValueError('foreign cached original normal SDK source')
sys.path.insert(0, str(SDK_DIRECTORY))
import sdk26_common as C
if Path(C.__file__).resolve() != SDK_DIRECTORY / 'sdk26_common.py':
    raise ValueError('foreign original normal SDK source origin')

ORIGINAL = C.PRIVATE / 'root-number494-source/kit411'
CALLERS = C.PRIVATE / 'root-number-local375-review02'
TOKEN = C.PRIVATE / 'root-number-runtime377'
PROJECT411_SHA = '4406009e147d8df6b02f6e339acaefcca01b0897a1d62fbe84204c6c7fc8da8b'
ORIGINAL_DRIVER_SHA = '041cdf3ad97a16336cab858a3e515ac0e808cf817631355164708719ad488d69'
CALLER_MANIFEST_SHA = '26c1ad1612ba3b1919242dce976215d55f176fe05832b8beaaffa5ea9b62987e'
TOKEN_MANIFEST_SHA = '1c4c3f02b9310bd218f40fd62da88ccda009001532897b3908fd11d3fcca8ee6'
NAPI_MANIFEST_SHA = '942d4cfd8dc6777f36e5462ae16739366691e6efbd4dc3a87285a0198ffc2fa1'
NUMBER_SOURCE_NAMES = {'produce580.py', 'project580.py', 'caller/LegacyNumberCorpus580.js',
                       'caller/LegacyNumberCorpus580.d.ts', 'caller/NumberCorpus580.ets'}
ROLES = ('system-granted', 'system-readonly', 'ordinary')
PERMISSIONS = {'system-granted': ['ohos.permission.GET_TELEPHONY_STATE', 'ohos.permission.SET_TELEPHONY_STATE'],
               'system-readonly': ['ohos.permission.GET_TELEPHONY_STATE'], 'ordinary': []}
ACCOUNT_PERMISSIONS = ['ohos.permission.MANAGE_LOCAL_ACCOUNTS', 'ohos.permission.GET_LOCAL_ACCOUNTS',
                       'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']


def record3(path):
    path = Path(path)
    C.require(path.is_absolute() and path.resolve() == path and
              not any(p.is_symlink() for p in (path, *path.parents)), 'unaliased actual source/artifact')
    s = path.lstat()
    C.require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'regular one-link source/artifact')
    value = dict(path=str(path), sha256=C.sha(path), bytes=s.st_size)
    after = path.lstat()
    C.require((after.st_dev, after.st_ino, after.st_mode, after.st_uid, after.st_gid,
               after.st_nlink, after.st_size, after.st_mtime_ns, after.st_ctime_ns) ==
              (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
               s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns), 'actual source/artifact changed')
    return value


def exact(descriptor):
    C.require(type(descriptor) is dict and set(descriptor) == {'path', 'sha256', 'bytes'} and
              type(descriptor['path']) is str and type(descriptor['bytes']) is int and descriptor['bytes'] >= 0 and
              type(descriptor['sha256']) is str and re.fullmatch('[a-f0-9]{64}', descriptor['sha256']), 'exact actual Ref3')
    C.require(record3(descriptor['path']) == descriptor, 'actual input changed')
    return Path(descriptor['path'])


def fixed_module(path, name, digest):
    path = Path(path)
    C.require(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest) and
              record3(path)['sha256'] == digest, 'fixed source identity must be bound before import')
    old = sys.modules.get(name)
    C.require(old is None or Path(old.__file__).resolve() == path, 'foreign cached normal source')
    if old is None:
        spec = importlib.util.spec_from_file_location(name, path)
        C.require(spec is not None and spec.loader is not None, 'fixed ordinary source loader')
        old = importlib.util.module_from_spec(spec)
        sys.modules[name] = old
        spec.loader.exec_module(old)
    C.require(Path(old.__file__).resolve() == path and record3(path)['sha256'] == digest,
              'fixed module origin/source changed')
    return old


def canonical_module(name):
    """Only a fixed actual canonical module, after the original clean-HEAD pin."""
    C.require(name in {'production579_target', 'batch_system_build_runtime_helpers',
        'network_whole579_project', 'batch_apps_select375_project',
        'batch_apps_select375_project_build', 'batch_apps_contact_picker_coordinator'},
        'fixed canonical source role')
    path = C.REPO / 'ci/capability-audit' / (name + '.py')
    before = record3(path)
    sys.path.insert(0, str(path.parent))
    module = fixed_module(path, name, before['sha256'])
    C.require(record3(path) == before, 'canonical source changed while loading')
    return module


def frozen_materials(number_sources):
    manifest = CALLERS / 'MANIFEST.json'
    C.require(record3(manifest)['sha256'] == CALLER_MANIFEST_SHA, 'original caller manifest')
    for row in C.load(manifest)['files']:
        path = CALLERS / row['path']
        C.require(path.resolve().is_relative_to(CALLERS) and record3(path)['sha256'] == row['sha256'] and
                  path.stat().st_size == row['bytes'], 'fixed caller bytes')
    supplement = TOKEN / 'MANIFEST.json'
    C.require(record3(supplement)['sha256'] == TOKEN_MANIFEST_SHA, 'original token manifest')
    for name, row in C.load(supplement)['files'].items():
        path = TOKEN / name
        C.require(path.resolve().is_relative_to(TOKEN) and record3(path)['sha256'] == row['sha256'] and
                  path.stat().st_size == row['bytes'], 'fixed token source')
    driver = record3(ORIGINAL / 'run_number_SDK411.py')
    C.require(driver['sha256'] == ORIGINAL_DRIVER_SHA, 'original SDK algorithm provenance')
    project = fixed_module(ORIGINAL / 'project411.py', '_number580_original_project411', PROJECT411_SHA)
    napi = project.validate_sources(NAPI_MANIFEST_SHA)
    overlay = fixed_module(HERE / 'project580.py', '_number580_fixed_project', number_sources['project580.py']['sha256'])
    return project, overlay, dict(caller_manifest=record3(manifest), token_supplement=record3(supplement),
        napi_supplement=record3(napi['path']), original_driver=driver,
        source_materials=overlay.source_materials())


def inputs(args, output):
    C.require(args.inputs is not None and args.inputs_sha256 is not None, 'actual Number SDK data input required')
    p = Path(args.inputs)
    C.require(record3(p)['sha256'] == args.inputs_sha256, 'actual Number SDK data SHA')
    value = C.load(p)
    C.require(type(value) is dict and set(value) == {'schema', 'source_commit', 'archive', 'image', 'profile',
              'normal_source', 'sdk_declaration'} and value['schema'] == 'numberlocal580-normal-sdk-inputs/v1' and
              value['source_commit'] == args.commit, 'fixed data-only Number SDK input')
    for name in ('archive', 'image', 'profile', 'normal_source', 'sdk_declaration'):
        exact(value[name])
    # Check both cache origins before either fixed module can execute a body.
    for name in ('production579_target', 'batch_system_build_runtime_helpers'):
        cached = sys.modules.get(name)
        C.require(cached is None or Path(cached.__file__).resolve() ==
                  C.REPO / 'ci/capability-audit' / (name + '.py'), 'foreign cached archive/profile reader')
    helpers = canonical_module('batch_system_build_runtime_helpers')
    target = canonical_module('production579_target')
    manifest = target.archive_manifest(value['archive']['path'])
    selected = manifest['context']
    C.require((selected['product'], selected['device']) == (args.product, args.device), 'actual archive target')
    profile = C.load(value['profile']['path'])
    helpers.validate_installed_profile(profile, archive_sha256=value['archive']['sha256'],
                                      system_image_sha256=value['image']['sha256'])
    C.require((profile['product'], profile['device'], profile['arch']) ==
              (args.product, args.device, selected['arch']) and
              profile['archive']['path'] == value['archive']['path'] and
              profile['system_image']['path'] == value['image']['path'], 'same actual image/archive full profile')
    member = selected['package_root'] + '/build-inputs.json'
    with tarfile.open(value['archive']['path'], 'r:gz') as tree:
        matches = [x for x in tree if x.name == member]
        C.require(len(matches) == 1 and matches[0].isfile() and 0 < matches[0].size <= 16 * 1024 * 1024,
                  'one bounded complete actual package source-input member')
        stream = tree.extractfile(matches[0])
        C.require(stream is not None, 'actual build-input member')
        with stream:
            raw = stream.read()
    (output / 'archive-build-inputs.json').write_bytes(raw)
    build_inputs = C.load(output / 'archive-build-inputs.json')
    C.require(build_inputs['source_git_revision'] == args.commit, 'actual package canonical source revision')
    source = C.load(value['normal_source']['path'])
    C.require(source['schema'] == 'postpackage-source579-output/v1' and source['source_commit'] == args.commit,
              'actual normally produced source context')
    number_sources = source['number_local']['sources']
    C.require(type(number_sources) is dict and set(number_sources) == NUMBER_SOURCE_NAMES,
              'fixed five Number SDK source nodes')
    sdk_sources = C.load(SDK_DIRECTORY / 'source-manifest.json')
    C.require(sdk_sources['schema'] == 'F-SDK-batch29-source-draft/v1', 'original fixed SDK source manifest')
    C.require(source['sdk_source_manifest'] == record3(SDK_DIRECTORY / 'source-manifest.json') and
              source['sdk_entry'] == record3(SDK_DIRECTORY / 'run_sdk_batch26.py'),
              'normal SOURCE must bind this exact original SDK manifest and dispatcher successor')
    observed = {p.relative_to(SDK_DIRECTORY).as_posix() for p in SDK_DIRECTORY.rglob('*') if p.is_file()}
    C.require(observed == set(sdk_sources['files']) | {'source-manifest.json'}, 'complete fixed normal SDK source set')
    for name, descriptor in sdk_sources['files'].items():
        path = SDK_DIRECTORY / name
        C.require(path.is_relative_to(SDK_DIRECTORY) and C.record(path) == descriptor,
                  'fixed normal SDK source changed')
    for descriptor in sdk_sources['external_inputs'].values():
        C.require(C.record(descriptor['path']) == descriptor, 'original complete SDK external-input source changed')
    for name, descriptor in number_sources.items():
        path = exact(descriptor)
        C.require(path == HERE / name, 'Number source path is fixed by source, not JSON')
        admitted = [row for row in sdk_sources['external_inputs'].values() if row['path'] == str(path)]
        C.require(len(admitted) == 1 and admitted[0] == C.record(path),
                  'Number source must also belong to the original sealed SDK external-input vector')
    C.require(args.sdk_declaration_receipt is not None and args.sdk_declaration_receipt_sha256 is not None and
              record3(Path(args.sdk_declaration_receipt)) == value['sdk_declaration'] and
              value['sdk_declaration']['sha256'] == args.sdk_declaration_receipt_sha256,
              'same normal SDK declaration receipt as original batch')
    declaration = C.load(value['sdk_declaration']['path'])
    C.require(declaration['source_commit'] == args.commit and declaration['exit_code'] == 0 and
              declaration['cleanup_verified'] is True and declaration['owned_container_absent'] is True and
              declaration['final_sdk_api']['path'] == str(C.SDK / 'ets/api/application/ServiceExtensionContext.d.ts') and
              declaration['final_sdk_api']['sha256'] == C.sha(declaration['final_sdk_api']['path']),
              'actual selected normal SDK declaration and closure')
    (output / 'archive-manifest.json').write_bytes(manifest['raw'])
    result = dict(inputs=record3(p), **{k:value[k] for k in ('archive', 'image', 'profile', 'normal_source', 'sdk_declaration')},
        manifest=record3(output / 'archive-manifest.json'), build_inputs=record3(output / 'archive-build-inputs.json'))
    return result, number_sources


def source_project(scaffold, project411, project580, run, role):
    files = scaffold.expected_sources({'run_id': run}, 'caller', C.SDK)
    files = {n:v for n,v in files.items() if not n.startswith('entry/src/main/ets/')}
    app = json.loads(files['AppScope/app.json5'])
    app['app']['bundleName'] = 'org.harmonycontrib.numberlocal376.' + role.replace('-', '')
    files['AppScope/app.json5'] = json.dumps(app, indent=2) + '\n'
    module = C.load(CALLERS / 'caller' / (role + '.module.json5'))
    C.require([p['name'] for p in module['module']['requestPermissions']] == PERMISSIONS[role],
              'three original disjoint permission roles')
    module['module']['deviceTypes'] = ['default']
    module['module']['abilities'][0].update(label='$string:app_name', icon='$media:app_icon',
        startWindowIcon='$media:app_icon', startWindowBackground='$color:background')
    files['entry/src/main/module.json5'] = json.dumps(module, indent=2) + '\n'
    for name in ('EntryAbility.ets', 'NumberLocalProbe.ets'):
        files['entry/src/main/ets/entryability/' + name] = (CALLERS / 'caller' / name).read_bytes().decode()
    for name in ('EntryAbility.ets', 'TokenObservation.ets'):
        relative = 'entry/src/main/ets/entryability/' + name
        files[relative] = (TOKEN / 'candidate/caller' / relative).read_bytes().decode()
    return project580.augment(project411.augment(files)), app['app']['bundleName'], PERMISSIONS[role]


def account_project(scaffold, run):
    # Account-only projection of fixed original sources; no fake TLS profile.
    project = canonical_module('network_whole579_project')
    bundle = project.bundle('systemvpn', 'account')
    permissions = project.permissions('account')
    C.require(permissions == ACCOUNT_PERMISSIONS, 'original account controller permission role')
    files = scaffold.expected_sources({'run_id': run}, 'caller', C.SDK)
    files = {n:v for n,v in files.items() if not n.startswith('entry/src/main/ets/')}
    app = json.loads(files['AppScope/app.json5']); app['app']['bundleName'] = bundle
    files['AppScope/app.json5'] = json.dumps(app, indent=2) + '\n'
    module = json.loads(files['entry/src/main/module.json5'])
    module['module'].update(project.module_fields('systemvpn', 'account', {'profile':'phone'}))
    module['module']['abilities'][0].update(label='$string:app_name', icon='$media:app_icon',
        startWindowIcon='$media:app_icon', startWindowBackground='$color:background')
    files['entry/src/main/module.json5'] = json.dumps(module, indent=2) + '\n'
    substitutions = {'__APPS579_RUN__':run, '__APPS579_CASE__':'systemvpn',
                     '__APPS579_ROLE__':'account', '__APPS579_BUNDLE__':bundle}
    sources = {}
    for original, relative in {'Journal.ets':'common/Journal.ets', 'AccountDriver.ets':'common/Driver.ets',
                              'EntryAbility.ets':'entryability/EntryAbility.ets', 'Index.ets':'pages/Index.ets'}.items():
        path = project.ROOT / original; sources[original] = record3(path)
        text = path.read_bytes().decode()
        for old,new in substitutions.items():
            text = text.replace(old,new)
        C.require(not re.search(r'__[A-Z0-9_]+__', text), 'only four fixed account source substitutions')
        files['entry/src/main/ets/' + relative] = text
    sources['project'] = record3(Path(project.__file__))
    return files, bundle, permissions, sources


def execute(args):
    C.pin(args.commit)
    target = C.target_context(args.product, args.device)
    out = C.fresh_output(args.output); receipt = out / 'evidence.json'
    report = dict(schema='number-local580-actual-SDK/v1', scope='four_unsigned_callers_ONLY_NOT_signing_guest_or_native_build',
        source_commit=args.commit, target=target, driver=record3(__file__), commands=[], failures=[], roles=[],
        account_controller=None, signed=False, guest_executed=False, runtime_pass=False,
        first_artifact_behavior_gate_passed=False, exit_code=1, started_utc=C.utc())
    C.save(receipt, report)
    if args.device == '2in1':
        report.update(status='not_applicable', applicability='phone_only_NO_phone_pass', exit_code=0,
            sdk_started=False, declared_inner_commands_completed_without_timeout=True, finished_utc=C.utc())
        C.save(receipt, report); return 0
    try:
        archive_binding, number_sources = inputs(args, out); report['archive_binding'] = archive_binding
        admission = C.input_admission(out, args.commit)
        if admission['exit_code'] != 0:
            C.input_rejected(out, report, receipt, admission); return 1
        report['input_admission'] = record3(out / 'input-admission.json')
        project411, project580, materials = frozen_materials(number_sources); report.update(materials)
        for name in ('batch_apps_select375_project', 'batch_apps_select375_project_build',
                     'batch_apps_contact_picker_coordinator'):
            cached = sys.modules.get(name)
            C.require(cached is None or Path(cached.__file__).resolve() ==
                      C.REPO / 'ci/capability-audit' / (name + '.py'), 'foreign cached SDK project/build/receipt reader')
        scaffold = canonical_module('batch_apps_select375_project')
        sdk_commands = canonical_module('batch_apps_select375_project_build').sdk_commands
        hap_reader = canonical_module('batch_apps_contact_picker_coordinator')
        ordinary_hap, hap_contents = hap_reader.ordinary_hap, hap_reader.hap_contents
        sdk = scaffold.sdk_contract(C.SDK); report['sdk'] = sdk
        selected = C.selected_device_profile(target); report['selected_device_profile'] = dict(selected, bytes=Path(selected['path']).stat().st_size)
        home = out / 'hvigor-home'; shutil.copytree(C.CACHE / 'wrapper', home / 'wrapper', symlinks=True)
        cpu = out / 'cpu-cap.cjs'; shutil.copyfile(scaffold.FIX / 'cpu-cap.cjs', cpu)
        tool_paths = {'node':C.NODE, 'ohpm':C.CLI / 'ohpm/bin/pm-cli.js', 'hvigor':C.CLI / '6.x/hvigor/bin/hvigorw.js', 'cpu_cap':cpu}
        tools = {name:C.record(path) for name,path in tool_paths.items()}
        report['tools'] = {name:record3(path) for name,path in tool_paths.items()}
        env = dict(os.environ, JAVA_HOME=str(C.JAVA), LC_ALL='C', LC_CTYPE='C', LANG='C',
            NODE_HOME=str(C.NODE.parent.parent), DEVECO_SDK_HOME=str(C.SDK.parent),
            HVIGOR_USER_HOME=str(home), OHPM_HOME=str(out / 'ohpm-home'))
        env.pop('NODE_OPTIONS', None)
        env['PATH'] = str(C.JAVA / 'bin') + os.pathsep + str(C.NODE.parent) + os.pathsep + env.get('PATH','')
        run = secrets.token_hex(16); report['run'] = run
        report['abi_binding'] = dict(archive_arch=target['arch'],
            abi={'arm64':'arm64-v8a','armv7a':'armeabi-v7a','x86_64':'x86_64'}[target['arch']],
            caller_kind='ArkTS_ABC_no_embedded_native_DSO', native_observer_built=False)
        def build(role, files, bundle, permissions, evidence, evidence_path, *, account_sources=None):
            directory = out / role; directory.mkdir()
            for name,value in files.items():
                p = directory / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(value.encode())
            source = {name:C.sha(directory / name) for name in files}
            manifest = dict(schema='number-local580-source/v1', files_sha256=source, role=role,
                source_commit=args.commit, run=run, target=target, archive_binding=archive_binding,
                sdk=sdk, selected_device_profile=report['selected_device_profile'], **materials)
            if account_sources is not None:
                manifest['source_references'] = account_sources
            C.save(directory / 'root-source-manifest.json', manifest)
            row = dict(role=role,bundle=bundle,exit_code=1,source_manifest=record3(directory / 'root-source-manifest.json'))
            for phase,argv in sdk_commands(tools):
                actual = C.command(argv, label=role+'-'+phase, cwd=directory, output=out,
                    report=evidence, receipt=evidence_path, commit=args.commit,
                    timeout=120 if phase=='dependencies' else 1800, env=env, project=role)
                if actual['exit_code'] != 0:
                    evidence['failures'].append(role+'/'+phase+': actual exit '+str(actual['exit_code'])); break
            else:
                hap = directory / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
                contents = ordinary_hap(hap, bundle, permissions)
                compiled, _ = hap_contents(hap)
                C.require(compiled['module']['deviceTypes'] == ['default'], 'compiled phone SDK profile')
                C.require(not any(n.startswith('libs/') and n.endswith('.so') for n in contents),
                          'Number/account ArkTS callers must not embed a foreign native ELF')
                row.update(exit_code=0,unsigned_hap=record3(hap),permissions=permissions)
            C.source_recheck(directory, source)
            return row
        for role in ROLES:
            files,bundle,permissions = source_project(scaffold,project411,project580,run,role)
            report['roles'].append(build(role,files,bundle,permissions,report,receipt));C.save(receipt,report)
        account_receipt = out / 'account-sdk-evidence.json'
        account = dict(schema='number-local580-account-SDK/v1',source_commit=args.commit,run=run,target=target,
            archive_binding=archive_binding,driver=report['driver'],commands=[],failures=[],signed=False,
            guest_executed=False,exit_code=1,first_artifact_behavior_gate_passed=False)
        files,bundle,permissions,account_sources = account_project(scaffold,run)
        report['source_references'] = dict(account=account_sources)
        C.save(account_receipt, account)
        account_row = build('account',files,bundle,permissions,account,account_receipt,account_sources=account_sources)
        account.update(role=account_row,source_references=account_sources,exit_code=account_row['exit_code'],finished_utc=C.utc())
        C.save(account_receipt,account)
        report['account_controller'] = dict(account_row,sdk_evidence=record3(account_receipt))
        if account['failures']:report['failures'].extend(account['failures'])
        C.assert_inner_commands_complete(receipt)
        C.assert_inner_commands_complete(account_receipt)
        C.require(frozen_materials(number_sources)[2] == materials and scaffold.sdk_contract(C.SDK) == sdk,
                  'normal SDK/helper/source inputs changed')
        for value in archive_binding.values(): exact(value)
        C.pin(args.commit)
        report['declared_inner_commands_completed_without_timeout'] = True
        report['exit_code'] = int(bool(report['failures']) or len(report['roles']) != 3 or
            any(row['exit_code'] != 0 for row in report['roles']) or account_row['exit_code'] != 0)
    except C.UnsafeCleanup as error:
        report.update(must_resolve_owned_SDK_processes_before_next_resource_stage=True,descendants_cleanup_verified=False)
        report['failures'].append(type(error).__name__+': '+str(error))
    except BaseException as error:
        report['failures'].append(type(error).__name__+': '+str(error))
    finally:
        report['finished_utc'] = C.utc();C.save(receipt,report)
    return report['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--commit',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--product',choices=('arm64_virt','armv7a_virt','x86_64_virt'),required=True)
    parser.add_argument('--device',choices=('phone','2in1'),required=True)
    parser.add_argument('--inputs',type=Path);parser.add_argument('--inputs-sha256')
    parser.add_argument('--sdk-declaration-receipt',type=Path);parser.add_argument('--sdk-declaration-receipt-sha256')
    args=parser.parse_args();C.require(args.execute,'normal root SDK execution must be explicit')
    if args.device == '2in1':return execute(args)
    try:
        with C.lease():return execute(args)
    except C.ResourceLeaseBusy:
        print(json.dumps(C.busy_result()));return 75


if __name__ == '__main__':
    raise SystemExit(main())
