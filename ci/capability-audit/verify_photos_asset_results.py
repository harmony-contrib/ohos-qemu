"""Require real new asset identity, public picker results and decoded JPEG pixels."""
import argparse
import json
import math
from pathlib import Path
import re

from photos_asset_contract import SCOPE, verify_inputs
from photos_asset_ui import verify_actions
from run_normal_hap_probe import BUNDLE, require_normal_identity
from run_root_probe import digest


def object_value(text):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('actual Photos object result required')
    return value


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Photos asset nonce required')
    expected = [name + '.' + str(cycle) for cycle in (1, 2) for name in
                ('default-album', 'recent-empty-or-current', 'recent-explicit-options', 'recent-options-unmodified')]
    expected += ['picker.invalid-count', 'metadata.complete', 'picker.opened', 'picker.user-cancel-result',
                 'asset.dialog-requested', 'asset.dialog-result', 'asset.written', 'asset.recent',
                 'asset.read-picker-requested', 'asset.selected', 'asset.readback']
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(expected):
        raise ValueError('complete Photos asset round trip required')
    values = {}
    for index, (row, name) in enumerate(zip(rows, expected)):
        if (not isinstance(row, dict) or set(row) != {'runId', 'sequence', 'name', 'pass', 'value'} or row['runId'] != run_id or
                type(row['sequence']) is not int or row['sequence'] != index + 1 or row['name'] != name or
                row['pass'] is not True or not isinstance(row['value'], str)):
            raise ValueError('failed, missing, reordered or stale Photos asset observation')
        value = values[name] = row['value']
        if name.startswith('default-album.') and not value.strip():
            raise ValueError('nonempty real album name required')
        if name.startswith(('recent-empty-or-current.', 'recent-explicit-options.')) or name == 'asset.recent':
            info = object_value(value)
            stamp = info.get('dateTaken')
            if (type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 or
                    not isinstance(info.get('identifier'), str) or not info['identifier']):
                raise ValueError('invalid actual recent asset metadata')
        if name.startswith('recent-options-unmodified.') and value != '{}':
            raise ValueError('Photos mutated caller-owned options')
    if object_value(values['picker.invalid-count']).get('code') != 401:
        raise ValueError('real public parameter rejection required')
    if object_value(values['picker.user-cancel-result']).get('photoUris') != []:
        raise ValueError('real picker cancellation must not select an asset')
    expected_source = 'file://' + BUNDLE + '/data/storage/el2/base/files/photos-source-' + run_id + '.jpg'
    if values['asset.dialog-requested'] != expected_source:
        raise ValueError('asset consent did not name the fresh caller-owned JPEG')
    created = json.loads(values['asset.dialog-result'])
    if (not isinstance(created, list) or len(created) != 1 or not isinstance(created[0], str) or
            re.fullmatch(r'file://media/Photo/[1-9][0-9]*/[^/]+/qemu-' + run_id + r'\.jpg', created[0]) is None):
        raise ValueError('consent must create exactly one uniquely titled real MediaLibrary asset')
    uri = created[0]
    if (values['asset.written'] != uri or values['asset.read-picker-requested'] != uri or
            object_value(values['asset.selected']).get('photoUris') != [uri]):
        raise ValueError('write/picker/read asset identities differ')
    expected_identifier = 0
    for character in 'qemu-' + run_id:
        expected_identifier = (expected_identifier * 13 + ord(character)) % 9999991
    recent = object_value(values['asset.recent'])
    if recent['dateTaken'] <= 0 or recent['identifier'] != str(expected_identifier):
        raise ValueError('recent provider did not return the uniquely created asset')
    pixels = object_value(values['asset.readback'])
    if (set(pixels) != {'width', 'height', 'red', 'green', 'blue', 'alpha'} or
            any(type(value) is not int for value in pixels.values()) or
            pixels['width'] != 64 or pixels['height'] != 64 or pixels['alpha'] != 255 or
            any(abs(pixels[key] - value) > 8 for key, value in [('red', 37), ('green', 149), ('blue', 211)])):
        raise ValueError('decoded JPEG dimensions/RGBA differ from actual source pixels')
    return {'observations': len(rows), 'created_asset_uri': uri, 'recent_identifier': recent['identifier'],
            'decoded_pixels': pixels, 'closed': [],
            'not_claimed': ['unselected gallery browsing', 'FA card', 'cloud provider', 'all Photos capabilities']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'actions', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'archive_sha256': digest(args.archive),
              'run_id': args.run_id, 'arch': args.arch, 'results_sha256': digest(args.results),
              'application_identity_sha256': digest(args.application_identity),
              'compiled_inputs_sha256': digest(args.inputs), 'actions_sha256': digest(args.actions),
              'verifier_sha256': digest(Path(__file__)),
              'ui_verifier_sha256': digest(Path(__file__).with_name('photos_asset_ui.py')),
              'failures': [], 'first_artifact_behavior_gate_passed': False}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        verify_actions(json.loads(args.actions.read_text()), BUNDLE)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
