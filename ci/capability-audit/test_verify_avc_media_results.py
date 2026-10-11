"""Synthetic media result fixtures only, not guest acceptance."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from verify_avc_media_results import BOUNDARIES, RGBA_BOUNDARY, encoder_steps, decoder_steps, expected_y, PTS, INTERVAL, verify

RUN = '59671e19c36640e1a587bc11eb2e9a3d'
UID = 20010036
IDENTITY = json.dumps({'applicationInfo': {'uid': UID, 'appPrivilegeLevel': 'normal', 'isSystemApp': False}})


def rows():
    result = [dict(type='identity', run_id=RUN, uid=UID, euid=UID)]

    def step(sequence, key):
        for name, code in sequence:
            result.append(dict(type='step', run_id=RUN, profile=key[0], mode=key[1], cycle=key[2],
                               name=name, actual=code, expected=code, passed=True))

    step(BOUNDARIES, (-1, -1, -1))
    step(RGBA_BOUNDARY, (-2, -2, -2))
    for profile in (0, 8):
        for mode in (0, 1, 2):
            for cycle in (1, 2, 3):
                key = profile, mode, cycle
                common = dict(run_id=RUN, profile=profile, mode=mode, cycle=cycle)
                step(encoder_steps(mode, cycle), key)
                result.append(dict(common, type='bitstream', pts=0, bytes=24, flags=8,
                                   sps_profile=66 if profile == 0 else 77))
                for frame in range(4):
                    result.append(dict(common, type='bitstream', pts=PTS + frame * INTERVAL,
                                       bytes=200, flags=2 if frame in (0, 2) else 0, sps_profile=-1))
                result.append(dict(common, type='bitstream', pts=PTS + 4 * INTERVAL, bytes=0, flags=1, sps_profile=-1))
                step(decoder_steps(cycle), key)
                for frame in range(4):
                    result.append(dict(common, type='pixels', frame=frame, pts=PTS + frame * INTERVAL,
                                       width=64, height=64, stride=64, format=1,
                                       expected_y=expected_y(RUN, frame, cycle),
                                       samples=4096, absolute_error=123, passed=True))
                step([('all_decoded_frames', 1)], key)
                result.append(dict(common, type='cycle', frames=4, passed=True))
    result.append(dict(type='summary', run_id=RUN, cycles=18, frames=72, passed=True))
    return result


def render(values):
    return '\n'.join(json.dumps(row) for row in values)


class AvcMediaVerifierTests(unittest.TestCase):
    def test_actual_rate_control_contract_and_strict_CQ_boundary(self):
        source = (Path(__file__).parent / 'probes/avc_media.cpp').read_text()
        self.assertIn('mode == BITRATE_MODE_CQ ?', source)
        self.assertIn('"dynamic_bitrate_cq_rejected"', source)
        self.assertEqual(dict(encoder_steps(0))['dynamic_bitrate'], 0)
        self.assertEqual(dict(encoder_steps(1))['dynamic_bitrate'], 0)
        self.assertEqual(dict(encoder_steps(2))['dynamic_bitrate_cq_rejected'], 3)
        broken = rows()
        for row in broken:
            if row.get('name') == 'dynamic_bitrate_cq_rejected':
                row.update(actual=0, expected=0)
        with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)

    def test_full_fixture_and_bm_prefix(self):
        self.assertEqual(len(verify(render(rows()), RUN, IDENTITY)), 710)
        verify(render(rows()), RUN, 'org.harmonycontrib.capabilityaudit:\n' + IDENTITY)

    def test_partial_stale_reordered_duplicate_cannot_pass(self):
        complete = rows()
        for broken in (complete[:-1], list(reversed(complete)), complete * 2, complete[:200] + complete[201:]):
            with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)
        for index in (0, 15, 20, 30, 100, 709):
            broken = rows()
            broken[index]['run_id'] = 'a' * 32
            with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)

    def test_false_status_or_tampered_step_codes_cannot_pass(self):
        for index, row in enumerate(rows()):
            if row['type'] != 'step': continue
            for key, value in (('actual', 9), ('expected', 9), ('actual', True), ('passed', 1), ('name', 'fake-success')):
                broken = rows()
                broken[index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    verify(render(broken), RUN, IDENTITY)

    def test_actual_profile_timestamp_idr_bytes_and_eos_are_required(self):
        for index, row in enumerate(rows()):
            if row['type'] != 'bitstream': continue
            changes = [('bytes', True), ('flags', 16)]
            if row['flags'] == 8: changes += [('sps_profile', 100), ('bytes', 0)]
            elif row['flags'] == 1: changes += [('bytes', 12)]
            else:
                changes += [('pts', 0), ('bytes', 0), ('bytes', 1048577)]
                if row['pts'] == PTS + 2 * INTERVAL: changes += [('flags', 0)]
            for key, value in changes:
                broken = rows()
                broken[index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    verify(render(broken), RUN, IDENTITY)

    def test_every_decoded_frame_requires_raw_challenge_metrics(self):
        index = next(index for index, row in enumerate(rows()) if row['type'] == 'pixels')
        for key, value in (('frame', -1), ('pts', PTS + 1), ('width', 0), ('height', 0), ('stride', 63),
                           ('format', 2), ('expected_y', 0), ('samples', 4095), ('absolute_error', 32769),
                           ('absolute_error', -1), ('samples', True), ('passed', 1)):
            broken = rows()
            broken[index][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)
        broken = rows()
        broken[index + 1] = copy.deepcopy(broken[index])
        with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)

    def test_privileged_or_mismatched_application_identity_fails(self):
        for key, value in (('appPrivilegeLevel', 'system_basic'), ('isSystemApp', True), ('uid', 0), ('uid', UID + 1)):
            identity = json.loads(IDENTITY)
            identity['applicationInfo'][key] = value
            with self.assertRaises(ValueError): verify(render(rows()), RUN, json.dumps(identity))

    def test_cli_keeps_failed_native_records_and_does_not_claim_full_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (('archive', 'host fixture only'), ('results', render(rows()[:-1])), ('identity', IDENTITY), ('inputs', '{}')):
                (root / name).write_text(data)
            completed = subprocess.run([sys.executable, str(Path(__file__).with_name('verify_avc_media_results.py')),
                '--archive', str(root / 'archive'), '--results', str(root / 'results'),
                '--application-identity', str(root / 'identity'), '--run-id', RUN,
                '--inputs', str(root / 'inputs'), '--arch', 'arm64',
                '--output', str(root / 'report')], capture_output=True)
            evidence = json.loads((root / 'report').read_text())
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(evidence['status'], 'fail')
            self.assertEqual(len(evidence['observations']), 709)
            for key in ('first_artifact_behavior_gate_passed', 'hardware_codec_tested', 'hevc_tested',
                        'mathematical_CBR_conformance_tested'):
                self.assertFalse(evidence[key])

    def test_real_RGBA_conversion_and_truncated_error_are_required(self):
        complete = rows()
        for index, row in enumerate(complete):
            if row.get('type') == 'pixels' and row.get('cycle') == 3:
                broken = rows()
                frame = row['frame']
                broken[index]['expected_y'] = 32 + ((ord(RUN[frame]) + frame + 3) % 16) * 8
                with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)
        for name, _ in RGBA_BOUNDARY:
            broken = rows()
            index = next(i for i, row in enumerate(broken) if row.get('name') == name)
            broken[index]['actual'] = 123
            with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)
        source = (Path(__file__).parent / 'probes/avc_media.cpp').read_text()
        self.assertIn('OH_AVCodecBufferAttr attr = {kPts, size - 1, 0, AVCODEC_BUFFER_FLAGS_NONE}', source)
        self.assertIn('"truncated_rgba_error", error, AV_ERR_UNKNOWN', source)
        self.assertIn('AV_PIXEL_FORMAT_RGBA', source)


if __name__ == '__main__':
    unittest.main()
