"""Mutation tests for independent MIC evidence; no fixture is a guest pass."""
import copy
import json
import unittest

import audio_capture_permission as P
import verify_audio_capture_results as V
from batch_media_audio_capture_challenge import CONFIG_STEPS


def node(text, bundle=P.BUNDLE, clickable=False, bounds='[0,0][120,40]'):
    return {'attributes': {'bundleName': bundle, 'text': text, 'visible': 'true',
            'enabled': 'true', 'clickable': str(clickable).lower(), 'bounds': bounds}, 'children': []}


class CaptureAcceptanceTests(unittest.TestCase):
    def test_dialog_requires_microphone_title_trusted_owner_and_one_button(self):
        labels = {'scope': P.SCOPE, 'bundle': P.BUNDLE, 'files_sha256': {'real-source': 'a' * 64},
                  'locales': [{'title': 'Allow Capability audit to use the microphone?', 'allow': 'Allow', 'deny': 'Deny'}]}
        title = node(labels['locales'][0]['title'])
        allow = node('Allow', clickable=True, bounds='[0,40][120,80]')
        deny = node('Deny', clickable=True, bounds='[120,40][240,80]')
        layout = {'attributes': {}, 'children': [title, allow, deny]}
        self.assertEqual(P.select(layout, labels, False)['attributes']['text'], 'Allow')
        self.assertEqual(P.select(layout, labels, True)['attributes']['text'], 'Deny')
        for mutate in ('other-app', 'camera-title', 'disabled', 'ambiguous'):
            broken = copy.deepcopy(layout)
            if mutate == 'other-app':
                for child in broken['children']:
                    child['attributes']['bundleName'] = 'untrusted.app'
            elif mutate == 'camera-title':
                broken['children'][0]['attributes']['text'] = 'Allow Capability audit to use the camera?'
            elif mutate == 'disabled':
                broken['children'][1]['attributes']['enabled'] = 'false'
            else:
                broken['children'].append(copy.deepcopy(allow))
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                P.select(broken, labels, False)

    def test_token_never_accepts_another_owner_a_grant_claim_or_unknown_state(self):
        run, uid = 'd' * 32, 20010001
        original = {'run_id': run, 'bundle': 'org.harmonycontrib.capabilityaudit', 'user_id': 100,
            'uid': uid, 'token_id': 123, 'permission': 'ohos.permission.MICROPHONE',
            'operation': 'query', 'result': 0, 'before': -1, 'after': -1, 'before_ns': 1, 'after_ns': 2}
        self.assertEqual(V.token(original, run, uid), (-1, 123))
        for change in ({'uid': uid + 1}, {'token_id': 0}, {'operation': 'grant'}, {'result': -1},
                       {'before': 0}, {'after': True}, {'permission': 'ohos.permission.CAMERA'}, {'run_id': 'e' * 32}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                V.token({**original, **change}, run, uid)

    def test_denied_actual_boundary_rejects_early_config_errors_success_or_pcm(self):
        run, uid = 'a' * 32, 20010001
        rows = [{'type': 'identity', 'run_id': run, 'uid': uid, 'euid': uid, 'mode': 'denied'}]
        files = {f'audio-capture-{run}-cycle{c}.pcm': {'absent': True} for c in (1, 2)}
        for cycle in (1, 2):
            for name, expected in CONFIG_STEPS[:10]:
                rows.append({'type': 'step', 'run_id': run, 'cycle': cycle, 'name': name,
                             'actual': expected, 'expected': expected})
            rows += [{'type': 'denial_generate', 'run_id': run, 'cycle': cycle, 'actual': 3, 'created': False},
                     {'type': 'step', 'run_id': run, 'cycle': cycle, 'name': 'destroy', 'actual': 0, 'expected': 0}]
        rows.append({'type': 'summary', 'run_id': run, 'cycles': 2, 'candidate_ok': True,
                     'independent_pcm_verification_required': True})
        text = lambda value: '\n'.join(json.dumps(r) for r in value)
        result = V.denied_results(text(rows), run, uid, files)
        self.assertTrue(result['positive_backend_control_required'])
        for mode in ('config', 'generated', 'PCM', 'destroy', 'uid', 'replay'):
            broken = copy.deepcopy(rows)
            if mode == 'config': broken[3]['actual'] = 3
            elif mode == 'generated': broken[11]['actual'] = 0
            elif mode == 'PCM': broken.insert(-1, {'type': 'chunk', 'run_id': run, 'cycle': 1, 'bytes': 4})
            elif mode == 'destroy': broken[12]['actual'] = 2
            elif mode == 'uid': broken[0]['uid'] = 0
            else: broken[-1]['run_id'] = 'b' * 32
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                V.denied_results(text(broken), run, uid, files)


if __name__ == '__main__':
    unittest.main()
