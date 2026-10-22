#!/usr/bin/env python3
"""Root's finite dedicated AU run on the newly packaged archive and original Owner.

The full main suite and this Audio boot retain distinct results. Original
Owner.run exclusively owns the shared lease, marker, VM, HDC and finish path.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import inspect
import json
import secrets

from au579_sources import AU, H, ROOT, checked, fixed, need, packet, production, record

B = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')
K = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-suite-after579-generated/kit-6776526-579-01')
KIT_SHA = 'ba7c0e3b363d30ffa2baef081edc7c29bba0bf6177e5e922b7fad08c0a89ecbb'
HEAD = '67765265103a932b9a562face76a882f07bed3e3'
FIELDS = {'schema', 'source_commit', 'owner_config', 'runtime_inputs', 'audio_source_manifest',
          'postpackage_receipt', 'main_boot', 'main_held_processes', 'main_constructor_registry',
          'main_attempt', 'api_network', 'api_gnss', 'independent_owners', 'earlier_attempts', 'number_local'}


def read(row):
    return json.loads(checked(row).read_text())


def pair(row):
    return {key: row[key] for key in ('path', 'sha256')}


def main_closed(data, archive):
    boot, held, registry = (read(data[name]) for name in
                           ('main_boot', 'main_held_processes', 'main_constructor_registry'))
    need(boot['archive_sha256'] == archive['sha256'] and boot['test_environment']['boot_id'],
         'the completed main attempt must use the same newly packaged archive')
    need(held['unknown_creation'] is False and held['children'] and
         all(row['reaped'] is True and row['last_signal_boundary'] is True and
             type(row['exit_code']) is int for row in held['children']), 'main original authority is not settled')
    need(any(row.get('event') == 'constructor_finalization' and
             row.get('all_actual_registered_groups_closed') is True for row in registry['events']),
         'main actual constructor finalization missing')
    main_root = checked(data['main_held_processes']).parent
    need(checked(data['main_constructor_registry']).is_relative_to(main_root) and
         checked(data['main_boot']).is_relative_to(main_root) and not (main_root / 'quarantine.json').exists(),
         'same original main output must be closed without quarantine')
    return boot['test_environment']['boot_id']


def independent_closed(data, archive):
    """Resource admission only; actual API verdicts remain in the fixed actor."""
    roots = {checked(data['main_held_processes']).parent}
    for name in ('network', 'gnss'):
        group = data['independent_owners'][name]
        result = read(group['report'])
        if name == 'gnss':
            need(result['schema'] == 'gnss579-original-owner-result/v1' and
                 result['source_commit'] == HEAD and type(result['exit_code']) is int and
                 result['cleanup_verified'] is True and type(result['failures']) is list,
                 'actual finished GNSS retention owner required')
            final = read(pair(result['dedicated']))
            actual = result['actual']
            need(checked(pair(result['dedicated'])).parent == checked(group['report']).parent,
                 'GNSS final report belongs to another original owner')
        else:
            final = result
            case = final.get('case_result')
            actual = case.get('api26_network') if type(case) is dict else None
        need(final['source_commit'] == HEAD and final['resources_executed'] is True and
             type(final['exit_code']) is int and type(final['failures']) is list and
             final['cleanup_verified'] is True,
             'actual independent original Owner.finish record required')
        wanted = data['api_' + name]
        if wanted is not None:
            need(type(actual) is dict and set(actual) == set(wanted) and
                 {key: pair(row) for key, row in actual.items()} == wanted and
                 pair(final['case_boot']) == wanted['boot'],
                 'independent final owner/raw/boot associations differ')
        need(pair(final['held_processes']) == group['held'] and
             pair(final['constructors']) == group['constructors'],
             'independent final settlement associations differ')
        root = checked(group['held']).parent
        need(root not in roots and checked(group['report']).parent == root,
             'independent owner output was reused or relabeled')
        roots.add(root)
        case_boot_ref = pair(final['case_boot'])
        main_closed(dict(main_boot=case_boot_ref, main_held_processes=group['held'],
                         main_constructor_registry=group['constructors']), archive)
        final_boot = read(pair(final['final_boot']))
        case_boot = read(case_boot_ref)
        need(final_boot['archive_sha256'] == archive['sha256'] and
             final_boot['test_environment']['boot_id'] == case_boot['test_environment']['boot_id'],
             'actual independent final and business boot differ')


def _run_original_arm64_phone579(data, output, *, entry_ref):
    need(type(data) is dict and set(data) == FIELDS and data['schema'] == 'actual-AU579-fixed-owner/v1' and
         data['source_commit'] == HEAD, 'finite current AU request')
    seam = production()
    from owner_sources579_root import admit_global579_owner_sources
    admit_global579_owner_sources()
    checked(entry_ref)
    for key in FIELDS - {'schema', 'source_commit', 'api_network', 'api_gnss', 'independent_owners', 'earlier_attempts', 'number_local'}:
        checked(data[key])
    need((data['api_network'] is None or (type(data['api_network']) is dict and
         set(data['api_network']) == {'retained', 'boot', 'protocol'})) and
         (data['api_gnss'] is None or (type(data['api_gnss']) is dict and
         set(data['api_gnss']) == {'retained', 'boot'})) and
         type(data['earlier_attempts']) is list, 'finite actual independent raw records and history')
    for row in (*(data['api_network'] or {}).values(), *(data['api_gnss'] or {}).values(), *data['earlier_attempts']):
        checked(row)
    need(type(data['independent_owners']) is dict and
         set(data['independent_owners']) == {'network', 'gnss'}, 'two actual independent final owners')
    for group in data['independent_owners'].values():
        need(type(group) is dict and set(group) == {'report', 'held', 'constructors'},
             'finite independent final owner records')
        for row in group.values():
            checked(row)
    packet(AU, 'FROZEN.json', data['audio_source_manifest']['sha256'])
    need(checked(data['audio_source_manifest']) == AU / 'FROZEN.json', 'fixed final Audio packet')
    launch = fixed('run_full_suite377', K)
    launch.verify_kit(KIT_SHA)
    owner_module = fixed('run_full_suite_owner376', K)
    runner = fixed('runner377', K)
    entry = fixed('owner_entry414', AU)
    binding = fixed('au579_runtime_inputs_root', Path(__file__).resolve().parent)
    config = owner_module.load_config(checked(data['owner_config']), data['owner_config']['sha256'])
    archive = pair(config['archive'])
    main_boot_id = main_closed(data, archive)
    independent_closed(data, archive)
    post = read(data['postpackage_receipt'])
    need(post['source_commit'] == HEAD and post['exit_code'] == 0 and post['failures'] == [] and
         pair(post['archive']) == archive and pair(post['package_receipt']) == pair(config['package_receipt']),
         'all actual new-package input-production stages required')
    native = read(pair(post['au579_native_owner']))
    sdk = read(pair(post['au579_sdk_stage']))
    onset_owner_ref = pair(post['audio_onset579_helper_owner'])
    onset_owner = read(onset_owner_ref)
    need(native['exit_code'] == sdk['exit_code'] == onset_owner['exit_code'] == 0 and
         native['cleanup_verified'] is True and native['owned_container_absent'] is True and
         onset_owner['cleanup_verified'] is True and
         not sdk.get('must_resolve_owned_SDK_processes_before_next_resource_stage'), 'actual AU producers not settled')
    native_proofs = native['native']
    onset_build_ref = dict(path=onset_owner['build_report'], sha256=onset_owner['build_report_sha256'])
    onset_build = read(onset_build_ref)
    helper = onset_build['helpers']['audio_onset_control579']
    onset = dict(schema='audio-onset579-input/v1', helper=dict(binary=record(Path(helper['binary'])),
        build=onset_build_ref, source=pair(helper['source']), production=onset_owner_ref),
        installed_dsos=pair(post['audio_onset579_installed_dsos']))
    profile = dict(path=config['environment']['OHOS_QA_RUNTIME_PROFILE'],
                   sha256=config['environment']['OHOS_QA_RUNTIME_PROFILE_SHA256'])
    checked(profile)
    children = runner.RootReviewedFixedRunner(data['runtime_inputs'])
    entry.connect_children(children)
    from runtime_supplements579 import gap as admit_gap
    registration = admit_gap(children)
    # All additions are finite sources admitted by the sealed production packet;
    # DATA cannot choose a source callback or constructor implementation.
    for source in (Path(binding.__file__).resolve(), seam.HERE / 'au579_production.py'):
        children.policy.sources[str(source)] = record(source)['sha256']
    original_factory = children.suite_function
    need(original_factory.__self__ is children and
         Path(original_factory.__func__.__code__.co_filename).resolve() == K / 'runner377.py',
         'unchanged bound original suite verifier')
    output = Path(output)
    need(output.is_absolute() and output.resolve() == output and output.parent == B and not output.exists(),
         'fresh direct BASE dedicated Audio output')
    report = dict(schema='actual-dedicated-AU579-owner-result/v1', source_commit=HEAD, entry=entry_ref,
        archive=archive, main_boot=data['main_boot'], main_boot_id=main_boot_id, actual_audio_boot=None,
        postpackage_receipt=data['postpackage_receipt'], failures=[], cleanup_verified=False,
        audio_runtime_verified=False, first_artifact_behavior_gate_passed=False, full_audit_passed=False)
    held = {}

    def save():
        if output.is_dir():
            (output / 'audio-owner579.json').write_text(json.dumps(report, indent=2) + '\n')

    def audio_run(args, *, owned_command, owned_guest_factory, owned_select_hook, owned_graphics3d_hook):
        owner = getattr(owned_guest_factory, '__self__', None)
        need(type(owner) is owner_module.Owner and owner.children is children and
             all(getattr(callback, '__self__', None) is owner for callback in
                 (owned_command, owned_select_hook, owned_graphics3d_hook)) and args.package_archive == owner.archive,
             'one original actual Owner and unchanged constructor callbacks')
        held['owner'] = owner
        resources = []
        original_finish = owner.finish

        def finish_original_resources():
            from capability578_stage import UnsettledCapability
            try:
                for io in reversed(resources):
                    if not io._closed:
                        io.close()
            except BaseException as error:
                owner.cleanup_complete = False
                raise UnsettledCapability('Audio inventory IO not settled: ' + str(error)) from error
            return original_finish()

        owner.finish = finish_original_resources
        boot_args = SimpleNamespace(archive=owner.archive, output=owner.output / 'audio-boot', hdc=owner.hdc,
            hdc_port=owner.guest_port, accel=config['environment'].get('QEMU_TEST_ACCEL', 'hvf'),
            resolution='1280x800', purpose='acceptance', kernel_diagnostic=None, power_diagnostic_wakeup=False,
            hold=False, candidate_kernel=None, candidate_kernel_evidence=None, power_button_after_quiet=False,
            wait_seconds=1800, stable_seconds=60, clock_probe=owner_module.descriptor(config['clock_probe']),
            clock_probe_build=owner_module.descriptor(config['clock_probe_build']))
        guest = owned_guest_factory(boot_args).start()
        owner.held_binding(guest)
        need(guest.report['test_environment']['boot_id'] != main_boot_id and
             json.loads((guest.directory / 'build-inputs.json').read_text())['source_git_revision'] == HEAD,
             'actual distinct newly packaged dedicated Audio boot')
        guest.save()
        initial_boot = owner.output / 'audio-initial-boot.json'
        with initial_boot.open('xb') as stream:
            stream.write((guest.args.output / 'boot.json').read_bytes())
        report['initial_audio_boot'] = record(initial_boot)
        save()
        from capability578_owned_io import OwnedIO
        from capability578_https import OwnedHTTPS

        def no_callers(*args, **kwargs):
            raise ValueError('readonly inventory prelude cannot install or build actors')

        io = OwnedIO(owner, guest, owner.output / 'inventory-prelude', run_id=secrets.token_hex(16),
            package_inputs={}, prepare_callers=no_callers, https_factory=OwnedHTTPS)
        resources.append(io)
        value, inventory_ref = binding.observe_inventory(io, native['inventory_tool'], profile_ref=profile)
        io.close()
        report['inventory'] = inventory_ref
        # Inventory and its real guest cleanup append original boot commands.
        # Seal only after those mutations; signing uses Authority.direct and
        # therefore preserves the original exact boot equality preconditions.
        boot = owner.output / 'audio-case-boot.json'
        with boot.open('xb') as stream:
            stream.write((guest.args.output / 'boot.json').read_bytes())
        report['actual_audio_boot'] = record(boot)
        save()
        onset_path = owner.output / 'onset-input.json'
        with onset_path.open('x') as stream:
            json.dump(onset, stream, indent=2); stream.write('\n')
        signing = binding.sign_on_original_owner(owner, guest, boot_ref=record(boot),
            preparation_ref=sdk['preparation'], sdk_inputs_ref=sdk['sdk_inputs'],
            package_receipt_ref=pair(config['package_receipt']), signer_dist=config['select']['signer_dist'],
            signer_jar=config['select']['signer_jar'], output=owner.output / 'audio-signing')
        inputs = binding.assemble_on_original_owner(owner, guest, boot_ref=record(boot),
            preparation_ref=sdk['preparation'], sdk_inputs_ref=sdk['sdk_inputs'], signing_ref=signing,
            package_receipt_ref=pair(config['package_receipt']), profile_ref=profile,
            threeuid_proof=native_proofs['threeuid'], control_proof=native_proofs['control'],
            inventory_value=value, inventory_ref=inventory_ref, original_inventory_io=io,
            onset_ref=record(onset_path), root_config_ref=data['owner_config'], output=owner.output / 'audio-inputs')
        report['inputs'] = inputs
        save()
        result = entry.run_on_owner(owner, guest, boot=record(boot), preparation=sdk['preparation'],
            inputs=inputs['inputs'], package_receipt=pair(config['package_receipt']), runtime_profile=profile,
            root_config=data['owner_config'], output=owner.output / 'audio-attempt')
        need(result.get('onset579_runtime_verified') is True and result['cleanup_errors'] == [],
             'actual original full Audio lifecycle/onset replay required')
        report['audio_runtime_verified'] = True
        report['audio_result'] = record(owner.output / 'audio-attempt/owner414-result.json')
        save()
        # The original guest is still held here. The unchanged independent AU
        # verifier performs its actual signature/CMS replay through this same
        # Owner; only the later original finish can settle its registration.
        report['gap_registration'] = registration.register_au_on_original_owner(
            owner, guest, dict(report=report['audio_result'], boot=record(boot)),
            output=owner.output / 'audio-gap579-replay')
        save()
        # Raw replay that can invoke an original decoder or crypto child stays
        # inside the original authenticated Runner, while this AU guest/Owner
        # is still held. The later original finish remains the final boundary.
        from runtime_supplements579 import final_raw
        from final_raw579_root import assemble
        integration, _seal = final_raw(children)
        packet_ref = assemble(request=data, archive=archive, au_report=report['audio_result'],
            au_boot=record(boot), output=owner.output / 'final579-packet.json')
        report['final_raw_attempt'] = integration.run_on_original_owner(owner, packet_ref,
            output=owner.output / 'final579-raw')
        save()
        # Original full-suite gate remains false: this is a separate actual AU
        # result which Root must reconcile with the main/Calendar/paired audit.
        return dict(status='dedicated_AU_observed', first_artifact_behavior_gate_passed=False)

    def fixed_factory(original):
        verified = original_factory(original)
        need(verified.__code__ is original.__code__, 'original full-suite verifier body retained')
        return audio_run

    children.suite_function = fixed_factory
    try:
        code = owner_module.run(checked(data['owner_config']), data['owner_config']['sha256'], output, children=children)
        need(code == 1, 'dedicated AU entry must not assert original full-suite acceptance')
        report['original_full_gate_returncode'] = code
    except BaseException as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        owner = held.get('owner')
        if owner is not None and owner.cleanup_complete:
            report['cleanup_verified'] = True
            report['held_processes'] = record(owner.output / 'held-processes.json')
            report['constructor_registry'] = record(owner.output / 'constructors377/registry.json')
            if owner.vm is not None:
                report['final_boot'] = record(owner.vm.args.output / 'boot.json')
        save()
    need(report['audio_runtime_verified'] and report['cleanup_verified'] and not report['failures'],
         'actual dedicated Audio validation or cleanup failed')
    # Freeze this report before the pure final seal takes its Ref. The seal is
    # a separate file and is never appended back to the already hashed input.
    owner_ref = record(output / 'audio-owner579.json')
    from runtime_supplements579 import FINAL
    seal = fixed('final579_seal', FINAL / 'candidate')
    final_ref = seal.finalize(attempt=report['final_raw_attempt'], au_held=report['held_processes'],
        au_constructors=report['constructor_registry'], au_owner_result=owner_ref,
        output=output / 'final579-gate.json')
    final = read(final_ref)
    completion = dict(schema='actual-AU579-and-final579-completion/v1', owner=owner_ref,
        final_gate=final_ref, audio_runtime_verified=True, cleanup_verified=True,
        first_artifact_behavior_gate_passed=final['first_artifact_behavior_gate_passed'])
    with (output / 'audio-completion579.json').open('x') as stream:
        json.dump(completion, stream, indent=2); stream.write('\n')
    return completion


def _run_later_targets579(data, output, *, entry_ref):
    need(type(data) is dict and set(data) == FIELDS and data['schema'] == 'actual-AU579-fixed-owner/v1' and
         data['source_commit'] == HEAD, 'finite current AU request')
    seam = production()
    from owner_sources579_root import admit_global579_owner_sources
    admit_global579_owner_sources()
    checked(entry_ref)
    for key in FIELDS - {'schema', 'source_commit', 'api_network', 'api_gnss', 'independent_owners', 'earlier_attempts', 'number_local'}:
        checked(data[key])
    need((data['api_network'] is None or (type(data['api_network']) is dict and
         set(data['api_network']) == {'retained', 'boot', 'protocol'})) and
         (data['api_gnss'] is None or (type(data['api_gnss']) is dict and
         set(data['api_gnss']) == {'retained', 'boot'})) and
         type(data['earlier_attempts']) is list, 'finite actual independent raw records and history')
    for row in (*(data['api_network'] or {}).values(), *(data['api_gnss'] or {}).values(), *data['earlier_attempts']):
        checked(row)
    need(type(data['independent_owners']) is dict and
         set(data['independent_owners']) == {'network', 'gnss'}, 'two actual independent final owners')
    for group in data['independent_owners'].values():
        need(type(group) is dict and set(group) == {'report', 'held', 'constructors'},
             'finite independent final owner records')
        for row in group.values():
            checked(row)
    packet(AU, 'FROZEN.json', data['audio_source_manifest']['sha256'])
    need(checked(data['audio_source_manifest']) == AU / 'FROZEN.json', 'fixed final Audio packet')
    launch = fixed('run_full_suite377', K)
    launch.verify_kit(KIT_SHA)
    owner_module = fixed('run_full_suite_owner376', K)
    runner = fixed('runner377', K)
    entry = fixed('owner_entry414', AU)
    binding = fixed('au579_runtime_inputs_root', Path(__file__).resolve().parent)
    config = owner_module.load_config(checked(data['owner_config']), data['owner_config']['sha256'])
    # Explicit later-target session; original ARM64 phone stays on old objects.
    selected_target = _actual_target579(checked(pair(config['archive'])))
    target_session = None
    if (selected_target['product'], selected_target['device']) != ('arm64_virt', 'phone'):
        target_folder = AU / 'target579'
        target_names = ('bindings_target579.py', 'common_target579.py', 'control_bridge_namespace_target579.py', 'control_session_namespace_target579.py', 'coordinator_global_target579.py', 'coordinator_namespace_target579.py', 'dispatch_target579.py', 'helper_admission_namespace_target579.py', 'onset_bridge_namespace_target579.py', 'onset_verify_namespace_target579.py', 'owner_entry_global_target579.py', 'owner_entry_namespace_target579.py', 'owner_handshake_global_target579.py', 'owner_handshake_namespace_target579.py', 'replay_target579.py', 'runtime_inputs_target579.py', 'tools_namespace_target579.py', 'verify_control_namespace_target579.py', 'verify_window_namespace_target579.py')
        pins = seam.au_module('bindings414').verify_sources()
        target_pins = json.loads((target_folder / 'SOURCES-TARGET579.json').read_text())
        need({p for p in target_folder.rglob('*') if p.is_file() or p.is_symlink()} ==
             {target_folder / name for name in target_names} | {target_folder / 'SOURCES-TARGET579.json'},
             'exact fixed later-target source folder')
        import sys
        for name in target_names:
            path = target_folder / name
            need(target_pins.get(str(path)) == pins.get(str(path)) == record(path)['sha256'],
                 'later target source absent from complete original AU admission')
            cached = sys.modules.get(path.stem)
            need(cached is None or Path(cached.__file__).resolve() == path,
                 'foreign cached later target source before import')
        dispatch = fixed('dispatch_target579', target_folder)
        target_session = dispatch.TargetSession579(config, original=binding,
            root_entry=Path(__file__).resolve())
        entry = target_session
        binding = target_session
    archive = pair(config['archive'])
    main_boot_id = main_closed(data, archive)
    independent_closed(data, archive)
    post = read(data['postpackage_receipt'])
    need(post['source_commit'] == HEAD and post['exit_code'] == 0 and post['failures'] == [] and
         pair(post['archive']) == archive and pair(post['package_receipt']) == pair(config['package_receipt']),
         'all actual new-package input-production stages required')
    native = read(pair(post['au579_native_owner']))
    sdk = read(pair(post['au579_sdk_stage']))
    onset_owner_ref = pair(post['audio_onset579_helper_owner'])
    onset_owner = read(onset_owner_ref)
    need(native['exit_code'] == sdk['exit_code'] == onset_owner['exit_code'] == 0 and
         native['cleanup_verified'] is True and native['owned_container_absent'] is True and
         onset_owner['cleanup_verified'] is True and
         not sdk.get('must_resolve_owned_SDK_processes_before_next_resource_stage'), 'actual AU producers not settled')
    native_proofs = native['native']
    onset_build_ref = dict(path=onset_owner['build_report'], sha256=onset_owner['build_report_sha256'])
    onset_build = read(onset_build_ref)
    helper = onset_build['helpers']['audio_onset_control579']
    onset = dict(schema='audio-onset579-input/v1', helper=dict(binary=record(Path(helper['binary'])),
        build=onset_build_ref, source=pair(helper['source']), production=onset_owner_ref),
        installed_dsos=pair(post['audio_onset579_installed_dsos']))
    profile = dict(path=config['environment']['OHOS_QA_RUNTIME_PROFILE'],
                   sha256=config['environment']['OHOS_QA_RUNTIME_PROFILE_SHA256'])
    checked(profile)
    children = runner.RootReviewedFixedRunner(data['runtime_inputs'])
    entry.connect_children(children)
    from runtime_supplements579 import gap as admit_gap
    registration = admit_gap(children)
    # All additions are finite sources admitted by the sealed production packet;
    # DATA cannot choose a source callback or constructor implementation.
    binding_source = Path(binding.__file__).resolve() if target_session is None else AU / 'target579/dispatch_target579.py'
    for source in (binding_source, seam.HERE / 'au579_production.py'):
        children.policy.sources[str(source)] = record(source)['sha256']
    original_factory = children.suite_function
    need(original_factory.__self__ is children and
         Path(original_factory.__func__.__code__.co_filename).resolve() == K / 'runner377.py',
         'unchanged bound original suite verifier')
    output = Path(output)
    need(output.is_absolute() and output.resolve() == output and output.parent == B and not output.exists(),
         'fresh direct BASE dedicated Audio output')
    report = dict(schema='actual-dedicated-AU579-owner-result/v1', source_commit=HEAD, entry=entry_ref,
        archive=archive, main_boot=data['main_boot'], main_boot_id=main_boot_id, actual_audio_boot=None,
        postpackage_receipt=data['postpackage_receipt'], failures=[], cleanup_verified=False,
        audio_runtime_verified=False, first_artifact_behavior_gate_passed=False, full_audit_passed=False)
    held = {}

    def save():
        if output.is_dir():
            (output / 'audio-owner579.json').write_text(json.dumps(report, indent=2) + '\n')

    def audio_run(args, *, owned_command, owned_guest_factory, owned_select_hook, owned_graphics3d_hook):
        owner = getattr(owned_guest_factory, '__self__', None)
        need(type(owner) is owner_module.Owner and owner.children is children and
             all(getattr(callback, '__self__', None) is owner for callback in
                 (owned_command, owned_select_hook, owned_graphics3d_hook)) and args.package_archive == owner.archive,
             'one original actual Owner and unchanged constructor callbacks')
        held['owner'] = owner
        resources = []
        original_finish = owner.finish

        def finish_original_resources():
            from capability578_stage import UnsettledCapability
            try:
                for io in reversed(resources):
                    if not io._closed:
                        io.close()
            except BaseException as error:
                owner.cleanup_complete = False
                raise UnsettledCapability('Audio inventory IO not settled: ' + str(error)) from error
            return original_finish()

        owner.finish = finish_original_resources
        boot_args = SimpleNamespace(archive=owner.archive, output=owner.output / 'audio-boot', hdc=owner.hdc,
            hdc_port=owner.guest_port, accel=config['environment'].get('QEMU_TEST_ACCEL', 'hvf'),
            resolution='1280x800', purpose='acceptance', kernel_diagnostic=None, power_diagnostic_wakeup=False,
            hold=False, candidate_kernel=None, candidate_kernel_evidence=None, power_button_after_quiet=False,
            wait_seconds=1800, stable_seconds=60, clock_probe=owner_module.descriptor(config['clock_probe']),
            clock_probe_build=owner_module.descriptor(config['clock_probe_build']))
        guest = owned_guest_factory(boot_args).start()
        owner.held_binding(guest)
        need(guest.report['test_environment']['boot_id'] != main_boot_id and
             json.loads((guest.directory / 'build-inputs.json').read_text())['source_git_revision'] == HEAD,
             'actual distinct newly packaged dedicated Audio boot')
        guest.save()
        initial_boot = owner.output / 'audio-initial-boot.json'
        with initial_boot.open('xb') as stream:
            stream.write((guest.args.output / 'boot.json').read_bytes())
        report['initial_audio_boot'] = record(initial_boot)
        save()
        from capability578_owned_io import OwnedIO
        from capability578_https import OwnedHTTPS

        def no_callers(*args, **kwargs):
            raise ValueError('readonly inventory prelude cannot install or build actors')

        if target_session is not None and target_session.target['arch'] == 'armv7a':
            def target_kernel_io(label):
                need(label == 'kernel-prelude', 'single source-fixed actual kernel prelude')
                actual_io = OwnedIO(owner, guest, owner.output / 'kernel-prelude', run_id=secrets.token_hex(16),
                    package_inputs={}, prepare_callers=no_callers, https_factory=OwnedHTTPS)
                resources.append(actual_io)  # before its first actual IO
                return actual_io
            target_session.prepare_kernel(owner, guest, resources=resources,
                create_io=target_kernel_io, root_config_ref=data['owner_config'])
        io = OwnedIO(owner, guest, owner.output / 'inventory-prelude', run_id=secrets.token_hex(16),
            package_inputs={}, prepare_callers=no_callers, https_factory=OwnedHTTPS)
        resources.append(io)
        value, inventory_ref = binding.observe_inventory(io, native['inventory_tool'], profile_ref=profile)
        io.close()
        if target_session is not None:
            value, inventory_ref = target_session.seal_inventory(owner, guest, io=io,
                resources=resources, value=value, ref=inventory_ref)
            report['clock_context'] = target_session.clock_context_ref
        report['inventory'] = inventory_ref
        # Inventory and its real guest cleanup append original boot commands.
        # Seal only after those mutations; signing uses Authority.direct and
        # therefore preserves the original exact boot equality preconditions.
        boot = owner.output / 'audio-case-boot.json'
        with boot.open('xb') as stream:
            stream.write((guest.args.output / 'boot.json').read_bytes())
        report['actual_audio_boot'] = record(boot)
        save()
        actual_onset = onset
        if target_session is not None and target_session.target['arch'] == 'armv7a':
            actual_onset = target_session.onset_input(native_proofs, pair(post['audio_onset579_installed_dsos']))
        onset_path = owner.output / 'onset-input.json'
        with onset_path.open('x') as stream:
            json.dump(actual_onset, stream, indent=2); stream.write('\n')
        signing = binding.sign_on_original_owner(owner, guest, boot_ref=record(boot),
            preparation_ref=sdk['preparation'], sdk_inputs_ref=sdk['sdk_inputs'],
            package_receipt_ref=pair(config['package_receipt']), signer_dist=config['select']['signer_dist'],
            signer_jar=config['select']['signer_jar'], output=owner.output / 'audio-signing')
        inputs = binding.assemble_on_original_owner(owner, guest, boot_ref=record(boot),
            preparation_ref=sdk['preparation'], sdk_inputs_ref=sdk['sdk_inputs'], signing_ref=signing,
            package_receipt_ref=pair(config['package_receipt']), profile_ref=profile,
            threeuid_proof=native_proofs['threeuid'], control_proof=native_proofs['control'],
            inventory_value=value, inventory_ref=inventory_ref, original_inventory_io=io,
            onset_ref=record(onset_path), root_config_ref=data['owner_config'], output=owner.output / 'audio-inputs')
        report['inputs'] = inputs
        save()
        result = entry.run_on_owner(owner, guest, boot=record(boot), preparation=sdk['preparation'],
            inputs=inputs['inputs'], package_receipt=pair(config['package_receipt']), runtime_profile=profile,
            root_config=data['owner_config'], output=owner.output / 'audio-attempt')
        need(result.get('onset579_runtime_verified') is True and result['cleanup_errors'] == [],
             'actual original full Audio lifecycle/onset replay required')
        report['audio_runtime_verified'] = True
        report['audio_result'] = record(owner.output / 'audio-attempt/owner414-result.json')
        save()
        # The original guest is still held here. The unchanged independent AU
        # verifier performs its actual signature/CMS replay through this same
        # Owner; only the later original finish can settle its registration.
        report['gap_registration'] = registration.register_au_on_original_owner(
            owner, guest, dict(report=report['audio_result'], boot=record(boot)),
            output=owner.output / 'audio-gap579-replay')
        save()
        # Raw replay that can invoke an original decoder or crypto child stays
        # inside the original authenticated Runner, while this AU guest/Owner
        # is still held. The later original finish remains the final boundary.
        from runtime_supplements579 import final_raw
        from final_raw579_root import assemble
        integration, _seal = final_raw(children)
        packet_ref = assemble(request=data, archive=archive, au_report=report['audio_result'],
            au_boot=record(boot), output=owner.output / 'final579-packet.json')
        report['final_raw_attempt'] = integration.run_on_original_owner(owner, packet_ref,
            output=owner.output / 'final579-raw')
        save()
        # Original full-suite gate remains false: this is a separate actual AU
        # result which Root must reconcile with the main/Calendar/paired audit.
        return dict(status='dedicated_AU_observed', first_artifact_behavior_gate_passed=False)

    def fixed_factory(original):
        verified = original_factory(original)
        need(verified.__code__ is original.__code__, 'original full-suite verifier body retained')
        return audio_run

    children.suite_function = fixed_factory
    try:
        code = owner_module.run(checked(data['owner_config']), data['owner_config']['sha256'], output, children=children)
        need(code == 1, 'dedicated AU entry must not assert original full-suite acceptance')
        report['original_full_gate_returncode'] = code
    except BaseException as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        owner = held.get('owner')
        if owner is not None and owner.cleanup_complete:
            report['cleanup_verified'] = True
            report['held_processes'] = record(owner.output / 'held-processes.json')
            report['constructor_registry'] = record(owner.output / 'constructors377/registry.json')
            if owner.vm is not None:
                report['final_boot'] = record(owner.vm.args.output / 'boot.json')
        save()
    need(report['audio_runtime_verified'] and report['cleanup_verified'] and not report['failures'],
         'actual dedicated Audio validation or cleanup failed')
    # Freeze this report before the pure final seal takes its Ref. The seal is
    # a separate file and is never appended back to the already hashed input.
    owner_ref = record(output / 'audio-owner579.json')
    from runtime_supplements579 import FINAL
    seal = fixed('final579_seal', FINAL / 'candidate')
    final_ref = seal.finalize(attempt=report['final_raw_attempt'], au_held=report['held_processes'],
        au_constructors=report['constructor_registry'], au_owner_result=owner_ref,
        output=output / 'final579-gate.json')
    final = read(final_ref)
    completion = dict(schema='actual-AU579-and-final579-completion/v1', owner=owner_ref,
        final_gate=final_ref, audio_runtime_verified=True, cleanup_verified=True,
        first_artifact_behavior_gate_passed=final['first_artifact_behavior_gate_passed'])
    with (output / 'audio-completion579.json').open('x') as stream:
        json.dump(completion, stream, indent=2); stream.write('\n')
    return completion


def _actual_target579(archive):
    # Original full AU closure is checked before either canonical import.
    pins = production().au_module('bindings414').verify_sources()
    folder = ROOT / 'ci/capability-audit'
    for source_name in ('batch_system_build_runtime_helpers', 'production579_target'):
        source = folder / (source_name + '.py')
        need(pins.get(str(source)) == record(source)['sha256'],
             'canonical target reader absent from complete actual AU source admission')
        module = fixed(source_name, folder)
        need(Path(module.__file__).resolve() == source and
             pins[str(source)] == record(source)['sha256'], 'changed fixed canonical target reader')
    actual = module.archive_manifest(archive)['context']
    need(actual['product'] in ('arm64_virt', 'armv7a_virt', 'x86_64_virt') and
         actual['device'] in ('phone', '2in1'), 'finite actual AU archive target')
    return actual


def run(data, output, *, entry_ref):
    """Source-fixed actual archive dispatch; the firstphone body is unchanged."""
    need(type(data) is dict and set(data) == FIELDS and
         data['schema'] == 'actual-AU579-fixed-owner/v1' and data['source_commit'] == HEAD,
         'finite current AU request before target selection')
    context = _actual_target579(checked(pair(read(data['owner_config'])['archive'])))
    # This pure fixed-source DATA check precedes either AU Owner/resource body.
    packet_source = fixed('final_raw579_root', Path(__file__).resolve().parent)
    number = packet_source.number_local_refs(data['number_local'])
    need((context['device'] == 'phone' and number is not None) or
         (context['device'] == '2in1' and number is None),
         'actual archive profile requires Number seven refs on phone, None on 2in1')
    if (context['product'], context['device']) == ('arm64_virt', 'phone'):
        return _run_original_arm64_phone579(data, output, entry_ref=entry_ref)
    need(context['product'] in ('arm64_virt', 'armv7a_virt', 'x86_64_virt') and
         context['device'] in ('phone', '2in1'), 'finite actual later-target package')
    return _run_later_targets579(data, output, entry_ref=entry_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--entry-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(args.execute and __debug__, 'explicit ordinary Python -B runtime action')
    request = dict(path=str(args.request), sha256=args.request_sha256)
    source = record(Path(__file__).resolve())
    need(source['sha256'] == args.entry_sha256, 'Root-reviewed entry source')
    result = run(read(request), args.output, entry_ref=source)
    print(json.dumps(dict(audio_runtime_verified=result['audio_runtime_verified'],
                         cleanup_verified=result['cleanup_verified'], final_gate=result['final_gate'],
                         first_artifact_behavior_gate_passed=result['first_artifact_behavior_gate_passed'])))
    return 0 if result['first_artifact_behavior_gate_passed'] is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
