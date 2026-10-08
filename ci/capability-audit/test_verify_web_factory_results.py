import copy
import json
from pathlib import Path
import tempfile
import unittest

from run_root_probe import digest
from verify_web_factory_results import TEMPLATE, SCOPE, verify, verify_inputs

RUN = '0123456789abcdef0123456789abcdef'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False,
                                         'uid': 20010001}})


def observations():
    rows = []

    def row(name, text='', values=None):
        rows.append({'name': name, 'runId': RUN, 'text': text, 'values': values or [], 'error': ''})

    row('setup')
    for generation in range(2):
        tag = str(generation)
        body = RUN + ':' + tag + ':stream-body'
        size = len(body)
        row('request.' + tag + '.main', 'auditweb://audit.local/main?generation=' + tag, [1, 0, 1])
        row('media.' + tag + '.source', 'auditweb://audit.local/media-' + tag + '.mp4|mp4', [0, 0, 1])
        row('media.' + tag + '.surface', str(123 + generation), [0, 0, 300, 120])
        row('request.' + tag + '.post', 'POST:' + RUN, [0, 13])
        row('stream.' + tag + '.initial', '', [size, 0, 0, 1, 0])
        row('stream.' + tag + '.invalid-size', '', [401, 0])
        row('stream.' + tag + '.read.1', '', [1, 1, 0])
        row('stream.' + tag + '.read.7', '', [7, 8, 0])
        row('stream.' + tag + '.read.4096', '', [size - 8, size, 1])
        row('stream.' + tag + '.complete', body, [size, size, 1, 0])
        row('handler.' + tag + '.finish', body)
        row('page.' + tag + '.title', 'OK-' + body)
        row('media.' + tag + '.release')
    row('summary', '', [2, 0])
    return rows


def encode(rows):
    return '\n'.join(map(json.dumps, rows)) + '\n'


class WebFactoryTests(unittest.TestCase):
    def test_complete_two_real_contract_sequences(self):
        self.assertEqual(verify(encode(observations()), RUN, IDENTITY), observations())

    def test_missing_duplicate_stale_failed_and_unrecognized(self):
        base = observations()
        for rows in (base[:-1], base + [base[-1]], base[:4] + base[5:],
                     [{**row, 'runId': 'a' * 32} for row in base],
                     [{**row, 'error': 'failed'} if row['name'] == 'summary' else row for row in base],
                     base[:-1] + [{**base[0], 'name': 'fabricated'}] + base[-1:]):
            with self.subTest(rows=rows[-1]['name']), self.assertRaises(ValueError):
                verify(encode(rows), RUN, IDENTITY)

    def test_each_returned_contract_is_required(self):
        for name in ('stream.0.complete', 'handler.1.finish', 'page.0.title',
                     'media.1.source', 'media.0.surface', 'media.1.release'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify(encode([row for row in observations() if row['name'] != name]), RUN, IDENTITY)

    def test_wrong_body_eof_position_surface_or_boundary(self):
        for name, field, value in (
                ('stream.0.complete', 'text', 'invented'),
                ('stream.0.read.7', 'values', [7, 7, 0]),
                ('stream.1.complete', 'values', [46, 46, 0, 0]),
                ('stream.0.invalid-size', 'values', [0, 0]),
                ('media.0.surface', 'text', '0'),
                ('media.1.surface', 'text', '123'),
                ('media.0.surface', 'values', [0, 0, -1, 0]),
                ('media.1.source', 'text', 'invented|video/mp4')):
            rows = copy.deepcopy(observations())
            next(row for row in rows if row['name'] == name)[field] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify(encode(rows), RUN, IDENTITY)

    def test_initial_empty_rect_is_not_claimed_as_decoded_video_or_visible_frame(self):
        rows = observations()
        for row in rows:
            if row['name'].endswith('.surface'):
                row['values'] = [0, 0, 0, 0]
        self.assertEqual(verify(encode(rows), RUN, IDENTITY), rows)
        self.assertIn('NOT_native_media_decoding', SCOPE)

    def test_requires_ordinary_identity(self):
        system = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'system_basic',
                                                'isSystemApp': True, 'uid': 20010001}})
        with self.assertRaises(ValueError):
            verify(encode(observations()), RUN, system)

    def test_exact_complete_typed_caller_and_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / 'Index.ets'
            sdk = root / '@ohos.web.webview.d.ts'
            page.write_text(TEMPLATE.read_text().replace('__WEB_FACTORY_RUN_ID__', RUN))
            sdk.write_text('SDK fixture')
            inputs = {'run_id': RUN, 'arch': 'arm64', 'role': 'ordinary_app', 'scope': SCOPE,
                      'request_permissions': [], 'template_sha256': digest(TEMPLATE),
                      'generated_source': str(page), 'generated_source_sha256': digest(page),
                      'sdk_declaration': str(sdk), 'sdk_declaration_sha256': digest(sdk)}
            verify_inputs(inputs, RUN, 'arm64')
            page.write_text(page.read_text().replace('await stream.read(-1)', 'await stream.read(1)'))
            inputs['generated_source_sha256'] = digest(page)
            with self.assertRaises(ValueError):
                verify_inputs(inputs, RUN, 'arm64')


if __name__ == '__main__':
    unittest.main()
