#!/usr/bin/env python3
"""Verify ordinary-app public Camera lifecycle and independently decoded photos."""
import argparse
import json
import math
from pathlib import Path
import re
import zipfile
from verify_audio_stream_results import application_identity, sha256

BUNDLE = 'org.harmonycontrib.capabilityaudit'

NATIVE_BOUNDARIES = ('ordinary_application', 'null_manager_create', 'null_manager_delete',
                     'null_input_open', 'null_input_close', 'null_session_begin', 'null_session_start',
                     'null_preview_start', 'null_preview_release')
NATIVE_CYCLE = ('manager_create', 'real_camera_enumeration', 'capabilities', 'real_YUV_preview_profile',
                '@profile', 'input_create', 'input_open', 'preview_create', 'callback_register', 'session_create',
                'start_before_config_rejected', 'config_begin', 'config_add_input', 'config_add_preview',
                'config_commit', 'session_start', 'real_frame_start', 'session_stop', '@frames',
                'real_frame_completion', 'callback_unregister', 'preview_release', 'session_release',
                'input_close', 'input_release', 'capabilities_release', 'cameras_release', 'manager_release')
ARKTS_PREFIX = ('effect_record_constructor', 'effect_record_unset_fields', 'effect_record_values',
                'effect_record_isolation', 'ordinary_user_permission', 'real_ArkUI_surface',
                'native_probe_started', 'native_complete')
ARKTS_CYCLE = ('camera_enumeration', 'real_profiles', 'input_open', 'session_configured', 'preview_started',
               'preview_frame_start', 'capture_requested_1', 'capture_call_returned_1',
               'photo_timestamp_1', 'photo_JPEG_1', 'photo_dimensions_1', 'photo_real_pixels_1',
               'capture_requested_2', 'capture_call_returned_2',
               'photo_timestamp_2', 'photo_JPEG_2', 'photo_dimensions_2', 'photo_real_pixels_2',
               'preview_frame_end', 'release_cycle')


def records(text, run, count):
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != count or any(not isinstance(row, dict) or row.get('run_id') != run for row in rows):
        raise ValueError('incomplete/stale/mixed Camera records')
    return rows


def step(row, name, cycle, kind):
    if (row.get('kind') != kind or row.get('name') != name or type(row.get('cycle')) is not int or
            row['cycle'] != cycle or row.get('pass') is not True or type(row.get('value')) not in (int, float) or
            not math.isfinite(row['value'])):
        raise ValueError('failed/malformed/reordered Camera step: ' + name)
    return row['value']


def decode_photo(path):
    from PIL import Image
    if path.is_symlink() or not path.is_file() or not 128 <= path.stat().st_size <= 16 * 1024 * 1024:
        raise ValueError('missing/unsafe Camera photo payload')
    with Image.open(path) as image:
        if image.format != 'JPEG' or not (160 <= image.width <= 1280 and 120 <= image.height <= 720):
            raise ValueError('invalid actual Camera JPEG/dimensions')
        pixels = image.convert('RGB')
        samples = []
        for bar in range(8):
            samples.extend(pixels.getpixel(((bar * 2 + 1) * pixels.width // 16, pixels.height // 2)))
        return {'width': pixels.width, 'height': pixels.height, 'samples': samples,
                'bytes': path.stat().st_size, 'sha256': sha256(path)}


def verify(native_text, arkts_text, run, arch, identity, photo_root):
    if not isinstance(run, str) or re.fullmatch('[0-9a-f]{32}', run) is None or arch not in ('armv7a', 'arm64', 'x86_64'):
        raise ValueError('fresh Camera run challenge and exact architecture required')
    uid = application_identity(identity)
    if uid // 200000 != 100 or uid % 200000 < 10000:
        raise ValueError('Camera probe must run in foreground account100 as an ordinary application')
    native = records(native_text, run, 67)
    first, last = native[0], native[-1]
    if (first.get('kind') != 'native_identity' or first.get('arch') != arch or
            any(type(first.get(field)) is not int or first[field] != uid for field in ('uid', 'euid'))):
        raise ValueError('Camera native identity differs from normal HAP')
    if (last.get('kind') != 'native_complete' or any(type(last.get(field)) is not int or last[field] != expected
            for field, expected in (('checks', 61), ('failures', 0), ('exit_code', 0))) or
            last.get('scope') != 'public_NDK_preview_callbacks_not_pixel_or_photo_validation'):
        raise ValueError('incomplete/failed public Camera C++ lifecycle')
    index = 1
    for name in NATIVE_BOUNDARIES:
        value = step(native[index], name, 0, 'native_case')
        if type(value) is not int or value != 0:
            raise ValueError('wrong Camera boundary record')
        index += 1
    for cycle in (1, 2):
        frame_maximum = 0
        for name in NATIVE_CYCLE:
            row = native[index]
            index += 1
            if name == '@profile':
                if (row.get('kind') != 'native_profile' or row.get('cycle') != cycle or
                        any(type(row.get(field)) is not int for field in ('cycle', 'format', 'width', 'height')) or
                        row['format'] != 1003 or not 160 <= row['width'] <= 1280 or not 120 <= row['height'] <= 720):
                    raise ValueError('missing actual native YUV profile')
            elif name == '@frames':
                if (row.get('kind') != 'native_frames' or row.get('cycle') != cycle or
                        any(type(row.get(field)) is not int for field in ('cycle', 'starts', 'ends', 'errors', 'maximum')) or
                        not 1 <= row['starts'] <= 10000 or not 1 <= row['ends'] <= 10000 or
                        row['errors'] != 0 or not 8 <= row['maximum'] <= 10000):
                    raise ValueError('native Camera did not produce real preview completion')
                frame_maximum = row['maximum']
            else:
                value = step(row, name, cycle, 'native_case')
                expected = (7400103 if name == 'start_before_config_rejected' else
                            1 if name == 'real_camera_enumeration' else
                            frame_maximum if name == 'real_frame_completion' else 0)
                if type(value) is not int or value != expected:
                    raise ValueError('wrong native Camera API result: ' + name)
    expected_checks = len(ARKTS_PREFIX) + 2 * len(ARKTS_CYCLE)
    arkts = records(arkts_text, run, expected_checks + 1)
    last = arkts[-1]
    if (last.get('kind') != 'arkts_complete' or last.get('pass') is not True or
            type(last.get('checks')) is not int or last['checks'] != expected_checks or
            type(last.get('failures')) is not int or last['failures'] != 0):
        raise ValueError('incomplete/failed Camera ArkTS lifecycle')
    for index, name in enumerate(ARKTS_PREFIX):
        row = arkts[index]
        value = step(row, name, 0, 'arkts_case')
        if type(value) is not int or value != 0 or not isinstance(row.get('detail'), str):
            raise ValueError('wrong Camera permission/native bridge evidence')
    index, timestamp, photos = len(ARKTS_PREFIX), 0, []
    for cycle in (1, 2):
        decoded = None
        for name in ARKTS_CYCLE:
            row = arkts[index]
            index += 1
            value = step(row, name, cycle, 'arkts_case')
            if not isinstance(row.get('detail'), str):
                raise ValueError('missing Camera diagnostic detail')
            if name == 'camera_enumeration' and (type(value) is not int or value != 1):
                raise ValueError('unexpected virtual Camera enumeration')
            if name == 'real_profiles' and (type(value) is not int or not 160 <= value <= 1280 or
                    not row['detail'].isdigit() or not 160 <= int(row['detail']) <= 1280):
                raise ValueError('missing actual ArkTS capture profiles')
            if name.startswith('photo_timestamp_'):
                if not timestamp < value < 1e20:
                    raise ValueError('photo timestamps must advance across captures/recreation')
                timestamp = value
                photo = int(name[-1])
                path = photo_root / f'camera-{run}-c{cycle}-p{photo}.jpg'
                decoded = decode_photo(path)
                photos.append({'cycle': cycle, 'photo': photo, **decoded})
            elif name.startswith('photo_JPEG_'):
                if type(value) is not int or value != decoded['bytes']:
                    raise ValueError('Camera JPEG bytes differ from actual payload')
            elif name.startswith('photo_dimensions_'):
                if type(value) is not int or value != decoded['width'] or row['detail'] != str(decoded['height']):
                    raise ValueError('Camera photo dimensions differ from actual decoder')
            elif name.startswith('photo_real_pixels_'):
                samples = json.loads(row['detail'])
                if (not isinstance(samples, list) or len(samples) != 24 or
                        any(type(component) is not int or not 0 <= component <= 255 for component in samples)):
                    raise ValueError('missing actual captured pixel samples')
                colors = {tuple(component // 32 for component in samples[start:start + 3]) for start in range(0, 24, 3)}
                if (type(value) is not int or value != len(colors) or value < 4 or max(samples) - min(samples) < 60 or
                        any(abs(a - b) > 8 for a, b in zip(samples, decoded['samples']))):
                    raise ValueError('captured pixels are blank/fabricated or differ from independent JPEG decoder')
            elif name in ('preview_frame_start', 'preview_frame_end'):
                if type(value) is not int or not 1 <= value <= 10000:
                    raise ValueError('missing real ArkTS preview callbacks')
            elif name in ('input_open', 'session_configured', 'preview_started', 'release_cycle'):
                if type(value) is not int or value != 0:
                    raise ValueError('wrong ArkTS Camera lifecycle result')
            elif name.startswith(('capture_requested_', 'capture_call_returned_')):
                if type(value) is not int or value != 0:
                    raise ValueError('Camera capture request/return evidence is invalid')
    return {'native_records': len(native), 'arkts_records': len(arkts), 'uid': uid, 'photos': photos}


def verify_captures(captures, run, arkts_text):
    from PIL import Image
    from guest_ui import select_node
    rows = [json.loads(line) for line in arkts_text.splitlines() if line.strip()]
    if not isinstance(captures, list) or len(captures) != 2:
        raise ValueError('two real live Camera compositor captures required')
    observed = []
    for cycle, capture in enumerate(captures, start=1):
        if (not isinstance(capture, dict) or type(capture.get('cycle')) is not int or
                capture['cycle'] != cycle or capture.get('run_id') != run):
            raise ValueError('wrong Camera capture generation/nonce')
        for field in ('layout', 'screenshot'):
            path = Path(capture.get(field, ''))
            if path.is_symlink() or not path.is_file() or sha256(path) != capture.get(field + '_sha256'):
                raise ValueError('actual Camera live capture missing or changed')
        for field in ('before_records', 'after_records'):
            prefix = capture.get(field)
            if not isinstance(prefix, list) or not prefix or prefix != rows[:len(prefix)]:
                raise ValueError('Camera screenshot phase differs from the actual final log')
            names = {row.get('name') for row in prefix if row.get('cycle') == cycle}
            if 'preview_started' not in names or 'preview_frame_start' in names:
                raise ValueError('Camera screenshot is not inside the actual live preview interval')
        if len(capture['before_records']) > len(capture['after_records']):
            raise ValueError('Camera screenshot phase went backwards')
        layout = json.loads(Path(capture['layout']).read_text())
        select_node(layout, BUNDLE, text='ArkTS preview live cycle ' + str(cycle))
        surface = select_node(layout, BUNDLE, identifier='camera-audit-preview')
        if surface != capture.get('selected_node'):
            raise ValueError('Camera screenshot rectangle differs from actual visible surface')
        left, top, width, height = surface['rect']
        with Image.open(capture['screenshot']) as image:
            if (image.format != 'PNG' or min(width, height) < 100 or
                    left + width > image.width or top + height > image.height):
                raise ValueError('actual Camera compositor image/rectangle invalid')
            pixels = image.convert('RGB')
            samples = [list(pixels.getpixel((left + (bar * 2 + 1) * width // 16, top + height // 2)))
                       for bar in range(8)]
        colors = {tuple(component // 32 for component in sample) for sample in samples}
        channels = [channel for sample in samples for channel in sample]
        if len(colors) < 4 or max(channels) - min(channels) < 60:
            raise ValueError('real Camera preview is blank or lacks the capture color pattern')
        observed.append({'cycle': cycle, 'samples': samples, 'color_count': len(colors),
                         'screenshot_sha256': capture['screenshot_sha256']})
    return observed


def verify_evidence(document, archive_sha, boot_id):
    from camera_probe_contract import verify_inputs, select_permission
    if (document.get('status') != 'pass' or document.get('persona') != 'camera' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('failures')):
        raise ValueError('Camera evidence is failed or belongs to another archive/boot')
    output = Path(document.get('result', '')).parent
    signed = output / 'ordinary-probe-signed.hap'
    if signed.is_symlink() or not signed.is_file() or sha256(signed) != document.get('hap_sha256'):
        raise ValueError('actual Camera signed HAP missing/changed')
    with zipfile.ZipFile(signed) as hap:
        module = json.loads(hap.read('module.json'))['module']
    permissions = module.get('requestPermissions', [])
    if (not isinstance(permissions, list) or len(permissions) != 1 or
            permissions[0].get('name') != 'ohos.permission.CAMERA'):
        raise ValueError('Camera HAP must declare only its real user-grant CAMERA permission')
    paths = {'raw_results': output / 'results.log', 'ordinary_identity': output / 'application-identity.json',
             'camera_native_results': output / 'native-results.log',
             'compiled_contract_inputs': Path(document.get('compiled_contract_inputs', '')),
             'camera_captures': Path(document.get('camera_captures', '')),
             'camera_permission_labels': Path(document.get('camera_permission_labels', '')),
             'result': Path(document.get('result', ''))}
    for field, path in paths.items():
        if path.is_symlink() or not path.is_file() or sha256(path) != document.get(field + '_sha256'):
            raise ValueError('Camera evidence file missing/changed: ' + field)
    run, arch = document['run_id'], document['arch']
    verify_inputs(json.loads(paths['compiled_contract_inputs'].read_text()), output / 'project', run, arch)
    identity = paths['ordinary_identity'].read_text()
    native, arkts = paths['camera_native_results'].read_text(), paths['raw_results'].read_text()
    actual = verify(native, arkts, run, arch, identity, output / 'photos')
    captures = verify_captures(json.loads(paths['camera_captures'].read_text()), run, arkts)
    result = json.loads(paths['result'].read_text())
    if (result.get('status') != 'pass' or result.get('run_id') != run or
            result.get('archive_sha256') != archive_sha or result.get('observations') != actual or
            result.get('preview_observations') != captures or result.get('visible_preview_validated') is not True or
            result.get('native_results_sha256') != document['camera_native_results_sha256'] or
            result.get('arkts_results_sha256') != document['raw_results_sha256'] or
            result.get('identity_sha256') != document['ordinary_identity_sha256']):
        raise ValueError('Camera recorded result differs from independent actual-data verification')
    if result.get('captures_sha256') != document['camera_captures_sha256']:
        raise ValueError('Camera verifier used different live compositor captures')
    action = document.get('camera_permission_action', {})
    layout = Path(action.get('layout', ''))
    if (action.get('scope') != 'actual_user_grant_dialog_NOT_shell_grant' or action.get('decision') != 'ALLOW' or
            layout.is_symlink() or not layout.is_file() or sha256(layout) != action.get('layout_sha256') or
            select_permission(json.loads(layout.read_text()), json.loads(paths['camera_permission_labels'].read_text())) !=
            action.get('selected_node')):
        raise ValueError('actual ordinary Camera permission decision not proven')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--native-results', type=Path, required=True)
    parser.add_argument('--arkts-results', type=Path, required=True)
    parser.add_argument('--photo-root', type=Path, required=True)
    parser.add_argument('--application-identity', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--captures', type=Path, help='actual two-generation live compositor evidence')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'normal-app NDK preview callbacks plus ArkTS capture/JPEG pixels/recreation',
              'run_id': args.run_id, 'archive': str(args.archive.resolve()), 'failures': [],
              'first_artifact_behavior_gate_passed': False, 'visible_preview_validated': False,
              'video_or_advanced_camera_validated': False}
    try:
        result.update(archive_sha256=sha256(args.archive), native_results_sha256=sha256(args.native_results),
                      arkts_results_sha256=sha256(args.arkts_results), identity_sha256=sha256(args.application_identity))
        result['observations'] = verify(args.native_results.read_text(), args.arkts_results.read_text(),
                                        args.run_id, args.arch, args.application_identity.read_text(), args.photo_root)
        if args.captures:
            result['preview_observations'] = verify_captures(json.loads(args.captures.read_text()),
                                                            args.run_id, args.arkts_results.read_text())
            result['visible_preview_validated'] = True
            result['captures_sha256'] = sha256(args.captures)
        result['status'] = 'pass'
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        result['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
