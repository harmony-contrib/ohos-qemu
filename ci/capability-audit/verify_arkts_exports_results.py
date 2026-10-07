#!/usr/bin/env python3
"""Verify complete actual reflection; absent values remain unresolved findings."""
import argparse
import json
from pathlib import Path
import re

from const_enum_contracts import LEDGER, sha256

A11Y_ENUMS = frozenset(('AccessibilitySourceType', 'FocusMoveResultCode', 'OperateVirtualNodeResult'))


def expected_modules():
    baseline = json.loads(LEDGER.read_text())
    return sorted({row['module'] for device in baseline['devices'].values()
                   for dimension in ('arkts11_module_load_gaps', 'arkts11_runtime_export_gaps')
                   for row in device[dimension]})


def verify(text, inputs, run_id, arch):
    if (re.fullmatch('[0-9a-f]{32}', run_id) is None or inputs.get('run_id') != run_id or
            inputs.get('arch') != arch or inputs.get('audit_baseline_sha256') != sha256(LEDGER) or
            inputs.get('modules') != expected_modules()):
        raise ValueError('export collection must cover the unchanged complete baseline with a fresh challenge')
    for key, path_key in (('native_source_sha256', 'native_source'), ('generated_source_sha256', 'generated_source')):
        if sha256(inputs[path_key]) != inputs[key]:
            raise ValueError('actual export collector source changed')
    template = Path(inputs['template'])
    if (inputs.get('role') != 'ordinary_app' or inputs.get('scope') != 'actual_all_own_exports_collection_only'
            or sha256(template) != inputs['template_sha256'] or
            Path(inputs['generated_source']).read_text() != template.read_text().replace('__RUN__', run_id)
            .replace('__MODULES__', json.dumps(expected_modules()))):
        raise ValueError('actual ordinary collector page differs from the complete requested modules')
    records = text.splitlines()
    if len(records) != 1:
        raise ValueError('one complete fresh reflection record required')
    report = json.loads(records[0])
    if (set(report) != {'runId', 'collection', 'modules', 'export_collection_complete'} or
            report['runId'] != run_id or report['collection'] != 'all_own_string_properties' or
            report['export_collection_complete'] is not True or not isinstance(report['modules'], list) or
            [row.get('module') for row in report['modules']] != expected_modules()):
        raise ValueError('missing/duplicate/stale modules or enumerable-only collection')
    for row in report['modules']:
        if set(row) != {'module', 'load_status', 'load_exception', 'module_type', 'collection_status',
                       'collection_exception', 'properties'}:
            raise ValueError('malformed raw module result')
        for name in ('load_status', 'module_type', 'collection_status'):
            if type(row[name]) is not int or row[name] < 0:
                raise ValueError('invalid actual module NAPI status/type')
        if not 0 <= row['module_type'] <= 9 or any(type(row[name]) is not bool for name in
                ('load_exception', 'collection_exception')) or not isinstance(row['properties'], list):
            raise ValueError('malformed actual module reflection')
        names = set()
        for value in row['properties']:
            if (not isinstance(value, dict) or set(value) != {'name', 'read_status', 'value_type', 'read_exception',
                                                               'enum_contract_applicable', 'enum_contract_valid'}
                    or not isinstance(value['name'], str) or value['name'] in names or
                    type(value['read_status']) is not int or value['read_status'] < 0 or
                    type(value['value_type']) is not int or not 0 <= value['value_type'] <= 9 or
                    type(value['read_exception']) is not bool or
                    type(value['enum_contract_applicable']) is not bool or
                    type(value['enum_contract_valid']) is not bool or
                    value['enum_contract_applicable'] !=
                    (row['module'] == '@ohos.accessibility' and value['name'] in A11Y_ENUMS) or
                    (value['enum_contract_valid'] and
                     (not value['enum_contract_applicable'] or value['read_status'] != 0 or
                      value['read_exception'] or value['value_type'] != 6))):
                raise ValueError('duplicate/malformed raw export property')
            names.add(value['name'])
        if ((row['load_status'] != 0 or row['load_exception'] or row['collection_status'] != 0 or
                row['collection_exception']) and row['properties']):
            raise ValueError('failed load/collection cannot claim readable exports')
    return report['modules']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from verify_first_artifact_gate import checksum
    result = {'status': 'fail', 'scope': 'complete_actual_export_collection_NOT_backend_or_full_gap_closure',
              'archive_sha256': checksum(args.archive), 'run_id': args.run_id, 'arch': args.arch,
              'inputs_sha256': sha256(args.inputs), 'results_sha256': sha256(args.results),
              'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        result['modules'] = verify(args.results.read_text(), json.loads(args.inputs.read_text()), args.run_id, args.arch)
        result['status'] = 'pass'
    except (ValueError, KeyError, TypeError, OSError) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'scope': result['scope']}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
