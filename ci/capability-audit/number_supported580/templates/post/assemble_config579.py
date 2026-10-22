#!/usr/bin/env python3
"""DATA-only final config projection. Never starts a resource or changes evidence."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = ROOT / '.tmp/parallel-capability-20261016'
B = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')
KIT = None
KIT_SHA = None
COMMIT = None
SCHEMA = 'full-suite-config579-DATA-only/v1'
SDK_BATCH = None
SELECT_ROOT = None
SDK_SHA = None
SELECT_SHA = None
CLOCK_SHA = 'b5dfd380803526d033cf44ace849cfad3fd11b1c2f2c7fe6a5b837c2caf06a9c'
PROBE_SHA = '257875523db7d62e8930ff2fc1e67c6b1c67096baff47a2f7dde93391589493e'
SUFFIX = 'entry/build/default/outputs/default/entry-default-unsigned.hap'
FIELDS = {'schema', 'source_commit', 'package_receipt', 'profile_receipt', 'mic_receipt', 'provider_preparation',
          'sdk_batch_receipt', 'select_root_receipt', 'clock_probe', 'clock_probe_build', 'hdc', 'qemu',
          'sdk', 'environment', 'signer_dist', 'signer_jar', 'share578', 'output',
          'source_kit_manifest', 'canonical_snapshot', 'snapshot_count'}


def need(value, message):
    if not value:
        raise ValueError(message)


def canonical(path, *, directory=False):
    need(type(path) in (str, Path) or isinstance(path, Path), 'literal actual path required')
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
         'canonical non-aliased input required: ' + str(path))
    info = path.stat()
    need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
         'actual directory or regular non-alias input required: ' + str(path))
    return path


def record(path):
    path = canonical(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return dict(path=str(path), sha256=digest.hexdigest(), bytes=path.stat().st_size)


def checked(row):
    need(type(row) is dict and set(row) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}), 'exact descriptor required')
    need(type(row['sha256']) is str and re.fullmatch('[a-f0-9]{64}', row['sha256']) and
         ('bytes' not in row or type(row['bytes']) is int), 'typed actual SHA/bytes required')
    actual = record(row['path'])
    need(all(actual[key] == value for key, value in row.items()), 'input descriptor changed: ' + str(row['path']))
    return actual


def two(row):
    return {key: row[key] for key in ('path', 'sha256')}


def load(row):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(checked(row)['path']).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


def completed(value, *, finish='finished_utc'):
    need(type(value.get('exit_code')) is int and value['exit_code'] == 0 and value.get('source_commit') == COMMIT and
         type(value.get(finish)) is str and bool(value[finish]) and not value.get('failures') and
         not value.get('must_resolve_owned_resources_before_next_stage') and
         not value.get('must_resolve_owned_SDK_processes_before_next_resource_stage'), 'completed current392 input required')


def shape(intent):
    need(type(intent) is dict and set(intent) == FIELDS and intent['schema'] == SCHEMA and intent['source_commit'] == COMMIT,
         'exact current394 intent/commit required')
    missing = [key for key, value in intent.items() if value is None]
    need(not missing, 'actual inputs still pending: ' + ', '.join(sorted(missing)))


def number580_sdk_receipt(batch, batch_path, commit, target, archive):
    """Read the fixed fifth-stage DATA; original SDK production remains authoritative."""
    def exact(row): return checked(row)
    def document(row): return load(row)
    stage = next(r for r in batch['stages'] if r['label'] == 'number-local580')
    expected = dict(product=target['product'], arch=target['arch'], device=target['device'],
        sdk_device='default' if target['device'] == 'phone' else '2in1')
    need(batch.get('target') == expected and stage.get('requested_roles') ==
        (['system-granted','system-readonly','ordinary'] if target['device'] == 'phone' else []),
        'Number stage must follow the actual archive ABI/profile and fixed roles')
    receipt = exact(stage['actual_receipt'])
    need(Path(receipt['path']) == Path(batch_path).parent/'number-local580/evidence.json',
        'fixed fifth normal Number SDK receipt path')
    actual = document(receipt)
    need(actual.get('schema') == 'number-local580-actual-SDK/v1' and
        actual.get('source_commit') == commit and actual.get('target') == expected and
        type(actual.get('exit_code')) is int and actual['exit_code'] == 0 and actual.get('failures') == [] and
        actual.get('signed') is False and actual.get('guest_executed') is False and actual.get('runtime_pass') is False and
        actual.get('first_artifact_behavior_gate_passed') is False and
        actual.get('declared_inner_commands_completed_without_timeout') is True,
        'completed same-target unsigned Number SDK only; never guest/native acceptance')
    if target['device'] == '2in1':
        need(actual.get('status') == 'not_applicable' and actual.get('applicability') == 'phone_only_NO_phone_pass' and
            actual.get('roles') == [] and actual.get('account_controller') is None and actual.get('commands') == [] and
            actual.get('sdk_started') is False and 'archive_binding' not in actual,
            'exact typed 2in1 N/A without phone caller inputs or success relabel')
        return receipt
    need(target['device'] == 'phone', 'Number SDK supports exactly phone or explicit 2in1 N/A')
    binding = actual['archive_binding']
    need(type(binding) is dict and set(binding) == {'inputs','archive','image','profile','normal_source',
        'sdk_declaration','manifest','build_inputs'}, 'complete actual Number normal archive binding')
    for value in binding.values():
        need(type(value) is dict and set(value) == {'path','sha256','bytes'} and
            type(value['bytes']) is int and value['bytes'] >= 0, 'actual typed Number archive Ref3')
        exact(value)
    need(exact(binding['archive']) == exact(archive), 'Number SDK belongs to the same actual package archive')
    roles = actual['roles']
    need(type(roles) is list and [r['role'] for r in roles] == ['system-granted','system-readonly','ordinary'],
        'three fixed independent unsigned Number roles')
    permissions = {'system-granted':['ohos.permission.GET_TELEPHONY_STATE','ohos.permission.SET_TELEPHONY_STATE'],
        'system-readonly':['ohos.permission.GET_TELEPHONY_STATE'], 'ordinary':[]}
    account = actual['account_controller']
    need(type(account) is dict and account.get('role') == 'account' and
        account.get('permissions') == ['ohos.permission.MANAGE_LOCAL_ACCOUNTS','ohos.permission.GET_LOCAL_ACCOUNTS',
            'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION'], 'independent local OS-account permission role')
    for role in roles + [account]:
        need(type(role.get('exit_code')) is int and role['exit_code'] == 0 and
            (role['role'] == 'account' or role.get('permissions') == permissions[role['role']]),
            'each actual unsigned role completed with its exact own permissions')
        for key in ('unsigned_hap','source_manifest'):
            descriptor = role[key]
            need(type(descriptor) is dict and set(descriptor) == {'path','sha256','bytes'} and
                type(descriptor['bytes']) is int and descriptor['bytes'] > 0, 'actual Number/account artifact Ref3')
            exact(descriptor)
    account_ref = exact(account['sdk_evidence'])
    need(Path(account_ref['path']) == Path(receipt['path']).parent/'account-sdk-evidence.json',
        'fixed independent account SDK receipt')
    account_sdk = document(account_ref)
    need(account_sdk.get('schema') == 'number-local580-account-SDK/v1' and
        account_sdk.get('source_commit') == commit and account_sdk.get('target') == expected and
        account_sdk.get('archive_binding') == binding and account_sdk.get('run') == actual['run'] and
        account_sdk.get('driver') == actual['driver'] and account_sdk.get('exit_code') == 0 and
        type(account_sdk.get('exit_code')) is int and account_sdk.get('failures') == [] and
        account_sdk.get('signed') is False and account_sdk.get('guest_executed') is False and
        account_sdk.get('first_artifact_behavior_gate_passed') is False and
        account_sdk.get('role') == {k:v for k,v in account.items() if k != 'sdk_evidence'} and
        account_sdk.get('source_references') == actual['source_references']['account'],
        'independent account role shares the actual source/archive/target/run only, never Number privileges')
    need(len(actual['commands']) == 6 and len(account_sdk['commands']) == 2 and
        [r['label'] for r in account_sdk['commands']] == ['account-dependencies','account-compile'] and
        all(r.get('project') == 'account' and type(r.get('exit_code')) is int and r['exit_code'] == 0 and
            not r.get('timed_out') for r in account_sdk['commands']) and
        all(type(r.get('exit_code')) is int and r['exit_code'] == 0 and not r.get('timed_out') for r in actual['commands']),
        'actual unsigned Number/account command summaries must remain complete; original dispatcher raw/lease guards retained')
    return receipt


def sdk_projection(batch_row, select_row, *, archive, target):
    """Original real392 receipts/HAPs only; no compiler/provenance receipt is manufactured."""
    need(two(checked(batch_row)) == dict(path=str(SDK_BATCH), sha256=SDK_SHA) and
         two(checked(select_row)) == dict(path=str(SELECT_ROOT), sha256=SELECT_SHA), 'sealed actual392 SDK roots required')
    batch, selection = load(batch_row), load(select_row)
    completed(batch); completed(selection)
    need(batch['requested_prepackage_stages_complete'] is True and batch['failures'] == [], 'all original14 SDK roles required')
    stages = {row['label']: row for row in batch['stages']}
    need(len(stages) == len(batch['stages']) == 5 and
         set(stages) == {'apps15','audio-calendar26','knowledge26','live-sdk39-26','number-local580'} and
         all(type(row.get('exit_code')) is int and row['exit_code'] == 0 for row in stages.values()),
         'four original unsigned-caller SDK stages plus exact Number stage; no NativeStrip replay')
    number = number580_sdk_receipt(batch, SDK_BATCH, COMMIT, target, archive)
    roles = []

    def add(role, evidence, project, source, expected_hap=None):
        evidence = checked(evidence); report = load(evidence)
        need(type(report.get('exit_code')) is int and report['exit_code'] == 0 and report.get('source_commit') == COMMIT and
             report.get('failures') == [], 'actual inner392 compiler receipt required: ' + role)
        rows = [row for row in report['haps'] if row.get('project') == project]
        need(len(rows) == 1, 'one actual role/project/HAP required: ' + role)
        hap = checked({key: rows[0][key] for key in ('path', 'sha256', 'bytes')})
        source = canonical(source, directory=True)
        need(Path(hap['path']) == source / SUFFIX and
             (expected_hap is None or checked(expected_hap) == hap), 'actual compiled project/HAP differs: ' + role)
        roles.append(dict(role=role, sdk_project=project, source_project=str(source), sdk_evidence=evidence, unsigned_hap=hap))

    for role in ('contacts-caller', 'contacts-seed', 'wallpaper-seed', 'wallpaper-query'):
        add('apps/' + role, stages['apps15']['actual_receipt'], role, SDK_BATCH.parent / 'apps15' / role)
    dedicated = load(stages['audio-calendar26']['actual_receipt'])
    for role in ('audio/normal', 'audio/denied', 'calendar/producer', 'calendar/observer', 'calendar/denied'):
        spec = dedicated['roles'][role]['spec']
        need(Path(spec['source_project']) == SDK_BATCH.parent / 'audio-calendar26' / role, 'actual dedicated source project differs')
        add(role, spec['sdk_evidence'], spec['sdk_project'], spec['source_project'], spec['unsigned_hap'])
    for role in ('importer', 'denied', 'query', 'curator'):
        add('knowledge/' + role, stages['knowledge26']['actual_receipt'], 'knowledge-' + role,
            SDK_BATCH.parent / 'knowledge26' / ('knowledge-' + role))
    add('live-inputs', stages['live-sdk39-26']['actual_receipt'], 'live-inputs', SDK_BATCH.parent / 'live-sdk39-26/live-inputs')
    build_row = checked(selection['build_receipt']); build = load(build_row)
    need(Path(build_row['path']) == SELECT_ROOT.parent / 'build/evidence.json' and
         two(checked(selection['challenge'])) == two(checked(build['challenge'])), 'actual select inner build/challenge join required')
    for role in ('caller', 'target_a', 'target_b'):
        add('select/' + role, build_row, role, SELECT_ROOT.parent / role)
    need(len(roles) == 17 and len({row['role'] for row in roles}) == 17, 'original14 plus supplemental select3 required')
    select = dict(challenge=checked(build['challenge']), role_inputs={row['sdk_project']: dict(
        source_project=row['source_project'], sdk_evidence=two(row['sdk_evidence']), unsigned_hap=two(row['unsigned_hap']))
        for row in roles if row['role'].startswith('select/')})
    return roles, select, number


def kit_modules():
    need(record(KIT / 'manifest.json')['sha256'] == KIT_SHA, 'adopted private393 kit changed')
    manifest = json.loads((KIT / 'manifest.json').read_text())
    for row in manifest['members']:
        if row['kind'] == 'file' and row['path'].endswith('.py'):
            need(record(KIT / row['path'])['sha256'] == row['sha256'], 'fixed393 executable bytes changed')
            previous = sys.modules.get(Path(row['path']).stem)
            # Root deliberately retains its interpreter startup sitecustomize;
            # only fresh child actors load the kit hook via their PYTHONPATH.
            need(row['path'] == 'sitecustomize.py' or previous is None or Path(previous.__file__) == KIT / row['path'],
                 'foreign private module already loaded: ' + row['path'])
    sys.path.insert(0, str(KIT)); sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
    entry = importlib.import_module('run_full_suite377')
    entry.verify_kit(KIT_SHA)
    return importlib.import_module('run_full_suite_owner376'), importlib.import_module('policy377')


def assemble(intent):
    global KIT, KIT_SHA, COMMIT, SDK_BATCH, SDK_SHA, SELECT_ROOT, SELECT_SHA
    need(type(intent) is dict and set(intent) == FIELDS and intent.get('schema') == SCHEMA and
        re.fullmatch('[a-f0-9]{40}',intent.get('source_commit','')), 'exact explicit current579 assembly data required')
    COMMIT = intent['source_commit']
    from runtimekit579_contract import verify_kit
    KIT, _, _ = verify_kit(intent, COMMIT)
    KIT_SHA = checked(intent['source_kit_manifest'])['sha256']
    actual_sdk, actual_select = checked(intent['sdk_batch_receipt']), checked(intent['select_root_receipt'])
    SDK_BATCH, SDK_SHA = Path(actual_sdk['path']), actual_sdk['sha256']
    SELECT_ROOT, SELECT_SHA = Path(actual_select['path']), actual_select['sha256']
    shape(intent)
    package = load(intent['package_receipt']); completed(package)
    need(package.get('schema') in ('F-representative-source-owner/v18','remaining579-one-target-source-owner/v1') and
         package.get('host_tests_executed') is False and
         package.get('capability_acceptance') == 'newly_packaged_QEMU_runtime_only' and package.get('cleanup_verified') is True and
         package.get('owned_container_absent') is True and package.get('owned_launcher_group_closed') is True and
         package.get('resource_lease_held') is False and package.get('resource_lease_released_after_verified_closure') is True and
         package['adopted_complete_host_environment']['PREPARE_ONLY'] == '0' and
         package['adopted_complete_host_environment']['BUILD_ONLY_LOAD'] == '0', 'actual closed native build, not prepare, required')
    archive = checked(package['package'])
    import sys
    sys.path.insert(0,str(ROOT/'ci/capability-audit'))
    from production579_target import archive_manifest
    target = archive_manifest(Path(archive['path']))['context']
    from production579_receipt import validate as validate_package_receipt
    validate_package_receipt(package,target,COMMIT)
    profile = load(intent['profile_receipt']); completed(profile, finish='observed_utc')
    profile_row = checked(profile['profile'])
    from batch_system_build_runtime_helpers import validate_installed_profile
    profile_doc = load(profile_row); validate_installed_profile(profile_doc, archive_sha256=archive['sha256'])
    need((profile_doc['product'],profile_doc['arch'],profile_doc['device']) ==
        (target['product'],target['arch'],target['device']), 'actual profile/package target differs')
    need(profile.get('status') == 'pass_actual_NEW_archive_image_staged_bytes_ONLY' and checked(profile['package']) == archive and
         profile.get('original_source_package_metadata_unchanged') is True, 'actual completed current installed profile required')
    mic = load(intent['mic_receipt']); completed(mic)
    need(mic.get('cleanup_verified') is True and mic.get('owned_container_absent') is True and
         mic.get('package_commit') == mic.get('native_product_source_commit') == COMMIT and checked(mic['package']) == archive and
         checked(mic['runtime_profile']) == profile_row and checked(mic['profile_preparation_receipt']) == checked(intent['profile_receipt']),
         'actual closed current MIC helper/profile/package join required')
    mic_build = checked(dict(path=mic['build_report'], sha256=mic['build_report_sha256']))
    need(Path(mic_build['path']) == Path(intent['mic_receipt']['path']).parent / 'helpers/build.json', 'actual outer MIC helpers/build.json required')
    prep = load(intent['provider_preparation'])
    need(prep.get('schema') == 'provider-inputs391-data-only/v1' and prep.get('status') == 'assembled_DATA_ONLY' and
         prep.get('source_commit') == COMMIT and checked(prep['archive']) == archive and
         checked(prep['package_receipt']) == checked(intent['package_receipt']) and prep.get('runtime_ready') is False and
         prep.get('production_binding_pending') is True and prep.get('first_artifact_behavior_gate_passed') is False and
         type(prep.get('closure_count')) is int and prep['closure_count'] == 0, 'actual current391 plan preparation required')
    capability = checked(prep['capability_inputs']); roles, selection, number_sdk = sdk_projection(
        intent['sdk_batch_receipt'], intent['select_root_receipt'], archive=archive, target=target)
    core, policy = kit_modules(); core.sources(applied=True)
    from parallel_runtime_suite import load_plan
    import batch_apps_completed_provider_binding as provider
    plan = load_plan(Path(capability['path']), dict(product=target['product'], device_type=target['device'], guest_arch=target['arch']))
    provider_families = {
        'phone': (('contacts-picker', 'inputs'), ('wallpaper', 'artifacts')),
        '2in1': (('wallpaper', 'artifacts'),),
    }
    need(target['device'] in provider_families, 'actual archive phone or 2in1 provider family selection required')
    original_firstphone = (target['product'], target['arch'], target['device']) == ('arm64_virt', 'arm64', 'phone')
    if not original_firstphone:
        import production579_completed_2in1_provider as later_provider
        later_kind = {'phone': later_provider.PHONE_KIND, '2in1': later_provider.KIND}[target['device']]
    for family, key in provider_families[target['device']]:
        spec = json.loads(canonical(plan['families'][family][key]).read_text())['provider']['production_build']
        if original_firstphone:
            need(set(spec) == provider.FIELDS and spec['kind'] == provider.KIND and spec['expected_source_commit'] == COMMIT and
                 spec['qa_root'] == str(ROOT) and checked(spec['archive']) == archive and
                 checked(spec['native_evidence']) == checked(intent['package_receipt']), 'original family is missing its actual current twelve-field provider binding')
        else:
            need(set(spec) == later_provider.FIELDS and spec['kind'] == later_kind and spec['target'] == target and
                 spec['expected_source_commit'] == COMMIT and spec['qa_root'] == str(ROOT) and checked(spec['archive']) == archive and
                 checked(spec['native_evidence']) == checked(intent['package_receipt']),
                 'later family is missing its exact current thirteen-field actual-target provider binding')
    clock, clock_build = checked(intent['clock_probe']), checked(intent['clock_probe_build'])
    if target['product'] == 'arm64_virt' and target['device'] == 'phone':
        need(clock['sha256'] == PROBE_SHA and clock_build['sha256'] == CLOCK_SHA, 'original actual r52 clock epoch required')
    from build_watchdog_clock_probe import verify_build
    verify_build(Path(clock['path']), Path(clock_build['path']), target['arch'])
    if (target['product'],target['device']) != ('arm64_virt','phone'):
        batch = load(intent['sdk_batch_receipt'])
        live_stages = [r for r in batch['stages'] if r['label'] == 'live-sdk39-26']
        need(len(live_stages) == 1, 'one actual selected SDK39 stage required')
        clock_production = load(live_stages[0]['actual_receipt'])['clock_tools']
        need(clock_production['arch'] == target['arch'] and
            two(checked(clock_production['binary'])) == two(clock) and
            two(checked(clock_production['build'])) == two(clock_build),
            'nonrepresentative clock must be the actual same-target normal SDK39 output')

    expected_sdk_target = dict(product=target['product'],arch=target['arch'],device=target['device'],sdk_device='default' if target['device'] == 'phone' else '2in1')
    need(load(intent['sdk_batch_receipt']).get('target') == expected_sdk_target,
        'actual completed SDK batch must match package ABI/profile')
    environment = dict(intent['environment'])
    need(not core.PROFILE_ENVIRONMENT_KEYS.intersection(environment), 'assembler supplies the four verified profile/MIC values; no conflicting overrides')
    expected = dict(QEMU_TEST_HVIGOR_HOME=policy.HVIGOR, QEMU_TEST_NODE_HOME=policy.NODE, JAVA_HOME=policy.JAVA,
                    HVIGOR_USER_HOME=policy.CACHE, HAP_SIGN=str(ROOT / 'scripts/sign_qemu_test_hap.py'), ARKDOWN='/Users/ranger/.volta/bin/arkdown',
                    QEMU_TEST_DOCKER_IMAGE=policy.IMAGE, OHOS_NATIVE_BINDINGS='/Volumes/PSSD/code/ohos-rs/ohos-native-bindings')
    need(all(environment.get(key) == value for key, value in expected.items()) and all(
        environment.get(key) == package['adopted_complete_host_environment'][key] for key in ('DOCKER_SOURCE_VOLUME', 'DOCKER_OUT_VOLUME')),
        'explicit existing SDK/bindings environment and actual native source/out names required')
    environment.update(OHOS_QA_RUNTIME_PROFILE=profile_row['path'], OHOS_QA_RUNTIME_PROFILE_SHA256=profile_row['sha256'],
                       OHOS_QA_MIC_TOOLS_BUILD=mic_build['path'], OHOS_QA_MIC_TOOLS_BUILD_SHA256=mic_build['sha256'])
    def tool(literal):
        need(type(literal) is str and Path(literal).is_absolute() and Path(literal).is_file(), 'explicit actual literal executable required')
        # Use the existing executable identity rules (aliases/hardlinks are
        # tools, not ordinary evidence-file descriptors); preserve argv0.
        path = Path(literal); target = path.resolve()
        value = dict(path=literal, resolved_path=str(target), sha256=policy.sha(target), bytes=target.stat().st_size, links=policy.Policy.links(path))
        core.tool_descriptor(value)
        return value
    selection.update(signer_dist=str(canonical(intent['signer_dist'], directory=True)), signer_jar=str(canonical(intent['signer_jar'])))
    from batch_apps_select375_project_verify import sdk_binding
    for role, spec in selection['role_inputs'].items(): sdk_binding(spec, role, Path(selection['challenge']['path']))
    share = intent['share578']
    need(type(share) is dict and set(share) == {'challenge', 'role_inputs', 'signer_dist', 'signer_jar'} and
         type(share['role_inputs']) is dict and set(share['role_inputs']) == {'caller', 'target_a', 'target_b'},
         'separate actual Share578 challenge/three roles/signer inputs required')
    challenge = checked(share['challenge'])
    from batch_apps_share578_project import load_challenge
    from batch_apps_share578_project_verify import sdk_binding as share_sdk_binding
    load_challenge(Path(challenge['path']))
    for role, supplied in share['role_inputs'].items():
        need(type(supplied) is dict and set(supplied) == {'source_project', 'sdk_evidence', 'unsigned_hap'},
             'exact separate Share578 SDK role fields required')
        need(load(supplied['sdk_evidence']).get('source_commit') == COMMIT, 'old Share SDK cannot be relabelled')
        share_sdk_binding(supplied, role, Path(challenge['path']))
    share = dict(challenge=challenge, role_inputs=share['role_inputs'],
        signer_dist=str(canonical(share['signer_dist'], directory=True)), signer_jar=str(canonical(share['signer_jar'])))
    config = dict(schema_version=1, archive=archive, package_receipt=checked(intent['package_receipt']), hdc=tool(intent['hdc']), qemu=tool(intent['qemu']),
                  sdk=str(canonical(intent['sdk'], directory=True)), clock_probe=clock, clock_probe_build=clock_build,
                  capability_inputs=capability, sdk_inputs=[row['sdk_evidence'] for row in roles], select=selection, share578=share, environment=environment)
    output = Path(intent['output'])
    need(output.is_absolute() and output.parent.resolve() == output.parent and output.parent.is_dir() and
         not output.exists() and not output.is_symlink() and not output.is_relative_to(ROOT), 'fresh external DATA output required')
    raw = json.dumps(config, indent=2, allow_nan=False) + '\n'
    # Original read-only loader/profile consumer must accept BEFORE final output.
    with tempfile.TemporaryDirectory(prefix='.config394-', dir=output.parent) as temporary:
        candidate = Path(temporary).resolve() / 'config.json'; candidate.write_text(raw)
        core.load_config(candidate, record(candidate)['sha256'])
    output.mkdir(mode=0o700)
    def write(name, value):
        path = output / name
        with path.open('x') as stream: stream.write(value if type(value) is str else json.dumps(value, indent=2, allow_nan=False) + '\n')
        return record(path)
    config_row = write('config.json', raw)
    role_map = write('sdk-role-map.json', dict(scope='actual unsigned SDK receipt/HAP mapping only; not runtime proof',
        roles=roles, number_local580_sdk=number_sdk))
    return write('assembly394.json', dict(schema=SCHEMA, status='assembled_DATA_ONLY', source_commit=COMMIT, config=config_row, role_map=role_map,
        input_descriptors={key: checked(intent[key]) for key in ('package_receipt', 'profile_receipt', 'mic_receipt', 'provider_preparation',
            'sdk_batch_receipt', 'select_root_receipt', 'clock_probe', 'clock_probe_build',
            'source_kit_manifest', 'canonical_snapshot')}, kit_manifest_sha256=KIT_SHA,
        original_12_config_fields_preserved_plus_share578=True, original_17_SDK_entries=True, Number3_separate=True,
        number_local580_sdk=number_sdk, Dockermetadata_created=False,
        resources_executed=False, runtime_validated=False, first_artifact_behavior_gate_passed=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--intent', type=Path, required=True); parser.add_argument('--intent-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(assemble(load(dict(path=str(args.intent), sha256=args.intent_sha256)))))
