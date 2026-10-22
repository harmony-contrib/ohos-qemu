"""Pure DATA assembly for four supplemental callers; SDK17 is unchanged."""
from pathlib import Path
from audio579_common import ROOT, HERE, OWN, need, ref, checked, doc, save, source_guard


def assemble_audio(export_ref, *, package, target, native):
    value = doc(export_ref)
    need(set(value) == {'schema', 'source_commit', 'archive', 'source_export', 'installed_runtime_profile',
         'midi_headers', 'midi_library', 'graphics3d', 'normal_source_context', 'provider_facts'} and value['schema'] == 'media579-actual-product-input-export/v1' and
         value['source_commit'] == package['source_commit'] and value['archive'] == package['archive'],
         'one fixed original media product export, never a code/ID/role selection')
    context = doc(source_guard(value['normal_source_context']))
    need(context['source_commit'] == package['source_commit'], 'normal source production must use this real new package Head')
    source = doc(value['source_export'])
    need(source['source_kind'] == 'actual_shared_source_and_out_readonly_export' and
         source['source_commit'] == package['source_commit'] and source['archive_sha256'] == package['archive']['sha256'] and
         source['product'] == target['product'] and source['resources_executed'] is True and
         source['cleanup_verified'] is True and source['failures'] == [],
         'actual original Root source/out export must complete, including original resource cleanup')
    need(set(value['midi_headers']) == {'midi/native_midi.h', 'midi/native_midi_base.h'}, 'two actual public MIDI headers')
    for name, row in value['midi_headers'].items():
        checked(row)
        need(source['files']['foundation/multimedia/midi_framework/interfaces/kits/c/' + name]['sha256'] == row['sha256'],
             'public header belongs to real same-package source export')
    checked(value['midi_library']); profile = doc(value['installed_runtime_profile'])
    from batch_system_build_runtime_helpers import validate_installed_profile
    validate_installed_profile(profile, archive_sha256=package['archive']['sha256'])
    need(profile['product'] == target['product'] and profile['arch'] == target['arch'] and profile['device'] == target['device'] and
         profile['dsos']['libohmidi.so']['image_file']['sha256'] == value['midi_library']['sha256'],
         'actual installed C API library, not another product or a host SDK substitute')
    graphics = doc(value['graphics3d'])
    need(graphics['schema'] == 'media579-graphics3d-actual-product/v1' and
         graphics['source_commit'] == package['source_commit'] and graphics['archive_sha256'] == package['archive']['sha256'] and
         graphics['source_export'] == value['source_export'] and graphics['installed_runtime_profile'] == value['installed_runtime_profile'],
         'same original complete product Graphics3D provenance, not extracted host functions')
    provider = doc(value['provider_facts'])
    need(provider['schema'] == 'media579-actual-provider-facts-not-policy/v1' and
         provider['source_commit'] == package['source_commit'] and provider['archive']['sha256'] == package['archive']['sha256'] and
         provider['source_export'] == value['source_export'] and provider['unsupported_policy_decision'] is None,
         'full same actual provider DATA; no source-derived unsupported/acceptance flag')
    need(type(provider['provider_inventory']) is list and provider['provider_inventory'] and provider['actual_image_facts'],
         'preserve complete provider inventory and independently dumped image facts')
    alsa = native['apps_paired579_alsa']
    for key in ('binary', 'build'): checked(alsa[key])
    return dict(schema='media579-audio-product-inputs/v1', source_commit=package['source_commit'],
        archive=package['archive'], arch=target['arch'], source_export=value['source_export'],
        installed_runtime_profile=value['installed_runtime_profile'], midi_headers=value['midi_headers'],
        midi_library=value['midi_library'], graphics3d=value['graphics3d'], alsa_inject=alsa,
        normal_source_context=value['normal_source_context'], provider_facts=value['provider_facts'])


def produce_normal_source_context(*, kit, normal_source, output):
    """Root normal source-production step; no SDK, parser test or acceptance.

    Write only after the real new Head/Kit/SOURCE exist. No field is inferred
    from this candidate's authoring base. Future source commits require genuine
    normal production and a new complete canonical snapshot, not a guard SHA edit.
    """
    normal, manifest = doc(normal_source), doc(kit)
    snapshot_ref = {key: normal['canonical_snapshot'][key] for key in ('path', 'sha256')}
    snapshot = doc(snapshot_ref)
    need(normal['source_commit'] == snapshot['source_commit'] and
         {key: normal['source_kit_manifest'][key] for key in ('path', 'sha256')} == kit,
         'actual normal SOURCE and complete real Kit identity')
    root = checked(kit).parent
    runtime = ref(root / 'SOURCES377.json')
    members = {row['path']: row for row in manifest['members']}
    need(members['SOURCES377.json']['sha256'] == runtime['sha256'], 'complete current runtime source vector')
    canonical = {row['path']: row['sha256'] for row in snapshot['files']}
    from usb579_contract import OWN as USB579_OWN
    own = []
    for path in [HERE / name for name in OWN] + [ROOT / 'ci/capability-audit' / name for name in USB579_OWN]:
        need(path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / '.tmp'), 'Root must first adopt these production sources')
        row = ref(path)
        need(canonical.get(str(path.relative_to(ROOT))) == row['sha256'], 'actual new Head snapshot must contain this entire new producer')
        own.append(row)
    output = Path(output)
    need(output.is_absolute() and output.is_relative_to(ROOT / '.tmp') and output.name == 'audio579-SOURCE-CONTEXT.json' and
         output.parent.is_dir() and not output.exists(), 'one fresh normal source-production DATA file outside canonical source')
    return save(output, dict(schema='audio579-normal-supplemental-source-context/v1',
        source_commit=normal['source_commit'], kit=kit, normal_source=normal_source,
        snapshot=snapshot_ref, runtime_sources=runtime, files=own,
        separate_from_original_SDK17_batch=True, source_only=True,
        runtime_pass=False, first_artifact_behavior_gate_passed=False))
