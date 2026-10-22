#!/usr/bin/env python3
"""Bind genuine current SDK/core artifacts into the original four-family input.

This is data preparation only. The original four-family producer still performs
all its source/project/helper checks and leaves production/runtime pending.
"""
import argparse
import json
from pathlib import Path

from runtimekit579_contract import ROOT, checked, read, record, require, verify_kit


def number580_sdk_receipt(batch, batch_path, commit, target, archive):
    """Read the fixed fifth-stage DATA; original SDK production remains authoritative."""
    def exact(row): return record(checked(row))
    def document(row): return read(checked(row))
    stage = next(r for r in batch['stages'] if r['label'] == 'number-local580')
    expected = dict(product=target['product'], arch=target['arch'], device=target['device'],
        sdk_device='default' if target['device'] == 'phone' else '2in1')
    require(batch.get('target') == expected and stage.get('requested_roles') ==
        (['system-granted','system-readonly','ordinary'] if target['device'] == 'phone' else []),
        'Number stage must follow the actual archive ABI/profile and fixed roles')
    receipt = exact(stage['actual_receipt'])
    require(Path(receipt['path']) == Path(batch_path).parent/'number-local580/evidence.json',
        'fixed fifth normal Number SDK receipt path')
    actual = document(receipt)
    require(actual.get('schema') == 'number-local580-actual-SDK/v1' and
        actual.get('source_commit') == commit and actual.get('target') == expected and
        type(actual.get('exit_code')) is int and actual['exit_code'] == 0 and actual.get('failures') == [] and
        actual.get('signed') is False and actual.get('guest_executed') is False and actual.get('runtime_pass') is False and
        actual.get('first_artifact_behavior_gate_passed') is False and
        actual.get('declared_inner_commands_completed_without_timeout') is True,
        'completed same-target unsigned Number SDK only; never guest/native acceptance')
    if target['device'] == '2in1':
        require(actual.get('status') == 'not_applicable' and actual.get('applicability') == 'phone_only_NO_phone_pass' and
            actual.get('roles') == [] and actual.get('account_controller') is None and actual.get('commands') == [] and
            actual.get('sdk_started') is False and 'archive_binding' not in actual,
            'exact typed 2in1 N/A without phone caller inputs or success relabel')
        return receipt
    require(target['device'] == 'phone', 'Number SDK supports exactly phone or explicit 2in1 N/A')
    binding = actual['archive_binding']
    require(type(binding) is dict and set(binding) == {'inputs','archive','image','profile','normal_source',
        'sdk_declaration','manifest','build_inputs'}, 'complete actual Number normal archive binding')
    for value in binding.values():
        require(type(value) is dict and set(value) == {'path','sha256','bytes'} and
            type(value['bytes']) is int and value['bytes'] >= 0, 'actual typed Number archive Ref3')
        exact(value)
    require(exact(binding['archive']) == exact(archive), 'Number SDK belongs to the same actual package archive')
    roles = actual['roles']
    require(type(roles) is list and [r['role'] for r in roles] == ['system-granted','system-readonly','ordinary'],
        'three fixed independent unsigned Number roles')
    permissions = {'system-granted':['ohos.permission.GET_TELEPHONY_STATE','ohos.permission.SET_TELEPHONY_STATE'],
        'system-readonly':['ohos.permission.GET_TELEPHONY_STATE'], 'ordinary':[]}
    account = actual['account_controller']
    require(type(account) is dict and account.get('role') == 'account' and
        account.get('permissions') == ['ohos.permission.MANAGE_LOCAL_ACCOUNTS','ohos.permission.GET_LOCAL_ACCOUNTS',
            'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION'], 'independent local OS-account permission role')
    for role in roles + [account]:
        require(type(role.get('exit_code')) is int and role['exit_code'] == 0 and
            (role['role'] == 'account' or role.get('permissions') == permissions[role['role']]),
            'each actual unsigned role completed with its exact own permissions')
        for key in ('unsigned_hap','source_manifest'):
            descriptor = role[key]
            require(type(descriptor) is dict and set(descriptor) == {'path','sha256','bytes'} and
                type(descriptor['bytes']) is int and descriptor['bytes'] > 0, 'actual Number/account artifact Ref3')
            exact(descriptor)
    account_ref = exact(account['sdk_evidence'])
    require(Path(account_ref['path']) == Path(receipt['path']).parent/'account-sdk-evidence.json',
        'fixed independent account SDK receipt')
    account_sdk = document(account_ref)
    require(account_sdk.get('schema') == 'number-local580-account-SDK/v1' and
        account_sdk.get('source_commit') == commit and account_sdk.get('target') == expected and
        account_sdk.get('archive_binding') == binding and account_sdk.get('run') == actual['run'] and
        account_sdk.get('driver') == actual['driver'] and account_sdk.get('exit_code') == 0 and
        type(account_sdk.get('exit_code')) is int and account_sdk.get('failures') == [] and
        account_sdk.get('signed') is False and account_sdk.get('guest_executed') is False and
        account_sdk.get('first_artifact_behavior_gate_passed') is False and
        account_sdk.get('role') == {k:v for k,v in account.items() if k != 'sdk_evidence'} and
        account_sdk.get('source_references') == actual['source_references']['account'],
        'independent account role shares the actual source/archive/target/run only, never Number privileges')
    require(len(actual['commands']) == 6 and len(account_sdk['commands']) == 2 and
        [r['label'] for r in account_sdk['commands']] == ['account-dependencies','account-compile'] and
        all(r.get('project') == 'account' and type(r.get('exit_code')) is int and r['exit_code'] == 0 and
            not r.get('timed_out') for r in account_sdk['commands']) and
        all(type(r.get('exit_code')) is int and r['exit_code'] == 0 and not r.get('timed_out') for r in actual['commands']),
        'actual unsigned Number/account command summaries must remain complete; original dispatcher raw/lease guards retained')
    return receipt


def render(value):
    require(set(value) == {'schema','source_commit','source_kit_manifest','canonical_snapshot','snapshot_count',
        'postpackage_receipt','sdk_batch_receipt','prepared_sources','templates','family_output'} and
        value['schema'] == 'four-family-bindings579/v1','finite current family input bindings required')
    verify_kit(value,value['source_commit']);commit=value['source_commit']
    post=read(checked(value['postpackage_receipt']));sdk_path=checked(value['sdk_batch_receipt']);sdk=read(sdk_path)
    sources=read(checked(value['prepared_sources']))
    require(post['exit_code'] == sdk['exit_code'] == 0 and post['source_commit'] == sdk['source_commit'] ==
        sources['source_commit'] == commit and post.get('failures') == sdk.get('failures') == [] and
        sdk['requested_prepackage_stages_complete'] is True and
        sources['source_kit_manifest'] == value['source_kit_manifest'], 'actual current production and caller inputs required')
    require(len(sdk['stages']) == 5 and {r['label'] for r in sdk['stages']} ==
        {'apps15','audio-calendar26','knowledge26','live-sdk39-26','number-local580'} and
        all(type(r.get('exit_code')) is int and r['exit_code'] == 0 and checked(r['actual_receipt'])
            for r in sdk['stages']), 'four original SDK stages plus exact Number stage required')
    import sys
    sys.path.insert(0,str(ROOT/'ci/capability-audit'))
    from production579_target import archive_manifest
    context = archive_manifest(checked(post['archive']))['context']
    expected_helpers = {
        'phone': {'core','audio','calendar','gnss','mic','netlink','number','number-recheck'},
        '2in1': {'core','audio','calendar','gnss','mic','netlink'},
    }
    require(context['device'] in expected_helpers and
        set(post['helpers']) == expected_helpers[context['device']],
        'exact same-archive phone eight or 2in1 six genuine producer outputs required')
    for kind,row in post['helpers'].items():
        actual=read(checked(row['launcher']))
        require(actual['exit_code'] == 0 and actual['cleanup_verified'] is True and actual['owned_container_absent'] is True and
            actual['source_commit'] == commit and Path(row['launcher']['path']).parent == Path(row['root']) and
            actual['package']['sha256'] == post['archive']['sha256'], 'actual original producer closure differs: '+kind)
    expected_target = dict(product=context['product'], arch=context['arch'], device=context['device'], sdk_device='default' if context['device'] == 'phone' else '2in1')
    require(post.get('target') == context and sdk.get('target') == expected_target and
        all(read(checked(r['actual_receipt'])).get('target') == expected_target for r in sdk['stages']),
        'all five actual SDK targets must match the newly packaged product/profile')
    number580_sdk_receipt(sdk, sdk_path, commit, context, post['archive'])
    templates=value['templates']
    require(set(templates) == {'contacts.json','wallpaper.json','live-inputs.json','capability-inputs.json'},
        'original four explicit templates required')
    paths={name:checked(row) for name,row in templates.items()};parent=paths['contacts.json'].parent
    require(all(path == parent/name for name,path in paths.items()),'same original template directory required')
    family=checked(sources['family_entry']).parent
    require(family.name == 'family' and family/'prepare_first_runtime_inputs377.py' == checked(sources['family_entry']),
        'actual prepared original family source required')
    target=Path(value['family_output'])
    require(target.is_absolute() and not target.exists() and not target.is_symlink(), 'fresh actual family output required')
    return {'schema':'four-family-SDK-inputs579-target/v2','product_commit':commit,'tools_commit':commit,
        'qa_root':str(ROOT),'here':str(family),'target':context,'package_receipt':post['package_receipt'],
        'core_root':post['helpers']['core']['root'],'SDK39_root':str(sdk_path.parent/'live-sdk39-26'),
        'knowledge_root':str(sdk_path.parent/'knowledge26'),
        'fresh_callers':record(sdk_path.parent/'apps15/caller-inputs.json'),
        'templates':templates,'output':str(target)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--inputs-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    require(record(args.inputs)['sha256'] == args.inputs_sha256,'actual family binding data identity required')
    result=render(read(args.inputs));target=args.output
    require(target.is_absolute() and target.parent.is_dir() and not target.exists() and not target.is_symlink(),
        'fresh family intent destination required')
    with target.open('x') as stream: stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(record(target)))


if __name__ == '__main__': main()
