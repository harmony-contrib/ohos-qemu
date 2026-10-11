#!/usr/bin/env python3
"""Require fresh ordinary-app real AVC encode/decode data and lifecycle."""
import argparse
import json
from pathlib import Path
import re
from verify_audio_stream_results import application_identity, sha256
from avc_media_contract import SCOPE, verify_inputs, verify_hap

BOUNDARIES = [('null_encoder_start', 3), ('null_decoder_start', 3), ('null_encoder_configure', 3)]
BOUNDARIES += [(name, 1) for name in (
    'avc_encoder_default_is_software', 'avc_decoder_default_is_software',
    'avc_encoder_hardware_absent', 'avc_decoder_hardware_absent', 'hevc_encoder_unadvertised',
    'hevc_encoder_hardware_absent', 'hevc_decoder_hardware_absent',
    'legacy_rk_encoder_avc_rejected', 'legacy_rk_encoder_hevc_rejected',
    'legacy_rk_decoder_avc_rejected', 'legacy_rk_decoder_hevc_rejected', 'hevc_create_by_mime_unsupported')]
ENCODER = [('default_encoder_create', 1), ('encoder_register', 0), ('encoder_configure', 0),
           ('encoder_prepare', 0), ('encoder_start', 0), ('encode_frame_0', 1), ('dynamic_bitrate', 0),
           ('encode_frame_1', 1), ('request_idr', 0), ('encode_frame_2', 1), ('encode_frame_3', 1),
           ('encoder_eos', 1), ('encoder_stop', 0), ('encoder_destroy', 0), ('real_headers_and_requested_idr', 1)]
DECODER = [('decoder_create', 1), ('decoder_register', 0), ('decoder_configure', 0),
           ('decoder_prepare', 0), ('decoder_start', 0), ('decoder_feed', 1), ('decoder_eos', 1),
           ('decoder_stop', 0), ('decoder_destroy', 0)]
PTS, INTERVAL = 123456789, 33333


def encoder_steps(mode, cycle=None):
    # A CQ encoder cannot accept bitrate updates; retain a real error-code
    # boundary and prove the subsequent frames/IDR/EOS still work unchanged.
    return ([('encoder_creation_path', cycle)] if cycle is not None else []) + [
        ('dynamic_bitrate_cq_rejected', 3) if mode == 2 and name == 'dynamic_bitrate'
        else (name, code) for name, code in ENCODER]


def decoder_steps(cycle):
    return [('decoder_creation_path', cycle)] + DECODER


def verify(text, run, identity_text):
    if not isinstance(run, str) or re.fullmatch('[0-9a-f]{32}', run) is None:
        raise ValueError('explicit fresh AVC run challenge required')
    uid = application_identity(identity_text)
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != 473 or any(not isinstance(row, dict) or row.get('run_id') != run for row in rows):
        raise ValueError('incomplete, stale or mixed default AVC media results: require 473 rows')
    fields = {
        'identity': {'type', 'run_id', 'uid', 'euid'},
        'step': {'type', 'run_id', 'profile', 'mode', 'cycle', 'name', 'actual', 'expected', 'passed'},
        'bitstream': {'type', 'run_id', 'profile', 'mode', 'cycle', 'pts', 'bytes', 'flags', 'sps_profile'},
        'pixels': {'type', 'run_id', 'profile', 'mode', 'cycle', 'frame', 'pts', 'width', 'height', 'stride',
                   'format', 'expected_y', 'samples', 'absolute_error', 'passed'},
        'cycle': {'type', 'run_id', 'profile', 'mode', 'cycle', 'frames', 'passed'},
        'summary': {'type', 'run_id', 'cycles', 'frames', 'passed'},
    }
    if any(set(row) != fields.get(row.get('type')) for row in rows):
        raise ValueError('unexpected or missing default AVC observation fields')
    if (rows[0].get('type') != 'identity' or type(rows[0].get('uid')) is not int or
            type(rows[0].get('euid')) is not int or rows[0]['uid'] != uid or rows[0]['euid'] != uid):
        raise ValueError('AVC native UID must match the ordinary HAP')
    index = 1

    def take(kind, key):
        nonlocal index
        row = rows[index]
        index += 1
        if row.get('type') != kind or any(type(row.get(field)) is not int or row[field] != value
                                        for field, value in zip(('profile', 'mode', 'cycle'), key)):
            raise ValueError('wrong AVC cycle/record: ' + str(row))
        return row

    def steps(sequence, key):
        for name, expected in sequence:
            row = take('step', key)
            if (row.get('name') != name or type(row.get('actual')) is not int or row['actual'] != expected or
                    type(row.get('expected')) is not int or row['expected'] != expected or row.get('passed') is not True):
                raise ValueError('failed AVC lifecycle/boundary: ' + str(row))

    steps(BOUNDARIES, (-1, -1, -1))
    for profile in (0, 8):
        for mode in (0, 1, 2):
            for cycle in (1, 2):
                key = profile, mode, cycle
                steps(encoder_steps(mode, cycle), key)
                packets = [take('bitstream', key) for _ in range(6)]
                frames, headers, eos = set(), 0, 0
                for packet in packets:
                    if any(type(packet.get(field)) is not int for field in ('pts', 'bytes', 'flags', 'sps_profile')):
                        raise ValueError('invalid AVC bitstream metrics')
                    flags, size = packet['flags'], packet['bytes']
                    if flags == 8:
                        headers += 1
                        if size <= 0 or packet['sps_profile'] != (66 if profile == 0 else 77):
                            raise ValueError('no actual expected-profile AVC SPS')
                    elif flags == 1:
                        eos += 1
                        if size != 0: raise ValueError('AVC EOS must be drained')
                    elif flags in (0, 2):
                        delta = packet['pts'] - PTS
                        frame = delta // INTERVAL
                        if (delta < 0 or delta % INTERVAL != 0 or frame not in range(4) or frame in frames or
                                size <= 0 or size > 1048576 or (frame == 2 and flags != 2)):
                            raise ValueError('missing/duplicate encoded frame, timestamp or requested IDR')
                        frames.add(frame)
                    else: raise ValueError('unexpected AVC packet flags')
                if frames != set(range(4)) or headers != 1 or eos != 1:
                    raise ValueError('AVC requires real headers, four unique frames and one EOS')
                steps(decoder_steps(cycle), key)
                seen = set()
                for _ in range(4):
                    row = take('pixels', key)
                    fields = ('frame', 'pts', 'width', 'height', 'stride', 'format', 'expected_y', 'samples', 'absolute_error')
                    if any(type(row.get(field)) is not int for field in fields): raise ValueError('invalid AVC pixel metrics')
                    frame = row['frame']
                    if (frame not in range(4) or frame in seen or row['pts'] != PTS + frame * INTERVAL or
                            row['width'] != 64 or row['height'] != 64 or not 64 <= row['stride'] <= 16384 or
                            row['format'] != 1 or row['expected_y'] != 32 + ((ord(run[frame]) + frame + cycle) % 16) * 8 or
                            row['samples'] != 4096 or not 0 <= row['absolute_error'] <= 4096 * 8 or row.get('passed') is not True):
                        raise ValueError('real decoded challenge pixels/timestamp failed')
                    seen.add(frame)
                steps([('all_decoded_frames', 1)], key)
                row = take('cycle', key)
                if type(row.get('frames')) is not int or row['frames'] != 4 or row.get('passed') is not True:
                    raise ValueError('AVC recreate cycle failed')
    last = rows[index]
    if (index != len(rows) - 1 or last.get('type') != 'summary' or last.get('passed') is not True or
            type(last.get('cycles')) is not int or last['cycles'] != 12 or
            type(last.get('frames')) is not int or last['frames'] != 48):
        raise ValueError('AVC media summary failed')
    return rows


def result(rows):
    return {'closed': ['behavior:media-video-encoder-creation-failure'], 'observations': len(rows),
            'scope': SCOPE, 'encoder_MIME_cycles': 6, 'encoder_default_name_cycles': 6,
            'decoder_MIME_cycles': 6, 'decoder_default_name_cycles': 6, 'challenged_frames': 48,
            'not_claimed': 'HEVC_encoding_or_full_codec_enumeration_or_recording_screen_capture_transcoding_pipelines'}


def verify_evidence(document, archive_sha, boot_id, arch, device=None, target=None):
    if (document.get('status') != 'pass' or document.get('persona') != 'avc-media' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False or
            (device is not None and document.get('device') != device) or
            (target is not None and document.get('target') != target)):
        raise ValueError('default AVC evidence must belong to this actual new package/boot/ABI')
    path = Path(document.get('result', ''))
    if not path.is_absolute() or path.name != 'verified-result.json':
        raise ValueError('explicit default AVC verifier result required')
    root = path.parent
    files = {'result': path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/avc-media-probe-inputs.json'}
    for key, file in files.items():
        if file.is_symlink() or not file.is_file() or sha256(file) != document.get(key + '_sha256'):
            raise ValueError('actual default AVC evidence missing or changed: ' + key)
    value = json.loads(path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('arch') != arch or
            value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != sha256(Path(__file__)) or
            any(value.get(key) is not False for key in ('hardware_codec_tested', 'hevc_tested',
                                                       'mathematical_CBR_conformance_tested'))):
        raise ValueError('default AVC result is stale or overclaims untested codec capabilities')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs')):
        if value.get(field) != sha256(files[key]):
            raise ValueError('default AVC verifier did not consume these captured inputs')
    inputs = verify_inputs(json.loads(files['compiled_contract_inputs'].read_text()), document['run_id'], arch)
    verify_hap(files['hap'], inputs, arch)
    identity = files['ordinary_identity'].read_text()
    rows = verify(files['raw_results'].read_text(), document['run_id'], identity)
    actual = result(rows)
    if (actual != value.get('result') or rows != value.get('results') or
            application_identity(identity) != document.get('ordinary_uid')):
        raise ValueError('default AVC summary differs from actual ordinary-app raw observations')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--application-identity', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    evidence = {'status': 'fail', 'scope': SCOPE, 'arch': args.arch,
                'archive': str(args.archive.resolve()), 'run_id': args.run_id, 'failures': [],
                'first_artifact_behavior_gate_passed': False, 'hardware_codec_tested': False,
                'hevc_tested': False, 'mathematical_CBR_conformance_tested': False}
    try:
        for name, path in (('archive', args.archive), ('results', args.results), ('application_identity', args.application_identity)):
            evidence[name + '_sha256'] = sha256(path)
        evidence['archive_sha256'] = sha256(args.archive)
        evidence['compiled_inputs_sha256'] = sha256(args.inputs)
        evidence['verifier_sha256'] = sha256(Path(__file__))
        text = args.results.read_text()
        evidence['observations'] = [json.loads(line) for line in text.splitlines() if line.strip()]
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        evidence['results'] = verify(text, args.run_id, args.application_identity.read_text())
        evidence['result'] = result(evidence['results'])
        evidence['status'] = 'pass'
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        evidence['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({key: value for key, value in evidence.items() if key not in ('observations', 'results')}))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
