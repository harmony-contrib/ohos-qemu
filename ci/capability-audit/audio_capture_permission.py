#!/usr/bin/env python3
"""Read pinned permission-manager labels and operate its real MIC dialog."""
import argparse
import json
from pathlib import Path
import re
import time

from audio_capture_contract import sha
from guest_ui import select_node, NodeNotReady, LayoutNotReady

BUNDLE = 'com.ohos.permissionmanager'
SCOPE = 'actual_trusted_MICROPHONE_dialog_resources'


def labels(root):
    base = Path(root) / 'applications/standard/permission_manager'
    main = base / 'permissionmanager/src/main'
    paths = [main / 'ets/common/model/permissionGroup.ets',
             main / 'ets/pages/dialogPlus.ets', main / 'ets/common/base/BasePermissionStrategy.ets',
             main / 'ets/common/permissionGroupManager/MicrophoneStrategy.ets']
    model, dialog, strategy, microphone = [p.read_text() for p in paths]
    if ("$r('app.string.group_label_microphone', appName)" not in microphone or
            'getButtonList(' in microphone or
            not re.search(r'getButtonList\(\): ButtonStatus\[\]\s*\{\s*return '
                          r'\[ButtonStatus\.DENY, ButtonStatus\.ALLOW\];\s*\}', strategy) or
            not re.search(r'new GroupInfo\(PermissionGroup\.MICROPHONE,.*?\[ButtonStatus\.DENY, ButtonStatus\.ALLOW\]', model) or
            "[ButtonStatus.ALLOW, $r('app.string.allow')]" not in model or
            "[ButtonStatus.DENY, $r('app.string.ban')]" not in model or
            'Button(buttonResource.get(' not in dialog or 'this.processClick(' not in dialog):
        raise ValueError('actual microphone permission title/button protocol changed')
    translations = {}
    for p in sorted((main / 'resources').glob('*/element/string.json')):
        paths.append(p)
        rows = json.loads(p.read_text())['string']
        values = {key: [r['value'] for r in rows if r['name'] == key]
                  for key in ('group_label_microphone', 'allow', 'ban')}
        if any(len(v) > 1 or any(not isinstance(s, str) or not s for s in v) for v in values.values()):
            raise ValueError('ambiguous actual microphone permission translation')
        translations[p.parts[-3]] = values
    base_values = translations.get('base', {})
    if any(len(base_values.get(k, [])) != 1 for k in ('group_label_microphone', 'allow', 'ban')):
        raise ValueError('base microphone permission resources missing')
    locales = []
    for name, values in translations.items():
        row = {k: (values[k] or base_values[k])[0] for k in base_values}
        if row['group_label_microphone'].count('%s') != 1:
            raise ValueError('microphone dialog application-name placeholder changed')
        locales.append({'locale': name, 'title': row['group_label_microphone'].replace('%s', 'Capability audit'),
                        'allow': row['allow'], 'deny': row['ban']})
    return {'schema_version': 1, 'scope': SCOPE, 'bundle': BUNDLE, 'locales': locales,
            'files_sha256': {str(p.relative_to(base)): sha(p) for p in paths}}


def select(layout, value, denied):
    if value.get('scope') != SCOPE or value.get('bundle') != BUNDLE or not value.get('files_sha256'):
        raise ValueError('actual trusted microphone resource provenance required')
    candidates = []
    seen = set()
    for locale in value['locales']:
        try:
            select_node(layout, BUNDLE, text=locale['title'])
        except NodeNotReady:
            continue
        text = locale['deny' if denied else 'allow']
        node = select_node(layout, BUNDLE, text=text, clickable=True)
        key = tuple(node['rect'])
        if key not in seen:
            seen.add(key)
            candidates.append(node)
    if len(candidates) != 1:
        raise NodeNotReady('one actual microphone title and decision button required')
    return candidates[0]


def decide(ui, value, denied, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            layout, path = ui.layout(bundle=BUNDLE, label='microphone-permission')
            node = select(layout, value, denied)
        except (NodeNotReady, LayoutNotReady):
            time.sleep(0.5)
            continue
        left, top, width, height = node['rect']
        ui.shell(f'uitest uiInput click {left + width // 2} {top + height // 2}', 'actual-MIC-permission-decision')
        return {'layout': str(path), 'layout_sha256': sha(path), 'selected_node': node,
                'decision': 'DENY' if denied else 'ALLOW', 'bundle': BUNDLE, 'scope': SCOPE}
    raise ValueError('actual trusted microphone dialog did not appear')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(labels(args.source_root), ensure_ascii=False))
