"""Require actual role-bound calls and real WM/RS pixel sequences."""
import json
import math
from pathlib import Path
import re

from build_screen_blink_probe import PERMISSIONS, ROLES, TEMPLATE, page
from run_root_probe import digest
from verify_certificate_results import identity as certificate_identity

SCOPE = 'real_screen_window_calls_settings_and_permissions_NOT_full_behavior_gate'


def identity(text, role):
    if role not in ROLES:
        raise ValueError('explicit blink role required')
    return certificate_identity(text, 'normal' if role == 'normal' else 'system')


def verify_inputs(value, run_id, arch, role):
    generated = Path(value['generated_source'])
    declaration, settings = Path(value['sdk_declaration']), Path(value['settings_declaration'])
    if (value.get('schema_version') != 1 or type(value.get('schema_version')) is not int or
            value.get('run_id') != run_id or value.get('role') != role or value.get('arch') != arch or
            value.get('scope') != SCOPE or role not in ROLES or arch not in ('arm64', 'armv7a', 'x86_64') or
            value.get('request_permissions') != (list(PERMISSIONS) if role == 'system' else []) or
            value.get('template_sha256') != digest(TEMPLATE) or
            declaration.name != '@ohos.accessibility.config.d.ts' or settings.name != '@ohos.settings.d.ts' or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(field) for path, field in (
                (generated, 'generated_source_sha256'), (declaration, 'sdk_declaration_sha256'),
                (settings, 'settings_declaration_sha256'))) or generated.read_text() != page(run_id, role)):
        raise ValueError('blink HAP source, SDK, nonce, ABI or role differs')


def rows(text, run_id, role):
    if role not in ROLES or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh blink nonce and role required')
    values = [json.loads(line) for line in text.splitlines()]
    for row in values:
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'text'} or
                row['runId'] != run_id or row['role'] != role or not isinstance(row['name'], str) or
                not isinstance(row['text'], str) or not isinstance(row['values'], list) or
                any(type(value) is not int for value in row['values'])):
            raise ValueError('malformed/stale blink observation')
    return values


def verify_initial(text, run_id, role, identity_text, *, restarted=False, allow_more=False):
    actual = rows(text, run_id, role)
    uid = identity(identity_text, role)
    denied = 202 if role == 'normal' else 201
    expected = [('identity', None, '')]
    if role == 'system':
        expected += [('initial.master', [], '1' if restarted else '0')]
    elif restarted:
        raise ValueError('only the settings-owning role may restart')
    expected += [('initial.start', [0 if restarted else 5, 0, 1] if role == 'system' else [-1, denied, 1], ''),
                 ('initial.stop', [0, 0, 1] if role == 'system' else [-1, denied, 1], '')]
    for field, invalid in (('mode', (0, 3, -1)), ('scenario', (0, 5, -1))):
        expected += [(f'invalid.{field}.{number}', [-1, 401 if role == 'system' else denied, 1], '')
                     for number in invalid]
    expected += [('ready', [1], '')]
    if len(actual) < len(expected) or (not allow_more and len(actual) != len(expected)):
        raise ValueError('missing/extra blink initial observations')
    for row, (name, values, string) in zip(actual, expected):
        if row['name'] != name or row['text'] != string:
            raise ValueError('blink initial order/value differs: ' + name)
        if values is None:
            if len(row['values']) != 3 or row['values'][:2] != [uid, uid] or row['values'][2] <= 1:
                raise ValueError('blink caller UID/PID does not match installed role')
        elif row['values'] != values:
            raise ValueError('blink initial API result differs: ' + name)
    return actual[:len(expected)]


def optical_sequence(path, rect):
    """Diagnostic frame freshness only; never accepts or discards pulse frames."""
    from PIL import Image
    if (not isinstance(rect, list) or len(rect) != 4 or
            any(type(value) is not int for value in rect) or
            min(rect[:2]) < 0 or rect[2] < 32 or rect[3] < 4):
        raise ValueError('invalid optical marker rectangle')
    left, top, width, height = rect
    with Image.open(path) as image:
        if left + width > image.width or top + height > image.height:
            raise ValueError('optical marker outside captured image')
        rgb = image.convert('RGB')
        value = 0
        for bit in range(8):
            x0 = left + int(width * (bit + .3) / 8)
            x1 = left + int(width * (bit + .7) / 8)
            pixels = list(rgb.crop((x0, top + height // 3, max(x0 + 1, x1),
                                    top + 2 * height // 3)).getdata())
            # Black/white remain distinguishable under the real yellow overlay.
            zeros = sum(r < 160 and g < 160 and abs(r - g) < 30 for r, g, _ in pixels)
            ones = sum(r > 220 and g > 220 and abs(r - g) < 30 for r, g, _ in pixels)
            if ones / len(pixels) >= .97:
                value |= 1 << bit
            elif zeros / len(pixels) < .97:
                return None
        return value


def classify_pixels(path, rect):
    from PIL import Image
    if (not isinstance(rect, list) or len(rect) != 4 or any(type(value) is not int for value in rect) or
            rect[0] < 0 or rect[1] < 0 or min(rect[2:]) < 80):
        raise ValueError('actual visible test surface rectangle required')
    left, top, width, height = rect
    with Image.open(path) as image:
        if image.format != 'PNG' or left + width > image.width or top + height > image.height:
            raise ValueError('test surface outside real PNG')
        pixels = list(image.convert('RGB').crop((left + width // 4, top + height // 4,
                      left + width * 3 // 4, top + height * 3 // 4)).getdata())
    off = sum(all(abs(value - wanted) <= 10 for value, wanted in zip(pixel, (32, 48, 64))) for pixel in pixels)
    on = sum(80 <= red <= 230 and 80 <= green <= 230 and blue < 75 and abs(red - green) < 30
             for red, green, blue in pixels)
    if off / len(pixels) >= 0.97:
        return 'off'
    if on / len(pixels) >= 0.97:
        return 'on'
    raise ValueError('actual test surface is neither its baseline nor the translucent yellow screen pulse')


def verify_frames(frames, rect, mode):
    if mode not in ('continuous', 'single', 'armed-single', 'off') or not isinstance(frames, list) or len(frames) < 3:
        raise ValueError('complete real compositor frame sequence required')
    previous = -1.0
    kinds = []
    paths = set()
    for frame in frames:
        path = Path(frame['path'])
        before, after = frame['before'], frame['after']
        if (path.is_symlink() or not path.is_file() or str(path) in paths or digest(path) != frame['sha256'] or
                type(before) not in (float, int) or type(after) not in (float, int) or
                not math.isfinite(before) or not math.isfinite(after) or
                before < previous or after < before or after - before > 3):
            raise ValueError('stale/tampered/overlapping or excessively delayed compositor capture')
        paths.add(str(path))
        previous = after
        kinds.append(classify_pixels(path, rect))
    transitions = sum(a != b for a, b in zip(kinds, kinds[1:]))
    if mode == 'continuous' and (kinds.count('on') < 2 or kinds.count('off') < 2 or transitions < 2):
        raise ValueError('continuous mode must really alternate rendered on/off pixels')
    if mode == 'single' and ('on' not in kinds or kinds[-1] != 'off' or
                            transitions != 1 or kinds[0] != 'on'):
        raise ValueError('single mode must render once and clear without an explicit stop')
    if mode == 'armed-single' and ('on' not in kinds or kinds[0] != 'off' or
                                  kinds[-1] != 'off' or transitions != 2):
        raise ValueError('armed single must show baseline, one actual pulse and automatic clear')
    if mode == 'off' and any(kind != 'off' for kind in kinds):
        raise ValueError('stopped/disabled/dead caller left visible screen pulse')
    return kinds


def verify_background_restored(baseline, frames):
    """Caller exit returns to the actual pre-launch compositor, not an assumed UI."""
    from PIL import Image
    if len(frames) < 3:
        raise ValueError('caller exit requires multiple real background frames')
    path = Path(baseline['path'])
    if path.is_symlink() or digest(path) != baseline['sha256']:
        raise ValueError('pre-launch background changed')
    with Image.open(path) as image:
        if image.format != 'PNG' or min(image.size) < 100:
            raise ValueError('actual pre-launch PNG required')
        size = image.size
        rect = (size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4)
        expected = list(image.convert('RGB').crop(rect).getdata())
    seen = {str(path)}
    previous = -1.
    for frame in frames:
        path = Path(frame['path'])
        before, after = frame['before'], frame['after']
        if (path.is_symlink() or str(path) in seen or digest(path) != frame['sha256'] or
                type(before) not in (float, int) or type(after) not in (float, int) or
                not math.isfinite(before) or not math.isfinite(after) or
                before < previous or after < before or after - before > 3):
            raise ValueError('invalid caller-exit compositor capture')
        seen.add(str(path))
        previous = after
        with Image.open(path) as image:
            if image.format != 'PNG' or image.size != size:
                raise ValueError('caller-exit display changed')
            actual = list(image.convert('RGB').crop(rect).getdata())
        same = sum(all(abs(a - b) <= 10 for a, b in zip(pixel, wanted))
                   for pixel, wanted in zip(actual, expected))
        if same / len(expected) < .97:
            raise ValueError('caller exit did not restore actual pre-launch background')
