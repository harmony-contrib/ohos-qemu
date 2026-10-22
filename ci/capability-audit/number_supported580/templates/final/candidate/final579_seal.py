"""Pure file/data finalization AFTER original finish. No oracle/child invocation."""
from pathlib import Path
import sys

from final579_contract import HERE, COMMIT, checked, doc, ref, save, need, own_sources


def settlement(held_ref, constructor_ref):
    held, registry = doc(held_ref), doc(constructor_ref)
    root = checked(held_ref).parent
    need(checked(constructor_ref).is_relative_to(root) and not (root / 'quarantine.json').exists(), 'same original output without quarantine')
    need(held['unknown_creation'] is False and held['children'] and all(
        row['reaped'] is True and row['last_signal_boundary'] is True and type(row['exit_code']) is int and
        type(row['pid']) is int and row['pid'] > 0 and row['argv'] for row in held['children']), 'original WNOWAIT Authority did not settle all actual handles')
    need(registry['scope'] == 'actual_root_held_registered_constructor_tree_ONLY' and not registry['failures'] and
        any(row.get('event') == 'constructor_finalization' and row.get('all_actual_registered_groups_closed') is True
            for row in registry['events']) and all(row['closed'] is True for row in registry['docker_operations']),
        'original Runner actual constructor/Docker finalization missing or failed')
    for handle in registry['handles'].values():
        matches = [row for row in held['children'] if row['pid'] == handle['pid'] and
            row['argv'] == handle['original_argv'] and
            (handle['returncode'] is None or handle['returncode'] == row['exit_code'])]
        need(matches,
            'original constructor handle/final held exit identity differs')
    # Original Runner.finalize may close a deliberately retained server group
    # through Authority.close_group without inventing a prior wait/actor_done.
    # Its actual reaped signal boundary is the resource fact. Expected exits
    # and terminated service semantics belong to the corresponding raw oracle.
    return dict(root=str(root), held=held_ref, constructors=constructor_ref,
        original_authority_settled=True, original_constructor_tree_settled=True)


def two(value):
    checked(value)
    return {key: value[key] for key in ('path', 'sha256')}


def independent_settlements(packet):
    """Read real final Owner reports, never a pre-finish business-held cut.

    The actual Network/GNSS source writes these reports after original finish.
    All resource facts are independently bound to final held/constructor raw.
    No raw oracle, process, decoder, transport or resource constructor is called.
    """
    reports = packet['independent_owners']
    need(type(reports) is dict and set(reports) == {'network', 'gnss'}, 'two fixed independent owners')
    result = {}
    for name in ('network', 'gnss'):
        row = reports[name]
        need(type(row) is dict and set(row) == {'report', 'held', 'constructors'} and
            all(type(item) is dict and set(item) == {'path', 'sha256'} for item in row.values()),
            'exact independent final report/held/constructors Ref2 only')
        closure = settlement(row['held'], row['constructors'])
        root = Path(closure['root'])
        report = doc(row['report'])
        need(checked(row['report']) == root / ('dedicated406.json' if name == 'network' else 'GNSS579-RESULT.json'),
            'fixed actual original owner final report path')
        actual_api = packet['api'][name]
        need(actual_api is None or (type(actual_api) is dict and set(actual_api) ==
            ({'retained', 'boot', 'protocol'} if name == 'network' else {'retained', 'boot'})),
            'original finite independent API raw refs')
        if name == 'network':
            dedicated_ref, dedicated = row['report'], report
            case_result = dedicated.get('case_result')
            attached = case_result.get('api26_network') if type(case_result) is dict else None
            if actual_api is not None:
                need(type(attached) is dict and set(attached) == set(actual_api) and
                    {key: two(item) for key, item in attached.items()} == actual_api and
                    doc(case_result['api26_network_index']) == attached,
                    'actual final Network case must bind exactly the supplied three raw refs')
        else:
            need(report['schema'] == 'gnss579-original-owner-result/v1' and
                type(report['exit_code']) is int and report['cleanup_verified'] is True and
                type(report['failures']) is list, 'actual completed GNSS final result required')
            attached = report['actual']
            if actual_api is not None:
                need(type(attached) is dict and set(attached) == set(actual_api) and
                    {key: two(item) for key, item in attached.items()} == actual_api,
                    'actual completed GNSS result must bind exactly its retained/boot refs')
            dedicated_ref = report['dedicated']
            need(checked(dedicated_ref) == root / 'dedicated-gnss579.json', 'actual original GNSS dedicated report')
            dedicated = doc(dedicated_ref)
        need(report['source_commit'] == dedicated['source_commit'] == COMMIT and
            dedicated['resources_executed'] is True and dedicated['cleanup_verified'] is True and
            type(dedicated['exit_code']) is int and type(dedicated['failures']) is list and
            dedicated['first_artifact_behavior_gate_passed'] is False,
            'actual independent final source/Owner.finish records required')
        need(two(dedicated['held_processes']) == row['held'] and
            two(dedicated['constructors']) == row['constructors'], 'actual post-finish closure differs')
        if actual_api is not None:
            need(two(dedicated['case_boot']) == actual_api['boot'], 'actual API/case boot differs')
        case, final = doc(dedicated['case_boot']), doc(dedicated['final_boot'])
        need(checked(dedicated['case_boot']).is_relative_to(root) and
            checked(dedicated['final_boot']) == checked(dedicated['case_boot']).parent / 'boot.json' and
            case['archive_sha256'] == final['archive_sha256'] == packet['archive']['sha256'] and
            case['purpose'] == 'acceptance' and
            case['test_environment']['external_keepalive'] is False and
            all(case['test_environment'][key] == final['test_environment'][key]
                for key in ('boot_id', 'udid', 'target', 'guest_arch', 'device_type', 'product')),
            'actual final independent boot does not belong to its original case/archive')
        # A completed cleanup permits the next serial AU attempt. It cannot
        # convert failed business, missing raw, bad final health, or restoration
        # into a pass. Preserve those values and failures as final-gate failures.
        business = []
        def observe(label, value, expected):
            same = value is expected if expected is True or expected is False or expected is None else (
                type(value) is type(expected) and value == expected)
            if not same:
                business.append(dict(observation=label, actual=value, expected=expected))
        observe('dedicated.status', dedicated.get('status'), 'pass_dedicated_narrow_chain_ONLY')
        observe('dedicated.exit_code', dedicated['exit_code'], 0)
        observe('dedicated.original_full_gate_returncode', dedicated.get('original_full_gate_returncode'), 1)
        observe('dedicated.failures', dedicated['failures'], [])
        setup = dedicated.get('application_test_setup')
        observe('dedicated.application_test_setup.restored', setup.get('restored') if type(setup) is dict else None, True)
        observe('case_boot.status', case.get('status'), 'pass')
        observe('final_boot.status', final.get('status'), 'pass')
        if actual_api is None:
            business.append(dict(observation='actual_api', actual=None, expected='original finite raw refs'))
        if name == 'gnss':
            observe('result.exit_code', report['exit_code'], 0)
            observe('result.original_owner_full_gate_returncode', report.get('original_owner_full_gate_returncode'), 1)
            observe('result.failures', report['failures'], [])
        result[name] = dict(report=row['report'], dedicated=dedicated_ref, actual_api=actual_api,
            case_boot=two(dedicated['case_boot']), final_boot=two(dedicated['final_boot']),
            boot_id=case['test_environment']['boot_id'], settlement=closure, business_failures=business)
    need(result['network']['settlement']['root'] != result['gnss']['settlement']['root'] and
        result['network']['boot_id'] != result['gnss']['boot_id'], 'independent owners/boots cannot be aliased')
    return result


def independent_business_failures(independent):
    return [dict(stage='original-independent-owner/' + name, detail=row)
        for name in ('network', 'gnss') for row in independent[name]['business_failures']]


def finalize(*, attempt, au_held, au_constructors, au_owner_result, output):
    """Read actual final proof + original final closure; never replay host tools.

    Root calls only after original AU Owner.finish/Authority.finish returned.
    A failed raw actor remains a failed global gate even when disposal succeeds.
    """
    source_vector = own_sources()
    actual = doc(attempt)
    need(actual['schema'] == 'actual-final579-original-owner-actor-attempt/v1' and
        actual['source_vector'] == source_vector, 'fixed actual final actor attempt/source')
    packet = doc(actual['packet'])
    result = doc(actual['result'])
    attempt_root = checked(attempt).parent
    expected_argv = [sys.executable, '-B', str(HERE / 'final579_actor.py'),
        '--packet', actual['packet']['path'], '--packet-sha256', actual['packet']['sha256'],
        '--output', str(attempt_root / 'raw')]
    need(actual['command']['argv'] == expected_argv and
        checked(actual['result']) == attempt_root / 'raw/result.json' and
        Path(actual['command']['log']) == attempt_root / 'actor.log' and
        attempt_root.is_relative_to(Path(actual['owner_output'])),
        'fixed actual actor argv/packet/output association')
    need(result['packet'] == actual['packet'] and result['source_vector'] == source_vector and
        result['first_artifact_behavior_gate_passed'] is False and result['owner_finish_still_required'] is True,
        'actor cannot seal the first package gate')
    need(ref(Path(actual['command']['log']))['sha256'] == actual['command']['sha256'], 'actual actor command log changed')
    closure = settlement(au_held, au_constructors)
    main = settlement(packet['main_settlement']['held'], packet['main_settlement']['constructors'])
    independent = independent_settlements(packet)
    need(result.get('independent_owners') == independent, 'actual actor independent final Owner replay changed')
    need(len({closure['root'], main['root'], independent['network']['settlement']['root'],
        independent['gnss']['settlement']['root']}) == 4, 'main/AU/Network/GNSS require four actual Owner roots')
    need(len({doc(packet['main_boot'])['test_environment']['boot_id'],
        doc(packet['au']['boot'])['test_environment']['boot_id'], independent['network']['boot_id'],
        independent['gnss']['boot_id']}) == 4, 'four actual fresh owning boot identities required')
    need(closure['root'] != main['root'] and Path(actual['owner_output']) == Path(closure['root']), 'independent dedicated AU original Owner required')
    registry, held = doc(au_constructors), doc(au_held)
    actor = registry['actors'][actual['actor_id']]
    need(actor['entry'] == str(HERE / 'final579_actor.py') and actor['argv'] == actual['command']['argv'] and
        actor['pid'] == actual['pid'] and actor['parent'] == 'root-final579-raw' and
        actor['started'] is True and actor['done'] is True, 'actual fixed final actor identity/argv/scope')
    handles = [row for row in registry['handles'].values() if row['actor'] == actual['actor_id']]
    need(len(handles) == 1 and handles[0]['returncode'] == actual['command']['exit_code'] and
        handles[0]['pid'] == actual['pid'], 'actual final actor exit mismatch')
    owner = doc(au_owner_result)
    need(owner['schema'] == 'actual-dedicated-AU579-owner-result/v1' and owner['cleanup_verified'] is True and
        owner['audio_runtime_verified'] is True and owner['held_processes'] == au_held and
        owner['audio_result'] == packet['au']['report'], 'original dedicated AU/finish record differs')
    final_boot, case_boot, main_boot = (doc(value) for value in (owner['final_boot'], packet['au']['boot'], packet['main_boot']))
    need(final_boot['archive_sha256'] == case_boot['archive_sha256'] == packet['archive']['sha256'] and
        final_boot['test_environment']['boot_id'] == case_boot['test_environment']['boot_id'] != main_boot['test_environment']['boot_id'],
        'actual AU final/case boot association; no main-boot relabel')
    failures = list(result['failures']) + [dict(stage='original-AU-owner', detail=row) for row in owner['failures']]
    for row in independent_business_failures(independent):
        if row not in failures:
            failures.append(row)
    # Recheck the additional original Number closure independently of the four
    # existing core roots; neither source completion nor release-scope filtering
    # can turn its missing local business proof into a gate pass.
    number_local = None
    try:
        from final579_families import replay_number_local580
        number_local = replay_number_local580(packet)
        observed_number = result['families']['number-local']
        need(doc(observed_number['proof']) == number_local,
             'completed independent Number replay changed after the actor')
        if number_local['applicable']:
            proof = number_local['replay']
            roots = {closure['root'], main['root'], independent['network']['settlement']['root'],
                     independent['gnss']['settlement']['root']}
            boots = {doc(packet['main_boot'])['test_environment']['boot_id'],
                     doc(packet['au']['boot'])['test_environment']['boot_id'],
                     independent['network']['boot_id'], independent['gnss']['boot_id']}
            need(proof['owner']['root'] not in roots and not set(proof['two_boot_ids']) & boots,
                 'Number requires its own actual Owner output and distinct controlled kernel boots')
    except Exception as error:
        failures.append(dict(stage='independent-number-local', error=type(error).__name__ + ': ' + str(error)))
    union = result.get('fullledger')
    baseline = result.get('baseline')
    if baseline is None:
        failures.append(dict(stage='final-baseline', error='actual original mandatory/raw baseline was not rebuilt'))
        required, mandatory = set(), {}
    else:
        required = set(baseline['required'])
        mandatory = baseline['mandatory']
        need(set(mandatory) == required - {'cxx-arkts11-gaps'}, 'original nonledger mandatory membership changed')
    if union is not None:
        need(baseline is not None and baseline['original_ledger'] is not None,
            'a union cannot replace the missing actual complete original baseline')
        from final579_union import collect as pure_union
        maps = dict(result['families'])
        maps['media'] = dict(registrations=baseline['media']['registrations'], failures=baseline['media']['failures'])
        rebuilt = pure_union(baseline['original_ledger'], maps, baseline['environment'])
        need(union == rebuilt, 'actual fixed union data changed after raw actor replay')
    for name, row in mandatory.items():
        if row.get('original_oracle_replayed') is not True:
            failures.append(dict(stage='final-mandatory/' + name, error='original actual oracle did not replay'))
        elif row['evidence'] is not None:
            checked(row['evidence'])
    complete = bool(union and union['obligation_complete'] is True and not union['effective_unresolved'] and
        not union['failures'] and not failures and actual['command']['exit_code'] == 0 and
        result['status'] == 'raw_union_complete_pending_original_owner_finish')
    report = dict(schema='actual-final579-global-raw-gate/v1', packet=actual['packet'],
        original_main_suite=packet['main_suite'], original_main_attempt=packet['main_attempt'],
        original_main_failures=list(doc(packet['main_suite'])['failures']), raw_actor_attempt=attempt,
        raw_actor_result=actual['result'], final_au_owner=au_owner_result,
        main_settlement=main, audio_settlement=closure, independent_owner_settlement=independent, fullledger=union,
        number_local_mandatory_replay=number_local,
        failures=failures, source_vector=source_vector,
        status='pass' if complete else 'fail', first_artifact_behavior_gate_passed=complete,
        statement='the completed fixed raw union, all four original final resource closures and every applicable independent local Number obligation must seal this archive')
    # This is the only conditional true in the new final interface. It follows
    # original finish and actual raw proofs; source/actor completion alone cannot.
    return save(Path(output), report)
