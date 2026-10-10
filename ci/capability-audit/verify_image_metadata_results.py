"""Strict narrow parser/factory diagnostic; never closes the complete release gate."""
import argparse
import json
from pathlib import Path
import re

from image_metadata_fixtures import FIXTURES, verify as verify_fixtures
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

SCOPE = 'real_typed_image_metadata_factory_values_NOT_public_constructors_or_full_gate'
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
    'avis.frames': ([90], ''),
    'avis.frame.0': ([100], ''),
    'avis.frame.45': ([100], ''),
    'avis.frame.89': ([100], ''),
    'avis.negative': ([-1, 7700204], ''),
    'avis.end': ([90, 7700204], ''),
    'avis.after-invalid': ([100], ''),
    'summary': ([16, 0], ''),
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
    return dict(closed=[], scope=SCOPE, observations=len(rows), formats=['DNG', 'TIFF', 'AVIS'])


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
