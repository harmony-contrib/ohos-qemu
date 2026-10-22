#!/usr/bin/env python3
"""Original-Runner authenticated final raw actor. Never seals the global gate."""
from pathlib import Path
import argparse
import json
import sys

from final579_contract import (ROOT, HERE, ORIGINAL, CXX, checked, doc, ref, save, need,
    packet as validate_packet, own_sources, actor_context, audio_sources)
import final579_baseline as baseline_module
import final579_families as family
import final579_union as union_module
from final579_seal import settlement, independent_settlements, independent_business_failures


def caption_family(packet, output):
    # Root admits the complete fixed final source vector before actor launch.
    # This is one fixed original ID/raw decoder, never a DATA-selected module.
    from final579_contract import fixed
    return fixed('caption579_registration', HERE / 'caption579').register_family(packet, output)


def networking_family(packet, output, *, replayed=None):
    from final579_contract import fixed
    return fixed('networking579_registration', HERE / 'networking579').register_family(packet, output, replayed=replayed)


def replay(packet_ref, output):
    actor = actor_context()
    packet = validate_packet(doc(packet_ref))
    audio_sources(packet['audio_source_manifest'], actor=actor)
    result = dict(schema='actual-final579-admitted-raw-actor/v1', packet=packet_ref,
        source_vector=own_sources(), archive=packet['archive'], baseline=None, families={},
        fullledger=None, retained_earlier_attempts=[], failures=[], status='raw_incomplete_or_failed',
        actual_applicable_count=None, actual_unresolved_count=None, actual_registered_count=None,
        owner_finish_still_required=True, runtime_pass=False, first_artifact_behavior_gate_passed=False)
    target = output / 'result.json'
    def persist():
        # Root reads the Ref only after this actor exits. The final immutable
        # hash belongs to the real completed actor attempt, not an early write.
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    def failure(stage, error):
        result['failures'].append(dict(stage=stage, error=type(error).__name__ + ': ' + str(error)))
        persist()
    persist()
    for row in packet['earlier_attempts']:
        value = doc(row)
        result['retained_earlier_attempts'].append(dict(evidence=row,
            status=value.get('status'), exit_code=value.get('exit_code'),
            failures=value.get('failures', value.get('errors')), counts_as_current_pass=False))
    try:
        result['independent_owners'] = independent_settlements(packet)
        result['failures'].extend(independent_business_failures(result['independent_owners']))
    except Exception as error:
        failure('independent-owner-final-settlement', error)
    try:
        result['main_settlement'] = settlement(packet['main_settlement']['held'], packet['main_settlement']['constructors'])
        need(checked(packet['main_suite']).is_relative_to(Path(result['main_settlement']['root'])) and
            checked(packet['main_boot']).is_relative_to(Path(result['main_settlement']['root'])), 'main original source/output identity')
        result['baseline'] = baseline_module.collect(packet)
        result['failures'].extend(result['baseline']['failures'])
        need(result['baseline']['main_attempt'] is not None and result['baseline']['deferred'] is not None,
            'actual full main launch and unique original ledger obligation were not reconstructed')
        result['original_main_attempt'] = packet['main_attempt']
    except Exception as error:
        failure('original-main-admission', error)
    actions = [('number-local', family.number_local580), ('system', family.system), ('calendar', family.calendar), ('audio', None), ('paired', family.paired), ('services', None), ('msdp', None), ('api', None), ('telephony', None), ('photos', None), ('media-whole', None), ('apps-additional', None), ('caption', caption_family), ('apps', None), ('provider', None), ('networking', networking_family)]
    for name, function in actions:
        directory = output / name
        directory.mkdir()
        try:
            if name == 'audio':
                observed = family.audio(packet, directory, actor)
            elif name == 'media-whole':
                observed = family.media_whole(packet, directory, actor)
            elif name == 'telephony':
                observed = family.telephony(packet, directory, actor)
            elif name == 'photos':
                observed = family.photos(packet, directory, actor)
            elif name == 'apps-additional':
                observed = family.apps_additional(packet, directory, actor)
            elif name == 'apps':
                observed = family.apps(packet, directory, actor)
            elif name == 'provider':
                need(result['baseline'] is not None and result['baseline']['original_ledger'] is not None, 'provider requires actual immutable original ledger base')
                observed = family.provider(packet, result['baseline']['original_ledger'], directory, actor, replayed=result['families'])
            elif name == 'services':
                observed = family.services(packet, directory, actor, result['families'])
            elif name == 'msdp':
                observed = family.msdp(packet, directory, actor, result['families'])
            elif name == 'api':
                need(result['baseline'] is not None and result['baseline']['original_ledger'] is not None, 'API needs actual complete original ledger base')
                observed = family.api(packet, result['baseline']['original_ledger'], directory)
            elif name == 'networking':
                observed = function(packet, directory, replayed=result['families'])
            else:
                observed = function(packet, directory)
            result['families'][name] = observed
            result['failures'].extend(dict(stage='raw-family/' + name, detail=item) for item in observed['failures'])
        except Exception as error:
            result['families'][name] = dict(registrations={}, failures=[dict(type=type(error).__name__, error=str(error))],
                source_dependency_pending='pending' in str(error).lower())
            failure('raw-family/' + name, error)
        persist()
    base = result['baseline']
    if base is not None and base['original_ledger'] is not None:
        try:
            maps = dict(result['families'])
            maps['media'] = dict(registrations=base['media']['registrations'], failures=base['media']['failures'])
            full = union_module.collect(base['original_ledger'], maps, base['environment'])
            result['fullledger'] = full
            for key in ('actual_applicable_count', 'actual_unresolved_count', 'actual_registered_count'):
                result[key] = full[key]
            result['obligation_name'] = CXX
            if full['obligation_complete'] and not result['failures'] and base['deferred'] is not None:
                result['status'] = 'raw_union_complete_pending_original_owner_finish'
        except Exception as error:
            failure('complete-original-ledger-union', error)
    persist()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--packet-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packet_ref = dict(path=str(args.packet), sha256=args.packet_sha256)
    checked(packet_ref)
    need(args.output.is_absolute() and args.output.resolve() == args.output and not args.output.exists(), 'fresh fixed original Owner actor output')
    args.output.mkdir(mode=0o700)
    try:
        result = replay(packet_ref, args.output)
    except BaseException as error:
        result = dict(schema='actual-final579-admitted-raw-actor/v1', packet=packet_ref,
            source_vector=own_sources(), baseline=None, families={}, fullledger=None,
            actual_applicable_count=None, actual_unresolved_count=None, actual_registered_count=None,
            status='raw_incomplete_or_failed', owner_finish_still_required=True,
            failures=[dict(stage='actor-admission', error=type(error).__name__ + ': ' + str(error))],
            runtime_pass=False, first_artifact_behavior_gate_passed=False)
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'actual_applicable_count', 'actual_unresolved_count',
        'actual_registered_count', 'first_artifact_behavior_gate_passed')}))
    return 0 if result['status'] == 'raw_union_complete_pending_original_owner_finish' else 1


if __name__ == '__main__':
    raise SystemExit(main())
