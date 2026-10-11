"""Actual component geometry, scroll and child-state preservation via packaged UI."""
import json
from pathlib import Path
import time
from PIL import Image

from guest_ui import LayoutNotReady, select_node
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.capabilityaudit'
IDS = {'parent': 'components-dynamic', 'a': 'components-child-a', 'b': 'components-child-b',
       'list': 'components-arc-list', 'bar': 'components-arc-bar'}


def checked_path(record, key):
    path = Path(record.get(key, ''))
    if (not path.is_absolute() or path.is_symlink() or not path.is_file() or
            digest(path) != record.get(key + '_sha256')):
        raise ValueError('actual component UI evidence changed: ' + key)
    return path


def inside(child, parent):
    x, y, w, h = child['rect']; left, top, width, height = parent['rect']
    if not (left - 2 <= x and top - 2 <= y and x + w <= left + width + 2 and y + h <= top + height + 2):
        raise ValueError('actual component child is outside its native container')


def geometry(nodes, phase, run_id, counter):
    if phase not in (1, 2) or type(phase) is not int or type(counter) is not int or counter not in (0, 1, 2):
        raise ValueError('actual row/column phase and ordinary child counter required')
    if (nodes['a']['attributes'].get('text') != run_id + ' child A ' + str(counter) or
            nodes['b']['attributes'].get('text') != run_id + ' child B'):
        raise ValueError('actual painted ordinary caller nonce/child state missing')
    inside(nodes['a'], nodes['parent']); inside(nodes['b'], nodes['parent'])
    a, b = nodes['a']['rect'], nodes['b']['rect']
    if phase == 1:
        if abs(a[1] - b[1]) > 2 or a[0] + a[2] > b[0] + 2:
            raise ValueError('actual RowLayoutAlgorithm did not lay out both children horizontally')
    elif abs(a[0] - b[0]) > 2 or a[1] + a[3] > b[1] + 2:
        raise ValueError('actual ColumnLayoutAlgorithm did not move the preserved children vertically')
    item = nodes['item']
    inside(item, nodes['list'])
    if item['attributes'].get('text') != run_id + ' item ' + ('0' if counter == 0 else '7'):
        raise ValueError('actual ArcList initial/scrolled nonce item is missing')


def painted(path, nodes):
    with Image.open(path) as image:
        image.load()
        if image.format != 'PNG' or min(image.size) < 100:
            raise ValueError('actual ordinary component compositor PNG required')
        image = image.convert('RGB')
        for key, expected in (('a', (176, 48, 32)), ('b', (32, 160, 48)), ('item', (48, 96, 32))):
            left, top, width, height = nodes[key]['rect']
            if min(left, top) < 0 or left + width > image.width or top + height > image.height:
                raise ValueError('actual component lies outside the compositor')
            pixels = list(image.crop((left, top, left + width, top + height)).get_flattened_data())
            count = sum(max(abs(a-b) for a, b in zip(pixel, expected)) <= 16 for pixel in pixels)
            if count < max(8, len(pixels) // 10):
                raise ValueError('actual component background not painted at its current native geometry: ' + key)
        left, top, width, height = nodes['bar']['rect']
        if min(left, top) < 0 or left + width > image.width or top + height > image.height:
            raise ValueError('actual ArcScrollBar lies outside compositor')
        pixels = list(image.crop((left, top, left + width, top + height)).get_flattened_data())
        if sum(max(abs(channel - 16) for channel in pixel) >= 24 for pixel in pixels) < 8:
            raise ValueError('actual ArcScrollBar thumb did not paint over its native background')


def exercise(ui, read_result, run_id, timeout=60, evidence_path=None):
    actions = dict(run_id=run_id, scope='actual_Arc_scroll_and_dynamic_row_column_UI_NOT_full_gate',
                   captures=[], attempts=[], clicks=[], first_artifact_behavior_gate_passed=False)
    def save():
        if evidence_path is not None:
            Path(evidence_path).write_text(json.dumps(actions, indent=2) + '\n')
    save()
    def wait_raw(predicate, label):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = read_result()
            if text.endswith('\n'):
                rows = [json.loads(line) for line in text.splitlines()]
                if any(row.get('runId') != run_id or row.get('error') != '' or row.get('chained') is not True for row in rows):
                    raise ValueError('real component factory/caller failed: ' + label)
                if predicate(rows): return text
            time.sleep(0.1)
        raise ValueError('actual component event timed out: ' + label)
    def click(identifier, label):
        row = ui.click(BUNDLE, identifier=identifier, label=label)
        row.update(identifier=identifier, label=label, layout_sha256=digest(Path(row['layout'])))
        actions['clicks'].append(row)
        save()
    def capture(phase, counter):
        deadline = time.monotonic() + timeout
        last = ''
        while time.monotonic() < deadline:
            row = dict(phase=phase, counter=counter)
            actions['attempts'].append(row)
            try:
                layout, path = ui.layout(bundle=BUNDLE, label=f'components-{phase}-{counter}')
                row.update(layout=str(path), layout_sha256=digest(path))
                ids = dict(IDS, item='components-item-' + ('0' if counter == 0 else '7'))
                nodes = {key: select_node(layout, BUNDLE, identifier=identifier) for key, identifier in ids.items()}
                geometry(nodes, phase, run_id, counter)
                screen = ui.screenshot(label=f'components-painted-{phase}-{counter}')
                row.update(nodes=nodes, screenshot=str(screen), screenshot_sha256=digest(screen))
                painted(screen, nodes)
                raw = read_result()
                native = ui.output / f'components-native-{phase}-{counter}.log'
                native.write_text(raw)
                row.update(native=str(native), native_sha256=digest(native), status='painted')
                actions['captures'].append(row); save(); return
            except (ValueError, LayoutNotReady) as error:
                last = str(error); row['error'] = last; save(); time.sleep(0.25)
        raise ValueError('actual component layout/compositor did not settle: ' + last)
    wait_raw(lambda rows: len(rows) == 1 and rows[0]['name'] == 'ready', 'initial')
    click('components-start', 'components-start-real-factories')
    capture(1, 0)
    click('components-scroll', 'components-real-scroll-to-last')
    wait_raw(lambda rows: any(row['name'] == 'scroll.request' for row in rows) and
             any(row['name'] == 'arc.index' and row['values'][2] == 7 for row in rows), 'real-scroll')
    # Child counter 1 is produced by a real click before the layout switch.
    click('components-child-a', 'components-row-child-click')
    wait_raw(lambda rows: any(row['name'] == 'child.clicked' and row['values'][0] == 1 for row in rows), 'child-one')
    capture(1, 1)
    click('components-switch', 'components-real-algorithm-switch')
    wait_raw(lambda rows: any(row['name'] == 'switch.column' for row in rows), 'switch')
    capture(2, 1)
    click('components-child-a', 'components-column-preserved-child-click')
    wait_raw(lambda rows: any(row['name'] == 'child.clicked' and row['values'][0] == 2 for row in rows), 'child-two')
    capture(2, 2)
    # Observation only: no callback invocation or native library substitution.
    return actions, read_result()


def verify_actions(actions, run_id, raw_text):
    if (actions.get('run_id') != run_id or
            actions.get('scope') != 'actual_Arc_scroll_and_dynamic_row_column_UI_NOT_full_gate' or
            actions.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('actual component UI belongs to another ordinary caller')
    clicks = actions.get('clicks')
    order = [('components-start', 'components-start-real-factories'),
             ('components-scroll', 'components-real-scroll-to-last'),
             ('components-child-a', 'components-row-child-click'),
             ('components-switch', 'components-real-algorithm-switch'),
             ('components-child-a', 'components-column-preserved-child-click')]
    if not isinstance(clicks, list) or len(clicks) != len(order):
        raise ValueError('actual scroll/child/switch UI actions missing')
    for row, (identifier, label) in zip(clicks, order):
        actual = select_node(json.loads(checked_path(row, 'layout').read_text()), BUNDLE,
                             identifier=identifier, clickable=True)
        if row.get('identifier') != identifier or row.get('label') != label or row.get('selected_node') != actual:
            raise ValueError('component action did not use its actual ordinary-app control')
    captures, attempts = actions.get('captures'), actions.get('attempts')
    order = [(1, 0), (1, 1), (2, 1), (2, 2)]
    if not isinstance(captures, list) or len(captures) != 4 or not isinstance(attempts, list):
        raise ValueError('initial/scroll/algorithm-switch/preserved-child captures missing')
    previous_native = ''
    for row, (phase, counter) in zip(captures, order):
        if (row.get('phase') != phase or row.get('counter') != counter or
                row.get('status') != 'painted' or row not in attempts or row.get('error')):
            raise ValueError('actual component captures are missing or reordered')
        layout = json.loads(checked_path(row, 'layout').read_text())
        ids = dict(IDS, item='components-item-' + ('0' if counter == 0 else '7'))
        nodes = {key: select_node(layout, BUNDLE, identifier=identifier) for key, identifier in ids.items()}
        if nodes != row.get('nodes'):
            raise ValueError('actual component capture geometry was replaced')
        geometry(nodes, phase, run_id, counter)
        painted(checked_path(row, 'screenshot'), nodes)
        native = checked_path(row, 'native').read_text()
        if not native.endswith('\n') or not native.startswith(previous_native) or not raw_text.startswith(native):
            raise ValueError('component compositor capture lacks its exact append-only native observation')
        rows = [json.loads(line) for line in native.splitlines()]
        children = [value for value in rows if value.get('name') == 'child.clicked']
        if (not rows or rows[0].get('name') != 'ready' or
                any(value.get('runId') != run_id or type(value.get('phase')) is not int or
                    value['phase'] > phase for value in rows) or
                len(children) != counter or
                (counter and children[-1].get('values', [])[:1] != [counter]) or
                (phase == 2 and not any(value.get('name') == 'switch.column' for value in rows))):
            raise ValueError('actual painted layout is not bound to its native phase and child state')
        previous_native = native
    # Retain every compositor attempt, including stale/unpainted frames.
    for row in attempts:
        for key in ('layout', 'screenshot', 'native'):
            if key in row: checked_path(row, key)
        if row.get('status') != 'painted' and not row.get('error'):
            raise ValueError('component compositor retry lost its original failure')
    return dict(actual_compositor_captures=4, real_scroll_to_last=True,
                row_to_column_native_layout=True, child_clicked_in_both_layouts=True)
