#!/usr/bin/env python3
"""Independent raw API/pixel oracle; no executor, Owner, SDK, or closure flags.

The parent must bind raw journal and QMP screendumps to the actual new package,
same boot, foreground window/ROI, signed HAP, process, command and cleanup fences.
This oracle only evaluates their bytes. It cannot establish that provenance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from graphics3d_asset import specification, descriptors
from graphics3d_contract import ACTIONS, commands

FIELDS = {'schema', 'run_id', 'boot_id', 'operation_id', 'action', 'seq',
          'monotonic_ms', 'pid', 'uid', 'kind', 'code', 'value_json'}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result

def decode(text):
    def forbidden(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(text, object_pairs_hook=unique, parse_constant=forbidden)

def parse_rows(text, run, boot, pid, uid):
    require(type(pid) is int and pid > 0 and type(uid) is int and uid > 0, 'Actual ordinary process/UID required')
    require(type(text) is str and text.endswith('\n') and len(text.encode()) <= 2 * 1024 * 1024, 'Truncated/oversized raw journal')
    result = []
    previous = -1
    for line in text.splitlines():
        require(0 < len(line) <= 16384, 'Raw line bound')
        row = decode(line)
        require(type(row) is dict and set(row) == FIELDS, 'Raw field set')
        require(type(row['schema']) is int and row['schema'] == 1 and row['run_id'] == run and
                row['boot_id'] == boot and row['pid'] == pid and row['uid'] == uid, 'Foreign raw identity')
        require(type(row['seq']) is int and row['seq'] == len(result) + 1, 'Raw sequence gap/duplicate')
        require(type(row['monotonic_ms']) is int and row['monotonic_ms'] >= previous, 'Raw time regression')
        require(type(row['code']) is int and type(row['value_json']) is str, 'Raw value/code type')
        require(type(row['operation_id']) is str and re.fullmatch('[a-f0-9]{32}', row['operation_id']), 'Raw operation nonce')
        require(row['kind'] in ('begin', 'api-return', 'api-throw', 'return', 'throw', 'end'), 'Unknown raw kind')
        row['value'] = decode(row['value_json'])
        result.append(row)
        previous = row['monotonic_ms']
    require(0 < len(result) <= 128, 'Raw record bound')
    return result

def ppm(blob):
    require(type(blob) is bytes and len(blob) <= 64 * 1024 * 1024, 'Bounded original PPM bytes required')
    offset, tokens = 0, []
    while len(tokens) < 4:
        while offset < len(blob) and blob[offset] in b' \t\r\n':
            offset += 1
        if offset < len(blob) and blob[offset] == 35:
            end = blob.find(b'\n', offset)
            require(end >= 0 and end - offset <= 1024, 'PPM comment bound')
            offset = end + 1
            continue
        start = offset
        while offset < len(blob) and blob[offset] not in b' \t\r\n':
            offset += 1
        require(0 < offset - start <= 10, 'PPM token bound')
        tokens.append(blob[start:offset])
    require(tokens[0] == b'P6' and tokens[3] == b'255' and
            all(re.fullmatch(b'[1-9][0-9]{0,4}', t) for t in tokens[1:3]), 'Original QMP P6 RGB8 required')
    width, height = map(int, tokens[1:3])
    require(64 <= width <= 8192 and 64 <= height <= 8192 and
            width * height <= 20 * 1024 * 1024, 'PPM dimensions')
    require(offset < len(blob) and blob[offset] in b' \t\r\n', 'PPM binary delimiter')
    offset += 2 if blob[offset:offset + 2] == b'\r\n' else 1
    require(len(blob) - offset == width * height * 3, 'PPM truncated/extra payload')
    return width, height, memoryview(blob)[offset:]

def pixels(blob, roi):
    width, height, rgb = ppm(blob)
    require(type(roi) in (tuple, list) and len(roi) == 4 and all(type(n) is int for n in roi), 'Actual integer viewport ROI required')
    x, y, w, h = roi
    require(x >= 0 and y >= 0 and w >= 128 and h >= 128 and x + w <= width and y + h <= height, 'Viewport outside original QMP image')
    groups = {name: {'count': 0, 'sum_x': 0., 'sum_y': 0., 'left': w,
                     'right': 0., 'top': h, 'bottom': 0.} for name in ('red', 'green')}
    background = 0
    for py in range(h):
        for px in range(w):
            start = ((y + py) * width + x + px) * 3
            r, g, b = rgb[start:start + 3]
            color = None
            if r > 100 and g < .35 * r and b < .35 * r:
                color = 'red'
            elif g > 100 and r < .35 * g and b < .35 * g:
                color = 'green'
            if color is not None:
                points = groups[color]
                points['count'] += 1
                points['sum_x'] += px + .5
                points['sum_y'] += py + .5
                points['left'] = min(points['left'], px + .5)
                points['right'] = max(points['right'], px + .5)
                points['top'] = min(points['top'], py + .5)
                points['bottom'] = max(points['bottom'], py + .5)
            if abs(r - 16) <= 3 and abs(g - 24) <= 3 and abs(b - 32) <= 3:
                background += 1
    result = {'width': w, 'height': h, 'background_fraction': background / (w * h)}
    for color, points in groups.items():
        result[color] = {'count': points['count']}
        if points['count']:
            result[color].update(cx=points['sum_x'] / points['count'],
                                 cy=points['sum_y'] / points['count'],
                                 **{key: points[key] for key in ('left', 'right', 'top', 'bottom')})
    return result

def evaluate_frame(measured, run, translated):
    spec = specification(run)
    w, h = measured['width'], measured['height']
    require(abs(w - h) <= 1, 'Actual fixed square Component3D viewport required')
    k = h / (2 * math.tan(spec['camera_fov'] / 2) * spec['camera_z'])
    delta = spec['translate_x'] if translated else 0
    for color, cx, cy, left, right, area in [('red', -.5, 0, -.85, -.15, .7),
                                          ('green', .55, -1 / 6, .15, .95, .4)]:
        m = measured[color]
        expected_area = area * (spec['scale'] * k) ** 2
        require(expected_area >= 64 and .75 * expected_area <= m['count'] <= 1.25 * expected_area,
                color + ' actual nonempty projected area')
        expected = {'cx': w / 2 + (cx * spec['scale'] + delta) * k,
                    'cy': h / 2 - (cy * spec['scale'] + spec['y']) * k,
                    'left': w / 2 + (left * spec['scale'] + delta) * k,
                    'right': w / 2 + (right * spec['scale'] + delta) * k,
                    'top': h / 2 - (.5 * spec['scale'] + spec['y']) * k,
                    'bottom': h / 2 - (-.5 * spec['scale'] + spec['y']) * k}
        for key, expected_value in expected.items():
            require(abs(m[key] - expected_value) <= 4, color + ' projected ' + key + ' mismatch')

def review(text, run, boot, pid, uid, captures, roi):
    rows = parse_rows(text, run, boot, pid, uid)
    begins = [row for row in rows if row['kind'] == 'begin']
    require([r['action'] for r in begins] == ACTIONS, 'Missing/extra/reordered actual command sequence')
    expected = commands(run, boot, [r['operation_id'] for r in begins])
    require(all(r['value'] == command for r, command in zip(begins, expected)), 'Raw command/input drift')
    require(len({r['operation_id'] for r in begins}) == len(begins), 'Operation nonce replay')
    require(all(r['operation_id'] in {b['operation_id'] for b in begins} for r in rows), 'Orphan raw row')
    operations = []
    for index, begin in enumerate(begins):
        rs = [r for r in rows if r['operation_id'] == begin['operation_id']]
        require(all(r['action'] == begin['action'] for r in rs), 'Operation action drift')
        require(rs[0] is begin and rs[-1]['kind'] == 'end' and
                sum(r['kind'] == 'begin' for r in rs) == 1 and
                sum(r['kind'] == 'end' for r in rs) == 1, 'Incomplete operation boundary')
        terminals = [r for r in rs if r['kind'] in ('return', 'throw')]
        require(len(terminals) == 1 and terminals[0]['kind'] == 'return' and
                rs[-2] is terminals[0] and terminals[0]['code'] == 0, 'Real operation failed/incomplete')
        require(begin['code'] == rs[-1]['code'] == 0 and rs[-1]['value'] is None, 'Control row corruption')
        require(all(r['code'] == 0 for r in rs if r['kind'] == 'api-return'), 'API return error')
        if index + 1 < len(begins):
            require(rs[-1]['seq'] < begins[index + 1]['seq'], 'Overlapping/reordered operations')
        apis = [r for r in rs if r['kind'] in ('api-return', 'api-throw')]
        if begin['action'] == 'load':
            require(len(apis) == 1 and apis[0]['kind'] == 'api-return' and
                    apis[0]['value'] == {'api': 'Scene.load', 'asset': 'graphics3d-audit.glb'}, 'Actual nonempty asset load missing')
            v = terminals[0]['value']
            require(v['generation'] == (1 if index == 0 else 2) and type(v['root_children']) is int and v['root_children'] > 0 and
                    v['group_name'] == 'AuditAsset' and v['red_name'] == 'AuditRed' and v['green_name'] == 'AuditGreen' and
                    v['red_type'] == v['green_type'] == 2 and v['camera_name'] == 'AuditCamera' and
                    v['camera_position'] == {'x': 0, 'y': 0, 'z': 3} and v['camera_rotation'] == {'x': 0, 'y': 0, 'z': 0, 'w': 1} and
                    v['camera_enabled'] is True and abs(v['camera_fov'] - math.pi / 3) < 1e-6 and
                    v['group_position'] == {'x': 0, 'y': 0, 'z': 0}, 'Actual loaded mesh/camera state wrong')
        elif begin['action'] == 'translate':
            value = terminals[0]['value']
            require(not apis and value['generation'] == (1 if index == 2 else 2) and
                    type(value['position']['x']) in (int, float) and
                    abs(value['position']['x'] - specification(run)['translate_x']) < 1e-5 and
                    value['position']['y'] == value['position']['z'] == 0, 'Actual group translation missing')
        elif begin['action'] == 'destroy':
            require(len(apis) == 1 and apis[0]['kind'] == 'api-return' and apis[0]['value'] ==
                    {'api': 'Scene.destroy', 'generation': 1 if index == 4 else 2}, 'Actual Scene.destroy acknowledgement missing')
        elif begin['action'] == 'invalid':
            require(len(apis) == 1 and apis[0]['kind'] == 'api-throw' and
                    apis[0]['value']['api'] == 'Scene.load' and apis[0]['value']['asset'] == 'graphics3d-invalid.glb' and
                    isinstance(apis[0]['value']['message'], str) and bool(apis[0]['value']['message']), 'Invalid GLB was not rejected by real Scene.load')
        else:
            require(not apis, 'Unexpected API operation')
        if begin['action'] in ('frame', 'quiet'):
            require(rs[-1]['monotonic_ms'] - begin['monotonic_ms'] >= begin['value']['wait_ms'], 'Actual settling/quiet interval missing')
        operations.append((begin, terminals[0]))
    frame_ops = [op for op in operations if op[0]['action'] == 'frame']
    require(type(captures) is dict and set(captures) == {op[0]['operation_id'] for op in frame_ops}, 'One original QMP image per frame operation required')
    frames = []
    for index, (begin, terminal) in enumerate(frame_ops):
        present = index not in (2, 5)
        value = terminal['value']
        require(value['generation'] == (1 if index < 3 else 2) and value['scene_present'] is present and
                (type(value['scheduled']) is bool if present else value['scheduled'] is None), 'Wrong actual frame lifecycle')
        blob = captures[begin['operation_id']]
        measured = pixels(blob, roi)
        if present:
            evaluate_frame(measured, run, translated=index in (1, 4))
        else:
            require(measured['red']['count'] == measured['green']['count'] == 0 and
                    measured['background_fraction'] >= .99, 'Destroyed scene left pixels/foreign foreground')
        frames.append({'operation_id': begin['operation_id'], 'ppm_sha256': hashlib.sha256(blob).hexdigest(), 'pixels': measured})
    for color in ('red', 'green'):
        for first, second in ((0, 3), (1, 4)):
            require(abs(frames[first]['pixels'][color]['cx'] - frames[second]['pixels'][color]['cx']) <= 3 and
                    abs(frames[first]['pixels'][color]['cy'] - frames[second]['pixels'][color]['cy']) <= 3, 'Recreated scene projection drift')
        require(frames[1]['pixels'][color]['cx'] - frames[0]['pixels'][color]['cx'] > .08 * roi[2], 'No actual visible group translation')
    require(all(r['value'] is None for r in rows if r['kind'] == 'return' and r['action'] in ('destroy', 'cleanup', 'quiet', 'invalid')), 'Control terminal value drift')
    return {'schema': 1, 'scope': 'nonempty_GLTF_pixels_translation_destroy_recreate_invalid_asset_retry_only',
            'run_id': run, 'boot_id': boot, 'pid': pid, 'uid': uid,
            'raw_sha256': hashlib.sha256(text.encode()).hexdigest(), 'assets': descriptors(run),
            'frames': frames, 'closed_ids': [], 'full_graphics3d_verified': False,
            'parent_provenance_required': ['new_package_and_checksum', 'actual_SDK_and_signed_HAP',
                'same_boot_process_token', 'foreground_viewport_ROI', 'QMP_capture_command_and_timing',
                'actual_cleanup_and_process_exit']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--uid', type=int, required=True)
    parser.add_argument('--roi', type=int, nargs=4, required=True, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    parser.add_argument('--capture', action='append', required=True, metavar='OPERATION_ID=ORIGINAL_QMP_PPM')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    capture = {}
    for value in args.capture:
        operation, separator, path = value.partition('=')
        require(separator and re.fullmatch('[a-f0-9]{32}', operation) and operation not in capture, 'Fresh unique capture binding required')
        capture[operation] = Path(path).read_bytes()
    result = review(args.raw.read_text(), args.run_id, args.boot_id, args.pid, args.uid, capture, args.roi)
    require(not args.output.exists(), 'Output already exists')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')

if __name__ == '__main__':
    main()
