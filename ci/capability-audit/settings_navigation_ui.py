"""Exercise public input Settings navigation, without changing any setting."""
import json
from pathlib import Path
import time

from guest_ui import LayoutNotReady, select_node
from run_root_probe import digest
from settings_navigation_evidence import CALLER, embedded_title, provider_binding


def wait_node(ui, identifier=None, titles=None, settings_uid=None, caller_uid=None, label='settings', deadline=None):
    deadline = time.monotonic() + 60 if deadline is None else deadline
    while time.monotonic() < deadline:
        try:
            layout, path = ui.layout(label=label)
        except LayoutNotReady:
            time.sleep(0.5)
            continue
        if identifier is not None:
            try:
                return {'layout': str(path), 'layout_sha256': digest(path),
                        'node': select_node(layout, CALLER, identifier=identifier)}
            except ValueError:
                pass
        else:
            for title in titles:
                try:
                    node = embedded_title(layout, title)
                except ValueError:
                    continue
                dump = ui.shell('aa dump -a -u 100', label + '-provider-host')
                try:
                    binding = provider_binding(dump, settings_uid, caller_uid)
                except ValueError:
                    continue
                dump_path = path.with_suffix('.ams.txt')
                dump_path.write_text(dump)
                return {'layout': str(path), 'layout_sha256': digest(path), 'node': node,
                        'title': title, 'provider_binding': binding,
                        'provider_dump': str(dump_path), 'provider_dump_sha256': digest(dump_path)}
        time.sleep(0.5)
    raise ValueError('actual Settings/caller node and provider binding not ready: ' + label)


def require_painted_title(path, node):
    from PIL import Image
    with Image.open(path) as image:
        image.load()
        if image.format != 'PNG' or min(image.size) < 100:
            raise ValueError('actual Settings compositor PNG required')
        left, top, width, height = node['rect']
        if left + width > image.width or top + height > image.height:
            raise ValueError('Settings title is outside the captured compositor')
        crop = image.convert('RGB').crop((left, top, left + width, top + height))
        if max(high - low for low, high in crop.getextrema()) < 32:
            raise ValueError('Settings title was not painted in the actual compositor capture')


def capture_provider(ui, titles, settings_uid, caller_uid, route, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 60
    attempts = []
    while clock() < deadline:
        provider = wait_node(ui, titles=titles, settings_uid=settings_uid, caller_uid=caller_uid,
                             label='settings-' + route + '-provider', deadline=deadline)
        screen = ui.screenshot(label='settings-' + route + '-compositor')
        attempt = {'provider': provider, 'screenshot': str(screen), 'screenshot_sha256': digest(screen)}
        attempts.append(attempt)
        try:
            require_painted_title(screen, provider['node'])
        except ValueError as error:
            attempt['error'] = str(error)
            sleep(0.25)
            continue
        attempt['status'] = 'painted'
        return provider, screen, attempts
    raise ValueError('Settings page never painted before the bounded capture deadline')


def exercise(ui, poll, run_id, caller_uid):
    from verify_settings_navigation_results import verify_rows, settings_identity
    raw_identity = ui.shell('bm dump -n com.ohos.settings', 'installed-settings-identity')
    settings_uid = settings_identity(raw_identity)
    identity_path = ui.output / 'settings-identity.json'
    identity_path.write_text(raw_identity)
    wait_node(ui, identifier='settings-probe-input', label='settings-caller-ready')
    startup = poll('"name":"ready"')
    methods = verify_rows(startup, run_id, startup=True)['methods']
    ime = methods[0]
    actions = {'settings_identity': str(identity_path), 'settings_identity_sha256': digest(identity_path),
               'settings_uid': settings_uid, 'caller_uid': caller_uid, 'pages': []}
    for cycle in (1, 2):
        for route, titles in (('input', ['Input methods', '输入法']), ('detail', [ime.get('label') or ime['name']])):
            request = ui.click(CALLER, identifier='settings-probe-' + route, label='settings-' + route + '-request')
            request['layout_sha256'] = digest(Path(request['layout']))
            provider, screen, attempts = capture_provider(ui, titles, settings_uid, caller_uid, route)
            ui.shell('uitest uiInput keyEvent Back', 'settings-' + route + '-back')
            returned = wait_node(ui, identifier='settings-probe-input', label='settings-returned-caller')
            actions['pages'].append({'cycle': cycle, 'route': route, 'request': request, 'provider': provider,
                                     'screenshot': str(screen), 'screenshot_sha256': digest(screen),
                                     'returned': returned, 'capture_attempts': attempts})
    return actions


def checked_path(record, key):
    path = Path(record[key])
    if not path.is_file() or path.is_symlink() or digest(path) != record.get(key + '_sha256'):
        raise ValueError('actual Settings UI evidence missing or changed: ' + key)
    return path


def verify_actions(actions, methods, caller_uid):
    from verify_settings_navigation_results import settings_identity
    settings_uid = settings_identity(checked_path(actions, 'settings_identity').read_text())
    if actions.get('settings_uid') != settings_uid or actions.get('caller_uid') != caller_uid:
        raise ValueError('Settings UI identities differ from actual package manager records')
    pages = actions.get('pages')
    if not isinstance(pages, list) or len(pages) != 4:
        raise ValueError('both Settings pages must open and return twice')
    for row, (cycle, route) in zip(pages, ((1, 'input'), (1, 'detail'), (2, 'input'), (2, 'detail'))):
        if row.get('cycle') != cycle or type(row['cycle']) is not int or row.get('route') != route:
            raise ValueError('Settings route cycles reordered or missing')
        request, provider, returned = (row[key] for key in ('request', 'provider', 'returned'))
        node = select_node(json.loads(checked_path(request, 'layout').read_text()), CALLER,
                           identifier='settings-probe-' + route, clickable=True)
        if node != request.get('selected_node'):
            raise ValueError('Settings request was not the actual enabled caller control')
        titles = ['Input methods', '输入法'] if route == 'input' else [methods[0].get('label') or methods[0]['name']]
        if provider.get('title') not in titles:
            raise ValueError('provider title differs from the requested Settings route')
        node = embedded_title(json.loads(checked_path(provider, 'layout').read_text()), provider['title'])
        binding = provider_binding(checked_path(provider, 'provider_dump').read_text(), settings_uid, caller_uid)
        if node != provider.get('node') or binding != provider.get('provider_binding'):
            raise ValueError('Settings provider UI/process proof differs from raw observations')
        node = select_node(json.loads(checked_path(returned, 'layout').read_text()), CALLER,
                           identifier='settings-probe-input')
        if node != returned.get('node'):
            raise ValueError('Back did not return to the original caller')
        require_painted_title(checked_path(row, 'screenshot'), provider['node'])
    return {'pages': 4, 'cycles': 2}
