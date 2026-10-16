#!/usr/bin/env python3
"""Verify actual ordinary Recorder permission boundaries and independent AV decode."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

from verify_audio_capture_results import verify_transport, verify_producer, sha, checked_file
from batch_media_recorder_challenge import verify as verify_decode, load_reference

SCOPE = 'ordinary_public_AVRecorder_independent_AAC_AVC_decode_and_real_MIC_UI_token'


def denied_results(text, run, uid, files):
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if (len(rows) < 3 or any(not isinstance(r, dict) or r.get('run_id') != run for r in rows) or
            rows[0] != {'type': 'recorder_identity', 'run_id': run, 'uid': uid, 'euid': uid, 'expected_denied': True} or
            rows[-1] != {'type': 'recorder_summary', 'run_id': run, 'cycles': 2, 'candidate_ok': True,
                         'independent_decode_required': True}):
        raise ValueError('actual denied Recorder identity/summary missing')
    if (rows[1].get('type') != 'recorder_step' or rows[1].get('cycle') != 0 or
            rows[1].get('name') != 'video_challenge' or rows[1].get('actual') != 0):
        raise ValueError('denied Recorder did not load the actual Surface input')
    allowed = {'recorder_step', 'recorder_denial', 'recorder_file', 'recorder_state', 'recorder_error'}
    if any(r.get('type') not in allowed or r.get('cycle') not in (1, 2) for r in rows[2:-1]):
        raise ValueError('denied Recorder produced frames or unexpected evidence')
    for cycle in (1, 2):
        group = [r for r in rows[2:-1] if r.get('cycle') == cycle]
        steps = [r for r in group if r['type'] == 'recorder_step']
        denials = [r for r in group if r['type'] == 'recorder_denial']
        if (not denials or denials[0].get('operation') != 'prepare' or
                any(type(r.get('actual')) is not int for r in denials)):
            raise ValueError('actual Recorder permission boundary missing')
        names = ['create', 'state_callback', 'error_callback', 'output_open']
        if denials[0]['actual'] == 0:
            if len(denials) != 2 or denials[1].get('operation') != 'start' or denials[1]['actual'] == 0:
                raise ValueError('denied Recorder unexpectedly started')
            names += ['input_surface', 'surface_geometry', 'surface_format', 'surface_usage', 'surface_timeout', 'reset']
        elif len(denials) != 1:
            raise ValueError('denied Recorder inconsistent Prepare failure')
        names += ['release']
        if [r.get('name') for r in steps] != names or any(type(r.get('actual')) is not int or
                r['actual'] != 0 or r.get('expected') != 0 for r in steps):
            raise ValueError('denied Recorder configuration/cleanup failed')
        if any(type(r.get('state')) is not int or r['state'] not in (0, 1, 5, 6)
               for r in group if r['type'] == 'recorder_state'):
            raise ValueError('denied Recorder emitted a recording state')
        records = [r for r in group if r['type'] == 'recorder_file']
        name = 'recorder-' + run + '-cycle' + str(cycle) + '.mp4'
        if len(records) != 1 or records[0].get('basename') != name or records[0].get('bytes') != 0 or records[0].get('persisted') is not True or files[name].get('bytes') != 0:
            raise ValueError('actual denied Recorder wrote media data')
    return {'mode': 'denied', 'cycles': 2, 'same_artifact_positive_backend_controls_required': True}


def verify(args):
    runtime, uid, denied, files, archive_sha = verify_transport(args, recorder=True)
    if (runtime.get('kind') != 'recorder' or
            runtime.get('recorder_runner_sha256') != sha(Path(__file__).with_name('media_recorder_runtime.py'))):
        raise ValueError('actual Recorder orchestration source differs')
    manifest, _, _ = load_reference(args.runtime.parent / 'challenge', args.run_id)
    video = runtime['video_input']
    if (sha(checked_file(video)) != manifest['video']['sha256'] or video.get('uid') != uid or video.get('mode') != 600):
        raise ValueError('actual ordinary Recorder Surface input differs')
    if denied:
        result = denied_results(args.results.read_text(), args.run_id, uid, files)
        decoders = None
    else:
        verify_producer(runtime)
        decoders = {}
        for name in ('ffmpeg', 'ffprobe'):
            path = Path(getattr(args, name)).resolve()
            decoders[name] = {'path': str(path), 'sha256': sha(path)}
        result = verify_decode(args.results, args.runtime.parent / 'private', args.runtime.parent / 'challenge',
                               args.application_identity, args.run_id, args.ffmpeg, args.ffprobe, args.decode_evidence)
    return {'status': 'pass', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch, 'boot_id': args.boot_id,
            'archive_sha256': archive_sha, 'expected_denied': denied, 'result': result, 'decoders': decoders,
            'inputs_sha256': {n: sha(getattr(args, n)) for n in ('results', 'inputs', 'runtime', 'hap', 'application_identity')},
            'verifier_sha256': sha(Path(__file__)), 'closed_requirements': [], 'first_artifact_behavior_gate_passed': False}


def verify_evidence(document, archive, boot_id, arch):
    archive = Path(archive)
    if (document.get('status') != 'pass' or document.get('persona') != 'media-recorder' or
            document.get('archive_sha256') != sha(archive) or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != []):
        raise ValueError('ordinary Recorder case differs from the actual archive/boot/ABI')
    result_path = Path(document['result'])
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('actual ordinary Recorder case result missing')
    root = result_path.parent
    paths = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/media-recorder-probe-inputs.json',
             'capture_runtime': root / 'capture/runtime.json'}
    if any(sha(path) != document.get(key + '_sha256') for key, path in paths.items()):
        raise ValueError('actual ordinary Recorder case evidence changed')
    saved = json.loads(result_path.read_text())
    decoders = saved.get('decoders') or {}
    # Re-run both real decoders into a new private directory. Prior decoded
    # bytes and an earlier pass field cannot satisfy package acceptance.
    with tempfile.TemporaryDirectory(prefix='qemu-recorder-replay-') as directory:
        actual = verify(SimpleNamespace(archive=archive, run_id=document['run_id'], arch=arch, boot_id=boot_id,
            results=paths['raw_results'], inputs=paths['compiled_contract_inputs'], runtime=paths['capture_runtime'],
            hap=paths['hap'], application_identity=paths['ordinary_identity'], decode_evidence=Path(directory),
            ffmpeg=Path(decoders.get('ffmpeg', {}).get('path', '/opt/homebrew/bin/ffmpeg')),
            ffprobe=Path(decoders.get('ffprobe', {}).get('path', '/opt/homebrew/bin/ffprobe'))))
    if actual != saved:
        raise ValueError('ordinary Recorder summary differs from actual independently decoded evidence')
    return actual


def verify_batch(batch, archive, boot_id, arch):
    if (batch.get('status') != 'pass' or batch.get('scope') != SCOPE + '_grant_deny_grant' or
            batch.get('archive_sha256') != sha(archive) or batch.get('boot_id') != boot_id or
            batch.get('arch') != arch or batch.get('first_artifact_behavior_gate_passed') is not False or
            len(batch.get('cases', [])) != 3):
        raise ValueError('same-artifact ordinary Recorder grant/deny/grant batch required')
    seen, results = set(), []
    for case, denied in zip(batch['cases'], (False, True, False)):
        path = Path(case['evidence'])
        if sha(path) != case.get('sha256'):
            raise ValueError('ordinary Recorder batch case evidence changed')
        actual = verify_evidence(json.loads(path.read_text()), archive, boot_id, arch)
        if actual['expected_denied'] is not denied or actual['run_id'] in seen:
            raise ValueError('Recorder backend controls missing or caller nonce replayed')
        seen.add(actual['run_id'])
        results.append(actual)
    return results


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'runtime', 'hap', 'application-identity', 'output', 'decode-evidence'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--ffmpeg', type=Path, default=Path('/opt/homebrew/bin/ffmpeg'))
    p.add_argument('--ffprobe', type=Path, default=Path('/opt/homebrew/bin/ffprobe'))
    p.add_argument('--run-id', required=True)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    a = p.parse_args()
    try: result = verify(a)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
        result = {'status': 'fail', 'failures': [str(e)], 'first_artifact_behavior_gate_passed': False}
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(result['status'] != 'pass')
