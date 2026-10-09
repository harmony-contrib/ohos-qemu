"""Host verifier fixtures, not Photos provider runtime evidence."""
import copy
import json
from pathlib import Path
import unittest

from run_normal_hap_probe import PERSONAS, result_directory, APP_FILES, verifier_arguments
from verify_photos_recent_results import verify

RUN = '5a52805338ef4b77a78efbc55b00519a'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
    'isSystemApp': False, 'uid': 20010001}})


def observations():
    rows = []
    for cycle in (1, 2):
        for name, value in [('default-album.' + str(cycle), '图片和视频'),
                            ('recent.' + str(cycle) + '.0', '{"dateTaken":0,"identifier":"0"}'),
                            ('recent.' + str(cycle) + '.1', '{"dateTaken":0,"identifier":"0"}'),
                            ('options-unmodified.' + str(cycle), '{}'),
                            ('picker.invalid-count.' + str(cycle), '{"code":401}')]:
            rows.append({'runId': RUN, 'sequence': len(rows) + 1, 'name': name, 'pass': True, 'value': value})
    rows.append({'runId': RUN, 'sequence': 11, 'name': 'summary', 'pass': True,
                 'value': 'metadata-defaults-reused-options-and-parameter-rejection-only'})
    return rows


class PhotosMetadataVerificationTests(unittest.TestCase):
    def verify_rows(self, rows, identity=IDENTITY):
        return verify('\n'.join(json.dumps(row) for row in rows) + '\n', RUN, identity)

    def test_complete_metadata_does_not_claim_asset_or_cloud_closure(self):
        result = self.verify_rows(observations())
        self.assertEqual(result['closed'], [])
        self.assertEqual(result['observations'], 11)
        self.assertIn('positive recent asset retrieval', result['not_claimed'])

    def test_each_missing_duplicate_or_failed_observation_is_rejected(self):
        for index in range(11):
            for mutation in ('missing', 'duplicate', 'failed', 'stale', 'sequence'):
                with self.subTest(index=index, mutation=mutation):
                    rows = observations()
                    if mutation == 'missing': rows.pop(index)
                    elif mutation == 'duplicate': rows.append(copy.deepcopy(rows[index]))
                    elif mutation == 'failed': rows[index]['pass'] = False
                    elif mutation == 'stale': rows[index]['runId'] = '0' * 32
                    else: rows[index]['sequence'] = True
                    with self.assertRaises(ValueError): self.verify_rows(rows)

    def test_failure_sentinel_and_invalid_provider_metadata_rejected(self):
        for value in ({'dateTaken': -1, 'identifier': '-1'}, {'dateTaken': True, 'identifier': '0'},
                      {'dateTaken': float('nan'), 'identifier': '0'}, {'dateTaken': 0, 'identifier': ''},
                      {'dateTaken': 0, 'identifier': 0}):
            rows = observations()
            rows[1]['value'] = json.dumps(value)
            with self.assertRaises(ValueError): self.verify_rows(rows)

    def test_parameter_error_mutation_and_blank_album_rejected(self):
        for index, value in ((0, ' '), (3, '{"period":86400}'), (4, '{"code":13900020}')):
            rows = observations()
            rows[index]['value'] = value
            with self.assertRaises(ValueError): self.verify_rows(rows)

    def test_system_or_privileged_caller_rejected(self):
        for key, value in (('isSystemApp', True), ('appPrivilegeLevel', 'system_basic'), ('uid', 0)):
            identity = json.loads(IDENTITY)
            identity['applicationInfo'][key] = value
            with self.assertRaises(ValueError): self.verify_rows(observations(), json.dumps(identity))

    def test_normal_runner_preserves_nonce_identity_and_correct_sandbox(self):
        persona = 'photos-recent'
        self.assertEqual(PERSONAS[persona][0], '--photos-recent-only')
        self.assertEqual(result_directory(persona), APP_FILES)
        args = verifier_arguments(persona, Path('/archive'), Path('/results'), Path('/identity'),
                                  RUN, 'arm64', Path('/output'))
        for flag, value in (('--run-id', RUN), ('--application-identity', '/identity'), ('--arch', 'arm64')):
            self.assertEqual(args[args.index(flag) + 1], value)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("'camera', 'settings-navigation', 'photos-recent'", suite)


if __name__ == '__main__':
    unittest.main()
