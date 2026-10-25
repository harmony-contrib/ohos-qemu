#!/usr/bin/env python3
"""Real AVScreenCapture -> AVTranscoder bytes, independent FFmpeg consumers.

These are additional media cases. No aggregate requirement or first-artifact gate
is closed by this module. Owner/HAP/UI/token provenance remains mandatory in the
existing ordinary-app runner; `verify_files` proves media content only.
"""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCENARIOS = ('screen-transcode', 'screen-deny', 'screen-revoke', 'screen-death',
             'transcode-cancel', 'transcode-death')
DECODE_W, DECODE_H = 160, 120
MAX_BYTES, MAX_FRAMES = 16 * 1024 * 1024, 480


def sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular media input required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def strict_json(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('duplicate media JSON key')
            value[key] = item
        return value
    def constant(_): raise ValueError('nonfinite media JSON value')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def nonce(run):
    if re.fullmatch('[0-9a-f]{32}', run or '') is None:
        raise ValueError('fresh 128-bit caller run required')
    return run


def palette(run, cycle=None):
    nonce(run)
    values = [[40 + 12 * (hashlib.sha256((run + ':' + str(phase) + ':' + str(i)).encode()).digest()[0] % 15)
             for i in range(56)] for phase in range(8)]
    return values if cycle is None else values[(cycle-1)*4:cycle*4]


def source(run, scenario):
    if scenario not in SCENARIOS:
        raise ValueError('explicit media scenario required')
    return (HERE / 'media_pipeline578_probe.ets').read_text().replace('__MEDIA578_RUN__', nonce(run)).replace(
        '__MEDIA578_SCENARIO__', scenario).replace('__MEDIA578_PALETTE__', json.dumps(palette(run)))


def parse_journal(text, run, scenario, *, incomplete=False):
    nonce(run)
    if scenario not in SCENARIOS or len(text) > 2 * 1024 * 1024 or not text.endswith('\n'):
        raise ValueError('bounded complete-line media journal required')
    rows = [strict_json(line) for line in text.splitlines()]
    if not rows or len(rows) > 10000:
        raise ValueError('bounded nonempty actual media journal required')
    identity = None
    last_time = -1
    for seq, row in enumerate(rows):
        if (set(row) != {'run_id', 'scenario', 'seq', 'uid', 'pid', 'active_ms', 'event', 'cycle', 'detail'} or
                row['run_id'] != run or row['scenario'] != scenario or type(row['seq']) is not int or row['seq'] != seq or
                type(row['uid']) is not int or row['uid'] // 200000 != 100 or row['uid'] % 200000 < 10000 or
                type(row['pid']) is not int or row['pid'] <= 1 or type(row['cycle']) is not int or row['cycle'] not in (0, 1, 2, 3) or
                type(row['active_ms']) not in (int, float) or not math.isfinite(row['active_ms']) or
                row['active_ms'] < last_time or not isinstance(row['event'], str) or not row['event'] or
                not isinstance(row['detail'], str) or len(row['detail']) > 8192):
            raise ValueError('actual media journal identity/sequence/clock differs')
        current = row['uid'], row['pid']
        if identity is not None and current != identity:
            raise ValueError('caller identity changed inside journal')
        identity, last_time = current, row['active_ms']
    if rows[0]['event'] != 'identity' or rows[0]['cycle'] != 0:
        raise ValueError('first actual caller identity missing')
    if not incomplete:
        summary = strict_json(rows[-1]['detail']) if rows[-1]['event'] == 'summary' else {}
        if (rows[-1]['event'] != 'summary' or type(summary.get('caller_completed')) is not bool or
                type(summary.get('independent_decode_required')) is not bool or summary != {
                'caller_completed': True, 'independent_decode_required': True} or
                any(r['event'] in ('failure', 'transcode.error') or (r['event'] == 'screen.error' and scenario != 'screen-deny') for r in rows)):
            raise ValueError('actual caller failed or did not finish')
        cleanup = [r for r in rows if r['event'] == 'cleanup.end']
        if len(cleanup) != 1 or json.loads(cleanup[0]['detail']) != []:
            raise ValueError('actual local resource cleanup did not finish')
    else:
        boundary = event(rows, 'owner.await-death')
        if (boundary['detail'] != ('screen' if scenario == 'screen-death' else 'transcode') or
                any(r['event'] != 'transcode.progress' for r in rows[boundary['seq']+1:]) or
                any(r['event'] in ('failure', 'transcode.complete', 'screen.error', 'transcode.error') for r in rows)):
            raise ValueError('durable actual death boundary missing; not a simulated death pass')
    return rows


def event(rows, name, *, detail=None):
    found = [r for r in rows if r['event'] == name and (detail is None or r['detail'] == detail)]
    if len(found) != 1:
        raise ValueError('one actual event required: ' + name + ':' + str(detail))
    return found[0]


def ordered(rows, names):
    points = [event(rows, n) for n in names]
    if [r['seq'] for r in points] != sorted({r['seq'] for r in points}):
        raise ValueError('actual API call/callback order differs')
    return points


def rational(value):
    if not isinstance(value, str) or re.fullmatch(r'-?\d+(?:/\d+)?', value) is None:
        raise ValueError('actual media rational required')
    a, _, b = value.partition('/')
    if b and int(b) == 0:
        raise ValueError('invalid media rational')
    return int(a) / (int(b) if b else 1)


def inspect_probe(probe, dimensions):
    streams = probe.get('streams')
    if not isinstance(streams, list) or len(streams) != 2:
        raise ValueError('exactly one actual audio and video stream required')
    video = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if (len(video) != 1 or len(audio) != 1 or video[0].get('codec_name') != 'h264' or
            (video[0].get('width'), video[0].get('height')) != tuple(dimensions) or
            audio[0].get('codec_name') != 'aac' or audio[0].get('sample_rate') != '48000' or
            audio[0].get('channels') != 2 or not 5 <= rational(video[0].get('avg_frame_rate')) <= 60):
        raise ValueError('real H264/AAC output format/geometry differs')
    frames = probe.get('frames', [])
    packets = probe.get('packets', [])
    if 'packets_and_frames' in probe:
        if frames or packets:
            raise ValueError('ambiguous actual decoder records')
        frames = [r for r in probe['packets_and_frames'] if r.get('type') == 'frame']
        packets = [r for r in probe['packets_and_frames'] if r.get('type') == 'packet']
    video_frames = [r for r in frames if r.get('media_type') == 'video']
    if not 8 <= len(video_frames) <= MAX_FRAMES:
        raise ValueError('bounded real decoded video frames required')
    pts = [float(r['best_effort_timestamp_time']) for r in video_frames]
    if (not all(math.isfinite(p) for p in pts) or any(b <= a or b-a > .5 for a, b in zip(pts, pts[1:])) or
            not .5 <= pts[-1] - pts[0] <= 15):
        raise ValueError('video PTS gaps/reversal/duration invalid')
    spans = []
    for stream in (video[0], audio[0]):
        rows = [p for p in packets if p.get('stream_index') == stream['index']]
        if not rows or len(rows) > 3000:
            raise ValueError('bounded actual packets for both streams required')
        dts = [float(p['dts_time']) for p in rows]
        times = [float(p['pts_time']) for p in rows]
        durations = [float(p['duration_time']) for p in rows]
        if (not all(math.isfinite(p) for p in dts + times + durations) or
                any(b <= a for a, b in zip(dts, dts[1:])) or any(d <= 0 or d > .5 for d in durations)):
            raise ValueError('audio/video packet DTS or duration invalid')
        spans.append((min(times), max(t + d for t, d in zip(times, durations))))
    if abs(spans[0][0]-spans[1][0]) > .25 or abs(spans[0][1]-spans[1][1]) > .3:
        raise ValueError('actual audio/video timeline diverged')
    return pts, spans


def decode(ffmpeg, ffprobe, media, dimensions, output):
    media, output = Path(media), Path(output)
    if media.is_symlink() or not media.is_file() or not 1 <= media.stat().st_size <= MAX_BYTES:
        raise ValueError('bounded actual output media file required')
    output.mkdir(parents=True, exist_ok=False)
    tools = {}
    for name, path in (('ffmpeg', ffmpeg), ('ffprobe', ffprobe)):
        path = Path(path).resolve()
        tools[name] = {'path': str(path), 'sha256': sha(path)}
    commands = []
    def run(argv, name):
        command = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=60, check=False)
        (output / (name + '.stdout')).write_bytes(command.stdout)
        (output / (name + '.stderr')).write_bytes(command.stderr)
        commands.append({'argv': [str(x) for x in argv], 'returncode': command.returncode})
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        if command.returncode != 0 or command.stderr:
            raise ValueError('independent actual decoder failed: ' + name)
        return command.stdout
    raw = run([tools['ffprobe']['path'], '-v', 'error', '-show_streams', '-show_frames', '-show_packets',
               '-of', 'json', str(media)], 'probe')
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('excessive actual decoder records')
    probe = strict_json(raw)
    pts, spans = inspect_probe(probe, dimensions)
    rgb, pcm = output / 'video.rgb', output / 'audio.pcm'
    run([tools['ffmpeg']['path'], '-nostdin', '-v', 'error', '-threads', '1', '-i', str(media), '-map', '0:v:0',
         '-vf', 'scale=160:120:flags=area', '-frames:v', str(MAX_FRAMES + 1), '-t', '16',
         '-fps_mode', 'passthrough', '-enc_time_base', '1:1000000', '-pix_fmt', 'rgb24', '-f', 'rawvideo', str(rgb)], 'video')
    run([tools['ffmpeg']['path'], '-nostdin', '-v', 'error', '-threads', '1', '-i', str(media), '-map', '0:a:0',
         '-t', '16', '-c:a', 'pcm_s16le', '-f', 's16le', str(pcm)], 'audio')
    if rgb.stat().st_size != len(pts) * DECODE_W * DECODE_H * 3:
        raise ValueError('independent decoded frame count differs from PTS records')
    if not 48000 * 4 // 2 <= pcm.stat().st_size <= 48000 * 4 * 16 or pcm.stat().st_size % 4:
        raise ValueError('actual independent stereo PCM output is truncated/empty/excessive')
    return probe, pts, spans, rgb.read_bytes(), pcm.read_bytes(), tools


def tile_samples(frame, roi):
    if (len(frame) != DECODE_W * DECODE_H * 3 or len(roi) != 4 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in roi)):
        raise ValueError('actual decoded frame/ROI required')
    left, top, width, height = roi
    if min(left, top) < 0 or min(width, height) < .1 or left+width > 1 or top+height > 1:
        raise ValueError('actual visible Canvas must fit inside the captured display')
    values = []
    for i in range(64):
        x = min(DECODE_W-1, int((left + (i % 8 + .5) * width / 8) * DECODE_W))
        y = min(DECODE_H-1, int((top + (i // 8 + .5) * height / 8) * DECODE_H))
        values.append(tuple(frame[(y*DECODE_W+x)*3:(y*DECODE_W+x)*3+3]))
    return values


def content(rgb, pts, run, roi, *, privacy, cycle=1):
    expected = palette(run, cycle)
    stride = DECODE_W * DECODE_H * 3
    if len(rgb) != len(pts) * stride:
        raise ValueError('frame bytes/PTS length differs')
    matches, ticks = [], {0: set(), 2: set()}
    previous_tick = {0: None, 2: None}
    for i in range(len(pts)):
        samples = tile_samples(rgb[i*stride:(i+1)*stride], roi)
        errors = [[abs(channel - value) for pixel, value in zip(samples[:56], values) for channel in pixel]
                  for values in expected]
        candidates = [p for p, err in enumerate(errors) if max(err) <= 32 and sum(err)/len(err) <= 12]
        if len(candidates) > 1:
            raise ValueError('ambiguous nonce texture')
        phase = candidates[0] if candidates else (-1 if max(c for pixel in samples for c in pixel) <= 32 else -2)
        if phase in (1, 3):
            raise ValueError('private or post-stop fresh pixels leaked into recorded output')
        if phase in ticks:
            bits = [sum(p)/3 for p in samples[56:]]
            if any(min(abs(v-32), abs(v-224)) > 35 for v in bits):
                raise ValueError('actual animation counter is corrupted')
            tick = sum((v > 128) << n for n, v in enumerate(bits))
            if previous_tick[phase] is not None and (tick-previous_tick[phase]) % 256 > 8:
                raise ValueError('actual rendered frames were reordered or their animation time skipped')
            previous_tick[phase] = tick
            ticks[phase].add(tick)
        matches.append(phase)
    for phase in (0, 2) if privacy else (0,):
        if matches.count(phase) < 6 or len(ticks[phase]) < 5:
            raise ValueError('actual fresh moving screen content is missing/frozen')
    if privacy:
        last_zero = max(i for i, p in enumerate(matches) if p == 0)
        first_two = min(i for i, p in enumerate(matches) if p == 2)
        if first_two <= last_zero:
            raise ValueError('actual privacy/recovery frame order differs')
        blacks = [i for i in range(last_zero+1, first_two) if matches[i] == -1]
        if not blacks or pts[blacks[-1]]-pts[blacks[0]] < .9:
            raise ValueError('actual privacy interval was not masked')
        if any(matches[i] != -1 for i in range(blacks[0], blacks[-1]+1)):
            raise ValueError('privacy mask leaked nonblack frames')
        if sum(p == -2 for p in matches) > max(10, len(pts)//8):
            raise ValueError('excessive unrelated frames obscure actual screen challenge')
    return {'frames': len(pts), 'phase_frames': {str(p): matches.count(p) for p in (0, -1, 2)},
            'animation_ticks': {str(k): len(v) for k, v in ticks.items()}}


def audio_content(raw, reference):
    # Reuse the existing independent root PCM challenge and lossy AAC matcher,
    # never a waveform or success report supplied by the ordinary HAP.
    from batch_media_recorder_challenge import pcm
    actual = pcm.pcm_values(raw)
    expected = reference if isinstance(reference, array) else pcm.pcm_values(reference)
    window = pcm.WINDOW
    matches = []
    # AAC priming and final encoder padding are bounded, not whole-stream skips.
    for frame in range(12000, len(actual)//2 - window - 12000, window):
        matches.append(pcm.match_window(actual[frame*2:(frame+window)*2], expected))
    if len(matches) < 2:
        raise ValueError('actual continuous independent audio challenge is missing')
    for a, b in zip(matches, matches[1:]):
        drift = ((b['source_frame']-a['source_frame']-window+24000) % 48000)-24000
        if abs(drift) > 256:
            raise ValueError('recorded stereo audio skipped/repeated source time')
    return {'windows': len(matches), 'minimum_correlation': min(m['minimum_correlation'] for m in matches)}


def transcode_timeline(source_pts, output_pts):
    if abs(len(source_pts)-len(output_pts)) > 1:
        raise ValueError('actual transcoder dropped/duplicated decoded video frames')
    if abs((output_pts[-1]-output_pts[0])-(source_pts[-1]-source_pts[0])) > .15:
        raise ValueError('actual transcoder dropped/extended video duration')
    if any(abs((a-source_pts[0])-(b-output_pts[0])) > .06 for a, b in zip(source_pts, output_pts)):
        raise ValueError('actual transcoder changed video frame presentation time')


def verify_files(results, private, challenge, run, scenario, roi, ffmpeg, ffprobe, output):
    if scenario in ('screen-death', 'transcode-death'):
        raise ValueError('death cases require original Owner process/custody replay; content-only verification cannot accept')
    rows = parse_journal(Path(results).read_text(), run, scenario)
    private, challenge, output = Path(private), Path(challenge), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    from batch_media_recorder_challenge import load_reference
    _, reference, _ = load_reference(challenge, run)
    # load_reference returns independent PCM samples then video bytes; the HAP never receives
    # the independent PCM reference. Its root-only actual producer is verified
    # separately by the original owner transport/token verifier.
    checks = []
    count = 2 if scenario == 'screen-transcode' else 1
    for cycle in range(1, count+1):
        group = [r for r in rows if r['cycle'] == cycle]
        capture = private / f'media578-{run}-{cycle}-capture.mp4'
        ordered(group, ['screen.create', 'screen.init', 'screen.mic', 'screen.start.request'])
        if scenario == 'screen-deny':
            event(group, 'screen.state', detail='1'); event(group, 'screen.release')
            if any(r['event'] == 'screen.running' or (r['event'] == 'screen.state' and r['detail'] == '0') for r in group):
                raise ValueError('denied screen capture unexpectedly ran')
            if not capture.is_file() or capture.stat().st_size != 0:
                raise ValueError('denied screen capture produced bytes')
            continue
        event(group, 'screen.state', detail='0')
        if scenario == 'screen-revoke':
            ordered(group, ['screen.running', 'owner.await-revoke', 'screen.revoked', 'screen.release'])
            event(group, 'screen.state', detail='2')
        else:
            ordered(group, ['screen.running', 'screen.stop.request', 'screen.stop.return', 'screen.release'])
            a, b = event(group, 'window.privacy', detail='true'), event(group, 'window.privacy', detail='false')
            if b['active_ms']-a['active_ms'] < 1500:
                raise ValueError('actual privacy interval too short')
        probe, pts, spans, rgb, raw, tools = decode(ffmpeg, ffprobe, capture, (640, 480), output / f'capture-{cycle}')
        pixels = content(rgb, pts, run, roi, privacy=scenario != 'screen-revoke', cycle=cycle)
        sound = audio_content(raw, reference)
        checks.append({'cycle': cycle, 'kind': 'screen', 'sha256': sha(capture), 'pixels': pixels, 'audio': sound})
        if scenario in ('screen-transcode', 'transcode-cancel'):
            ordered(group, ['transcode.create', 'transcode.fds', 'transcode.prepare', 'transcode.start', 'transcode.release'])
            if int(event(group, 'transcode.fds')['detail']) != capture.stat().st_size:
                raise ValueError('actual converter input is not this captured file')
            target = private / f'media578-{run}-{cycle}-transcoded.mp4'
            if scenario == 'transcode-cancel':
                ordered(group, ['transcode.start', 'transcode.pause', 'transcode.cancel', 'transcode.release'])
                if any(r['event'] == 'transcode.complete' for r in group):
                    raise ValueError('cancellation completed a full conversion')
                # Partial canceled files are retained; their size/stability and
                # descriptor cleanup require the original owner observations.
                if not target.is_file() or target.stat().st_size > MAX_BYTES:
                    raise ValueError('canceled output custody missing')
                checks.append({'cycle': cycle, 'kind': 'canceled', 'sha256': sha(target)})
                continue
            ordered(group, ['transcode.start.request', 'transcode.complete', 'transcode.release'])
            _, out_pts, out_spans, out_rgb, out_raw, _ = decode(ffmpeg, ffprobe, target, (320, 240), output / f'transcode-{cycle}')
            transcode_timeline(pts, out_pts)
            if abs(len(out_raw)-len(raw)) > 4*4096:
                raise ValueError('actual transcoder dropped/extended audio samples')
            checks.append({'cycle': cycle, 'kind': 'transcoded', 'sha256': sha(target),
                           'pixels': content(out_rgb, out_pts, run, roi, privacy=True, cycle=cycle),
                           'audio': audio_content(out_raw, reference)})
    return {'status': 'content_verified_NOT_runtime_acceptance', 'run_id': run, 'scenario': scenario,
            'checks': checks, 'closed_requirements': [], 'first_artifact_behavior_gate_passed': False,
            'ordinary_hap_owner_ui_token_and_cleanup_replay_required': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    render = sub.add_parser('source')
    render.add_argument('--run-id', required=True); render.add_argument('--scenario', choices=SCENARIOS, required=True)
    verify = sub.add_parser('verify-content')
    for name in ('results', 'private', 'challenge', 'ffmpeg', 'ffprobe', 'output'):
        verify.add_argument('--' + name, type=Path, required=True)
    verify.add_argument('--run-id', required=True); verify.add_argument('--scenario', choices=SCENARIOS, required=True)
    verify.add_argument('--roi', required=True, help='actual Canvas rect / actual display, left,top,width,height')
    args = parser.parse_args()
    if args.command == 'source':
        print(source(args.run_id, args.scenario), end='')
    else:
        roi = [float(v) for v in args.roi.split(',')]
        print(json.dumps(verify_files(args.results, args.private, args.challenge, args.run_id, args.scenario,
                                     roi, args.ffmpeg, args.ffprobe, args.output), indent=2))


if __name__ == '__main__':
    main()
