"""Real Camera permission UI and live surfaces on the enclosing owned VM."""
import json
from pathlib import Path
import shlex
import time

from camera_probe_contract import PERMISSION_BUNDLE, select_permission
from guest_ui import select_node


def allow_camera(ui, labels, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    error = None
    while time.monotonic() < deadline:
        try:
            layout, path = ui.layout(bundle=PERMISSION_BUNDLE, label='camera-trusted-permission')
            node = select_permission(layout, labels)
        except ValueError as problem:
            error = problem
            time.sleep(1)
            continue
        # A lost click reply must not be retried against a different dialog.
        left, top, width, height = node['rect']
        ui.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2),
                 'camera-actual-trusted-Allow-node')
        return {'layout': str(path), 'selected_node': node, 'decision': 'ALLOW',
                'bundle': PERMISSION_BUNDLE, 'scope': 'actual_user_grant_dialog_NOT_shell_grant'}
    raise ValueError('actual Camera permission UI not confirmed: ' + str(error))


def current_rows(value, run):
    lines = value[:value.rfind('\n') + 1].splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    if any(not isinstance(row, dict) or row.get('run_id') != run or
           row.get('kind') == 'probe_error' or row.get('pass') is False for row in rows):
        raise ValueError('Camera live capture observed a stale or failed application run')
    return rows


def live_captures(ui, shell, remote, bundle, run, wait_seconds):
    captures = []
    for cycle in (1, 2):
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            value = shell('cat ' + shlex.quote(remote) + ' 2>/dev/null',
                          'camera-live-phase-' + str(cycle), accepted_failure=True)
            rows = current_rows(value, run)
            names = {row.get('name') for row in rows if row.get('cycle') == cycle}
            if 'preview_frame_start' in names:
                raise ValueError('missed the real live Camera preview interval')
            if 'preview_started' in names:
                time.sleep(1)
                layout, path = ui.layout(bundle=bundle, label='camera-live-' + str(cycle))
                select_node(layout, bundle, text='ArkTS preview live cycle ' + str(cycle))
                surface = select_node(layout, bundle, identifier='camera-audit-preview')
                screenshot = ui.screenshot(label='camera-live-' + str(cycle))
                after = shell('cat ' + shlex.quote(remote), 'camera-phase-after-screen-' + str(cycle))
                after_rows = current_rows(after, run)
                if any(row.get('cycle') == cycle and row.get('name') == 'preview_frame_start'
                       for row in after_rows):
                    raise ValueError('Camera capture finished after the live interval')
                captures.append({'cycle': cycle, 'run_id': run, 'layout': str(path),
                                 'selected_node': surface, 'screenshot': str(screenshot),
                                 'before_records': rows, 'after_records': after_rows})
                break
            time.sleep(1)
        else:
            raise ValueError('actual Camera preview did not start before its deadline')
    return captures


def receive_photos(command, hdc, target, app_files, output, run):
    root = Path(output) / 'photos'
    root.mkdir()
    for cycle in (1, 2):
        for photo in (1, 2):
            name = f'camera-{run}-c{cycle}-p{photo}.jpg'
            command([hdc, '-t', target, 'file', 'recv', app_files + name, root / name],
                    'actual-camera-photo-' + str(cycle) + '-' + str(photo))
            if not (root / name).is_file() or (root / name).is_symlink():
                raise ValueError('actual private Camera JPEG transfer failed')
    return root
