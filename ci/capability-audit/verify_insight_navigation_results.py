"""Require native Page/Link dispatch, challenged receiver data and actual pixels.

Archive/boot/signature/command provenance belongs to the enclosing verifier.
This parser never declares a complete first-artifact gate.
"""
import json
from pathlib import Path
import re
from PIL import Image, ImageChops
from build_insight_navigation_probe import BUNDLE, ROLES
from build_insight_driver_probe import TARGET_BUNDLE
from verify_insight_driver_results import expected_info, verify_info
from verify_insight_decorator_build import verify_metadata
from guest_ui import select_node


def verify(text, nonce, role, uid, metadata, target_nonce):
    source = {row['intentName']: row for row in verify_metadata(metadata, target_nonce)}
    observations = [json.loads(line) for line in text.splitlines()]
    expected_names = (['identity', 'lookup.link', 'lookup.page'] +
        [name + '.' + kind + '.' + str(cycle) for kind in ('page', 'link') for cycle in range(2)
            for name in ('dispatch', 'returned')] + ['summary'] if role == 'system' else
        ['identity', 'denied.page', 'denied.link', 'summary'])
    if (role not in ROLES or type(uid) is not int or uid < 10000 or
            re.fullmatch('[a-f0-9]{32}', nonce or '') is None or
            not text.endswith('\n') or len(observations) != len(expected_names)):
        raise ValueError('complete actual navigation caller role/identity/observations required')
    for row, name in zip(observations, expected_names):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'data', 'error'} or
                row['runId'] != nonce or row['role'] != role or row['name'] != name or row['error'] != '' or
                type(row['data']) is not str or type(row['values']) is not list or
                any(type(value) is not int for value in row['values'])):
            raise ValueError('foreign, malformed, failed or reordered navigation observations')
    identity = observations[0]['values']
    if len(identity) != 3 or identity[:2] != [uid, uid] or identity[2] <= 1 or observations[0]['data']:
        raise ValueError('navigation actual UID/eUID/PID differs')
    if observations[-1]['values'] != [1] or observations[-1]['data']:
        raise ValueError('navigation summary is not complete')
    if role != 'system':
        if any(row['values'] != [1, 202 if role == 'normal' else 201, 1] or row['data']
               for row in observations[1:-1]):
            raise ValueError('native Page and Link executions require numeric role-specific denials')
        return observations
    for index, name in ((1, 'AuditLink'), (2, 'AuditPage')):
        if observations[index]['values']:
            raise ValueError('invalid metadata lookup payload')
        verify_info(json.loads(observations[index]['data']), expected_info(source[name]))
    for index, (kind, cycle) in enumerate((kind, cycle) for kind in ('page', 'link') for cycle in range(2)):
        dispatch, returned = observations[3 + 2 * index:5 + 2 * index]
        expected = dict(bundleName=TARGET_BUNDLE, moduleName='entry',
            abilityName='' if kind == 'link' else 'EntryAbility',
            insightIntentName='AuditLink' if kind == 'link' else 'AuditPage', executeMode=0,
            insightIntentParam={'value': nonce + ':' + kind + ':' + str(cycle)})
        if kind == 'link': expected['uris'] = [uri(target_nonce, nonce, cycle)]
        if dispatch['values'] or json.loads(dispatch['data']) != expected:
            raise ValueError('actual navigation dispatch differs from its exact registered intent and challenge')
        if returned['values'] != [0] or json.loads(returned['data']) != {}:
            raise ValueError('actual navigation dispatch failed')
    return observations


def uri(target_nonce, caller_nonce, cycle):
    return 'audit://intent/' + target_nonce + '?challenge=' + caller_nonce + ':' + str(cycle)


def marker_text(kind, cycle, target_nonce, caller_nonce):
    if kind == 'page': return target_nonce + ':' + caller_nonce + ':page:' + str(cycle) + ':actual:echo:link'
    if kind == 'link': return target_nonce + ':' + uri(target_nonce, caller_nonce, cycle)
    raise ValueError('exact page/link phase required')


def verify_receiver(target_text, page_text, target_nonce, caller_nonce, caller_uid, target_uid, caller_pid):
    targets = [json.loads(line) for line in target_text.splitlines()]
    pages = [json.loads(line) for line in page_text.splitlines()]
    if not target_text.endswith('\n') or not page_text.endswith('\n') or not targets or not pages:
        raise ValueError('complete independent actual receiver journals required')
    for row in targets:
        if (set(row) != {'runId', 'name', 'uid', 'pid', 'want'} or row['runId'] != target_nonce or
                row['name'] not in ('create', 'newWant') or row['uid'] != target_uid or
                type(row['pid']) is not int or row['pid'] <= 1 or not isinstance(row['want'], dict)):
            raise ValueError('foreign or malformed native intent receiver identity')
    matched = []
    for kind in ('page', 'link'):
        for cycle in range(2):
            challenge = caller_nonce + ':' + kind + ':' + str(cycle)
            candidates = []
            for row in targets:
                want = row['want']; parameters = want.get('parameters', {})
                value = (parameters.get('ohos.insightIntent.executeParam.param', {}).get('value')
                         if kind == 'page' else parameters.get('value'))
                if value != challenge: continue
                if (parameters.get('ohos.aafwk.param.callerUid') != caller_uid or
                        parameters.get('ohos.aafwk.param.callerPid') != caller_pid or
                        parameters.get('ohos.aafwk.param.callerBundleName') != BUNDLE or
                        parameters.get('ohos.insightIntent.executeParam.name') != ('AuditPage' if kind == 'page' else 'AuditLink') or
                        parameters.get('isShellCall') is not False):
                    raise ValueError('receiver challenge did not originate from the actual non-root signed intent caller')
                if kind == 'page':
                    if (parameters.get('ohos.insightIntent.executeParam.mode') != 0 or
                            parameters.get('ohos.insightIntent.decoratorType') != 2 or
                            parameters.get('ohos.insightIntent.pageParam.pagePath') !=
                            '@normalized:N&&&vpn-policy-probe/src/main/ets/pages/Index&'):
                        raise ValueError('native Page receiver was not dispatched through its registered page intent')
                elif want.get('uri') != uri(target_nonce, caller_nonce, cycle) or parameters.get('ohos.insightIntent.execute.openlink.flag') != 1:
                    raise ValueError('native Link receiver was not dispatched through the exact openLink intent URI')
                candidates.append(row)
            if len(candidates) != 1: raise ValueError('one actual receiver callback required for each independent challenge')
            matched.append(candidates[0])
    if matched[0]['name'] != 'create' or matched[1]['name'] != 'newWant' or any(row['pid'] != matched[0]['pid'] for row in matched):
        raise ValueError('actual cold-start Page and reused warm Page/Link identities differ')
    actual_pages = []
    for row in pages:
        if set(row) != {'runId', 'event', 'value', 'routerParameters', 'result'} or row['runId'] != target_nonce:
            raise ValueError('foreign or malformed page view observation')
        if row['value'] in (caller_nonce + ':page:0', caller_nonce + ':page:1'):
            actual_pages.append(row)
    if len(actual_pages) != 2 or [row['value'] for row in actual_pages] != [caller_nonce + ':page:0', caller_nonce + ':page:1']:
        raise ValueError('both real page parameter delivery callbacks required')
    for cycle, row in enumerate(actual_pages):
        if row['event'] != 'newParam' or row['result'] != marker_text('page', cycle, target_nonce, caller_nonce):
            raise ValueError('real Page reuse did not update the challenged view')
        parameters = json.loads(row['routerParameters'])
        if (parameters.get('value') != caller_nonce + ':page:' + str(cycle) or
                parameters.get('ohos.aafwk.param.callerBundleName') != BUNDLE or
                parameters.get('ohos.aafwk.param.callerUid') != caller_uid or
                parameters.get('ohos.aafwk.param.callerPid') != caller_pid):
            raise ValueError('Page lifecycle parameters lost their native caller identity')
    return dict(receiver_callbacks=matched, page_callbacks=actual_pages)


def phase_pixels(path, node):
    x, y, width, height = node['rect']
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('actual navigation compositor PNG required')
    with Image.open(path) as image:
        if image.format != 'PNG' or x + width > image.width or y + height > image.height:
            raise ValueError('navigation compositor image does not contain its actual view')
        text = image.convert('RGB').crop((x, y, x + width, y + height))
    ink = [index % width for index, pixel in enumerate(text.getdata()) if max(pixel) < 150]
    if len(ink) < 100 or (max(ink) - min(ink) + 1) < width * .85:
        raise ValueError('metadata success reused a blank or earlier shorter compositor view')
    return dict(dark_text_pixels=len(ink)), text


def verify_views(phases, target_nonce, caller_nonce):
    if [(row.get('kind'), row.get('cycle')) for row in phases] != [('page', 0), ('page', 1), ('link', 0), ('link', 1)]:
        raise ValueError('all four distinct actual navigation views required')
    previous = {}; metrics = []
    for row in phases:
        kind, cycle = row['kind'], row['cycle']
        layout = json.loads(Path(row['layout']).read_text())
        node = select_node(layout, TARGET_BUNDLE, text=marker_text(kind, cycle, target_nonce, caller_nonce))
        if node != row['selected_node'] or node['attributes'].get('id') != ('insight-decorator-ready' if kind == 'page' else 'insight-decorator-uri'):
            raise ValueError('navigation view/selector does not match actual native hierarchy')
        pixels, text = phase_pixels(row['screenshot'], node)
        item = dict(kind=kind, cycle=cycle, **pixels)
        if kind in previous:
            earlier, earlier_rect = previous[kind]
            if earlier_rect != node['rect']: raise ValueError('navigation view changed its geometry between challenges')
            changed = sum(max(pixel) > 10 for pixel in ImageChops.difference(earlier, text).getdata())
            if changed < 10: raise ValueError('new navigation challenge reused unchanged actual text pixels')
            item['changed_text_pixels'] = changed
        previous[kind] = text, node['rect']; metrics.append(item)
    return metrics
