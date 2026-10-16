#!/usr/bin/env python3
"""Replay independent token/UI/live-process/PCM evidence for active MIC revocation."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from verify_audio_capture_results import checked_file, sha, token, verify_transport, verify_producer
from batch_media_audio_event_challenge import verify as verify_pcm
from guest_ui import select_node

SCOPE = 'ordinary_public_MIC_live_revocation_without_process_kill_and_independent_PCM'


def verify_revocation(value, runtime, result, uid, run):
    ready, observation = value['ready'], value['token']
    # A revoke result must have the same real token observed around the public
    # dialog. No root grant, force-stop or replacement process can substitute.
    checked = dict(observation, operation='query', before=-1)
    state, token_id = token(checked, run, uid)
    if (state != -1 or observation.get('operation') != 'revoke' or
            type(observation.get('before')) is not int or observation['before'] != 0 or
            any(row['observation']['token_id'] != token_id for row in runtime['tokens']) or
            value.get('process_before') != value.get('process_after')):
        raise ValueError('active revocation did not affect the same real token and live ordinary process')
    process = value['process_before']
    if (process.get('uid') != uid or type(process.get('pid')) is not int or process['pid'] <= 0 or
            type(process.get('starttime')) is not int or process['starttime'] <= 0):
        raise ValueError('same live unprivileged process identity required')
    signal, ack = result['signals'][0], result['acks'][0]
    if (ready.get('run_id') != run or ready.get('action') != 'revoke' or ready.get('uid') != uid or
            ready.get('nonce') != signal['nonce'] or value.get('ack_nonce') != signal['nonce'] or
            ready.get('monotonic_ns') != signal['monotonic_ns'] or ready.get('state_result') != 0 or
            ready.get('state') != 2 or ready.get('frames_result') != 0 or type(ready.get('frames')) is not int or
            ready['frames'] <= 0 or type(ready.get('copied_bytes')) is not int or ready['copied_bytes'] <= 0 or
            not signal['monotonic_ns'] <= observation['before_ns'] <= observation['after_ns'] <= ack['monotonic_ns']):
        raise ValueError('revoke must occur strictly inside the fresh native live-stream handshake')
    checkpoint = checked_file(value['checkpoint'])
    actual = checked_file(runtime['files']['audio-event-' + run + '-mode0-baseline.pcm'])
    if sha(checkpoint) != sha(actual):
        raise ValueError('before-revoke PCM differs from the actual native checkpoint')
    controls = value['ack_files']
    prefix = 'audio-event-' + run + '-revoke-ack'
    if len(controls) != 2 or controls[0] != prefix or not controls[1].startswith(prefix + '.publish-'):
        raise ValueError('actual exclusive revocation ACK publication evidence missing')
    for name in controls:
        record = runtime['files'][name]
        if (record.get('uid') != uid or record.get('mode') != 600 or record.get('bytes') != 33 or
                checked_file(record).read_bytes() != (signal['nonce'] + '\n').encode()):
            raise ValueError('actual revocation ACK was not private and owned by the ordinary caller')
    return {'token_id': token_id, 'actual_revoke_interval_ns': [observation['before_ns'], observation['after_ns']],
            'same_live_process': process}


def verify(args):
    runtime, uid, _, _, archive_sha = verify_transport(args, audio_event=True)
    if (runtime.get('kind') != 'active-microphone-revocation' or
            runtime.get('revoke_runner_sha256') != sha(Path(__file__).with_name('audio_revoke_runtime.py'))):
        raise ValueError('actual active revocation orchestration source differs')
    action = runtime['start_action']
    layout = Path(action['layout'])
    if (sha(layout) != action['layout_sha256'] or select_node(json.loads(layout.read_text()),
            'org.harmonycontrib.capabilityaudit', text='Start audio audit', clickable=True) != action['selected_node']):
        raise ValueError('actual ordinary stream-start action missing')
    verify_producer(runtime)
    result = verify_pcm(args.results, args.runtime.parent / 'private', args.runtime.parent / 'challenge/challenge.json',
                        args.runtime.parent / 'challenge/challenge.pcm', args.application_identity, args.run_id, 0)
    revoke = verify_revocation(runtime['revocation'], runtime, result, uid, args.run_id)
    lifecycle = [json.loads(checked_file(item).read_text()) for name, item in sorted(runtime['files'].items())
                 if '-background-' in name]
    if ([r.get('event') for r in lifecycle] != ['native_start_requested', 'background_not_requested', 'native_finished'] or
            any(r.get('run_id') != args.run_id or r.get('mode') != 0 for r in lifecycle) or
            json.loads(lifecycle[0]['detail']) != {'needs_background': False} or
            json.loads(lifecycle[-1]['detail']) != {'native_status': 1, 'native_still_running': False, 'background_failed': False}):
        raise ValueError('ordinary foreground UIAbility did not observe actual native completion')
    return {'status': 'pass', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch, 'boot_id': args.boot_id,
            'archive_sha256': archive_sha, 'result': result, 'revocation': revoke,
            'inputs_sha256': {n: sha(getattr(args, n)) for n in ('results', 'inputs', 'runtime', 'hap', 'application_identity')},
            'verifier_sha256': sha(Path(__file__)), 'closed_requirements': [], 'first_artifact_behavior_gate_passed': False}


def verify_evidence(document, archive, boot_id, arch):
    archive = Path(archive)
    if (document.get('status') != 'pass' or document.get('persona') != 'audio-revoke' or
            document.get('archive_sha256') != sha(archive) or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != []):
        raise ValueError('ordinary active revoke differs from actual archive/boot/ABI')
    result_path = Path(document['result'])
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('actual ordinary revocation result missing')
    root = result_path.parent
    paths = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/media-audio-event-probe-inputs.json',
             'capture_runtime': root / 'capture/runtime.json'}
    if any(sha(path) != document.get(key + '_sha256') for key, path in paths.items()):
        raise ValueError('actual active revocation evidence changed')
    actual = verify(SimpleNamespace(archive=archive, run_id=document['run_id'], arch=arch, boot_id=boot_id,
        results=paths['raw_results'], inputs=paths['compiled_contract_inputs'], runtime=paths['capture_runtime'],
        hap=paths['hap'], application_identity=paths['ordinary_identity']))
    if actual != json.loads(result_path.read_text()):
        raise ValueError('active revocation summary differs from independent replay')
    return actual


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'runtime', 'hap', 'application-identity', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    a = p.parse_args()
    try: result = verify(a)
    except (OSError, ValueError, KeyError, TypeError) as e:
        result = {'status': 'fail', 'failures': [str(e)], 'first_artifact_behavior_gate_passed': False}
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(result['status'] != 'pass')
