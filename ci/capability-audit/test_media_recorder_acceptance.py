"""Permission-boundary mutation fixtures; no fixture is package acceptance."""
import copy
import json
import unittest

import verify_media_recorder_results as V

RUN, UID = 'a' * 32, 20010001


def denial(prepared=False):
    rows = [{'type': 'recorder_identity', 'run_id': RUN, 'uid': UID, 'euid': UID, 'expected_denied': True},
            {'type': 'recorder_step', 'run_id': RUN, 'cycle': 0, 'name': 'video_challenge', 'actual': 0}]
    files = {}
    for cycle in (1, 2):
        def step(name):
            return {'type': 'recorder_step', 'run_id': RUN, 'cycle': cycle, 'name': name, 'actual': 0, 'expected': 0}
        rows += [step(n) for n in ('create', 'state_callback', 'error_callback', 'output_open')]
        rows += [{'type': 'recorder_denial', 'run_id': RUN, 'cycle': cycle, 'operation': 'prepare',
                  'actual': 0 if prepared else 3}]
        if prepared:
            rows += [step(n) for n in ('input_surface', 'surface_geometry', 'surface_format', 'surface_usage', 'surface_timeout')]
            rows += [{'type': 'recorder_denial', 'run_id': RUN, 'cycle': cycle, 'operation': 'start', 'actual': 3}, step('reset')]
        rows += [step('release')]
        name = 'recorder-' + RUN + '-cycle' + str(cycle) + '.mp4'
        rows += [{'type': 'recorder_file', 'run_id': RUN, 'cycle': cycle, 'basename': name, 'bytes': 0, 'persisted': True}]
        files[name] = {'bytes': 0}
    rows += [{'type': 'recorder_summary', 'run_id': RUN, 'cycles': 2, 'candidate_ok': True, 'independent_decode_required': True}]
    return rows, files


def check(rows, files):
    return V.denied_results('\n'.join(json.dumps(r) for r in rows), RUN, UID, files)


class RecorderPermissionBoundary(unittest.TestCase):
    def test_prepare_or_start_denial_requires_full_configuration_and_cleanup(self):
        for prepared in (False, True):
            rows, files = denial(prepared)
            self.assertTrue(check(rows, files)['same_artifact_positive_backend_controls_required'])
            for mutation in ('early_failure', 'release_failure', 'started', 'media_bytes', 'stale', 'root_uid', 'missing_cycle'):
                changed, changed_files = copy.deepcopy(rows), copy.deepcopy(files)
                if mutation == 'early_failure': changed[3]['actual'] = 3
                elif mutation == 'release_failure':
                    next(r for r in changed if r.get('name') == 'release')['actual'] = 3
                elif mutation == 'started':
                    changed.insert(-1, {'type': 'recorder_state', 'run_id': RUN, 'cycle': 1, 'state': 2})
                elif mutation == 'media_bytes':
                    next(iter(changed_files.values()))['bytes'] = 1024
                elif mutation == 'stale': changed[5]['run_id'] = 'b' * 32
                elif mutation == 'root_uid': changed[0]['uid'] = 0
                else: changed = [r for r in changed if r.get('cycle') != 2]
                with self.subTest(prepared=prepared, mutation=mutation), self.assertRaises(ValueError):
                    check(changed, changed_files)

    def test_denied_start_success_or_frame_delivery_is_always_failure(self):
        rows, files = denial(True)
        for payload in ({'type': 'recorder_frame', 'frame': 0}, {'type': 'recorder_pause'}):
            changed = copy.deepcopy(rows)
            changed.insert(-1, {**payload, 'run_id': RUN, 'cycle': 1})
            with self.assertRaises(ValueError): check(changed, files)
        changed = copy.deepcopy(rows)
        next(r for r in changed if r.get('operation') == 'start')['actual'] = 0
        with self.assertRaises(ValueError): check(changed, files)
        for truncated in ([], rows[:1], rows[:2]):
            with self.assertRaises(ValueError): check(truncated, files)


if __name__ == '__main__':
    unittest.main()
