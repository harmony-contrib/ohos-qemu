#!/usr/bin/env python3
"""Verify real ArkWeb factory/callback objects; never attest media decoding."""
import argparse
import json
import math
from pathlib import Path
import re

from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('web_factory_probe.ets')
SCOPE = 'four_ArkWeb_factory_and_callback_types_NOT_native_media_decoding'
CONTRACTS = ('WebHttpBodyStream', 'WebResourceHandler', 'MediaSourceInfo', 'NativeMediaPlayerSurfaceInfo')
MEDIA_EVENTS = frozenset(('rect', 'play', 'pause', 'seek', 'volume', 'muted', 'rate', 'release',
                         'fullscreen.enter', 'fullscreen.exit'))


def verify_inputs(inputs, run_id, arch):
    page = Path(inputs['generated_source'])
    declaration = Path(inputs['sdk_declaration'])
    if (inputs.get('run_id') != run_id or inputs.get('arch') != arch or
            inputs.get('role') != 'ordinary_app' or inputs.get('scope') != SCOPE or
            inputs.get('request_permissions') != [] or page.is_symlink() or declaration.is_symlink() or
            not page.is_file() or not declaration.is_file() or
            declaration.name != '@ohos.web.webview.d.ts' or
            digest(TEMPLATE) != inputs.get('template_sha256') or
            digest(page) != inputs.get('generated_source_sha256') or
            digest(declaration) != inputs.get('sdk_declaration_sha256') or
            page.read_text() != TEMPLATE.read_text().replace('__WEB_FACTORY_RUN_ID__', run_id)):
        raise ValueError('ArkWeb factory caller must match the complete current typed page and API26 SDK')


def verify(text, run_id, identity_text):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh ArkWeb factory challenge required')
    require_normal_identity(identity_text)
    rows = [json.loads(line) for line in text.splitlines()]
    if (not rows or rows[0].get('name') != 'setup' or rows[-1].get('name') != 'summary'):
        raise ValueError('ArkWeb setup/complete sequence missing')
    groups = {}
    for row in rows:
        if (set(row) != {'name', 'runId', 'text', 'values', 'error'} or row['runId'] != run_id or
                row['error'] != '' or not isinstance(row['name'], str) or
                not isinstance(row['text'], str) or not isinstance(row['values'], list) or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in row['values'])):
            raise ValueError('failed/malformed/stale ArkWeb factory observation')
        groups.setdefault(row['name'], []).append(row)

    def only(name, text=None, values=None):
        matches = groups.get(name, [])
        if len(matches) != 1:
            raise ValueError('missing/duplicate ArkWeb observation: ' + name)
        row = matches[0]
        if ((text is not None and row['text'] != text) or
                (values is not None and row['values'] != values)):
            raise ValueError('actual ArkWeb factory contract differs: ' + name)
        return row

    expected = {'setup', 'summary'}
    only('setup', '', [])
    only('summary', '', [2, 0])
    surface_ids = []
    for generation in range(2):
        tag = str(generation)
        body = run_id + ':' + tag + ':stream-body'
        size = len(body)
        observations = {
            'request.' + tag + '.main': ('auditweb://audit.local/main?generation=' + tag, [1, 0, 1]),
            'request.' + tag + '.post': ('POST:' + run_id, [0, 13]),
            'stream.' + tag + '.initial': ('', [size, 0, 0, 1, 0]),
            'stream.' + tag + '.invalid-size': ('', [401, 0]),
            'stream.' + tag + '.read.1': ('', [1, 1, 0]),
            'stream.' + tag + '.read.7': ('', [7, 8, 0]),
            'stream.' + tag + '.read.4096': ('', [size - 8, size, 1]),
            'stream.' + tag + '.complete': (body, [size, size, 1, 0]),
            'handler.' + tag + '.finish': (body, []),
            'page.' + tag + '.title': ('OK-' + body, []),
            'media.' + tag + '.source': ('auditweb://audit.local/media-' + tag + '.mp4|mp4', [0, 0, 1]),
        }
        for name, (value, numbers) in observations.items():
            expected.add(name)
            only(name, value, numbers)
        stream_names = [name for name in observations if name.startswith('stream.')]
        indices = [next(i for i, row in enumerate(rows) if row['name'] == name) for name in stream_names]
        if indices != sorted(indices):
            raise ValueError('body stream progress was not observed in execution order')
        surface_name = 'media.' + tag + '.surface'
        expected.add(surface_name)
        surface = only(surface_name)
        if (re.fullmatch('[1-9][0-9]*', surface['text']) is None or len(surface['values']) != 4 or
                any(value < 0 for value in surface['values'][2:])):
            raise ValueError('native media callback lacks an actual surface identity/rectangle')
        surface_ids.append(surface['text'])
        for event in MEDIA_EVENTS:
            name = 'media.' + tag + '.' + event
            expected.add(name)
            for row in groups.get(name, []):
                if row['text'] != '':
                    raise ValueError('media callback observer contains manufactured text')
                numbers = row['values']
                lengths = {'rect': 4, 'seek': 1, 'volume': 1, 'muted': 1, 'rate': 1}
                if len(numbers) != lengths.get(event, 0):
                    raise ValueError('invalid native media callback arguments')
                if event == 'rect':
                    if any(value < 0 for value in numbers[2:]):
                        raise ValueError('negative native media callback dimensions')
        # The SDK does not promise positive dimensions before the external
        # player supplies video metadata. This observer never acknowledges a
        # decoder, so an initial empty rect is legitimate, not a frame pass.
        only('media.' + tag + '.release', '', [])
    if surface_ids[0] == surface_ids[1] or not set(groups) <= expected:
        raise ValueError('stale native media surface or unrecognized/failed observation')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'application-identity', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch,
              'failures': [], 'first_artifact_behavior_gate_passed': False}
    try:
        report.update(archive_sha256=digest(args.archive), results_sha256=digest(args.results),
                      inputs_sha256=digest(args.inputs),
                      application_identity_sha256=digest(args.application_identity))
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['results'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
