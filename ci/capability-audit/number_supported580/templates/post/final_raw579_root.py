"""Root-only assembly of actual closed-main and held-AU raw DATA.

No oracle, parser child, VM, SDK, signer, lease or resource owner is created.
The final fixed actor performs all semantic replay under the original AU Owner.
"""
from pathlib import Path
import json

from au579_sources import checked, need, record

HEAD = '67765265103a932b9a562face76a882f07bed3e3'


def two(value):
    return {key: value[key] for key in ('path', 'sha256')}


def document(value):
    return json.loads(checked(two(value)).read_text())


NUMBER_LOCAL_KEYS580 = {'owner_report', 'corpus', 'owner_closure', 'command_attempt',
                        'config', 'spec', 'observer_proof'}


def number_local_refs(value):
    """Preserve complete actual Number DATA; semantic replay stays in final actor."""
    if value is None:
        return None
    need(type(value) is dict and set(value) == NUMBER_LOCAL_KEYS580,
         'exact seven completed original Number refs required')
    result = {}
    for name, item in value.items():
        need(type(item) is dict and set(item) == {'path', 'sha256', 'bytes'} and
             type(item['bytes']) is int and item['bytes'] >= 0,
             'Number raw keeps exact Ref3 with integer byte count')
        source = checked(two(item))
        need(source.stat().st_size == item['bytes'], 'actual Number raw byte count differs')
        result[name] = dict(item)
    return result


def assemble(*, request, archive, au_report, au_boot, output):
    attempt_ref = two(request['main_attempt'])
    attempt = document(attempt_ref)
    need(attempt['schema'] == 'actual-main579-command-attempt/v1',
         'actual external main launch receipt required')
    settlement = dict(held=two(request['main_held_processes']),
                      constructors=two(request['main_constructor_registry']))
    need(attempt['settlement'] == settlement and attempt['boot'] == two(request['main_boot']),
         'actual independent main exit receipt and closed resource refs differ')
    main_root = checked(settlement['held']).parent
    suite_ref = two(attempt['suite'])
    suite = document(suite_ref)
    work = Path(suite['work'])
    need(work.is_absolute() and work.resolve() == work and work.is_relative_to(main_root) and
         checked(suite_ref) == main_root / 'full-suite.json' and
         checked(two(request['main_boot'])) == work / 'boot/boot.json',
         'actual original main work and final boot must be retained')
    calendar_summary = document(record(main_root / 'calendar579-after-main.json'))
    resource_ref = two(calendar_summary['report'])
    resource = document(resource_ref)
    phase1, phase2 = two(resource['phase1']), two(resource['phase2'])
    need(suite['supplemental_checks']['calendar579-phase1']['evidence'] == phase1,
         'actual original phase1 differs from the resource transition')
    transition = document(phase2)['resource_transition']
    need(two(transition['phase1']) == phase1,
         'actual second Calendar phase belongs to another first phase')
    calendar = dict(phase1=phase1, phase2=phase2,
        first_boot=two(transition['first_boot']),
        second_boot=record(checked(resource_ref).parent / 'boot/boot.json'),
        resource_report=resource_ref)
    live_ref = record(main_root / 'paired579-live-proof/evidence.json')
    live = document(live_ref)
    pair_ref = two(live['paired_report'])
    api_binding = document(record(main_root / 'api26-main579-binding.json'))
    network, gnss = request['api_network'], request['api_gnss']
    need((network is None or (type(network) is dict and set(network) == {'retained', 'boot', 'protocol'})) and
         (gnss is None or (type(gnss) is dict and set(gnss) == {'retained', 'boot'})),
         'finite actual original independent Network and GNSS raw inputs')
    for value in (*(network or {}).values(), *(gnss or {}).values(), *calendar.values()):
        checked(two(value))
    owners = request['independent_owners']
    need(type(owners) is dict and set(owners) == {'network', 'gnss'},
         'actual independent final owner settlement records required')
    for group in owners.values():
        need(type(group) is dict and set(group) == {'report', 'held', 'constructors'},
             'finite original independent owner records')
        for row in group.values():
            checked(two(row))
    history = request['earlier_attempts']
    need(type(history) is list, 'actual prior evidence refs only')
    for value in history:
        checked(two(value))
    value = dict(schema='actual-final579-root-packet/v1', source_commit=HEAD,
        archive=two(archive), main_suite=suite_ref, main_boot=two(request['main_boot']),
        main_attempt=attempt_ref, runtime_root=str(work), main_settlement=settlement,
        independent_owners={name: {key: two(row) for key, row in group.items()}
            for name, group in owners.items()},
        system_index=record(main_root / 'system579-semantic-index.json'), calendar=calendar,
        api=dict(kind='raw_assembly', main_index=two(api_binding['main_index']),
            surface=record(work / 'arkts-exports/evidence.json'),
            network={key: two(row) for key, row in network.items()} if network is not None else None,
            gnss={key: two(row) for key, row in gnss.items()} if gnss is not None else None),
        paired=dict(report=pair_ref, live_proof=live_ref),
        au=dict(report=two(au_report), boot=two(au_boot)),
        audio_source_manifest=two(request['audio_source_manifest']),
        earlier_attempts=[two(row) for row in history],
        number_local=number_local_refs(request['number_local']))
    output = Path(output)
    with output.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
    return record(output)
