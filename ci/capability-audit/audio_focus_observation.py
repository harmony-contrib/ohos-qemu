"""Actual fixed-source selectors and service joins for ordinary audio focus tests."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from guest_ui import NodeNotReady, bounds, select_node

HERE = Path(__file__).resolve().parent
MAP = HERE.parents[1] / 'docs/capability-audit/parallel/network/audio-observation-20261016.json'
DIALOG = 'com.ohos.notificationdialog'
BUNDLES = ('org.harmonycontrib.capabilityaudit', 'org.harmonycontrib.capabilityauditfocus')


def source_contract(root):
    value = json.loads(MAP.read_text())
    if value['background_tasks']['sa_id'] != 1903 or value['notifications']['sa_id'] != 3203:
        raise ValueError('actual service observation map differs')
    for item in value['sources'].values():
        p = Path(root) / item['path']
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('fixed actual audio-observation source differs: ' + item['path'])
    return {'scope': 'actual_fixed_audio_background_and_notification_service_sources',
            'map_sha256': hashlib.sha256(MAP.read_bytes()).hexdigest(),
            'sources_sha256': {v['path']: v['sha256'] for v in value['sources'].values()},
            'translations': value['authorization_dialog']['translations'], 'dialog_bundle': DIALOG}


def notification_node(layout, contract):
    if contract.get('dialog_bundle') != DIALOG or not contract.get('sources_sha256'):
        raise ValueError('actual trusted notification dialog provenance required')
    # Phone has duplicate horizontal/vertical buttons, with one hidden layout.
    # Ignore hidden candidates, but reject multiple visible matches.
    candidates = {}
    for translation in contract['translations'].values():
        title = translation['group_label_notification'].replace('%s', 'Capability audit')
        try:
            select_node(layout, DIALOG, text=title)
        except NodeNotReady:
            continue
        pending = [(node, '') for node in (layout if isinstance(layout, list) else [layout])]
        count = 0
        while pending:
            node, parent_bundle = pending.pop()
            count += 1
            if count > 100000 or not isinstance(node, dict) or not isinstance(node.get('attributes'), dict):
                raise ValueError('malformed notification UI hierarchy')
            a = node['attributes']
            bundle = a.get('bundleName') or parent_bundle
            if (bundle == DIALOG and a.get('text') == translation['ALLOW'] and a.get('visible') == 'true' and
                    a.get('enabled') == 'true' and a.get('clickable') == 'true' and a.get('type') == 'Button'):
                rect = list(bounds(a.get('bounds')))
                candidates[tuple(rect)] = {'attributes': a, 'bundle': bundle, 'rect': rect}
            children = node.get('children', [])
            if not isinstance(children, list): raise ValueError('malformed notification UI children')
            pending.extend((child, bundle) for child in children)
    if len(candidates) != 1:
        raise NodeNotReady('one visible current-app notification authorization button required')
    return next(iter(candidates.values()))


def records(text, notification=False):
    if not isinstance(text, str) or any(s in text.lower() for s in ('permission denied', 'param invaild', 'unknown option')):
        raise ValueError('actual audio service dump failed')
    if notification and 'notification list:\n' not in text:
        raise ValueError('actual active notification list is unavailable')
    pattern = r'(?m)^No\.([0-9]+)' + (r'\s*\n' if notification else r'(?=\t|$)')
    starts = list(re.finditer(pattern, text))
    if not starts:
        if not notification and text.strip().endswith('No running continuous task'):
            return []
        raise ValueError('actual audio service record list missing')
    if [int(m.group(1)) for m in starts] != list(range(1, len(starts) + 1)):
        raise ValueError('duplicate or invalid actual service record numbers')
    rows = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        item = {}
        for line in text[start.end():end].splitlines():
            match = re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9]*):\s*(.*?)\s*', line)
            if not match: continue
            key, value = match.groups()
            if key in item: raise ValueError('duplicate actual service field: ' + key)
            item[key] = value
        rows.append(item)
    return rows


def integer(row, name, minimum=0):
    value = row.get(name, '')
    if re.fullmatch(r'0|[1-9][0-9]*', value) is None or int(value) < minimum:
        raise ValueError('invalid actual service integer: ' + name)
    return int(value)


def active_task(uid_text, all_text, notifications_text, uid, pid, bundle, task_id, notification_id):
    if type(uid) is not int or uid // 200000 != 100 or uid % 200000 < 10000 or bundle not in BUNDLES:
        raise ValueError('actual ordinary audio caller identity required')
    own = [r for r in records(uid_text) if integer(r, 'uid') == uid]
    if len(own) != 1:
        raise ValueError('one actual continuous audio task for this UID required')
    task = own[0]
    if (integer(task, 'pid', 1) != pid or integer(task, 'continuousTaskId') != task_id or
            integer(task, 'notificationId') != notification_id or task.get('abilityName') != 'EntryAbility' or
            task.get('wantAgentBundleName') != bundle or task.get('wantAgentAbilityName') != 'EntryAbility'):
        raise ValueError('actual continuous audio task belongs to another session')
    matches = [r for r in records(all_text) if integer(r, 'uid') == uid and integer(r, 'pid', 1) == pid and
               integer(r, 'continuousTaskId') == task_id]
    if len(matches) != 1:
        raise ValueError('UID task has no unique full service record')
    full = matches[0]
    modes = full.get('backgroundModes', '')
    if (re.fullmatch(r'(?:[0-9]+,)+', modes) is None or 3 not in list(map(int, modes.rstrip(',').split(','))) or
            full.get('suspendState') != 'false' or full.get('bundleName') != bundle or
            integer(full, 'notificationId') != notification_id or
            full.get('isCombinedTaskNotification') != 'false'):
        raise ValueError('actual recording task suspended, combined, or has no audioRecording mode')
    joined = [r for r in records(notifications_text, notification=True) if integer(r, 'OwnerUid') == uid and
              integer(r, 'Id') == notification_id and r.get('Label') == full.get('notificationLabel')]
    if len(joined) != 1:
        raise ValueError('actual active background notification owner/ID/label does not match the task')
    return {'task': full, 'notification': joined[0], 'identity_key': [uid, notification_id, full['notificationLabel']]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(source_contract(args.source_root), ensure_ascii=False))
