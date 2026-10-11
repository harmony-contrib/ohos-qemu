"""Verify real SDK factory calls and two RS-backed dark/light callback cycles."""
import json
import math
from pathlib import Path
import re
import zipfile

from build_luminance_probe import TEMPLATE, page
from run_root_probe import digest
from verify_certificate_results import identity
from sign_luminance_probe import configure_profile

SCOPE = 'real_RS_luminance_factory_and_callbacks_NOT_full_gate'


def verify_inputs(value, run_id, arch):
    generated, declaration = Path(value['generated_source']), Path(value['sdk_declaration'])
    if (value.get('schema_version') != 1 or type(value.get('schema_version')) is not int or
            value.get('run_id') != run_id or value.get('arch') != arch or value.get('role') != 'system' or
            arch not in ('arm64', 'armv7a', 'x86_64') or value.get('scope') != SCOPE or
            value.get('request_permissions') != [] or value.get('template_sha256') != digest(TEMPLATE) or
            declaration.name != '@ohos.arkui.UIContext.d.ts' or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(field)
                for path, field in ((generated, 'generated_source_sha256'), (declaration, 'sdk_declaration_sha256'))) or
            generated.read_text() != page(run_id, 'system')):
        raise ValueError('luminance typed source/SDK/nonce/ABI or permission scope changed')


def verify(text, run_id, identity_text):
    if re.fullmatch('[a-f0-9]{32}', run_id) is None:
        raise ValueError('fresh luminance nonce required')
    uid = identity(identity_text, 'system')
    rows = [json.loads(line) for line in text.splitlines()]
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['error'] != '' or not isinstance(row['name'], str) or
                not isinstance(row['values'], list) or any(type(v) not in (float, int) or
                    not math.isfinite(v) for v in row['values'])):
            raise ValueError('stale/failed/malformed luminance observation')
    position = 0

    def take(name, expected=None):
        nonlocal position
        if position >= len(rows) or rows[position]['name'] != name:
            raise ValueError('luminance observation missing or reordered: ' + name)
        value = rows[position]['values']
        position += 1
        if any(type(v) is not int for v in value) or (expected is not None and value != expected):
            raise ValueError('luminance exact result differs: ' + name)
        return value

    caller = take('identity')
    if len(caller) != 3 or caller[:2] != [uid, uid] or caller[2] <= 1:
        raise ValueError('luminance caller does not match installed system role')
    take('factory', [1, 1, 1])
    take('invalid.bright.256', [100001, 1])
    take('invalid.bright.-1', [100001, 1])
    for cycle in range(2):
        count = 0
        for phase, lower, upper in (('dark', 0, 40), ('bright', 215, 255)):
            name = phase + '.' + str(cycle)
            samples = []
            while position < len(rows) and rows[position]['name'] == 'sample.' + name:
                values = rows[position]['values']
                if len(values) != 2 or type(values[1]) is not int or values[1] != 1 or not 0 <= values[0] <= 255:
                    raise ValueError('invalid real RS luminance callback')
                samples.append(values[0])
                position += 1
            if not any(lower <= value <= upper for value in samples):
                raise ValueError('rendered background did not produce expected real luminance: ' + name)
            count += len(samples)
            take(name, [count])
        take('off.' + str(cycle), [count, count])
    take('cleanup', [1])
    take('summary', [1])
    if position != len(rows):
        raise ValueError('extra callbacks/results after luminance cleanup')
    return rows


def verify_evidence(document, archive_sha, boot_id, arch, device):
    if (document.get('status') != 'pass' or document.get('scope') !=
            'real_factory_RS_callbacks_and_unsubscription_NOT_full_gate' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('failures') != [] or
            set(document.get('roles', {})) != {'system'} or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None):
        raise ValueError('actual luminance factory observations on this new package required')
    record = document['roles']['system']
    paths = {}
    for field in ('inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt', 'raw_results'):
        path = Path(record[field])
        if path.is_symlink() or not path.is_file() or digest(path) != record.get(field + '_sha256'):
            raise ValueError('luminance evidence changed or missing: ' + field)
        paths[field] = path
    nonce = record['run_id']
    if record.get('status') != 'pass' or record.get('uid') != identity(paths['application_identity'].read_text(), 'system'):
        raise ValueError('actual luminance system caller differs')
    verify_inputs(json.loads(paths['inputs'].read_text()), nonce, arch)
    receipt = json.loads(paths['signing_receipt'].read_text())
    profile = receipt.get('verified_profile', {})
    with zipfile.ZipFile(paths['signed_hap']) as hap:
        compiled = json.loads(hap.read('module.json'))
    if (receipt.get('status') != 'pass' or receipt.get('role') != 'system' or
            receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
            receipt.get('signed_sha256') != digest(paths['signed_hap']) or
            receipt.get('unsigned_sha256') != digest(paths['unsigned_hap']) or
            configure_profile(json.loads(json.dumps(profile)), 'system', document['udid'], compiled) != profile):
        raise ValueError('luminance caller signature/permission scope differs')
    actual = verify(paths['raw_results'].read_text(), nonce, paths['application_identity'].read_text())
    if actual != record.get('results'):
        raise ValueError('luminance summary differs from actual observations')
    return ['arkts_export:@ohos.arkui.UIContext:LuminanceSampler']
