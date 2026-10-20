#!/usr/bin/env python3
"""Small parser/pixel fixtures only; no codec, SDK, VM or runtime success model."""
import copy
import json
from pathlib import Path
import unittest

import media_pipeline578 as m

RUN = '19c3f8d21ad44e2db65a930fcb4d2df7'
FIXTURE = Path(__file__).with_name('fixtures')/'media_pipeline578'/'journal-parser-only.jsonl'


def frame(phase, tick, cycle=1):
    values = m.palette(RUN, cycle)[phase]+[224 if tick & (1 << n) else 32 for n in range(8)]
    data = bytearray()
    for y in range(m.DECODE_H):
        for x in range(m.DECODE_W):
            value = values[(y*8//m.DECODE_H)*8 + x*8//m.DECODE_W]
            data.extend((value, value, value))
    return bytes(data)


class Media578Parser(unittest.TestCase):
    def test_public_source_has_real_data_endpoints(self):
        source = m.source(RUN, 'screen-transcode')
        self.assertNotIn('__MEDIA578_', source)
        for method in ('createAVScreenCaptureRecorder', 'startRecording', 'stopRecording', 'setMicEnabled',
                       'setWindowPrivacyMode', 'createAVTranscoder', 'fdSrc', 'fdDst', '.prepare(', '.start(', '.cancel('):
            self.assertIn(method, source)
        self.assertEqual(len(m.palette(RUN)), 8)
        self.assertNotEqual(m.palette(RUN, 1), m.palette(RUN, 2))
        for bad in ('', RUN.upper(), RUN+'0'):
            with self.assertRaises(ValueError): m.source(bad, 'screen-transcode')

    def test_complete_line_clock_identity_and_no_summary_coercion(self):
        text = FIXTURE.read_text()
        rows = m.parse_journal(text, RUN, 'screen-deny')
        self.assertEqual(len(rows), 4)
        for mutate in ('truncate', 'clock', 'uid', 'seq', 'boolean'):
            changed = copy.deepcopy(rows)
            if mutate == 'truncate': data = text[:-1]
            else:
                if mutate == 'clock': changed[-1]['active_ms'] = -1
                if mutate == 'uid': changed[-1]['uid'] += 1
                if mutate == 'seq': changed[-1]['seq'] = True
                if mutate == 'boolean': changed[-1]['detail'] = '{"caller_completed":1,"independent_decode_required":true}'
                data = ''.join(json.dumps(r)+'\n' for r in changed)
            with self.assertRaises(ValueError, msg=mutate): m.parse_journal(data, RUN, 'screen-deny')
        with self.assertRaises(ValueError): m.strict_json('{"pid":2,"pid":3}')
        with self.assertRaises(ValueError): m.strict_json('{"x":NaN}')

    def test_privacy_pixels_and_fresh_animation(self):
        rows = [frame(0, i) for i in range(8)] + [bytes(m.DECODE_W*m.DECODE_H*3)]*15 + [frame(2, i+50) for i in range(8)]
        pts = [i/10 for i in range(len(rows))]
        result = m.content(b''.join(rows), pts, RUN, [0, 0, 1, 1], privacy=True)
        self.assertEqual(result['animation_ticks'], {'0': 8, '2': 8})
        for corrupt in ('secret', 'after-stop', 'frozen', 'old-cycle', 'roi'):
            changed = rows.copy(); roi = [0, 0, 1, 1]
            if corrupt == 'secret': changed[12] = frame(1, 12)
            if corrupt == 'after-stop': changed[-1] = frame(3, 99)
            if corrupt == 'frozen': changed[:8] = [frame(0, 0)]*8
            if corrupt == 'old-cycle': changed[:8] = [frame(0, i, 2) for i in range(8)]
            if corrupt == 'roi': roi = [0, 0, 1.1, 1]
            with self.assertRaises(ValueError, msg=corrupt): m.content(b''.join(changed), pts, RUN, roi, privacy=True)

    def test_pts_reversal_and_stream_shape(self):
        probe = {'streams': [{'index': 0, 'codec_type': 'video', 'codec_name': 'h264', 'width': 640,
                             'height': 480, 'avg_frame_rate': '10/1'},
                            {'index': 1, 'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': '48000', 'channels': 2}],
                 'frames': [{'media_type': 'video', 'best_effort_timestamp_time': str(i/10)} for i in range(10)],
                 'packets': [{'stream_index': stream, 'dts_time': str(i/10), 'pts_time': str(i/10), 'duration_time': '.1'}
                             for stream in (0, 1) for i in range(10)]}
        self.assertEqual(len(m.inspect_probe(probe, (640, 480))[0]), 10)
        for corrupt in ('reverse', 'missing-audio', 'wrong-size', 'missing-duration'):
            value = copy.deepcopy(probe)
            if corrupt == 'reverse': value['frames'][5]['best_effort_timestamp_time'] = '0'
            if corrupt == 'missing-audio': value['streams'].pop()
            if corrupt == 'wrong-size': value['streams'][0]['width'] = 320
            if corrupt == 'missing-duration': value['packets'][0]['duration_time'] = 'nan'
            with self.assertRaises(ValueError, msg=corrupt): m.inspect_probe(value, (640, 480))

    def test_content_cli_cannot_accept_death_or_pass_summary(self):
        with self.assertRaisesRegex(ValueError, 'death cases require'):
            m.verify_files(None, None, None, RUN, 'screen-death', None, None, None, None)
        from verify_media_pipeline578_results import verify_batch
        with self.assertRaises(ValueError): verify_batch([{'status': 'pass'}]*11)


if __name__ == '__main__': unittest.main()
