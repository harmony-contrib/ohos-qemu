"""Strict actual readonly photo-query objects, not general media/knowledge proof."""
import json
import math
from pathlib import Path
import re
import zipfile

from build_photo_result_set_probe import DECLARATION, PERMISSION, ROLES, SCOPE, TEMPLATE, module, page
from run_root_probe import digest
from sign_photo_result_set_probe import configure_profile
from verify_certificate_results import identity as base_identity

EVIDENCE_SCOPE = 'three_actual_photo_query_roles_ResultSet_values_cursors_boundaries_NOT_full_gate_or_knowledge'


def identity(text, role):
    if role not in ROLES:
        raise ValueError('exact photo query role required')
    return base_identity(text, 'normal' if role == 'normal' else 'system')


def expected(role, nonce):
    page(nonce, role)
    rows = [('identity', None, '')]
    if role != 'system':
        rows += [('denied.' + str(index), [202 if role == 'normal' else 201, 1], '') for index in range(2)]
    else:
        for cycle in range(2):
            suffix = '.' + str(cycle)
            rows += [(name + suffix, values, text) for name, values, text in (
                ('query.shape', [1, 1], ''),
                ('factory', [5, 2, -1, 1], ''), ('first', [1, 0, 0], ''),
                ('values.first', [7, 1.25, 4, 0, 17, 127, 255, 1], nonce),
                ('row.first', [5, 7, 1.25, 4, 0, 17, 127, 255, 1], nonce),
                ('blob-copy', [255, 0], ''), ('last', [1, 1, 1], ''),
                ('values.last', [8, 2.5, 4, 0, 17, 127, 255, 1], nonce),
                ('past-last', [0], ''), ('invalid.column', [8, 8, 0, 7], ''),
                ('invalid.row', [8, 8, 0, 7], ''), ('closed', [2, 1], ''),
                ('bare-close', [1], ''), ('empty', [5, 0, 0, 0], ''),
                ('empty-blob', [2, 1, 0, 1, 0, 1], ''),
                ('invalid.sql', [1], ''), ('media-table', None, ''),
                ('recovery', [7, 1.25, 4, 0, 17, 127, 255, 1], nonce))]
    return rows + [('released', [1], ''), ('summary', [2], '')]


def verify(text, nonce, role, identity_text):
    if not text.endswith('\n'):
        raise ValueError('complete append-only photo query journal required')
    uid = identity(identity_text, role)
    rows = [json.loads(line) for line in text.splitlines()]
    contract = expected(role, nonce)
    if len(rows) != len(contract):
        raise ValueError('missing/extra photo query observations')
    for sequence, (row, (name, values, string)) in enumerate(zip(rows, contract), 1):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'sequence', 'name', 'values', 'text', 'error'} or
                row['runId'] != nonce or row['role'] != role or type(row['sequence']) is not int or
                row['sequence'] != sequence or row['name'] != name or row['error'] != '' or row['text'] != string or
                not isinstance(row['values'], list) or any(type(value) not in (int, float) or
                    not math.isfinite(value) for value in row['values'])):
            raise ValueError('failed/stale/malformed/reordered photo query observation: ' + name)
        actual = row['values']
        if name == 'identity':
            if (len(actual) != 3 or any(type(value) is not int for value in actual) or
                    actual[:2] != [uid, uid] or actual[2] <= 1):
                raise ValueError('photo query caller identity differs')
        elif name.startswith('media-table.'):
            if (len(actual) != 3 or any(type(value) is not int for value in actual) or
                    actual[0] < 0 or actual[1:] != [1, 1]):
                raise ValueError('real readonly Photos count query required')
        elif actual != values:
            raise ValueError('actual query/cursor/type/boundary behavior differs: ' + name)
    return rows


def verify_inputs(value, nonce, arch, role):
    generated, declaration = (Path(value[key]) for key in ('generated_source', 'sdk_declaration'))
    builder = Path(__file__).with_name('build_photo_result_set_probe.py')
    shared = Path(__file__).with_name('build_always_on_vpn_probe.py')
    project = generated.parents[5]
    module_path = project / 'entry/src/main/module.json5'
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
            value.get('run_id') != nonce or value.get('role') != role or value.get('arch') != arch or
            arch not in ('arm64', 'armv7a', 'x86_64') or value.get('scope') != SCOPE or
            value.get('request_permissions') != ([PERMISSION] if role == 'system' else []) or
            value.get('template_sha256') != digest(TEMPLATE) or declaration.name != DECLARATION or
            value.get('builder_sha256') != digest(builder) or value.get('shared_builder_sha256') != digest(shared) or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(key) for path, key in (
                (generated, 'generated_source_sha256'), (declaration, 'sdk_declaration_sha256'),
                (module_path, 'module_sha256'))) or generated.read_text() != page(nonce, role) or
            json.loads(module_path.read_text()) != module(role)):
        raise ValueError('actual compiled photo query source/SDK/role inputs changed')


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status') != 'pass' or document.get('scope') != EVIDENCE_SCOPE or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('target') != target or
            document.get('failures') != [] or document.get('caller_cleanup_verified') is not True or
            document.get('first_artifact_behavior_gate_passed') is not False or
            document.get('verifier_sha256') != digest(Path(__file__)) or
            set(document.get('roles', {})) != set(ROLES) or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None):
        raise ValueError('all real photo query roles in this exact packaged guest required')
    nonces = set()
    for role, record in document['roles'].items():
        paths = {}
        for field in ('inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt', 'raw_results'):
            path = Path(record[field])
            if path.is_symlink() or not path.is_file() or digest(path) != record.get(field + '_sha256'):
                raise ValueError('photo query evidence changed/missing: ' + field)
            paths[field] = path
        nonce = record['run_id']; nonces.add(nonce)
        if record.get('status') != 'pass' or record.get('actual_uid') != identity(paths['application_identity'].read_text(), role):
            raise ValueError('installed photo query identity differs')
        verify_inputs(json.loads(paths['inputs'].read_text()), nonce, arch, role)
        receipt = json.loads(paths['signing_receipt'].read_text())
        profile = receipt.get('verified_profile', {})
        with zipfile.ZipFile(paths['signed_hap']) as hap:
            compiled = json.loads(hap.read('module.json'))
        if (receipt.get('status') != 'pass' or receipt.get('role') != role or
                receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
                receipt.get('signed_sha256') != digest(paths['signed_hap']) or
                receipt.get('unsigned_sha256') != digest(paths['unsigned_hap']) or
                configure_profile(json.loads(json.dumps(profile)), role, document['udid'], compiled) != profile):
            raise ValueError('actual signed photo query permission contract differs')
        actual = verify(paths['raw_results'].read_text(), nonce, role, paths['application_identity'].read_text())
        if actual != record.get('results'):
            raise ValueError('photo query summary differs from actual journal')
    if len(nonces) != len(ROLES):
        raise ValueError('independent fresh nonce for each photo query role required')
    return ['arkts_export:@ohos.file.photoAccessHelper:ResultSet']
