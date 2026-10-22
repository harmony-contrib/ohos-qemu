"""Pure exact-scope union. It never promotes slices or changes original reports."""
from final579_contract import ORIGINAL, PHOTOS_2IN1, ref, doc, need


def collect(original, families, environment):
    need(type(original) is dict, 'one actual original complete ledger replay required')
    expected = set(original['closed']) | {row['id'] for row in original['unresolved']}
    closed, additions, failures, parallel = dict(original['closed']), {}, [], {}
    for family, result in families.items():
        failures.extend(dict(stage='registration/' + family, detail=item) for item in result['failures'])
        for identifier, proof in result['registrations'].items():
            need(identifier in expected, 'registration outside immutable expected IDs: ' + identifier)
            if identifier in closed:
                if family == 'api' and proof.get('source') in (
                        'original registered typed non-function oracle',
                        'original independently verified screen-blink typed function'):
                    need(proof['proof'] == original['closed'][identifier], 'API non-function proof differs from original complete typed oracle')
                if 'archive_sha256' in proof:
                    need(proof['archive_sha256'] == original['archive_sha256'], 'different archive in additional complete raw proof')
                parallel.setdefault(identifier, []).append(dict(family=family, proof=proof))
                # Both inputs were obtained by fixed independent raw oracles.
                # Keep the base proof verbatim and attach the second proof; no
                # existing ID or early failure is overwritten or cleared.
            else:
                closed[identifier] = proof
                additions[identifier] = dict(family=family, proof=proof)
    provider_obligations = families.get('provider')
    need(provider_obligations is not None, 'fixed provider raw action must run')
    pending_provider = list(provider_obligations['unresolved'])
    need(provider_obligations['required_obligations_complete'] is (not pending_provider and not provider_obligations['failures']),
        'provider completion cannot be inferred from whole-ID registration elsewhere')
    networking_obligations = families.get('networking')
    need(networking_obligations is not None, 'fixed original nine Networking raw action must run')
    pending_networking = list(networking_obligations['unresolved'])
    need(networking_obligations['required_obligations_complete'] is
        (not pending_networking and not networking_obligations['failures']),
        'whole original Networking completion cannot come from typed/provider registered status')
    telephony_obligations = families.get('telephony')
    need(telephony_obligations is not None,'fixed original full telephony supported raw action must run')
    pending_telephony = list(telephony_obligations['unresolved'])
    need(telephony_obligations['required_obligations_complete'] is
        (not pending_telephony and not telephony_obligations['failures']),
        'L22 cannot close from another family without complete modem/RTT/5A supported obligations')
    msdp_obligations = families.get('msdp')
    need(msdp_obligations is not None,'fixed original nine-modality supported raw action must run')
    pending_msdp = list(msdp_obligations['unresolved'])
    need(msdp_obligations['required_obligations_complete'] is
        (not pending_msdp and not msdp_obligations['failures']),
        'S08 cannot close from another family without its complete supported framework and provider obligations')
    local_number = families.get('number-local')
    need(local_number is not None, 'independent supported-local Number family must run')
    local_number_required = environment['device_type'] == 'phone'
    pending_number = []
    if local_number_required:
        if (local_number.get('local_id') != 'number580:phone-supported-local' or
                local_number.get('applicable') is not True or
                local_number.get('required_local_obligations_complete') is not True or
                local_number.get('failures')):
            pending_number.append('number580:phone-supported-local')
    else:
        need(local_number.get('applicable') is False,
             'independent local Number applicability follows actual device profile')
    profile = {}
    if environment['device_type'] == 'phone' and PHOTOS_2IN1 in expected:
        ledger = doc(ref(ORIGINAL))
        matches = [row for row in ledger['requirements'] if row['id'] == PHOTOS_2IN1]
        need(len(matches) == 1 and matches[0]['assessment']['work_package'] == 'photos' and
            '首ARM64 phone后仍需2in1独立画像接受' in matches[0]['assessment']['next_required'],
            'only the original exact 2in1 Photos whole-provider requirement is profile-specific')
        profile[PHOTOS_2IN1] = dict(disposition='not_applicable_to_phone_whole_provider_only',
            original_requirement=matches[0], original_ledger=ref(ORIGINAL),
            later_true_2in1_required=True, counts_as_fixed=False, counts_as_runtime_pass=False,
            phone_Knowledge_Photos_data_permission_slices_still_required=True)
    applicable = expected - set(profile)
    effective_closed = {identifier: proof for identifier, proof in closed.items() if identifier in applicable}
    unresolved = [row for row in original['unresolved'] if row['id'] in applicable and row['id'] not in closed]
    return dict(original_replay=original, fixed_registrations=additions, parallel_verified_replays=parallel, effective_closed=effective_closed,
        effective_unresolved=unresolved, profile_dispositions=profile,
        original_expected_count=len(expected), actual_applicable_count=len(applicable),
        actual_unresolved_count=len(unresolved), actual_registered_count=len(set(closed) & applicable),
        policy_dispositions=original['release_exclusions'],
        policy_meaning='original exact user-authorized unsupported/excluded source scope; never fixed or runtime pass',
        unresolved_provider_obligations=pending_provider, unresolved_networking_obligations=pending_networking,
        unresolved_telephony_obligations=pending_telephony, unresolved_msdp_obligations=pending_msdp,
        unresolved_number_local_obligations=pending_number,
        failures=failures, obligation_complete=not unresolved and not failures and not pending_provider and not pending_networking and not pending_telephony and not pending_msdp and not pending_number,
        runtime_pass=False, first_artifact_behavior_gate_passed=False)
