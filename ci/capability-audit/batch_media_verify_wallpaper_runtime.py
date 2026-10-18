#!/usr/bin/env python3
"""Recompute wallpaper file, UI, nonce, permission and pixel observations.

No UI-success text, ACK, callback count, wallpaper API return or runner status
is accepted as content evidence. This cannot close the full package gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import zipfile

from PIL import Image, ImageOps, ImageStat
from batch_apps_contact_picker_coordinator import verify_signed_payload
from enclosing_acceptance_guest import validate_binding
from guest_ui import bounds, NodeNotReady, select_node, command_exit
from hap_identity_binding import verify_hap_token_identity

HERE = Path(__file__).resolve().parent
CASES = ('desktop-1', 'desktop-2', 'lock-1', 'lock-2', 'cancel')
BASE = '/data/service/el1/public/wallpaper/100'
PATHS = {'desktop': BASE + '/system/wallpaper_home', 'lock': BASE + '/lockscreen/wallpaper_lock'}
CFG = BASE + '/wallpapercfg'
SEED = 'org.harmonycontrib.wallpaperchallenge'
SETTINGS = 'com.ohos.settings'
PHOTOS = 'com.ohos.photos'
SCOPE = 'real_Settings_PhotoPicker_static_wallpaper_files_and_pixels_NOT_full_wallpaper_or_package_gate'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(value):
    if not isinstance(value, dict) or set(value) != {'path', 'sha256'}:
        raise ValueError('exact raw evidence file record required')
    path = Path(value['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or sha(path) != value['sha256']:
        raise ValueError('raw evidence missing, linked or changed')
    return path


def check_challenge(value):
    if (value.get('schema_version') != 1 or re.fullmatch('[0-9a-f]{32}', value.get('run_id', '')) is None or
            set(value.get('images', {})) != set(CASES) or value.get('expected_bundle') != SEED or
            value.get('expected_request_permissions') != [] or
            value.get('generator_sha256') != sha(HERE / 'batch_media_wallpaper_runtime.py')):
        raise ValueError('fresh complete challenge/source contract required')
    if (type(value.get('width')) is not int or type(value.get('height')) is not int or
            not 320 <= value['width'] <= 4096 or not 320 <= value['height'] <= 4096 or value['width']*value['height'] > 8_000_000):
        raise ValueError('bounded actual-display challenge dimensions required')
    template = checked(value['template'])
    # Build and acceptance snapshots have different absolute roots. Bind the
    # exact trusted template bytes, while retaining its actual original path.
    if sha(template) != sha(HERE / 'fixtures/batch_media/wallpaper_runtime/Index.ets'):
        raise ValueError('original seed/denial source required')
    if checked(value['generated_page']).read_text() != template.read_text().replace('__WALLPAPER_RUN__', value['run_id']):
        raise ValueError('generated source differs from actual run/template')
    hashes = set()
    for record in value['images'].values():
        path = checked(record)
        with Image.open(path) as image:
            image.load()
            if image.format != 'PNG' or image.size != (value['width'], value['height']) or image.mode != 'RGB':
                raise ValueError('bounded original RGB PNG challenge required')
            if min(ImageStat.Stat(image).stddev) < 25:
                raise ValueError('flat/silence image is not a random spatial challenge')
        hashes.add(record['sha256'])
    if len(hashes) != len(CASES):
        raise ValueError('independent new challenge per update/cancel required')


def parse_remote_stat(text, remote, maximum=33554432):
    lines = text.strip().splitlines()
    if len(lines) != 2:
        raise ValueError('complete actual stat/hash pair required')
    match = re.fullmatch(r'([0-9]+) ([0-9]+) ([0-7]{3,4}) ([0-9]+) ([0-9]+) ([0-9]+)', lines[0])
    digest = re.fullmatch(r'([0-9a-f]{64})  ' + re.escape(remote), lines[1])
    if not match or not digest:
        raise ValueError('actual file stat/path/hash malformed')
    uid, gid, mode, size, mtime, inode = match.groups()
    if not 0 < int(size) <= maximum or int(mode, 8) & 0o002 or int(inode) <= 0:
        raise ValueError('unbounded/empty/world-writable actual file')
    return {'uid': int(uid), 'gid': int(gid), 'mode': int(mode, 8), 'size': int(size),
            'mtime': int(mtime), 'inode': int(inode), 'sha256': digest.group(1)}


def transferred(value):
    before, after = (checked(value[key]).read_text() for key in ('before', 'after'))
    if before != after:
        raise ValueError('actual guest file changed during transfer')
    meta = parse_remote_stat(before, value['remote'])
    path = checked(value['file'])
    if sha(path) != meta['sha256'] or path.stat().st_size != meta['size']:
        raise ValueError('received bytes differ from real guest stat/hash')
    return path, meta


def pixels(actual_path, reference_path, rect=None, *, minimum_fraction=0.68):
    """Spatial tile medians, bounded tolerance, no arbitrary search/alignment.

    Full service images and display captures use actual center-cover geometry.
    UI text/icons may cover some tiles, but all quadrants must carry the new
    challenge. Cannot accept an embedded preview thumbnail or one-color match.
    """
    with Image.open(actual_path) as source, Image.open(reference_path) as expected:
        if source.width * source.height > 16_777_216 or expected.width * expected.height > 16_777_216:
            raise ValueError('image pixel budget exceeded')
        source.load(); expected.load()
        actual = source.convert('RGB')
        if rect is not None:
            x, y, width, height = rect
            if min(x, y) < 0 or min(width, height) < 48 or x + width > actual.width or y + height > actual.height:
                raise ValueError('real screenshot node outside its capture')
            actual = actual.crop((x, y, x + width, y + height))
        target = ImageOps.fit(expected.convert('RGB'), actual.size, method=Image.Resampling.BILINEAR, centering=(0.5, 0.5))
        good = [0, 0, 0, 0]; total = [0, 0, 0, 0]; errors = []
        for row in range(12):
            for column in range(12):
                x = (2 * column + 1) * actual.width // 24
                y = (2 * row + 1) * actual.height // 24
                radius = max(1, min(actual.size) // 180)
                box = (max(0, x-radius), max(0, y-radius), min(actual.width, x+radius+1), min(actual.height, y+radius+1))
                observed = ImageStat.Stat(actual.crop(box)).median
                wanted = ImageStat.Stat(target.crop(box)).median
                error = max(abs(a-b) for a, b in zip(observed, wanted))
                quadrant = (row >= 6) * 2 + (column >= 6)
                total[quadrant] += 1; good[quadrant] += error <= 26; errors.append(error)
        fraction = sum(good) / sum(total)
        if fraction < minimum_fraction or min(a/b for a, b in zip(good, total)) < 0.5:
            raise ValueError('new challenged wallpaper pixels not independently painted')
        return {'matched_tiles': sum(good), 'sampled_tiles': sum(total), 'quadrants': good,
                'fraction': fraction, 'median_max_channel_error': sorted(errors)[len(errors)//2]}


def thumbnail(layout, screenshot, challenge, *, owner=SETTINGS):
    if owner not in (PHOTOS, SETTINGS):
        raise ValueError('Photos picker UI must be actual provider or Settings host')
    pending = [(root, '', 0) for root in (layout if isinstance(layout, list) else [layout])]
    candidates = {}; count = 0
    while pending:
        node, inherited, depth = pending.pop(); count += 1
        if count > 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('bounded genuine Photos hierarchy required')
        attrs, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attrs, dict) or not isinstance(children, list):
            raise ValueError('malformed Photos hierarchy')
        bundle = attrs.get('bundleName') or inherited
        if bundle == owner and attrs.get('visible') == 'true' and attrs.get('type') in ('Image', 'GridItem'):
            rect = list(bounds(attrs.get('bounds')))
            try:
                metrics = pixels(screenshot, challenge, rect, minimum_fraction=0.85)
            except ValueError:
                pass
            else:
                candidates[tuple(rect)] = ({'attributes': attrs, 'bundle': bundle, 'rect': rect}, metrics)
        pending.extend((child, bundle, depth+1) for child in children)
    if not candidates:
        raise NodeNotReady('fresh random challenge thumbnail not painted in real Photos')
    # Nested Image/GridItem may describe exactly the same actual rectangle.
    if len(candidates) != 1:
        raise ValueError('ambiguous multiple matching Photos thumbnails')
    return next(iter(candidates.values()))


def seed_rows(text, run, *, denial=False):
    rows = [json.loads(line) for line in text.splitlines()]
    if not 10 <= len(rows) <= 40:
        raise ValueError('complete bounded real import/denial log required')
    for index, row in enumerate(rows):
        if (set(row) != {'runId', 'sequence', 'name', 'detail', 'timestampMs'} or row['runId'] != run or
                type(row['sequence']) is not int or row['sequence'] != index+1 or
                type(row['timestampMs']) is not int or row['timestampMs'] <= 0):
            raise ValueError('stale/reordered real seed evidence')
    expected = [(name, case) for case in CASES for name in ('import.request', 'import.complete')]
    uris = []
    for row, (name, case) in zip(rows, expected):
        detail = json.loads(row['detail'])
        if row['name'] != name or detail.get('case') != case or type(detail.get('bytes')) is not int or detail['bytes'] <= 100:
            raise ValueError('all five actual private PNG imports required')
        if name == 'import.complete':
            if re.fullmatch(r'file://media/Photo/[1-9][0-9]*/[^\x00\r\n]+', detail.get('uri', '')) is None:
                raise ValueError('real MediaLibrary-created URI required')
            uris.append(detail['uri'])
    if len(set(uris)) != 5:
        raise ValueError('five distinct real created Photo URIs required')
    if not denial and len(rows) != 10:
        raise ValueError('unexpected prior calls before import capture')
    if denial:
        if len(rows) != 26:
            raise ValueError('all eight actual denied API invocations required')
        for pair, (kind, operation) in enumerate((k, op) for k in (0, 1) for op in ('setWallpaper', 'reset', 'setImage', 'restore')):
            request, error = rows[10+pair*2:12+pair*2]
            requested, rejected = json.loads(request['detail']), json.loads(error['detail'])
            if (request['name'] != 'denied.request' or error['name'] != 'denied.error' or
                    requested != {'type': kind, 'operation': operation} or
                    rejected.get('type') != kind or rejected.get('operation') != operation or
                    type(rejected.get('code')) is not int or rejected['code'] not in ((201,) if operation in ('setWallpaper', 'reset') else (201, 202)) or
                    not isinstance(rejected.get('message'), str) or not rejected['message']):
                raise ValueError('ordinary API permission/system boundary failed or wrong error')
    return rows, uris


def bms_identity(record, bundle, *, ordinary=False):
    raw = checked(record).read_text().removeprefix(bundle + ':\n')
    app = json.loads(raw)['applicationInfo']
    if ((app.get('name') or app.get('bundleName')) != bundle or type(app.get('uid')) is not int or app['uid']//200000 != 100 or
            app.get('isSystemApp') is not (not ordinary) or
            (ordinary and app.get('appPrivilegeLevel') != 'normal')):
        raise ValueError('actual installed BMS identity/account differs')
    if ordinary and app['uid'] % 200000 < 10000:
        raise ValueError('ordinary caller cannot use a reserved system app UID')
    if bundle in (SETTINGS, 'org.harmonycontrib.wallpaperquery') and app.get('appPrivilegeLevel') != 'system_basic':
        raise ValueError('Settings actual original system_basic identity required')
    token = app.get('accessTokenId')
    if type(token) is not int or not 0 < token < 2**32:
        raise ValueError('actual BMS accessTokenId required')
    return app['uid'], token


def bms(record, bundle, *, ordinary=False):
    return bms_identity(record, bundle, ordinary=ordinary)[0]


def replay_observation(observation, script, target, *, commands=None):
    """Bind raw GuestUi output to its exact indexed command and exit frame."""
    row, index = observation['command'], observation['command_index']
    if type(index) is not int or index < 0 or commands is not None and (
            index >= len(commands) or commands[index] != row):
        raise ValueError('raw observation command index differs')
    argv = row['argv']
    if (row.get('exit_code') != 0 or row.get('timed_out') or len(argv) != 5 or
            argv[1:4] != ['-t', target, 'shell']):
        raise ValueError('raw observation failed or targets another guest')
    markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', argv[4])
    if len(markers) != 1:
        raise ValueError('one exact raw observation exit nonce required')
    marker = markers[0]
    tail = '; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"'
    if argv[4] != script + tail:
        raise ValueError('raw observation helper arguments or shell footer differs')
    transport = checked({k: row[k] for k in ('path', 'sha256')}).read_text().replace('\r', '')
    body, code = command_exit(transport, marker)
    if code != 0:
        raise ValueError('actual observation guest exit was not successful')
    raw = checked(observation['raw']).read_text()
    # GuestUi strips terminal LF. Reproduce exactly; do not rewrite raw/log.
    if body.rstrip('\n') != raw:
        raise ValueError('raw observation differs from actual command stdout')
    return raw


def verify_token_observation(record, *, run, boot, target, bundle, permission,
                             original_BMS=None, commands=None):
    proof = json.loads(checked(record).read_text())
    roles = {SEED: 'seed', SETTINGS: 'settings', 'org.harmonycontrib.wallpaperquery': 'query'}
    role = roles.get(bundle)
    if (role is None or proof.get('schema_version') != 1 or proof.get('run_id') != run or
            proof.get('boot_id') != boot or proof.get('role') != role or
            re.fullmatch('[a-f0-9]{32}', run) is None):
        raise ValueError('fresh exact native token observation required')
    identities = []
    indices = []
    for key in ('baseline', 'before', 'after'):
        observation = proof[key]
        replay_observation(observation, 'bm dump -n ' + bundle, target, commands=commands)
        identities.append(bms_identity(observation['raw'], bundle, ordinary=role == 'seed'))
        indices.append(observation['command_index'])
    uid, token = identities[0]
    if any(identity != (uid, token) for identity in identities):
        raise ValueError('BMS UID/accessTokenId changed across native token query')
    if original_BMS is not None and bms_identity(original_BMS, bundle, ordinary=role == 'seed') != (uid, token):
        raise ValueError('native token query differs from original runtime BMS identity')
    helper = proof['helper']; remote = '/data/local/tmp/wallpaper-coordinator-' + run + '/token'
    checked(helper['binary']); checked(helper['build_receipt'])
    if sha(checked(helper['source'])) != sha(HERE / 'fixtures/batch_media/wallpaper_receipts/token_query.cpp'):
        raise ValueError('native token observation uses another helper source')
    script = 'unset LD_LIBRARY_PATH LD_PRELOAD; ' + shlex.join([remote, run, str(uid), bundle, permission])
    raw = replay_observation(proof, script, target, commands=commands)
    if not indices[0] < indices[1] < proof['command_index'] < indices[2]:
        raise ValueError('BMS/token command ordering differs')
    value = json.loads(raw)
    verify_hap_token_identity(value, bundle=bundle, uid=uid, token_id=token)
    if (value.get('run_id') != run or value.get('boot_id') != boot or value.get('user_id') != 100 or
            value.get('permission') != permission or type(value.get('grant')) is not int or
            value['grant'] not in (-1, 0) or type(value.get('before_ns')) is not int or value['before_ns'] <= 0 or
            type(value.get('after_ns')) is not int or value['after_ns'] < value['before_ns']):
        raise ValueError('actual native permission/clock/run observation differs')
    return value


def acks(actions, run, boot):
    expected = ['verify-package-identities-and-permissions', 'resolve-service-default-resources',
                'import-five-PNGs-via-real-Photos-consent']
    for case in CASES[:4]:
        expected += ['show-settings-main', 'show-real-'+case.split('-')[0]]
    expected += ['show-settings-main', 'cancel-real-Photos-picker', 'show-settings-main',
                 'ordinary-denied-set-and-restore', 'show-settings-main', 'show-real-desktop',
                 'show-settings-main', 'show-real-lock', 'delete-only-created-Photos-assets-via-real-UI',
                 'remove-owned-seed-private-inputs']
    if [action.get('action') for action in actions] != expected:
        raise ValueError('complete ordered root coordination actions required')
    for index, action in enumerate(actions):
        request = json.loads(checked(action['request']).read_text())
        ack = json.loads(checked(action['ack']).read_text())
        if (request.get('schema_version') != 1 or request.get('run_id') != run or request.get('boot_id') != boot or
                type(request.get('sequence')) is not int or request['sequence'] != index+1 or
                request.get('action') != action['action'] or re.fullmatch('[a-f0-9]{32}', request.get('nonce', '')) is None or
                ack != {k: request[k] for k in ('schema_version', 'run_id', 'boot_id', 'sequence', 'nonce', 'action')} or
                type(action.get('started_ns')) is not int or type(action.get('finished_ns')) is not int or
                not 0 <= action['finished_ns'] - action['started_ns'] <= 180_000_000_000):
            raise ValueError('stale or malformed action synchronization')
    if len({json.loads(checked(a['request']).read_text())['nonce'] for a in actions}) != len(actions):
        raise ValueError('reused action nonce')


def stage_files(stage):
    from account_state import parse_snapshot
    if not all(parse_snapshot(checked(stage['account']).read_text()).values()):
        raise ValueError('same-boot actual foreground account100 missing')
    inventory = set()
    for kind, directory in (('desktop', 'system'), ('lock', 'lockscreen')):
        names = checked(stage[kind+'_inventory']).read_text().splitlines()
        for name in names:
            if not name.startswith(BASE+'/'+directory+'/'):
                raise ValueError('wallpaper inventory crossed user/directory')
        if len(names) != len(set(names)) or len(names) > 32:
            raise ValueError('duplicate/excessive actual inventory')
        inventory.update(names)
    presence = checked(stage['cfg_presence']).read_text().strip()
    if presence == 'present': inventory.add(CFG)
    elif presence != 'absent': raise ValueError('actual cfg presence unknown')
    if inventory != set(stage['files']):
        raise ValueError('omitted actual user wallpaper file')
    result = {}
    for remote, value in stage['files'].items():
        if value['remote'] != remote:
            raise ValueError('wrong actual source path')
        path, meta = transferred(value)
        result[remote] = (path, meta)
    if type(stage['started_ns']) is not int or type(stage['finished_ns']) is not int or stage['finished_ns'] <= stage['started_ns']:
        raise ValueError('actual bounded observation interval required')
    return result


def system_canvas(tree, screenshot, bundle, identifier):
    """Replay untouched display/window geometry, retaining clipped visibility.

    A SceneBoard status bar may clip a desktop node's visible bounds. Its
    original bounds alone do not prove a full compositor canvas: require the
    full hierarchy root, actual host WindowScene, and the separately observed
    top system-bar window accounting for the entire clipped strip. Pixel
    verification still consumes the original whole PNG, never this rect.
    """
    if bundle not in ('com.ohos.sceneboard', 'com.ohos.launcher', 'com.ohos.systemui', 'com.ohos.systemui.screenlock'):
        raise ValueError('actual system compositor owner required')
    if bundle == 'com.ohos.sceneboard' and identifier not in (
            'SCBDesktop_Flex_Desktop', 'ScreenLockRootComponent', 'MainPageView_Screen_Lock_Home'):
        raise ValueError('source-defined SceneBoard desktop/lock node required')
    selected = select_node(tree, bundle, identifier=identifier)
    roots = tree if isinstance(tree, list) else [tree]
    if len(roots) != 1:
        raise ValueError('one actual complete display hierarchy required')
    with Image.open(screenshot) as picture:
        picture.load()
        if picture.format != 'PNG' or picture.width * picture.height > 16_777_216:
            raise ValueError('actual unmodified PNG display capture required')
        full = [0, 0, picture.width, picture.height]
    if list(bounds(roots[0]['attributes'].get('bounds'))) != full:
        raise ValueError('hierarchy root differs from complete compositor capture')
    paths, windows, bars = [], [], []
    def visit(node, owner, ancestors):
        attributes = node['attributes']; owner = attributes.get('bundleName') or owner
        path = ancestors + [(attributes, owner)]
        if attributes is selected['attributes']: paths.append(path)
        if attributes.get('type') == 'WindowScene' and attributes.get('visible') == 'true':
            windows.append((attributes, owner))
        if attributes.get('id') == 'StatusBarBackground_Row_0' and attributes.get('visible') == 'true':
            bars.append(path)
        for child in node.get('children', []): visit(child, owner, path)
    visit(roots[0], '', [])
    if len(paths) != 1:
        raise ValueError('selected system node path is ambiguous')
    attrs = selected['attributes']
    host = attrs.get('hostWindowId')
    if (attrs.get('displayId') != '0' or re.fullmatch('[1-9][0-9]*', host or '') is None or
            list(bounds(attrs.get('origBounds'))) != full):
        raise ValueError('actual system display/host/original full-plane geometry required')
    owners = [(a, owner) for a, owner in paths[0] if a.get('type') == 'WindowScene']
    if len(owners) != 1:
        raise ValueError('one real system WindowScene ancestor required')
    window, owner = owners[0]
    if (owner != bundle or window.get('visible') != 'true' or window.get('hostWindowId') != host or
            window.get('displayId') != '0' or list(bounds(window.get('origBounds'))) != full or
            list(bounds(window.get('bounds'))) != selected['rect']):
        raise ValueError('system node is an embedded or foreign window')
    visible = selected['rect']; overlay_host = None
    if visible != full:
        x, y, width, height = visible
        if x != 0 or y <= 0 or width != full[2] or y + height != full[3]:
            raise ValueError('unsupported system viewport clipping')
        matches = []
        for path in bars:
            bar, bar_owner = path[-1]
            ancestors = [(a, o) for a, o in path if a.get('type') == 'WindowScene']
            if len(ancestors) != 1: continue
            bar_window, window_owner = ancestors[0]
            rect = list(bounds(bar.get('bounds')))
            if (bar_owner in ('com.ohos.sceneboard', 'com.ohos.systemui') and window_owner == bar_owner and
                    bar_window.get('visible') == 'true' and
                    rect == [0, 0, width, y] and list(bounds(bar.get('origBounds'))) == rect and
                    bar.get('displayId') == bar_window.get('displayId') == '0' and
                    re.fullmatch('[1-9][0-9]*', bar.get('hostWindowId', '')) is not None and
                    bar.get('hostWindowId') == bar_window.get('hostWindowId') != host):
                outer = list(bounds(bar_window.get('bounds')))
                if (outer[:3] == [0, 0, width] and y <= outer[3] <= full[3] and
                        list(bounds(bar_window.get('origBounds'))) == outer):
                    matches.append((bar, bar_window))
        if len(matches) != 1:
            raise ValueError('clipped strip lacks one actual matching system status-bar window')
        overlay_host = matches[0][0]['hostWindowId']
    allowed_hosts = {host} if overlay_host is None else {host, overlay_host}
    if (len({a.get('hostWindowId') for a, _ in windows}) != len(windows) or
            any(a.get('hostWindowId') not in allowed_hosts for a, _ in windows)):
        raise ValueError('foreign or duplicate visible compositor window')
    return {'canvas_rect': full, 'visible_rect': visible, 'display_id': '0',
            'host_window_id': host, 'top_overlay_host_window_id': overlay_host}


def system_window(stage, plan):
    kind = stage['screen_kind']; selected = plan['screens'][kind]
    allowed = (('com.ohos.sceneboard', 'com.ohos.launcher') if kind == 'desktop' else
               ('com.ohos.sceneboard', 'com.ohos.systemui', 'com.ohos.systemui.screenlock'))
    if set(selected) != {'bundle', 'identifier'} or selected['bundle'] not in allowed:
        raise ValueError('actual profile-specific system desktop/lock window identity required')
    tree = json.loads(checked(stage['layout']).read_text())
    node = select_node(tree, selected['bundle'], identifier=selected['identifier'])
    system_canvas(tree, checked(stage['screenshot']), selected['bundle'], selected['identifier'])
    dump = checked(stage['ams']).read_text()
    apps = re.split(r'(?=^    AppRunningRecord ID #)', dump, flags=re.M)
    # A visible lockscreen can be hosted by a service process whose AMS app
    # state is BACKGROUND. Do not invent foreground status for that process;
    # the actual visible full-window UITest owner supplies presentation proof.
    owners = [app for app in apps if re.search(r'^      process name \['+re.escape(selected['bundle'])+
              r'(?::[^\]]+)?\]$', app, re.M) and
              re.search(r'^      pid #[1-9][0-9]*  uid #[1-9][0-9]*$', app, re.M)]
    if len(owners) != 1:
        raise ValueError('actual system compositor owner process evidence missing')
    actual_uid = int(re.search(r'^      pid #[1-9][0-9]*  uid #([1-9][0-9]*)$', owners[0], re.M).group(1))
    if actual_uid//200000 != 100:
        raise ValueError('system viewport belongs to another current user')
    if selected['bundle'] == 'com.ohos.sceneboard' and selected['identifier'] not in (
            ('SCBDesktop_Flex_Desktop',) if kind == 'desktop' else ('ScreenLockRootComponent', 'MainPageView_Screen_Lock_Home')):
        raise ValueError('SceneBoard desktop/lock identity was relabeled')
    if not re.fullmatch(r'[1-9][0-9]*(?: [1-9][0-9]*)?\n?', checked(stage['renderer_pids']).read_text()):
        raise ValueError('real wallpaper renderer process required')
    return node


def photos_provider(dump, host):
    if host not in (SETTINGS, SEED):
        raise ValueError('known real picker host required')
    records = re.split(r'(?=^    uri \[)', dump, flags=re.M)
    records = [row for row in records if row.startswith('    uri [/com.ohos.photos/') and
               'bundle name [com.ohos.photos]' in row and 'ability type [UIEXTENSION]' in row and
               f'root host bundle name [{host}]' in row and
               re.search(r'AbilityRecord ID #[0-9]+\s+state #(FOREGROUND|ACTIVE)\b', row)]
    if len(records) != 1:
        raise ValueError('actual Photos UIExtension provider for this host required')


def layout_transition_unavailable(argv, raw):
    """Only GuestUi's exact window-enumeration retry, never a failed action."""
    if len(argv) != 5 or argv[3] != 'shell': return False
    markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', argv[4])
    if len(markers) != 1: return False
    marker = markers[0]
    tail = '; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"'
    if not argv[4].endswith(tail): return False
    script = argv[4][:-len(tail)]
    if re.fullmatch(r'test ! -e (/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.json)'
                    r' && uitest dumpLayout -p \1(?: -b [A-Za-z0-9_.]+)?', script) is None:
        return False
    try:
        body, code = command_exit(raw.replace('\r', ''), marker)
    except ValueError:
        return False
    return code == 1 and body.strip() == 'DumpLayout failed:Get window nodes failed'


def verify_renderer_lifecycle(value, env):
    """Replay every pending/connected raw cut and gate an absent initial renderer."""
    from batch_apps_wallpaper_connection import ConnectionNotReady, parse_connection
    commands = value['commands']; allowed_nonzero = set()
    def require_transport(row):
        if (type(row.get('exit_code')) is not int or row['exit_code'] != 0 or row.get('timed_out') or
                len(row.get('argv', [])) != 5 or row['argv'][:4] != [value['hdc'],'-t',env['target'],'shell']):
            raise ValueError('renderer observation targets another transport')
        from hdc_transport import failed
        if failed(checked({k:row[k] for k in ['path','sha256']}).read_text()):
            raise ValueError('renderer observation reported HDC failure')
    matches = [(i,row) for i,row in enumerate(commands) if row.get('label') == 'renderer-BMS']
    if len(matches) != 1:
        raise ValueError('one actual renderer BMS command required')
    index,row = matches[0]
    require_transport(row)
    raw = replay_observation({'raw':value['renderer_identity'],'command':row,'command_index':index},
        'bm dump -n com.ohos.wallpaper',env['target'],commands=commands)
    start = raw.find('{')
    if start < 0: raise ValueError('actual renderer BMS JSON missing')
    def unique(pairs):
        result = {}
        for key,item in pairs:
            if key in result: raise ValueError('duplicate renderer BMS key')
            result[key] = item
        return result
    bms = json.JSONDecoder(object_pairs_hook=unique).raw_decode(raw[start:])[0]
    def observation(label, descriptor, script):
        rows = [(i,r) for i,r in enumerate(commands) if r.get('label') == label]
        if len(rows) != 1: raise ValueError('one exact renderer observation required: '+label)
        i,r = rows[0]
        require_transport(r)
        return replay_observation({'raw':descriptor,'command':r,'command_index':i},script,env['target'],commands=commands),i
    def pid_cut(label, descriptor, reported, *, baseline=False):
        rows = [(i,r) for i,r in enumerate(commands) if r.get('label') == label]
        if len(rows) != 1: raise ValueError('one exact renderer PID command required')
        i,r = rows[0];argv = r['argv']
        require_transport(r)
        markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=',argv[4])
        if len(markers) != 1 or argv[4] != 'pidof com.ohos.wallpaper; task_ui_rc=$?; printf "\\n'+markers[0]+'%s\\n" "$task_ui_rc"':
            raise ValueError('renderer PID command script/nonce differs')
        transport = checked({k:r[k] for k in ['path','sha256']}).read_text()
        from hdc_transport import failed
        if failed(transport): raise ValueError('renderer PID transport reported HDC failure')
        body,code = command_exit(transport,markers[0]);derived = checked(descriptor).read_text()
        if code == 1:
            if body != '' or derived != '': raise ValueError('renderer absence has nonempty actual output')
            expected = dict(state='absent_before_first_public_desktop_set' if baseline else 'negative_absence_ONLY_NOT_connected',
                guest_exit_code=1,command_label=label,command={k:r[k] for k in ['path','sha256']})
            allowed_nonzero.add(i)
        elif code == 0:
            if re.fullmatch(r'[1-9][0-9]*',body.rstrip('\n')) is None or derived != body.rstrip('\n'):
                raise ValueError('one real renderer PID required')
            expected = dict(state='actual_pid_ONLY_NOT_connected',guest_exit_code=0,command_label=label)
        else: raise ValueError('renderer PID command failed with unexpected guest status')
        if reported != expected or type(reported.get('guest_exit_code')) is not int:
            raise ValueError('renderer PID summary differs from actual raw observation')
        return derived,i,code
    module = value.get('renderer_module')
    if module != ('phone_wallpaper' if env['device_type'] == 'phone' else 'pad_wallpaper'):
        raise ValueError('renderer module belongs to another device profile')
    stages = value['stages'];baseline = stages[0]
    if baseline.get('name') != 'baseline': raise ValueError('first actual renderer baseline required')
    pids,pid_index,code = pid_cut('baseline-renderer-pid',baseline['renderer_pids'],baseline['renderer_observation'],baseline=True)
    ams,ams_index = observation('baseline-AMS',baseline['ams'],'aa dump -a -u 100')
    if ams_index >= pid_index: raise ValueError('initial renderer AMS/PID order changed')
    try:
        parse_connection(ams,bms,pids,module_name=module,allow_pending=True)
        baseline_state = 'connected'
    except ConnectionNotReady as error: baseline_state = error.state
    product = None
    if code == 1:
        if baseline_state != 'absent_service_and_process': raise ValueError('baseline absence contradicts actual complete AMS')
        # The current native guard checks the new source/GN/compile/image bytes.
        # An older image plus a new caller cannot authorize this new baseline.
        import tempfile
        import batch_media_wallpaper_native as native
        with tempfile.TemporaryDirectory(prefix='wallpaper-first-set-native-') as temporary:
            actual = native.archive_native(checked(value['archive']),checked(value['boot']),Path(temporary).resolve()/'native')
        product = {key:actual[key] for key in ['archive_sha256','boot_id','product','image','guard']}
        if actual['archive_sha256'] != value['archive']['sha256'] or actual['boot_id'] != env['boot_id']:
            raise ValueError('negative renderer baseline has another actual native product')
    records = value.get('renderer_readiness')
    if not isinstance(records,list) or [r.get('stage') for r in records] != ['desktop-1','desktop-2']:
        raise ValueError('both actual desktop renderer readiness traces required')
    previous_formal = pid_index
    for readiness in records:
        name = readiness['stage'];matching = [s for s in stages if s['name'] == name]
        if len(matching) != 1: raise ValueError('one actual desktop stage required')
        stage = matching[0]
        if stage.get('renderer_readiness') != readiness or readiness.get('scope') != 'real_public_desktop_set_connection_readiness_ONLY' or readiness.get('status') != 'connected':
            raise ValueError('renderer readiness differs from its actual stage')
        began,ended = readiness['started_ns'],readiness['finished_ns']
        if type(began) is not int or type(ended) is not int or not stage['started_ns'] <= began < ended <= stage['finished_ns'] or ended-began > 45_000_000_000:
            raise ValueError('bounded renderer readiness interval missing')
        probes = readiness['probes']
        if not isinstance(probes,list) or not 1 <= len(probes) <= 256: raise ValueError('bounded complete renderer probes required')
        previous_end = began;previous_command = previous_formal
        for n,probe in enumerate(probes):
            if (type(probe['started_ns']) is not int or type(probe['finished_ns']) is not int or
                    not previous_end <= probe['started_ns'] <= probe['finished_ns'] <= ended):
                raise ValueError('renderer probe timing/order changed')
            prefix = name+'-wait-renderer-'+str(n).zfill(3)
            pids,pi,_ = pid_cut(prefix+'-pid',probe['renderer_pids'],probe['pid_observation'])
            ams,ai = observation(prefix+'-AMS',probe['ams'],'aa dump -a -u 100')
            if not previous_command < pi < ai: raise ValueError('renderer pending raw command order changed')
            try:
                connection = parse_connection(ams,bms,pids,module_name=module,allow_pending=True)
                state = 'connected'
                if probe.get('connection') != connection: raise ValueError('renderer connected summary changed')
            except ConnectionNotReady as error:
                state = error.state
                if 'connection' in probe: raise ValueError('pending renderer contains a connected proof')
            if probe.get('state') != state or (n == len(probes)-1) != (state == 'connected'):
                raise ValueError('renderer readiness skipped/fabricated a terminal raw cut')
            previous_end,previous_command = probe['finished_ns'],ai
        _,formal_ams = observation(name+'-AMS',stage['ams'],'aa dump -a -u 100')
        if previous_command >= formal_ams: raise ValueError('formal desktop proof did not follow actual readiness')
        formal_pids,formal_pid,formal_code = pid_cut(name+'-renderer-pid',stage['renderer_pids'],stage['renderer_observation'])
        if formal_code != 0 or formal_ams >= formal_pid: raise ValueError('formal desktop PID proof missing or out of order')
        parse_connection(checked(stage['ams']).read_text(),bms,formal_pids,module_name=module)
        previous_formal = formal_pid
    return allowed_nonzero,product


def verify(path):
    value = json.loads(Path(path).read_text())
    if (value.get('schema_version') != 1 or value.get('scope') != SCOPE or value.get('status') != 'collected' or
            value.get('failures') != [] or value.get('first_artifact_behavior_gate_passed') is not False or
            sha(checked(value['runner'])) != sha(HERE / 'batch_media_wallpaper_runtime.py')):
        raise ValueError('complete original runner evidence required')
    boot = json.loads(checked(value['boot']).read_text())
    env = validate_binding(boot, sha(checked(value['archive'])))
    if env['boot_id'] != value['boot_id']:
        raise ValueError('wallpaper evidence belongs to another boot')
    challenge = json.loads(checked(value['challenge']).read_text()); check_challenge(challenge)
    if challenge['run_id'] != value['run_id']:
        raise ValueError('wallpaper evidence belongs to another challenge')
    plan = json.loads(checked(value['plan']).read_text())
    if plan['screens']['desktop'] == plan['screens']['lock']:
        raise ValueError('desktop and lock cannot use the same viewport identity')
    seed_uid = bms(value['seed_identity'], SEED, ordinary=True)
    settings_uid = bms(value['settings_identity'], SETTINGS)
    for role, bundle in (('seed', SEED), ('settings', SETTINGS)):
        matches = [(i, row) for i, row in enumerate(value['commands']) if row.get('label') == role + '-BMS']
        if len(matches) != 1:
            raise ValueError('one original runtime BMS command required')
        index, command = matches[0]
        replay_observation({'raw': value[role + '_identity'], 'command': command, 'command_index': index},
                           'bm dump -n ' + bundle, env['target'], commands=value['commands'])
    bms(value['renderer_identity'], 'com.ohos.wallpaper')
    bms(value['photos_identity'], PHOTOS)
    if seed_uid == settings_uid:
        raise ValueError('ordinary denied caller and Settings identities overlap')
    acks(value['actions'], value['run_id'], value['boot_id'])
    if not value['commands']:
        raise ValueError('actual guest command evidence required')
    imports, uris = seed_rows(transferred(value['seed_log'])[0].read_text(), value['run_id'])
    denied, denied_uris = seed_rows(transferred(value['denied_log'])[0].read_text(), value['run_id'], denial=True)
    if uris != denied_uris or denied[:10] != imports:
        raise ValueError('ordinary caller replaced its imported asset history')
    for log in ('seed_log', 'denied_log'):
        _, meta = transferred(value[log])
        if meta['uid'] != seed_uid or not value[log]['remote'].startswith('/data/app/el2/100/base/'+SEED+'/files/'):
            raise ValueError('ordinary caller results are not its actual private data')
    for name in CASES:
        path, meta = transferred(value['private_PNGs'][name])
        expected_remote = '/data/app/el2/100/base/'+SEED+'/files/'+name+'.png'
        if (value['private_PNGs'][name]['remote'] != expected_remote or meta['uid'] != seed_uid or
                meta['mode'] & 0o077 or sha(path) != challenge['images'][name]['sha256']):
            raise ValueError('actual ordinary-owned private PNG differs from host random challenge')
        index = CASES.index(name)*2
        request, complete = (json.loads(imports[i]['detail']) for i in (index, index+1))
        if (request['bytes'] != path.stat().st_size or complete['bytes'] != path.stat().st_size or
                not request.get('sourceUri', '').endswith('/'+name+'.png')):
            raise ValueError('actual import bytes/source do not bind the received original private PNG')
    names = ['baseline', 'desktop-1', 'desktop-2', 'lock-1', 'lock-2', 'picker-cancel', 'preview-cancel',
             'preview-back', 'permission-denied', 'desktop-restore', 'lock-restore']
    if [s.get('name') for s in value['stages']] != names:
        raise ValueError('complete ordered positive/overwrite/cancel/denial/default sequence required')
    stages = {s['name']: stage_files(s) for s in value['stages']}
    intervals = [(s['started_ns'], s['finished_ns']) for s in value['stages']]
    if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('overlapping or reordered actual snapshots')
    metrics = {}
    previous = stages['baseline']
    for name in CASES[:4]:
        kind = name.split('-')[0]; current = stages[name]
        if PATHS[kind] not in current or CFG not in current:
            raise ValueError('new current-user wallpaper persistence missing')
        config = json.loads(current[CFG][0].read_text())
        if config['SystemResType' if kind == 'desktop' else 'LockScreenResType'] != 1:
            raise ValueError('real persisted resource type is not PICTURE')
        other = 'lock' if kind == 'desktop' else 'desktop'
        if {k: v[1]['sha256'] for k, v in previous.items() if '/'+('lockscreen' if other == 'lock' else 'system')+'/' in k} != {
                k: v[1]['sha256'] for k, v in current.items() if '/'+('lockscreen' if other == 'lock' else 'system')+'/' in k}:
            raise ValueError('single-target write changed the other wallpaper')
        source = checked(challenge['images'][name])
        metrics[name] = {'persisted': pixels(current[PATHS[kind]][0], source, minimum_fraction=0.95)}
        stage = next(s for s in value['stages'] if s['name'] == name)
        if stage['screen_kind'] != kind:
            raise ValueError('requested wallpaper target used the other screen')
        system_window(stage, plan)
        metrics[name]['compositor'] = pixels(checked(stage['screenshot']), source)
        if name.endswith('-2') and current[PATHS[kind]][1]['sha256'] == stages[kind+'-1'][PATHS[kind]][1]['sha256']:
            raise ValueError('second challenge reused old persisted bytes/cache')
        previous = current
    baseline = {k: v[1] for k, v in stages['lock-2'].items()}
    for name in ('picker-cancel', 'preview-cancel', 'preview-back', 'permission-denied'):
        if {k: v[1] for k, v in stages[name].items()} != baseline:
            raise ValueError('cancel/back/ordinary denial wrote wallpaper bytes')
    for kind in ('desktop', 'lock'):
        stage = next(s for s in value['stages'] if s['name'] == kind+'-restore')
        if stage['screen_kind'] != kind:
            raise ValueError('default restore captured the other screen')
        files = stages[kind+'-restore']
        if PATHS[kind] in files or CFG not in files:
            raise ValueError('restore retained challenged user resource')
        config = json.loads(files[CFG][0].read_text())
        if config['SystemResType' if kind == 'desktop' else 'LockScreenResType'] != 0:
            raise ValueError('restore did not persist DEFAULT resource type')
        default, _ = transferred(value['defaults'][kind]); system_window(stage, plan)
        metrics[kind+'-restore'] = pixels(checked(stage['screenshot']), default)
        if kind == 'desktop' and files.get(PATHS['lock'], (None, {}))[1].get('sha256') != stages['lock-2'][PATHS['lock']][1]['sha256']:
            raise ValueError('desktop default restore changed the lock wallpaper')
    if any('/system/' in key or '/lockscreen/' in key for key in stages['lock-restore']):
        raise ValueError('final default restore left user wallpaper resources')
    # Raw independent contracts are validated below, not summary booleans.
    verify_external_observations(value, env, challenge, uris, seed_uid, settings_uid)
    verify_ui_actions(value, challenge)
    renderer_negative_commands,renderer_product=verify_renderer_lifecycle(value,env)
    for command_index,command in enumerate(value['commands']):
        if type(command.get('exit_code')) is not int or command['exit_code'] != 0 or command.get('timed_out'):
            raise ValueError('guest transport command failed')
        raw = checked({key: command[key] for key in ('path', 'sha256')}).read_text()
        argv = command['argv']
        if len(argv) < 5 or argv[0] != value['hdc'] or argv[1:3] != ['-t', env['target']] or argv[3] not in ('shell', 'file'):
            raise ValueError('command does not target this enclosing guest')
        if argv[3] == 'shell':
            marker = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', argv[4])
            if len(marker) != 1:
                raise ValueError('actual remote shell success marker missing/nonzero')
            _, code = command_exit(raw.replace('\r', ''), marker[0])
            if code != 0 and command_index not in renderer_negative_commands and not layout_transition_unavailable(argv, raw):
                raise ValueError('actual remote shell success marker missing/nonzero')
    cleanup_commands = [command for command in value['commands'] if command.get('label') == 'owned-private-inputs-absent']
    if len(cleanup_commands) != 1 or not cleanup_commands[0]['argv'][4].startswith(
            'for wallpaper_name in desktop-1 desktop-2 lock-1 lock-2 cancel; do test ! -e '):
        raise ValueError('actual final guest private-file absence query required')
    return {'schema_version': 1, 'scope': SCOPE, 'status': 'pass', 'run_id': value['run_id'],
            'boot_id': value['boot_id'], 'archive_sha256': value['archive']['sha256'], 'metrics': metrics,
            'verifier_sha256': sha(Path(__file__)), 'closed_requirements': [], 'negative_renderer_baseline_native_product': renderer_product,
            'first_artifact_behavior_gate_passed': False}


def verify_ui_actions(value, challenge):
    thumbnails = []
    ids = []
    for action in value['ui_actions']:
        layout = Path(action['layout'])
        if layout.is_symlink() or sha(layout) != action['layout_sha256']:
            raise ValueError('actual UI action hierarchy changed')
        tree = json.loads(layout.read_text())
        if action['kind'] == 'click':
            selected = select_node(tree, action['bundle'], **action['selector'], clickable=True)
            if selected != action['selected_node']:
                raise ValueError('UI action not bound to actual visible enabled control')
            ids.append(action['selector'].get('identifier'))
        elif action['kind'] == 'challenge-thumbnail':
            selected, metrics = thumbnail(tree, checked(action['screenshot']), checked(challenge['images'][action['case']]), owner=action['ui_bundle'])
            photos_provider(checked(action['provider_dump']).read_text(), SETTINGS)
            if selected != action['node'] or metrics != action['metrics']:
                raise ValueError('Photos selection did not target the actual challenged thumbnail')
            thumbnails.append(action['case'])
        else:
            raise ValueError('unknown UI action')
    if thumbnails != list(CASES[:4])+['cancel', 'cancel']:
        raise ValueError('all fresh Settings PhotoPicker selections required')
    for identifier, count in {'settings_wallpaper_entry': 8, 'wallpaper_apply_home': 2,
                              'wallpaper_apply_lock': 2, 'wallpaper_restore_home': 1,
                              'wallpaper_restore_lock': 1, 'wallpaper_cancel': 1}.items():
        if ids.count(identifier) != count:
            raise ValueError('missing/extra actual explicit UI action: ' + identifier)
    select_node(json.loads(checked(value['back_return_layout']).read_text()), SETTINGS,
                identifier='settings_wallpaper_entry', clickable=True)


def verify_external_observations(value, env, challenge, uris, seed_uid, settings_uid):
    """Root adapters preserve raw independently collected receipts, never pass flags.

    Strict external layouts are documented in the handoff. Missing real token,
    build, consent, default resolver or deletion-query output is a hard failure.
    """
    def external(key):
        document = json.loads(checked(value[key]).read_text())
        if document.get('run_id') != value['run_id'] or document.get('boot_id') != env['boot_id']:
            raise ValueError('external observation belongs to another actual run/boot')
        return document
    imported = external('import_observation')
    if imported['uris'] != uris or imported['seed_uid'] != seed_uid:
        raise ValueError('root import history/UID differs from actual caller')
    module = json.loads(checked(imported['compiled_module']).read_text())
    if module['module'].get('requestPermissions', []) != [] or module['app']['bundleName'] != SEED:
        raise ValueError('ordinary import/denial caller received permissions or wrong bundle')
    if checked(imported['compiled_page']).read_bytes() != checked(challenge['generated_page']).read_bytes():
        raise ValueError('actual compiled caller source differs from frozen template/run')
    unsigned, signed, build_path, signing_path = (checked(imported[key]) for key in
                                                ('unsigned_hap', 'signed_hap', 'build_receipt', 'signing_receipt'))
    build, signing = json.loads(build_path.read_text()), json.loads(signing_path.read_text())
    if (build.get('status') != 'pass' or build.get('generated_page_sha256') != sha(checked(challenge['generated_page'])) or
            build.get('unsigned_sha256') != sha(unsigned) or signing.get('status') != 'pass' or
            signing.get('signed_sha256') != sha(signed) or signing.get('unsigned_sha256') != sha(unsigned)):
        raise ValueError('actual official build/sign receipts must bind unchanged compiled inputs and HAPs')
    profile = signing.get('verified_profile', {}).get('bundle-info', {})
    if profile.get('bundle-name') != SEED or profile.get('apl') != 'normal' or profile.get('app-feature') != 'hos_normal_app':
        raise ValueError('ordinary import/denial signer profile differs')
    verify_signed_payload(unsigned, signed)
    with zipfile.ZipFile(signed) as final:
        if json.loads(final.read('module.json')) != module:
            raise ValueError('actual ordinary HAP module differs from observed module')
    actions = imported['consent_actions']
    if len(actions) != 5:
        raise ValueError('one actual Photos user consent per fresh input required')
    for case, action in zip(CASES, actions):
        if action['case'] != case:
            raise ValueError('consent order differs from imported challenge')
        tree = json.loads(checked(action['layout']).read_text())
        if action['ui_bundle'] not in (PHOTOS, SEED):
            raise ValueError('actual import Photos provider/ordinary host owner required')
        from photos_dialog_contract import select_dialog
        node, contract = select_dialog(tree, action['ui_bundle'], 'save', label=imported['app_label'], count=1)
        if node != action['node'] or action.get('dialog') != contract or action.get('selector') != {'text': contract['allow']}:
            raise ValueError('actual Photos save consent control required')
        photos_provider(checked(action['provider_dump']).read_text(), SEED)
        checked(action['screenshot'])
    cancelled = external('picker_cancel_observation')
    if cancelled['ui_bundle'] not in (PHOTOS, SETTINGS):
        raise ValueError('actual cancelled picker owner required')
    from photos_asset_ui import button_ancestor
    node = button_ancestor(json.loads(checked(cancelled['layout']).read_text()), cancelled['ui_bundle'],
                           'Third_Select_PickerClose')
    if node != cancelled['node']:
        raise ValueError('actual Photos close action required')
    photos_provider(checked(cancelled['provider_dump']).read_text(), SETTINGS)
    checked(cancelled['screenshot'])
    rejected = external('denied_observation')
    token = verify_token_observation(rejected['token_query'], run=value['run_id'], boot=env['boot_id'],
        target=env['target'], bundle=SEED, permission='ohos.permission.SET_WALLPAPER',
        original_BMS=value['seed_identity'])
    before = verify_token_observation(rejected['before_normal_token'], run=value['run_id'], boot=env['boot_id'],
        target=env['target'], bundle=SEED, permission='ohos.permission.SET_WALLPAPER',
        original_BMS=value['seed_identity'])
    if token['grant'] != -1 or before['grant'] != -1 or token['token_id'] != before['token_id']:
        raise ValueError('actual ordinary SET_WALLPAPER denial token query required')
    granted = verify_token_observation(rejected['settings_token_query'], run=value['run_id'], boot=env['boot_id'],
        target=env['target'], bundle=SETTINGS, permission='ohos.permission.SET_WALLPAPER',
        original_BMS=value['settings_identity'])
    if granted['grant'] != 0:
        raise ValueError('actual installed Settings wallpaper permission grant required')
    resolution = external('default_resolution')
    raw = json.loads(checked(resolution['actual_GetCfgFiles_query']).read_text())
    if (raw.get('resource_path') != 'resource/themes/theme/' or not isinstance(raw.get('paths'), list) or
            raw.get('run_id') != value['run_id'] or raw.get('boot_id') != value['boot_id']):
        raise ValueError('real ordered config-policy query output required')
    binary, source, build_file = (checked(resolution[name]) for name in ('query_binary', 'query_source', 'query_build_receipt'))
    build = json.loads(build_file.read_text())
    if (sha(source) != sha(HERE/'fixtures/batch_media/wallpaper_runtime/default_resolver.cpp') or
            build.get('status') != 'pass' or build.get('source_sha256') != sha(source) or
            build.get('binary_sha256') != sha(binary) or build.get('arch') != env['guest_arch']):
        raise ValueError('real default resolver product build must bind exact source/binary/ABI')
    elf = binary.read_bytes()
    if (elf[:4] != b'\x7fELF' or len(elf) < 20 or int.from_bytes(elf[18:20], 'little') !=
            {'arm64': 183, 'armv7a': 40, 'x86_64': 62}[env['guest_arch']]):
        raise ValueError('actual guest ABI resolver ELF required')
    for kind in ('desktop', 'lock'):
        item = resolution[kind]
        if raw.get('resolved', {}).get(kind) != item['remote']:
            raise ValueError('default path differs from actual config-policy/service resolver output')
        if item['remote'] != value['defaults'][kind]['remote'] or not item['remote'].startswith(('/system/', '/vendor/', '/sys_prod/', '/chip_prod/')):
            raise ValueError('actual trusted system default path required')
        if item.get('manifest') is not None:
            manifest = json.loads(checked(item['manifest']).read_text())
            if not raw['paths']:
                raise ValueError('manifest default has no actual config-policy resource directory')
            root = raw['paths'][0].rstrip('/')+'/default/'
            section = 'home' if kind == 'desktop' else 'lock'
            expected = root+section+'/base/resources/'+manifest['image']['src']
            description = raw['descriptions'][kind]
            if description != {'manifest_remote': root+section+'/manifest.json', 'manifest_state': 'resolved'}:
                raise ValueError('manifest differs from actual service resolver path/state')
            if item['remote'] != expected or '..' in Path(item['remote']).parts:
                raise ValueError('default resource differs from actual service manifest resolution')
        elif item['remote'] != '/system/etc/wallpaper'+('default' if kind == 'desktop' else 'lockdefault')+'.jpeg':
            raise ValueError('service fallback default path differs')
        elif raw['descriptions'][kind]['manifest_state'] != 'fallback':
            raise ValueError('fallback was not selected by actual service resolver')
    cleanup = external('cleanup_observation')
    if cleanup['deleted_uris'] != uris:
        raise ValueError('cleanup must target exactly the created five Photo assets')
    query = json.loads(checked(cleanup['actual_asset_query']).read_text())
    if set(query) != {'queried_uris', 'active_uris'} or query['queried_uris'] != uris or query['active_uris'] != []:
        raise ValueError('independent real media query must show created assets removed from active library')
    if len(cleanup['ui_actions']) != 10:
        raise ValueError('five actual Photos browser delete actions and titled confirmations required')
    for index,action in enumerate(cleanup['ui_actions']):
        tree = json.loads(checked(action['layout']).read_text())
        if index % 2:
            from photos_dialog_contract import select_dialog
            node, contract = select_dialog(tree, PHOTOS, 'delete')
            if action['dialog'] != contract or action['selector'] != {'text':contract['allow']}:
                raise ValueError('delete confirmation differs from actual Photos single-image dialog')
        else:
            if action['selector'] != {'identifier':'ToolBarButtonDelete'} or action.get('dialog'):
                raise ValueError('actual Photos browser delete toolbar action required')
            node = select_node(tree, PHOTOS, **action['selector'], clickable=True)
        if node != action['node']:
            raise ValueError('cleanup action differs from actual Photos UI control')
        checked(action['screenshot'])
    checked(value['private_cleanup'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.runtime)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'status': 'fail', 'scope': SCOPE, 'failures': [type(error).__name__+': '+str(error)],
                  'first_artifact_behavior_gate_passed': False, 'closed_requirements': []}
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'scope')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
