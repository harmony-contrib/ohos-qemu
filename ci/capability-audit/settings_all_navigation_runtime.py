"""Capture exact provider titles or challenged no-navigation caller frames."""
import hashlib
import json
from pathlib import Path
import re
import time

from PIL import Image
from guest_ui import bounds, LayoutNotReady, NodeNotReady
from insight_contract_common import file_record
from settings_navigation_evidence import CALLER, SETTINGS, page_binding, provider_binding

TITLES = {
    'input': ('输入法', 'Input methods'), 'network': ('设置网络',),
    'display': ('显示和亮度',), 'mobile': ('移动网络',), 'refresh': ('屏幕刷新率',),
    'sound': ('声音和振动',), 'biometrics': ('生物识别和密码',),
    'about': ('关于本机',), 'nfc': ('NFC',),
}


def title_node(tree, bundle, titles, *, marker=False):
    pending = [(tree, '', False)]; selected = []
    while pending:
        node, parent, inside_title = pending.pop()
        attributes = node.get('attributes', {}); owner = attributes.get('bundleName') or parent
        in_title = inside_title or attributes.get('type') == 'TitleBar'
        if (owner == bundle and attributes.get('visible') == 'true' and
                attributes.get('type') == 'Text' and attributes.get('text') in titles and
                ((marker and attributes.get('id') == 'settings-run-marker') or (not marker and in_title))):
            selected.append({'attributes': attributes, 'bundle': owner,
                             'rect': list(bounds(attributes.get('bounds')))})
        pending.extend((child, owner, in_title) for child in node.get('children', []))
    if len(selected) != 1: raise ValueError('one actual requested Settings title/challenge text required')
    return selected[0]


def painted(path, node):
    with Image.open(path) as picture:
        picture.load()
        if picture.format != 'PNG': raise ValueError('actual Settings PNG required')
        x, y, width, height = node['rect']
        if width <= 0 or height <= 0 or x < 0 or y < 0 or x+width > picture.width or y+height > picture.height:
            raise ValueError('Settings challenged text is outside the actual capture')
        crop = picture.convert('RGB').crop((x, y, x+width, y+height))
        colors = list(crop.get_flattened_data())
        bright = sum(min(color) > 170 for color in colors)
        dark = sum(max(color) < 110 for color in colors)
        if bright < 20 or dark < 20 or max(high-low for low, high in crop.getextrema()) < 32:
            raise ValueError('actual Settings challenged title not painted')
        return {'bright_pixels': bright, 'dark_pixels': dark,
                'crop_sha256': hashlib.sha256(crop.tobytes()).hexdigest()}


def caller_only_binding(dump, settings_uid, caller_uid, caller_pid):
    if (type(caller_pid) is not int or caller_pid <= 0 or type(caller_uid) is not int or
            type(settings_uid) is not int or caller_uid == settings_uid or
            caller_uid // 200000 != 100 or settings_uid // 200000 != 100):
        raise ValueError('actual no-navigation caller PID required')
    apps = re.split(r'(?=^    AppRunningRecord ID #)', dump, flags=re.M)
    hosts = [app for app in apps if f'process name [{CALLER}]' in app and
             re.search(r'^      pid #'+str(caller_pid)+r'  uid #'+str(caller_uid)+r'$', app, re.M) and
             'state #FOREGROUND' in app]
    settings = [app for app in apps if re.search(r'^      pid #[1-9][0-9]*  uid #'+str(settings_uid)+r'$', app, re.M) and
                re.search(r'^      process name \[com\.ohos\.settings(?::[^\]]+)?\]$', app, re.M) and
                'state #FOREGROUND' in app]
    if len(hosts) != 1 or settings: raise ValueError('profile boundary navigated away or left a foreground Settings provider')
    return {'caller_pid': caller_pid, 'caller_uid': caller_uid, 'settings_foreground_absent': True}


def observation(layout, screenshot, ams, route, supported, nonce, methods, app_label,
                settings_uid, caller_uid, caller_pid):
    if not supported:
        node = title_node(layout, CALLER, ('Settings challenge '+nonce,), marker=True)
        binding = caller_only_binding(ams, settings_uid, caller_uid, caller_pid)
    else:
        titles = (methods[0].get('label') or methods[0]['name'],) if route == 'detail' else (
            (app_label,) if route == 'app-detail' else TITLES[route])
        owner = CALLER if route in ('input', 'detail') else SETTINGS
        node = title_node(layout, owner, titles)
        if route in ('input', 'detail', 'network'):
            ability = 'OpenNetworkUIExtensionAbility' if route == 'network' else 'ExternalCommonUIExtensionAbility'
            binding = provider_binding(ams, settings_uid, caller_uid, ability=ability)
            if binding['host_pid'] != caller_pid: raise ValueError('Settings extension belongs to another host PID')
        else:
            binding = page_binding(ams, settings_uid, caller_uid)
            if binding['caller_pid'] != caller_pid: raise ValueError('Settings page displaced another caller PID')
    metrics = painted(screenshot, node)
    return {'node': node, 'binding': binding, 'pixels': metrics}


def capture(ui, shell, output, label, route, supported, nonce, methods, app_label,
            settings_uid, caller_uid, caller_pid, timeout=60):
    report = {'scope': 'Settings actual provider/paint presentation only_NOT_archive_or_gate',
              'status': 'running', 'samples': [], 'started': time.monotonic(), 'timeout_seconds': timeout}
    report['deadline'] = report['started'] + timeout
    previous = None; stable = 0
    def save(): Path(output).write_text(json.dumps(report, indent=2)+'\n')
    while time.monotonic() < report['deadline']:
        sample = {'started': time.monotonic(), 'label': label}; report['samples'].append(sample)
        try:
            layout, path = ui.layout(label=label)
            picture = ui.screenshot(label=label)
            dump = shell('aa dump -a -u 100', label+'-AMS-'+str(len(report['samples'])))
            ams = Path(output).with_name(Path(output).stem+'-AMS-'+str(len(report['samples']))+'.txt')
            ams.write_text(dump)
            sample.update(layout=file_record(path), screenshot=file_record(picture), AMS=file_record(ams),
                          finished=time.monotonic())
            if sample['finished'] > report['deadline']: raise ValueError('Settings capture exceeded original presentation deadline')
            actual = observation(layout, picture, dump, route, supported, nonce, methods, app_label,
                                 settings_uid, caller_uid, caller_pid)
            fingerprint = (actual['node']['rect'], actual['node']['attributes']['text'],
                           actual['binding'], actual['pixels']['crop_sha256'])
            stable = stable+1 if fingerprint == previous else 1; previous = fingerprint
            sample.update(observation=actual, consecutive_identical_presentations=stable); save()
            if stable == 3: report['status'] = 'pass_presentation_only'; save(); return report
        except (LayoutNotReady, NodeNotReady, ValueError) as error:
            sample.update(not_ready=str(error), finished=time.monotonic()); previous=None;stable=0;save()
        time.sleep(.25)
    report['status']='fail_presentation_only';save()
    raise ValueError('Settings requested page or profile boundary never became stably painted')
