"""Require two distinct ordinary widget lifecycles and both caller denial roles.

The enclosing verifier must still bind source/HAP signatures, commands and a new
archive/boot. These journal and UI checks alone never close the artifact gate.
"""
import json
import re
from pathlib import Path
from PIL import Image, ImageChops
from build_insight_form_host_probe import BUNDLE, ROLES
from guest_ui import select_node


def rows(text):
    if text and not text.endswith('\n'):
        raise ValueError('truncated form observation')
    return [json.loads(line) for line in text.splitlines()]


def verify(text, nonce, role, uid):
    if (role not in ROLES or type(uid) is not int or uid < 10000 or
            re.fullmatch('[a-f0-9]{32}', nonce or '') is None):
        raise ValueError('actual non-root form caller identity and nonce required')
    observations = rows(text)
    if not observations:
        raise ValueError('actual form observations required')
    for row in observations:
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'cycle', 'name', 'values', 'data', 'error'} or
                row['runId'] != nonce or row['role'] != role or type(row['cycle']) is not int or
                row['cycle'] not in (0, 1) or row['error'] != '' or type(row['data']) is not str or
                type(row['values']) is not list or any(type(value) is not int for value in row['values'])):
            raise ValueError('foreign, failed or malformed widget observation')
    cycles = (0, 1) if role == 'system' else (0,)
    expected_cycles = [cycle for cycle in cycles for row in observations if row['cycle'] == cycle]
    if [row['cycle'] for row in observations] != expected_cycles:
        raise ValueError('widget recreation cycles are missing, foreign or interleaved')
    identifiers = []
    for cycle in cycles:
        actual = [row for row in observations if row['cycle'] == cycle]
        ordered = [row for row in actual if row['name'] != 'update']
        names = (['identity', 'acquired', 'load', 'request', 'delete', 'deleted.reject', 'summary']
                 if role == 'system' else ['identity', 'denied', 'summary'])
        if [row['name'] for row in ordered] != names:
            raise ValueError('complete acquisition/request/deletion boundary required')
        identity = ordered[0]['values']
        if len(identity) != 3 or identity[:2] != [uid, uid] or identity[2] <= 1 or ordered[0]['data']:
            raise ValueError('widget caller actual UID/eUID/PID differs')
        if ordered[-1]['values'] != [1] or ordered[-1]['data']:
            raise ValueError('invalid widget completion payload')
        if role != 'system':
            if len(actual) != 3 or ordered[1]['values'] != [1, 202 if role == 'normal' else 201, 1] or ordered[1]['data']:
                raise ValueError('exact native numeric form system/permission denial required')
            continue
        identifier = ordered[1]['data']
        if re.fullmatch('[1-9][0-9]{0,18}', identifier) is None or int(identifier) > (1 << 63) - 1:
            raise ValueError('native string form ID is absent or invalid')
        if identifier in identifiers:
            raise ValueError('recreation reused the deleted widget ID')
        identifiers.append(identifier)
        if ordered[1]['values'] != [1, 0]:
            raise ValueError('actual widget acquisition or lock state differs')
        for row in ordered[2:5]:
            if row['values'] != [1] or row['data'] != identifier:
                raise ValueError('widget service operation refers to another ID')
        if ordered[5]['values'] != [1, 16501001, 1] or ordered[5]['data'] != identifier:
            raise ValueError('deleted native form ID must be rejected as nonexistent')
        updates = [row for row in actual if row['name'] == 'update']
        if len(updates) != 2 or any(row['values'] != [1] or row['data'] != identifier for row in updates):
            raise ValueError('both initial data and requested update callbacks required')
        acquired_at = next(index for index, row in enumerate(actual) if row['name'] == 'acquired')
        delete_at = next(index for index, row in enumerate(actual) if row['name'] == 'delete')
        if any(not acquired_at < index < delete_at for index, row in enumerate(actual) if row['name'] == 'update'):
            raise ValueError('widget callback escaped its active lifecycle')
    return identifiers


def verify_provider(text, target_nonce, identifiers):
    if re.fullmatch('[a-f0-9]{32}', target_nonce or '') is None or len(identifiers) != 2:
        raise ValueError('complete fresh provider nonce and two widget identities required')
    actual = rows(text)
    expected = [dict(runId=target_nonce, name=name, formId=identifier)
                for identifier in identifiers for name in ('add', 'update', 'update.success', 'remove')]
    if actual != expected:
        raise ValueError('actual FormExtension add/update/remote update completion/removal differs')
    return actual


def verify_layout(document, target_nonce, identifier, state):
    if state not in ('added', 'updated'):
        raise ValueError('exact widget data phase required')
    marker = select_node(document, BUNDLE, identifier='insight-form-widget-data')
    expected = target_nonce + ':' + identifier + ':' + state
    if marker['attributes'].get('text') != expected or marker['attributes'].get('originalText') != expected:
        raise ValueError('actual widget view did not bind its fresh provider data')
    frame = select_node(document, BUNDLE, identifier='insight-form-host-widget')
    return {'marker': marker, 'frame': frame}


def phase_pixels(path, layout, target_nonce, identifier, state):
    nodes = verify_layout(layout, target_nonce, identifier, state)
    left, top, width, height = nodes['frame']['rect']
    x, y, text_width, text_height = nodes['marker']['rect']
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('actual compositor PNG required')
    with Image.open(path) as image:
        if image.format != 'PNG' or image.size[0] < left + width or image.size[1] < top + height:
            raise ValueError('widget screenshot does not contain its actual view')
        picture = image.convert('RGB')
    colors = list(picture.crop((left, top, left + width, top + height)).getdata())
    matching = sum(all(abs(value - expected) <= 4 for value, expected in zip(pixel, (221, 238, 255)))
                   for pixel in colors)
    text = picture.crop((x, y, x + text_width, y + text_height))
    dark = sum(max(pixel) < 180 for pixel in text.getdata())
    if matching < len(colors) * .85 or dark < 50:
        raise ValueError('widget rendered neither its expected card surface nor real data text')
    return dict(card_pixels=len(colors), matched_background_pixels=matching, dark_text_pixels=dark), text


def verify_pixels(acquired_image, updated_image, acquired_layout, updated_layout, target_nonce, identifier):
    acquired = verify_layout(acquired_layout, target_nonce, identifier, 'added')
    updated = verify_layout(updated_layout, target_nonce, identifier, 'updated')
    if acquired['frame']['rect'] != updated['frame']['rect'] or acquired['marker']['rect'] != updated['marker']['rect']:
        raise ValueError('widget evidence changed its data/view rectangle')
    initial_metrics, initial_text = phase_pixels(acquired_image, acquired_layout, target_nonce, identifier, 'added')
    updated_metrics, updated_text = phase_pixels(updated_image, updated_layout, target_nonce, identifier, 'updated')
    metrics = [initial_metrics, updated_metrics]
    pictures = [initial_text, updated_text]
    difference = ImageChops.difference(*pictures)
    changed = sum(max(pixel) > 10 for pixel in difference.getdata())
    if changed < 10:
        raise ValueError('updated widget hierarchy reused unchanged compositor text pixels')
    return dict(phases=metrics, changed_text_pixels=changed)
