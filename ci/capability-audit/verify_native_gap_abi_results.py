"""Complete fresh system-loader ABI proof, not ordinary-app/backend behavior."""
import json
from pathlib import Path
import re

from const_enum_contracts import LEDGER, sha256
SOURCE_LOCK = Path(__file__).resolve().parents[2] / 'scripts/openharmony_7_0_release_source_lock.json'


def validate_definitions(document, device, arch):
    baseline = json.loads(LEDGER.read_text())['devices'][device]['native_abi_gaps']
    source_pin = [row['revision'] for row in json.loads(SOURCE_LOCK.read_text())['projects']
                  if row['path'] == 'interface/sdk_c']
    if (document.get('status') != 'pass' or document.get('arch') != arch or document.get('device') != device
            or document.get('scope') != 'offline_actual_final_image_complete_original_Native_gap_ABI_NOT_behavior'
            or document.get('audit_baseline_sha256') != sha256(LEDGER)
            or document.get('source_lock_sha256') != sha256(SOURCE_LOCK)
            or source_pin != [document.get('sdk_c_revision')]
            or re.fullmatch('[a-f0-9]{64}', document.get('actual_syscap_sha256', '')) is None
            or re.fullmatch('[a-f0-9]{64}', document.get('device_profile_sha256', '')) is None
            or len(document.get('contracts', [])) != len(baseline)):
        raise ValueError('actual complete final-image Native ABI definitions required')
    for row, original in zip(document['contracts'], baseline):
        if (row.get('original_requirement') != original or row.get('syscap') != original['syscap']
                or row.get('library') != original['library'] or row.get('id') !=
                'native:' + original['syscap'] + ':' + original['library']
                or not isinstance(row.get('functions'), list) or row['functions'] != sorted(set(row['functions']))
                or len(row['functions']) < original['public_function_count']
                or not set(original['missing_symbols']) <= set(row['functions'])
                or any(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name) is None for name in row['functions'])
                or not row.get('source_inputs_sha256')
                or any(re.fullmatch('[a-f0-9]{64}', value) is None for value in row['source_inputs_sha256'].values())
                or any(type(row.get(key)) is not bool for key in
                       ('needs_library', 'declared_by_final_image', 'required_by_active_contract'))):
            raise ValueError('omitted/altered original Native ABI contract')
        if row['needs_library']:
            if (row.get('status') != 'all_source_contract_symbols_present' or
                    not (row['declared_by_final_image'] or row['required_by_active_contract']) or
                    row.get('scope') != 'required_actual_native_ABI' or
                    re.fullmatch('[a-f0-9]{64}', row.get('library_sha256', '')) is None):
                raise ValueError('required library was not completely verified in the actual image')
        elif (row.get('status') != 'optional_undeclared' or row['declared_by_final_image'] or
              row['required_by_active_contract'] or row.get('implemented') is not False or
              row.get('scope') != 'optional_undeclared_NOT_implemented'):
            raise ValueError('actual declared/required library cannot become an optional exemption')
    return document['contracts']


def runtime_path(row, arch):
    prefix = '/system/lib/' if arch == 'armv7a' else '/system/lib64/'
    value = row.get('image_entry', {}).get('image_path', '')
    root_prefix = '/lib/' if arch == 'armv7a' else '/lib64/'
    if value.startswith(root_prefix):
        value = '/system' + value
    if row['needs_library'] and (not value.startswith(prefix) or '..' in Path(value).parts
                               or Path(value).name != row['library']):
        raise ValueError('verified Native library path is not the selected actual system ABI')
    return value if row['needs_library'] else ''


def verify(text, definitions, arch, device, run_id, code):
    specs = validate_definitions(definitions, device, arch)
    if re.fullmatch('[a-f0-9]{32}', run_id) is None or type(code) is not int or code != 0:
        raise ValueError('fresh Native ABI run and actual successful process exit required')
    actual = [json.loads(line) for line in text.splitlines()]
    expected = []
    checked = 0
    for spec in specs:
        path = runtime_path(spec, arch)
        expected.append({'kind': 'library', 'id': spec['id'], 'runId': run_id,
                         'required': spec['needs_library'], 'loaded': spec['needs_library'], 'path': path})
        if spec['needs_library']:
            for name in spec['functions']:
                expected.append({'kind': 'symbol', 'id': spec['id'], 'runId': run_id,
                                 'name': name, 'resolved': True, 'origin': path})
                checked += 1
    count = sum(row['needs_library'] for row in specs)
    expected.append({'kind': 'summary', 'runId': run_id, 'loaded_libraries': count,
                     'optional_undeclared': len(specs) - count, 'checked_symbols': checked, 'pass': True})
    # JSON equality alone would accept True == 1. Preserve every field type.
    if (len(actual) != len(expected) or any(set(row) != set(wanted) or any(
            type(row[key]) is not type(wanted[key]) or row[key] != wanted[key] for key in wanted)
            for row, wanted in zip(actual, expected))):
        raise ValueError('missing/stale/unresolved/wrong-owner Native ABI observations')
    return {'scope': 'actual_system_DSO_loader_all_original_native_ABI_contracts_NOT_app_or_backend',
            'contract_count': len(specs), 'loaded_libraries': count, 'checked_symbols': checked,
            'resolved_original_contracts': [row['id'] for row in specs],
            'optional_undeclared_not_implemented': [row['id'] for row in specs if not row['needs_library']]}
