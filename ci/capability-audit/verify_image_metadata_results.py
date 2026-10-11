"""Strict narrow parser/factory diagnostic; never closes the complete release gate."""
import argparse
import json
from pathlib import Path
import re

from image_metadata_fixtures import FIXTURES, verify as verify_fixtures
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

SCOPE = 'real_image_metadata_and_Avis_constructor_NOT_Dng_Tiff_constructors_or_full_gate'
AVIS_CONTRACT = 'arkts_export:@ohos.multimedia.image:AvisMetadata'
EXPECTED = {
    'dng.selected': ([1, 4, 0, 0], 'FakeCamera ModelX'),
    'dng.default': ([1, 4, 0, 0], 'FakeCamera ModelX'),
    'dng.negative': ([-1, 7700204], ''),
    'dng.after-invalid': ([1, 4, 0, 0], 'FakeCamera ModelX'),
    'tiff.selected': ([1, 2, 1, 72, 72, 2], ''),
    'tiff.default': ([1, 2, 1, 72, 72, 2], ''),
    'tiff.negative': ([-1, 7700204], ''),
    'tiff.end': ([1, 7700204], ''),
    'tiff.after-invalid': ([1, 2, 1, 72, 72, 2], ''),
    'avis.constructor': ([1, 1, 1, 1, 1], ''),
    'avis.frames': ([90], ''),
    'avis.frame.0': ([100], ''),
    'avis.instance.0': ([1], ''),
    'avis.frame.45': ([100], ''),
    'avis.instance.45': ([1], ''),
    'avis.frame.89': ([100], ''),
    'avis.instance.89': ([1], ''),
    'avis.negative': ([-1, 7700204], ''),
    'avis.end': ([90, 7700204], ''),
    'avis.after-invalid': ([100], ''),
    'avis.constructor-after-read': ([1, 1, 1, 1], ''),
    'summary': ([21, 0], ''),
}


def verify(text, run_id, identity):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh image metadata nonce required')
    require_normal_identity(identity)
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(EXPECTED):
        raise ValueError('image metadata observations incomplete')
    for row, (name, (values, text)) in zip(rows, EXPECTED.items()):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'text', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['values'] != values or
                not isinstance(row['values'], list) or any(type(item) is not int for item in row['values']) or
                row['text'] != text or row['error'] != ''):
            raise ValueError('failed, stale or malformed image metadata observation: ' + name)
    return dict(closed=[AVIS_CONTRACT], scope=SCOPE, observations=len(rows), formats=['DNG', 'TIFF', 'AVIS'])


def verify_inputs(path, run_id, arch):
    value = json.loads(path.read_text())
    root = path.parent
    template = Path(__file__).with_name('image_metadata_probe.ets')
    page = root / 'entry/src/main/ets/pages/Index.ets'
    module = root / 'entry/src/main/module.json5'
    if (value.get('schema_version') != 1 or value.get('run_id') != run_id or value.get('arch') != arch or
            value.get('scope') != SCOPE or value.get('fixtures') != FIXTURES or
            value.get('template_sha256') != digest(template) or
            value.get('generated_source_sha256') != digest(page) or
            page.read_text() != template.read_text().replace('__IMAGE_METADATA_RUN__', run_id) or
            value.get('module_sha256') != digest(module) or value.get('request_permissions') != [] or
            json.loads(module.read_text())['module'].get('requestPermissions') != [] or
            re.fullmatch('[0-9a-f]{64}', value.get('sdk_declaration_sha256', '')) is None):
        raise ValueError('image metadata compiled contract changed')
    verify_fixtures(root / 'entry/src/main/resources/rawfile')


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('persona') != 'image-metadata' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('image metadata evidence must belong to the actual package/boot/architecture')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit image metadata result required')
    root = result_path.parent
    files = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/image-metadata-probe-inputs.json'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual image metadata evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('arch') != arch or
            value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(__file__))):
        raise ValueError('image metadata summary is stale or from another run')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('inputs_sha256', 'compiled_contract_inputs')):
        if value.get(field) != digest(files[key]):
            raise ValueError('image metadata verifier did not consume the captured evidence')
    verify_inputs(files['compiled_contract_inputs'], document['run_id'], arch)
    identity = files['ordinary_identity'].read_text()
    actual = verify(files['raw_results'].read_text(), document['run_id'], identity)
    if actual != value.get('result') or require_normal_identity(identity) != document.get('ordinary_uid'):
        raise ValueError('image metadata summary differs from actual ordinary-app observations')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch,
        archive_sha256=digest(args.archive), results_sha256=digest(args.results),
        application_identity_sha256=digest(args.application_identity), inputs_sha256=digest(args.inputs),
        verifier_sha256=digest(Path(__file__)), first_artifact_behavior_gate_passed=False, failures=[])
    try:
        verify_inputs(args.inputs, args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
