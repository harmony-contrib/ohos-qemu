"""Only fixed admitted raw oracle calls; DATA never names code or an ID."""
from pathlib import Path
import os
import subprocess

from final579_contract import (ROOT, HERE, AU, ORIGINAL, checked, doc, ref, save,
    need, fixed, frozen_dependency, audio_sources, api_source_root)

MEDIA_IDS = {'behavior:media-recording-input-backends-missing', 'behavior:video-encoder-dependent-media-pipelines'}
SYSTEM_IDS = {'behavior:app-domain-verification-extension-missing', 'behavior:session-manager-profile-gap'}
CALENDAR_ID = 'behavior:calendar-lifecycle-device-difference'
AU_ID = 'behavior:audio-interrupt-haptic-renderer-dependency'
API_ID = 'behavior:api26-runtime-export-mismatches-phone'
PAIRED_IDS = {'behavior:avcast-media-controller-provider-mismatch', 'behavior:distributed-hardware-ui-preinstall-path-mismatch'}


NUMBER_LOCAL_ID580 = 'number580:phone-supported-local'
NUMBER_NORMAL_SOURCE580 = {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-postpackage579-generated/source-6776526-579-01/SOURCE579.json', 'sha256': '9d0440c9ec3a31f21a9ef59ed161e5a8613dac691723f5d1dc4a52a25b1c1b31', 'bytes': 6675}


def replay_number_local580(packet):
    """Pure completed independent Number replay, never whole-ID registration."""
    actual = _au_actual_target579(checked(packet['archive']))
    if actual['device'] != 'phone':
        need(packet['number_local'] is None, 'phone local Number evidence cannot be relabelled as 2in1')
        return dict(schema='final579-number-local-mandatory/v1', id=NUMBER_LOCAL_ID580,
            applicable=False, device=actual['device'], registrations={},
            runtime_pass=False, first_artifact_behavior_gate_passed=False)
    need(packet['number_local'] is not None, 'completed independent local Number attempt is mandatory on phone')
    source = doc(NUMBER_NORMAL_SOURCE580)
    need(source['source_commit'] == packet['source_commit'], 'actual normal Number source belongs to this final HEAD')
    directory = checked(NUMBER_NORMAL_SOURCE580).parent / 'number'
    # All ten Number code/data members are admitted in the final authority's
    # complete immutable source vector, before the actor's first command.
    registration = fixed('register580', directory)
    proof = registration.replay_completed(packet['number_local'])
    need(proof['id'] == NUMBER_LOCAL_ID580 and proof['source_commit'] == packet['source_commit'] and
         proof['archive_sha256'] == packet['archive']['sha256'] and
         proof['required_local_obligations_complete'] is True and
         proof['aggregate_provider_passed'] is False and proof['whole_id_registered'] is False and
         len(proof['two_boot_ids']) == 2 and len(set(proof['two_boot_ids'])) == 2 and
         type(proof['owner']['root']) is str and Path(proof['owner']['root']).is_absolute(),
         'all supported local semantics, actual owned two boots and source/archive identity must replay')
    return dict(schema='final579-number-local-mandatory/v1', id=NUMBER_LOCAL_ID580,
        applicable=True, device=actual['device'], registrations={}, completed=packet['number_local'],
        replay=proof, runtime_pass=False, first_artifact_behavior_gate_passed=False)


def number_local580(packet, output):
    proof = replay_number_local580(packet)
    return dict(registrations={}, failures=[], proof=save(output / 'number-local.json', proof),
        local_id=NUMBER_LOCAL_ID580, applicable=proof['applicable'],
        required_local_obligations_complete=(proof['applicable'] and
            proof['replay']['required_local_obligations_complete'] is True))


def checked_map(value, allowed):
    need(type(value) is dict and set(value) <= allowed, 'fixed exact-ID oracle output required')
    return value


def system(packet, output):
    folder = frozen_dependency('system') / 'candidate'
    module = fixed('system579_registration', folder)
    result = module.register_system_cases(archive=packet['archive'], boot=packet['main_boot'], index=packet['system_index'])
    checked_map(result['registrations'], SYSTEM_IDS)
    return dict(registrations=result['registrations'], failures=result['failures'], proof=save(output / 'system.json', result))


def calendar(packet, output):
    folder = frozen_dependency('calendar') / 'candidate/ci/capability-audit'
    module = fixed('calendar579_semantic_replay', folder)
    data = packet['calendar']
    need(type(data) is dict and set(data) == {'phase1', 'phase2', 'first_boot', 'second_boot', 'resource_report'}, 'five actual Calendar phase/resource Refs')
    first, main = doc(data['first_boot']), doc(packet['main_boot'])
    need(first['archive_sha256'] == doc(data['second_boot'])['archive_sha256'] == packet['archive']['sha256'] and
        all(first['test_environment'][key] == main['test_environment'][key]
            for key in ('boot_id', 'udid', 'target', 'guest_arch', 'device_type')) and
        checked(data['first_boot']).is_relative_to(checked(packet['main_settlement']['held']).parent),
        'Calendar actual main-boot snapshot -> real later boot archive chain')
    proposal = module.registration_candidate(original_ledger=ref(ORIGINAL), **data)
    result_ref = save(output / 'calendar.json', proposal)
    replay = proposal['raw_replay']
    need(proposal['original_id'] == CALENDAR_ID, 'exact Calendar original ID')
    failures = list(replay['retained_failures']) + list(replay['replay_errors'])
    registrations = {}
    if proposal['candidate_for_root_ledger_review'] is True and replay['semantic_replay_complete'] is True and not failures:
        registrations[CALENDAR_ID] = dict(archive_sha256=packet['archive']['sha256'],
            boot_id=replay['observed_scope']['first_boot'], related_boot_id=replay['observed_scope']['second_boot'],
            evidence=result_ref, resolution='complete_original_Calendar17_two_boot_raw_semantics',
            verifier_source=ref(folder / 'calendar579_semantic_replay.py'))
    return dict(registrations=registrations, failures=failures, proof=result_ref)


def _audio_original_arm64_phone579(packet, output, actor):
    audio_sources(packet['audio_source_manifest'], actor=actor)
    binding = fixed('bindings414', AU)
    coordinator = fixed('coordinator414', AU)
    binding.verify_sources()
    data = packet['au']
    need(type(data) is dict and set(data) == {'report', 'boot'}, 'actual original AU report/boot only')
    report, boot = doc(data['report']), doc(data['boot'])
    need(boot['archive_sha256'] == packet['archive']['sha256'] and
        boot['test_environment']['boot_id'] != doc(packet['main_boot'])['test_environment']['boot_id'] and
        boot['test_environment']['device_type'] == doc(packet['main_boot'])['test_environment']['device_type'] and
        not report.get('error') and not report['cleanup_errors'] and report['onset579_runtime_verified'] is True,
        'actual dedicated AU attempt failed or substituted main boot')
    commands = []
    def actual_signature_command(argv, label):
        need(subprocess.Popen is actor.ProxyPopen and actor.STATE is not None, 'original admitted actor proxy only')
        argv = list(map(str, argv))
        if argv and argv[0] == 'java':
            argv[0] = str(Path(os.environ['JAVA_HOME']) / 'bin/java')
        # This runs only in the original authenticated actor. The original
        # ProxyPopen RPC retains every actual child under the same Authority.
        completed = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
        number = str(len(commands)).zfill(4)
        stdout, stderr = output / (number + '.stdout'), output / (number + '.stderr')
        stdout.write_text(completed.stdout); stderr.write_text(completed.stderr)
        commands.append(dict(argv=argv, exit_code=completed.returncode, label=label,
            stdout=ref(stdout), stderr=ref(stderr)))
        need(completed.returncode == 0, 'actual actor signature/CMS command failed')
        return completed.stdout + completed.stderr
    proof = coordinator.verify_observations(checked(report['raw_collection']), checked(packet['archive']), checked(data['boot']),
        signature_output=output / 'signatures', signature_command=actual_signature_command,
        control480_registry=checked(report['control480_root_raw']['registry']),
        control480_held=checked(report['control480_root_raw']['held']))
    need(proof['anchor']['synchronization_verified'] is True and proof['native_pipeline_source_image_witness_verified'] is True, 'no_onset_anchor')
    result = dict(schema='actual-final579-AU-actor-replay/v1', report=data['report'], boot=data['boot'],
        audio_source_manifest=packet['audio_source_manifest'], original_raw_replay=proof,
        actual_signature_commands=commands, original_owner_finish_still_required=True,
        runtime_pass=False, first_artifact_behavior_gate_passed=False)
    proof_ref = save(output / 'audio.json', result)
    return dict(registrations={AU_ID: dict(archive_sha256=packet['archive']['sha256'], boot_id=proof['boot_id'],
        boot=data['boot'], evidence=proof_ref, actual_collection=report['raw_collection'],
        verifier_source=ref(AU / 'coordinator414.py'),
        resolution='original_crossUID_CONTROL_VDI_PCM_and_stream_frame0_mixedPCM_same_OFD_HW_MONOTONIC')},
        failures=[], proof=proof_ref)


def _audio_later_targets579(packet, output, actor):
    audio_sources(packet['audio_source_manifest'], actor=actor)
    binding = fixed('bindings414', AU)
    coordinator = fixed('replay_target579', AU / 'target579')
    binding.verify_sources()
    data = packet['au']
    need(type(data) is dict and set(data) == {'report', 'boot'}, 'actual original AU report/boot only')
    report, boot = doc(data['report']), doc(data['boot'])
    need(boot['archive_sha256'] == packet['archive']['sha256'] and
        boot['test_environment']['boot_id'] != doc(packet['main_boot'])['test_environment']['boot_id'] and
        boot['test_environment']['device_type'] == doc(packet['main_boot'])['test_environment']['device_type'] and
        not report.get('error') and not report['cleanup_errors'] and report['onset579_runtime_verified'] is True,
        'actual dedicated AU attempt failed or substituted main boot')
    commands = []
    def actual_signature_command(argv, label):
        need(subprocess.Popen is actor.ProxyPopen and actor.STATE is not None, 'original admitted actor proxy only')
        argv = list(map(str, argv))
        if argv and argv[0] == 'java':
            argv[0] = str(Path(os.environ['JAVA_HOME']) / 'bin/java')
        # This runs only in the original authenticated actor. The original
        # ProxyPopen RPC retains every actual child under the same Authority.
        completed = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
        number = str(len(commands)).zfill(4)
        stdout, stderr = output / (number + '.stdout'), output / (number + '.stderr')
        stdout.write_text(completed.stdout); stderr.write_text(completed.stderr)
        commands.append(dict(argv=argv, exit_code=completed.returncode, label=label,
            stdout=ref(stdout), stderr=ref(stderr)))
        need(completed.returncode == 0, 'actual actor signature/CMS command failed')
        return completed.stdout + completed.stderr
    proof = coordinator.verify_observations(checked(report['raw_collection']), checked(packet['archive']), checked(data['boot']),
        signature_output=output / 'signatures', signature_command=actual_signature_command,
        control480_registry=checked(report['control480_root_raw']['registry']),
        control480_held=checked(report['control480_root_raw']['held']))
    need(proof['anchor']['synchronization_verified'] is True and proof['native_pipeline_source_image_witness_verified'] is True, 'no_onset_anchor')
    result = dict(schema='actual-final579-AU-actor-replay/v1', report=data['report'], boot=data['boot'],
        audio_source_manifest=packet['audio_source_manifest'], original_raw_replay=proof,
        actual_signature_commands=commands, original_owner_finish_still_required=True,
        runtime_pass=False, first_artifact_behavior_gate_passed=False)
    proof_ref = save(output / 'audio.json', result)
    return dict(registrations={AU_ID: dict(archive_sha256=packet['archive']['sha256'], boot_id=proof['boot_id'],
        boot=data['boot'], evidence=proof_ref, actual_collection=report['raw_collection'],
        verifier_source=proof['target579_verifier_source'],
        resolution='original_crossUID_CONTROL_VDI_PCM_and_stream_frame0_mixedPCM_same_OFD_HW_MONOTONIC')},
        failures=[], proof=proof_ref)


def _au_actual_target579(archive):
    # Original full AU closure is checked before either canonical import.
    pins = fixed('bindings414', AU).verify_sources()
    folder = ROOT / 'ci/capability-audit'
    for source_name in ('batch_system_build_runtime_helpers', 'production579_target'):
        source = folder / (source_name + '.py')
        need(pins.get(str(source)) == ref(source)['sha256'],
             'canonical target reader absent from complete actual AU source admission')
        module = fixed(source_name, folder)
        need(Path(module.__file__).resolve() == source and
             pins[str(source)] == ref(source)['sha256'], 'changed fixed canonical target reader')
    actual = module.archive_manifest(archive)['context']
    need(actual['product'] in ('arm64_virt', 'armv7a_virt', 'x86_64_virt') and
         actual['device'] in ('phone', '2in1'), 'finite actual AU archive target')
    return actual


def audio(packet, output, actor):
    actual = _au_actual_target579(checked(packet['archive']))
    if (actual['product'], actual['device']) == ('arm64_virt', 'phone'):
        return _audio_original_arm64_phone579(packet, output, actor)
    return _audio_later_targets579(packet, output, actor)


def api(packet, original, output):
    folder = api_source_root()
    module = fixed('api26_579_registration', folder)
    projected = fixed('api26_connected579_sources', folder).load()
    original_steps = projected.steps
    original_adapter = original_steps.load_adapter(ROOT)
    data = packet['api']
    assembly_ref, assembly_failures = None, []
    if type(data) is dict and set(data) == {'kind', 'main_index', 'surface', 'network', 'gnss'}:
        need(data['kind'] == 'raw_assembly', 'fixed API raw assembly data format only')
        assembler = fixed('api26_579_main', folder)
        assembly_ref = assembler.records_from_completed_main(data['main_index'], archive=packet['archive'],
            main_boot=packet['main_boot'], runtime_root=Path(packet['runtime_root']), surface=data['surface'],
            output=output / 'assembly', network=data['network'], gnss=data['gnss'])
        assembled = doc(assembly_ref)
        need(assembled['schema'] == 'api26-fixed-record-assembly579/v1' and
            assembled['main_index'] == data['main_index'], 'actual fixed API record assembly origin')
        assembly_failures = list(assembled['retained_failures'])
        data = assembled['api']
    need(type(data) is dict and set(data) == {'surface', 'families', 'boundaries'}, 'fixed API actual surface/families/boundaries data')
    result_ref = module.collect_registered(archive=packet['archive'], main_boot=packet['main_boot'],
        runtime_root=Path(packet['runtime_root']),
        original=ref(ROOT / 'docs/capability-audit/runtime/arm64-phone/arkts-export-surface-latest.json'), surface=data['surface'],
        families=data['families'], boundaries=data['boundaries'], output=output / 'registration',
        original_steps=original_steps, original_adapter=original_adapter)
    result = doc(result_ref)
    need(result['schema'] == 'api26-original181-registration579/v1' and
        result['archive_sha256'] == packet['archive']['sha256'] and
        result['boot_id'] == doc(packet['main_boot'])['test_environment']['boot_id'], 'actual complete original API typed replay identity')
    need(result['original_replay'] == original, 'API replay cannot replace the one original ledger base')
    members = {'arkts_export:' + module_name + ':' + name for module_name, name in original_api_members()}
    allowed = {API_ID} | members
    checked_map(result['registrations'], allowed)
    excluded = members & set(original['release_exclusions']['ids'])
    need({row['id'] for row in result['policy_excluded_members']} == excluded and
        len(result['policy_excluded_members']) == len(excluded) and
        set(result['supported_required']) == members - excluded and
        len(result['supported_required']) == len(members - excluded) and
        all(row['runtime_pass'] is False and row['treated_as_typed_pass'] is False
            for row in result['policy_excluded_members']),
        'only the original exact release_scope intersection is excluded/nonpass')
    if API_ID in result['registrations']:
        need(result['supported_scope_complete'] is True and not assembly_failures and not result['retained_failures'] and
            members - excluded <= set(result['registrations']) and
            not excluded & set(result['registrations']),
            'the aggregate needs every original supported typed member; no Location/BT/RTT exclusion')
    return dict(registrations=result['registrations'], failures=assembly_failures + result['retained_failures'], proof=result_ref,
        actual_record_assembly=assembly_ref,
        unresolved_members=result['unresolved_members'], policy_excluded_members=result['policy_excluded_members'])


def telephony(packet, output, actor):
    # Exact new canonical source is already admitted by the whole final vector.
    return fixed('telephony579_registration',ROOT/'ci/capability-audit').collect(packet,output,actor)


def photos(packet, output, actor):
    # Source admission is part of the actual final SOURCE-MANIFEST. The fixed
    # existing Photos oracle runs only in this original authenticated actor.
    module = fixed('photos579_final_family', ROOT / 'ci/capability-audit')
    # The actor has already created output; the original Photos collector
    # requires a fresh child directory and owns creating it itself.
    return module.collect(packet, output / 'retained', actor)


def provider(packet, original, output, actor, *, replayed):
    # One fixed source module; packet contains no code selector or new field.
    folder = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-identity-generated/source-whole579-next01/provider579/candidate')
    module = fixed('provider579_registration', folder)
    return module.collect(packet, original, output, actor, replayed=replayed)


def media_whole(packet, output, actor):
    module = fixed('media579_registration', HERE / 'media579')
    return module.collect(packet, output, actor)


def original_api_members():
    baseline = doc(ref(ROOT / 'docs/capability-audit/native-arkts11-gap-ledger.json'))
    rows = baseline['devices']['phone']['arkts11_runtime_export_gaps']
    result = {(row['module'], member['name']) for row in rows for member in row['missing']}
    need(len(result) == 181 and len({module for module, _name in result}) == 54, 'original exact API181/54')
    return result


def paired(packet, output):
    folder = frozen_dependency('paired') / 'candidate/ci/capability-audit'
    module = fixed('apps_paired579_semantic_replay', folder)
    result = module.registration_candidate(original_ledger=ref(ORIGINAL), data=packet['paired'], archive=packet['archive'])
    need(result['schema'] == 'paired579-two-original-ID-registration-candidate/v1', 'actual paired fixed proposal schema')
    raw = result['raw_replay']
    proof_ref = save(output / 'paired.json', result)
    failures = list(raw['retained_failures']) + list(raw['replay_errors'])
    registrations = {}
    if result['candidate_for_root_ledger_review'] is True and raw['semantic_replay_complete'] is True and not failures:
        need(set(raw['original_ID_candidates']) == PAIRED_IDS and all(raw['original_ID_candidates'].values()), 'both exact complete paired ID raw contracts')
        boots = raw['checks']['original_resources']['distinct_boots']
        need(len(boots) == len(set(boots)) == 2 and doc(packet['main_boot'])['test_environment']['boot_id'] not in boots and
            doc(packet['au']['boot'])['test_environment']['boot_id'] not in boots, 'actual paired endpoints cannot be relabeled main/AU boots')
        for identifier in PAIRED_IDS:
            registrations[identifier] = dict(archive_sha256=packet['archive']['sha256'], related_boot_ids=boots,
                evidence=proof_ref, resolution='complete_original_paired_PIN_UI_remote_camera_MIC_AVCast_independent_consumption_lifecycle',
                verifier_source=ref(folder / 'apps_paired579_semantic_replay.py'))
    return dict(registrations=registrations, failures=failures, proof=proof_ref)


def services(packet, output, actor, replayed):
    module = fixed('owning_services579_registration', ROOT / 'ci/capability-audit')
    result = module.collect(packet, output, actor, replayed=replayed)
    checked_map(result['registrations'], {'behavior:phone-published-capabilities-not-declared',
        'behavior:advertising-service-provider-missing'})
    return result


def apps_additional(packet, output, actor):
    from final579_contract import own_sources
    path = HERE / 'additional579/additional579_registration.py'
    vector = doc(own_sources())
    admitted = {row['path']: row['sha256'] for row in vector['files']}
    need(admitted.get(str(path)) == ref(path)['sha256'], 'complete fixed additional eight-ID source must be admitted')
    return fixed('additional579_registration', path.parent).collect(packet, output, actor)


def apps(packet, output, actor):
    # This exact private raw oracle is admitted before import. It does not
    # create an Owner or accept a case/module/ID selector from the packet.
    from final579_contract import own_sources
    path = HERE / 'apps579/apps579_whole_registration.py'
    vector = doc(own_sources())
    matches = [row for row in vector['files'] if row['path'] == str(path)]
    need(len(matches) == 1 and matches[0]['sha256'] == ref(path)['sha256'],
         'Root must admit the complete fixed Apps raw registration source')
    module = fixed('apps579_whole_registration', path.parent)
    return module.collect(packet, output, actor)


def msdp(packet, output, actor, replayed):
    module = fixed('msdp579_registration', ROOT / 'ci/capability-audit')
    result = module.collect(packet, output, actor, replayed=replayed)
    checked_map(result['registrations'], {'behavior:msdp-device-status-mock-or-missing-clients'})
    return result
