#!/usr/bin/env python3
"""Verify ordinary public Capturer against independent PCM, token and UI evidence.

This verifies one grant or denial case. The suite must require grant/deny/grant
on the same new artifact; revocation, focus, Recorder and the full gate are separate.
"""
import argparse
import json
from pathlib import Path
import re
from types import SimpleNamespace

import audio_capture_contract as contract
from audio_capture_permission import select as select_permission
from batch_media_audio_capture_challenge import verify as verify_pcm, CONFIG_STEPS
from run_normal_hap_probe import require_normal_identity
from spring_loading_input import binding
from run_root_probe import digest

SCOPE = 'ordinary_public_MIC_Capturer_independent_PCM_token_UI_lifecycle_and_clock'
def sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular actual microphone evidence required')
    return digest(path)


def token(value, run, uid, allow_transition=False):
    if (not isinstance(value, dict) or value.get('run_id') != run or value.get('uid') != uid or
            value.get('user_id') != 100 or value.get('bundle') != 'org.harmonycontrib.capabilityaudit' or
            value.get('permission') != 'ohos.permission.MICROPHONE' or value.get('operation') != 'query' or
            type(value.get('token_id')) is not int or value['token_id'] <= 0 or value.get('result') != 0 or
            type(value.get('result')) is not int or type(value.get('after')) is not int or
            type(value.get('before')) is not int or value.get('before') not in (-1, 0) or
            value.get('after') not in (-1, 0) or
            (not allow_transition and value.get('after') != value.get('before')) or
            type(value.get('before_ns')) is not int or value['before_ns'] <= 0 or
            type(value.get('after_ns')) is not int or value['after_ns'] < value['before_ns']):
        raise ValueError('independent actual microphone token evidence invalid')
    return value['after'], value['token_id']


def denied_results(text, run, uid, files):
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if (not rows or any(not isinstance(r, dict) or r.get('run_id') != run for r in rows) or
            rows[0] != {'type': 'identity', 'run_id': run, 'uid': uid, 'euid': uid, 'mode': 'denied'} or
            rows[-1] != {'type': 'summary', 'run_id': run, 'cycles': 2, 'candidate_ok': True,
                         'independent_pcm_verification_required': True}):
        raise ValueError('denied native capture identity/summary failed or stale')
    allowed = {'step', 'denial_generate', 'denial_start', 'format', 'quiet', 'pcm_file'}
    if any(r.get('type') not in allowed or r.get('cycle') not in (1, 2) for r in rows[1:-1]):
        raise ValueError('denied Capturer returned actual PCM or unexpected events')
    config = CONFIG_STEPS[:10]
    for cycle in (1, 2):
        group = [r for r in rows[1:-1] if r['cycle'] == cycle]
        steps = [r for r in group if r['type'] == 'step']
        if len(steps) < len(config) + 1:
            raise ValueError('denied Capturer did not exercise the real configured source')
        for row, (name, expected) in zip(steps, config):
            if (row.get('name') != name or type(row.get('actual')) is not int or row['actual'] != expected or
                    row.get('expected') != expected):
                raise ValueError('denied capture failed before the real permission boundary')
        generated = [r for r in group if r['type'] == 'denial_generate']
        started = [r for r in group if r['type'] == 'denial_start']
        if len(generated) != 1 or type(generated[0].get('actual')) is not int or type(generated[0].get('created')) is not bool:
            raise ValueError('one actual GenerateCapturer result required for each denied cycle')
        if generated[0]['created']:
            if generated[0]['actual'] != 0 or len(started) != 1 or type(started[0].get('actual')) is not int or started[0]['actual'] == 0:
                raise ValueError('denied native Capturer unexpectedly started or generation failed inconsistently')
            names = [r.get('name') for r in steps]
            if names != [n for n, _ in config] + ['get_rate', 'get_channels', 'get_format', 'prepared',
                'prepared.value', 'pause_before_start', 'release', 'destroy']:
                raise ValueError('denied created Capturer lifecycle is incomplete')
            for row in steps[len(config):]:
                expected = {'prepared.value': 1, 'pause_before_start': 2}.get(row['name'], 0)
                if row.get('actual') != expected or type(row.get('actual')) is not int:
                    raise ValueError('denied Capturer lifecycle cleanup failed')
        elif generated[0]['actual'] == 0 or started or [r.get('name') for r in steps] != [n for n, _ in config] + ['destroy']:
            raise ValueError('denied GenerateCapturer boundary inconsistent')
        if steps[-1].get('actual') != 0 or type(steps[-1].get('actual')) is not int:
            raise ValueError('denied Capturer builder cleanup failed')
        for row in group:
            if row['type'] == 'pcm_file' and (row.get('bytes') != 0 or row.get('written_bytes') != 0 or row.get('persisted') is not True):
                raise ValueError('denied Capturer persisted microphone samples')
            if row['type'] == 'quiet' and (row.get('before_bytes') != 0 or row.get('after_bytes') != 0 or row.get('unexpected') != 0):
                raise ValueError('denied Capturer delivered microphone data after release')
        file = files[f'audio-capture-{run}-cycle{cycle}.pcm']
        if not file.get('absent') and file.get('bytes') != 0:
            raise ValueError('real denied private microphone file contains data')
    return {'cycles': 2, 'mode': 'denied', 'positive_backend_control_required': True,
            'scope': 'denied_real_token_and_native_capture_boundary_NOT_standalone_permission_closure'}


def checked_file(record):
    path = Path(record['path'])
    if not path.is_absolute() or sha(path) != record.get('sha256'):
        raise ValueError('actual captured microphone evidence changed')
    return path


def verify(args):
    run, arch = args.run_id, args.arch
    runtime = json.loads(args.runtime.read_text())
    archive_sha = sha(args.archive)
    if (runtime.get('status') != 'captured_NOT_independently_verified' or runtime.get('run_id') != run or
            runtime.get('archive_sha256') != archive_sha or runtime.get('boot_id') != args.boot_id or
            runtime.get('arch') != arch or type(runtime.get('expected_denied')) is not bool or
            runtime.get('cleanup_errors') != [] or runtime.get('runner_sha256') != sha(Path(__file__).with_name('audio_capture_runtime.py'))):
        raise ValueError('microphone runtime must belong to this exact archive/boot/ABI and cleanly completed run')
    denied = runtime['expected_denied']
    boot_path = Path(runtime['boot'])
    if sha(boot_path) != runtime['boot_sha256']:
        raise ValueError('microphone acceptance boot changed')
    binding(json.loads(boot_path.read_text()), archive_sha, args.boot_id, arch, runtime['device'], runtime['target'])
    value = json.loads(args.inputs.read_text())
    contract.verify_inputs(value, run, arch, denied)
    contract.verify_hap(args.hap, value, arch)
    uid = require_normal_identity(args.application_identity.read_text())
    observations = runtime.get('tokens', [])
    if (len(observations) < 3 or observations[0].get('phase') != 'before-launch' or
            observations[-1].get('phase') != 'after-capture' or
            any(r.get('phase') != 'after-dialog' for r in observations[1:-1])):
        raise ValueError('independent token observations do not span the actual ordinary capture')
    token_id = None
    token_time = 0
    for index, row in enumerate(observations):
        state, current = token(row['observation'], run, uid, allow_transition=0 < index < len(observations) - 1)
        if token_id is None:
            token_id = current
        if (current != token_id or row['observation']['before_ns'] < token_time or
                (index == 0 and state != -1) or (index == len(observations) - 1 and state != (-1 if denied else 0))):
            raise ValueError('microphone token changed or was not independently granted/denied')
        token_time = row['observation']['after_ns']
    if token(observations[-2]['observation'], run, uid)[0] != (-1 if denied else 0):
        raise ValueError('actual committed microphone dialog state missing')
    labels_path = Path(runtime['labels'])
    if sha(labels_path) != runtime['labels_sha256']:
        raise ValueError('trusted microphone resource evidence changed')
    labels = json.loads(labels_path.read_text())
    action = runtime['permission_action']
    layout = Path(action['layout'])
    if (sha(layout) != action['layout_sha256'] or action.get('decision') != ('DENY' if denied else 'ALLOW') or
            select_permission(json.loads(layout.read_text()), labels, denied) != action.get('selected_node')):
        raise ValueError('actual trusted microphone UI decision does not match recorded nodes')
    files = runtime['files']
    for name, item in files.items():
        if item.get('absent') is True:
            continue
        path = checked_file(item)
        if (path.name != name or path.stat().st_size != item.get('bytes') or item.get('uid') != uid or
                (name.endswith('.pcm') and item.get('mode') != 600)):
            raise ValueError('actual microphone files are truncated, stale or owned by another caller')
    permission = json.loads(checked_file(files[f'audio-capture-{run}-permission.json']).read_text())
    if (permission.get('run_id') != run or permission.get('expected_denied') is not denied or
            permission.get('permissions') != ['ohos.permission.MICROPHONE'] or
            permission.get('auth_results') != [-1 if denied else 0] or
            any(type(v) is not int for v in permission.get('auth_results', [])) or
            permission.get('dialog_shown_results') != [True] or
            any(type(v) is not bool for v in permission.get('dialog_shown_results', []))):
        raise ValueError('actual public permission request result disagrees with independent token/UI')
    tools_path = Path(runtime['tools'])
    if sha(tools_path) != runtime['tools_sha256']:
        raise ValueError('microphone tool build evidence changed')
    tools = json.loads(tools_path.read_text())
    if (tools.get('status') != 'pass' or tools.get('arch') != arch or tools.get('inputs_unchanged') is not True or
            tools.get('builder_sha256') != sha(Path(__file__).with_name('build_audio_capture_tools.py'))):
        raise ValueError('actual microphone tools failed compilation/input binding')
    for name, source in (('alsa_inject', 'batch_media_alsa_inject.c'), ('audio_capture_token', 'probes/audio_capture_token.cpp')):
        row = tools['tools'][name]
        if (row.get('source_sha256') != sha(Path(__file__).parent / source) or
                sha(tools_path.parent / name) != row.get('binary_sha256')):
            raise ValueError('stale actual microphone orchestration executable')
        library = runtime['guest_libraries'][name]
        path = checked_file(library)
        if contract.runtime_identity(path.read_bytes(), arch) != row.get('linked_library_runtime_sha256'):
            raise ValueError('root tool uses another artifact library')
    if denied:
        result = denied_results(args.results.read_text(), run, uid, files)
    else:
        producer = runtime['producer']
        path = Path(producer['log'])
        if producer.get('host_exit_code') != 0 or sha(path) != producer['log_sha256']:
            raise ValueError('real independent PCM producer failed or its evidence changed')
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        expected = [{'event': 'feeding', 'device': 'hw:CARD=QemuCapture,DEV=1,SUBDEV=0',
                     'rate': 48000, 'channels': 2, 'bytes': 192000},
                    {'event': 'played', 'frames': 960000, 'rate': 48000, 'channels': 2,
                     'repeats': 20, 'source_bytes': 192000}]
        if rows != expected:
            raise ValueError('real producer did not complete the exact independent stereo source')
        result = verify_pcm(args.results, args.runtime.parent / 'private', args.runtime.parent / 'challenge/challenge.json',
            args.runtime.parent / 'challenge/challenge.pcm', run, args.application_identity)
    return {'status': 'pass', 'scope': SCOPE, 'run_id': run, 'arch': arch, 'boot_id': args.boot_id,
        'archive_sha256': archive_sha, 'expected_denied': denied, 'result': result,
        'inputs_sha256': {name: sha(getattr(args, name)) for name in ('results', 'inputs', 'runtime', 'hap', 'application_identity')},
        'verifier_sha256': sha(Path(__file__)), 'closed_requirements': [],
        'first_artifact_behavior_gate_passed': False}


def verify_evidence(document, archive, boot_id, arch):
    archive = Path(archive)
    if (document.get('status') != 'pass' or document.get('persona') != 'audio-capture' or
            document.get('archive_sha256') != sha(archive) or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != []):
        raise ValueError('ordinary microphone case must belong to the actual artifact/boot/ABI')
    result_path = Path(document['result'])
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('actual ordinary microphone case result missing')
    root = result_path.parent
    paths = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/audio-capture-probe-inputs.json',
             'capture_runtime': root / 'capture/runtime.json'}
    if any(sha(path) != document.get(key + '_sha256') for key, path in paths.items()):
        raise ValueError('actual microphone case evidence changed')
    actual = verify(SimpleNamespace(archive=archive, run_id=document['run_id'], arch=arch, boot_id=boot_id,
        results=paths['raw_results'], inputs=paths['compiled_contract_inputs'], runtime=paths['capture_runtime'],
        hap=paths['hap'], application_identity=paths['ordinary_identity']))
    if actual != json.loads(result_path.read_text()):
        raise ValueError('ordinary microphone case summary differs from independently replayed evidence')
    return actual


def verify_batch(batch, archive, boot_id, arch):
    if (batch.get('status') != 'pass' or batch.get('scope') != SCOPE + '_grant_deny_grant' or
            batch.get('archive_sha256') != sha(archive) or batch.get('boot_id') != boot_id or
            batch.get('arch') != arch or batch.get('first_artifact_behavior_gate_passed') is not False or
            len(batch.get('cases', [])) != 3):
        raise ValueError('same-artifact ordinary microphone grant/deny/grant batch required')
    seen = set()
    results = []
    for case, denied in zip(batch['cases'], (False, True, False)):
        path = Path(case['evidence'])
        if sha(path) != case.get('sha256'):
            raise ValueError('actual ordinary microphone batch case changed')
        actual = verify_evidence(json.loads(path.read_text()), archive, boot_id, arch)
        if actual['expected_denied'] is not denied or actual['run_id'] in seen:
            raise ValueError('microphone positive backend controls missing or caller nonce replayed')
        seen.add(actual['run_id'])
        results.append(actual)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'runtime', 'hap', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--arch', choices=contract.ABIS, required=True)
    args = parser.parse_args()
    try:
        result = verify(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'status': 'fail', 'scope': SCOPE, 'error': str(error), 'closed_requirements': [],
                  'first_artifact_behavior_gate_passed': False}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'error': result.get('error')}))
    return result['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
