"""Drive only the ordinary test app's observed Photos controls, never coordinates."""
import json
from pathlib import Path
import time

from guest_ui import bounds, select_node
from run_root_probe import digest


def button_ancestor(layout, bundle, identifier):
    pending = [(node, '', (), 0) for node in (layout if isinstance(layout, list) else [layout])]
    selected = []
    count = 0
    while pending:
        node, inherited, ancestors, depth = pending.pop()
        count += 1
        if count > 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('invalid Photos hierarchy')
        attrs, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attrs, dict) or not isinstance(children, list):
            raise ValueError('invalid Photos hierarchy node')
        actual = attrs.get('bundleName') or inherited
        lineage = ancestors + ((attrs, actual),)
        if actual == bundle and attrs.get('id') == identifier and attrs.get('visible') == 'true':
            buttons = [item for item, owner in lineage if owner == bundle and item.get('type') == 'Button'
                       and all(item.get(key) == 'true' for key in ('visible', 'enabled', 'clickable'))]
            if not buttons:
                raise ValueError('Photos close icon has no owned enabled Button ancestor')
            selected.append({'attributes': buttons[-1], 'bundle': bundle,
                             'rect': list(bounds(buttons[-1].get('bounds')))})
        pending.extend((child, actual, lineage, depth + 1) for child in children)
    if len(selected) != 1:
        raise ValueError('unique owned Photos close button required')
    return selected[0]


def dialog_control(layout, bundle, kind):
    if kind == 'cancel':
        return button_ancestor(layout, bundle, 'Third_Select_PickerClose')
    if kind == 'save':
        select_node(layout, bundle, text='允许“Capability audit”保存 1 张图片？')
        node = select_node(layout, bundle, identifier='advanced_dialog_button_1', clickable=True)
        if node['attributes'].get('text') != '允许':
            raise ValueError('expected one-test-image consent action')
        return node
    if kind == 'select':
        node = select_node(layout, bundle, identifier='currentSelectCount')
        if node['attributes'].get('text') != '已选 1/1':
            raise ValueError('expected exactly one preselected test image')
        select_node(layout, bundle, text='完成')
        return select_node(layout, bundle, identifier='Complete', clickable=True)
    raise ValueError('unknown Photos test dialog')


def exercise(ui, bundle, poll, run_id):
    actions = []

    def observe(marker):
        value = poll('"name":"' + marker + '"')
        rows = [json.loads(line) for line in value.splitlines()]
        if not rows or any(not isinstance(row, dict) or row.get('runId') != run_id or row.get('sequence') != index + 1 or
               row.get('pass') is not True for index, row in enumerate(rows)):
            raise ValueError('failed/stale Photos observation before UI action')

    def open_button(identifier, label):
        action = ui.click(bundle, identifier=identifier, label=label)
        action.update(kind=label, layout_sha256=digest(Path(action['layout'])))
        actions.append(action)

    def dialog(kind):
        deadline = time.monotonic() + 30
        while True:
            layout, path = ui.layout(label='photos-' + kind)
            try:
                node = dialog_control(layout, bundle, kind)
                break
            except ValueError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)
        screen = ui.screenshot(label='photos-' + kind)
        left, top, width, height = node['rect']
        ui.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2),
                 'photos-' + kind + '-observed-control')
        actions.append({'kind': kind, 'layout': str(path), 'layout_sha256': digest(path),
                        'selected_node': node, 'screenshot': str(screen), 'screenshot_sha256': digest(screen)})

    observe('metadata.complete')
    open_button('photos-open-picker', 'open-picker')
    observe('picker.opened')
    dialog('cancel')
    observe('picker.user-cancel-result')
    open_button('photos-save-asset', 'create-test-asset')
    observe('asset.dialog-requested')
    dialog('save')
    observe('asset.recent')
    open_button('photos-read-asset', 'read-test-asset')
    observe('asset.read-picker-requested')
    dialog('select')
    observe('asset.readback')
    return actions


def verify_actions(actions, bundle):
    expected = ('open-picker', 'cancel', 'create-test-asset', 'save', 'read-test-asset', 'select')
    identifiers = {'open-picker': 'photos-open-picker', 'create-test-asset': 'photos-save-asset',
                   'read-test-asset': 'photos-read-asset'}
    if not isinstance(actions, list) or len(actions) != len(expected):
        raise ValueError('all six observed Photos UI actions required')
    for action, kind in zip(actions, expected):
        path = Path(action['layout'])
        if path.is_symlink() or action['kind'] != kind or digest(path) != action['layout_sha256']:
            raise ValueError('Photos action layout changed')
        layout = json.loads(path.read_text())
        node = (select_node(layout, bundle, identifier=identifiers[kind], clickable=True)
                if kind in identifiers else dialog_control(layout, bundle, kind))
        if node != action['selected_node']:
            raise ValueError('Photos action differs from actual uniquely matched control')
        if kind not in identifiers:
            screen = Path(action['screenshot'])
            if screen.is_symlink() or digest(screen) != action['screenshot_sha256']:
                raise ValueError('Photos compositor evidence changed')
            from PIL import Image
            with Image.open(screen) as capture:
                capture.verify()
                if capture.format != 'PNG' or min(capture.size) < 100:
                    raise ValueError('invalid Photos compositor capture')
