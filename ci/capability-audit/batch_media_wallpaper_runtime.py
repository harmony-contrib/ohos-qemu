#!/usr/bin/env python3
"""Observe real Settings/Photos/wallpaper operations on an enclosing acceptance VM.

Root owns installation, user consent and system screen transitions. A nonce ACK
only coordinates those actions; independently collected files/UI/pixels decide
the result. This module never starts a VM, compiles, grants or writes a media DB.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import time

from PIL import Image, ImageDraw
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from guest_ui import GuestUi, GuestUiCommandError, LayoutNotReady, NodeNotReady, command_exit, select_node

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'fixtures/batch_media/wallpaper_runtime'
SETTINGS = 'com.ohos.settings'
SEED = 'org.harmonycontrib.wallpaperchallenge'
PHOTOS = 'com.ohos.photos'
CASES = ('desktop-1', 'desktop-2', 'lock-1', 'lock-2', 'cancel')
SCOPE = 'real_Settings_PhotoPicker_static_wallpaper_files_and_pixels_NOT_full_wallpaper_or_package_gate'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular evidence file required')
    return {'path': str(path.resolve()), 'sha256': sha(path)}


def write_json(path, value):
    path = Path(path)
    # Fresh evidence only. No overwrite of previous runs or symlink following.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def prepare(output, width, height):
    if type(width) is not int or type(height) is not int or not (320 <= width <= 4096 and 320 <= height <= 4096):
        raise ValueError('challenge size must be the actual display geometry, 320..4096')
    if width * height > 8_000_000:
        raise ValueError('bounded challenge pixel budget exceeded')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    run = secrets.token_hex(16)
    document = {'schema_version': 1, 'run_id': run, 'width': width, 'height': height,
                'generator_sha256': sha(Path(__file__)), 'images': {}}
    for name in CASES:
        image = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(image)
        # Random, spatially distinct low-frequency tiles survive real JPEG
        # persistence, picker thumbnails and compositor scaling. Not a fixture.
        for row in range(12):
            for column in range(12):
                color = tuple(24 + secrets.randbelow(208) for _ in range(3))
                draw.rectangle((column * width // 12, row * height // 12,
                                (column + 1) * width // 12 - 1, (row + 1) * height // 12 - 1), fill=color)
        path = output / (name + '.png')
        image.save(path, format='PNG')
        document['images'][name] = record(path)
    template = (FIXTURE / 'Index.ets').read_text()
    page = output / 'Index.ets'
    page.write_text(template.replace('__WALLPAPER_RUN__', run))
    document.update(template=record(FIXTURE / 'Index.ets'), generated_page=record(page),
                    expected_bundle=SEED, expected_request_permissions=[])
    write_json(output / 'challenge.json', document)
    return output / 'challenge.json'


def wait_ack(directory, request, *, timeout=90, clock=time.monotonic, sleep=time.sleep):
    """Exactly one complete owned 0600 ACK; content is synchronization only."""
    if not 1 <= timeout <= 180:
        raise ValueError('bounded root-action deadline required')
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != os.getuid():
        raise ValueError('owned root-action directory required')
    directory = directory.resolve()
    stem = request['run_id'] + '-' + str(request['sequence']).zfill(3) + '-' + request['nonce']
    pending = directory / (stem + '.request.json')
    fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(request, stream, ensure_ascii=False)
        stream.write('\n')
    reply = directory / (stem + '.ack.json')
    deadline = clock() + timeout
    while clock() < deadline:
        try:
            fd = os.open(reply, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            sleep(0.1)
            continue
        with os.fdopen(fd, 'rb') as stream:
            stat = os.fstat(stream.fileno())
            import stat as mode
            if (not mode.S_ISREG(stat.st_mode) or stat.st_uid != os.getuid() or stat.st_mode & 0o777 != 0o600 or
                    stat.st_nlink != 1 or not 1 <= stat.st_size <= 4096):
                raise ValueError('ACK must be a complete owned bounded 0600 regular file')
            raw = stream.read(4097)
        expected = {key: request[key] for key in ('schema_version', 'run_id', 'boot_id', 'sequence', 'nonce', 'action')}
        if json.loads(raw) != expected or clock() > deadline:
            raise ValueError('stale/malformed/action-mismatched ACK or exceeded original deadline')
        return {'request': record(pending), 'ack': record(reply)}
    raise ValueError('root action timed out; no implicit consent or completion: ' + request['action'])


def exact_absent_renderer_command(row, *, target, hdc):
    """Negative pidof observation ONLY; never a successful renderer proof."""
    if (type(row.get('exit_code')) is not int or row['exit_code'] != 0 or
            row.get('argv', [])[:4] != [str(hdc), '-t', target, 'shell'] or len(row['argv']) != 5):
        raise ValueError('renderer absence requires exact healthy command transport')
    script = row['argv'][4]
    markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', script)
    if len(markers) != 1 or script != ('pidof com.ohos.wallpaper; task_ui_rc=$?; printf "\\n' +
            markers[0] + '%s\\n" "$task_ui_rc"'):
        raise ValueError('renderer absence requires the exact pidof command')
    if Path(row['path']).is_symlink() or not Path(row['path']).is_file() or sha(row['path']) != row['sha256']:
        raise ValueError('renderer absence raw command changed')
    raw = Path(row['path']).read_text()
    body, code = command_exit(raw, markers[0])
    if body != '' or code != 1 or '[Fail]' in raw:
        raise ValueError('only actual guest pidof exit1 with byte-empty output is absence')
    return {'state': 'negative_absence_ONLY_NOT_connected', 'guest_exit_code': 1,
            'command_label': row['label'], 'command': {'path': row['path'], 'sha256': row['sha256']}}


class Runtime:
    def __init__(self, args):
        self.args = args
        self.output = args.output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.challenge = json.loads(args.challenge.read_text())
        self.plan = json.loads(args.plan.read_text())
        self.run = self.challenge['run_id']
        if re.fullmatch('[a-f0-9]{32}', self.run) is None:
            raise ValueError('fresh challenge nonce required')
        self.guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, self.output / 'guest')
        self.boot_id = self.guest.env['boot_id']
        self.renderer_module = 'phone_wallpaper' if self.guest.env['device_type'] == 'phone' else 'pad_wallpaper'
        self.value = {'schema_version': 1, 'scope': SCOPE, 'status': 'fail', 'failures': [],
                      'run_id': self.run, 'boot_id': self.boot_id, 'hdc': str(args.hdc), 'renderer_module': self.renderer_module, 'archive': record(args.archive),
                      'boot': record(args.boot), 'challenge': record(args.challenge), 'plan': record(args.plan),
                      'runner': record(Path(__file__)), 'commands': [], 'actions': [], 'stages': [],
                      'first_artifact_behavior_gate_passed': False}
        self.ui = GuestUi(self.command, args.hdc, self.guest.target, self.output / 'ui')
        self.save()

    def save(self):
        # Sole runner-owned report may update; raw evidence is always exclusive.
        path = self.output / 'runtime.json'
        path.write_text(json.dumps(self.value, ensure_ascii=False, indent=2) + '\n')
        return path

    def capture_failure(self):
        """Observe a real failed UI without actions, ACKs or acceptance claims."""
        result = {'scope': 'same_boot_failure_UI_ONLY_NOT_runtime_or_cleanup_proof',
                  'boot_id': self.boot_id, 'errors': []}
        self.value.setdefault('failure_diagnostics', []).append(result)
        # Coordinator actions may already have expired. Use the same bounded
        # transport and guest health checks for read-only diagnosis only; never
        # reset the action deadline or let this path publish an ACK.
        ui = GuestUi(lambda argv, label: Runtime.command(self, argv, label),
                     self.args.hdc, self.guest.target, self.output / 'failure-ui')
        def boot(label):
            raw = ui.shell('cat /proc/sys/kernel/random/boot_id', label)
            path = self.output / (label + '.txt')
            with path.open('x') as stream:
                stream.write(raw)
            result[label] = record(path)
            if raw.strip() != self.boot_id:
                raise ValueError('failure UI belongs to another kernel boot')
        prefix = 'failure-' + str(len(self.value['failure_diagnostics']))
        try:
            boot(prefix + '-boot-before')
        except Exception as error:
            result['errors'].append({'observation': 'boot_before', 'error': str(error)})
            self.save()
            return result
        for name, capture in [
                ('layout', lambda: record(ui.layout(label=prefix + '-tree')[1])),
                ('screenshot', lambda: record(ui.screenshot(label=prefix + '-pixels')))]:
            try:
                result[name] = capture()
            except Exception as error:
                result['errors'].append({'observation': name, 'error': str(error)})
        try:
            boot(prefix + '-boot-after')
            result['same_boot_verified'] = True
        except Exception as error:
            result['errors'].append({'observation': 'boot_after', 'error': str(error)})
        self.save()
        return result

    def command(self, argv, label):
        self.guest.healthy()
        argv = list(map(str, argv))
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        path = self.output / ('command-' + str(len(self.value['commands'])).zfill(4) + '.log')
        with path.open('x') as stream:
            stream.write(result.stdout + result.stderr)
        self.value['commands'].append({'argv': argv, 'label': label, 'exit_code': result.returncode, **record(path)})
        self.save()
        from hdc_transport import failed
        if result.returncode or failed(result.stdout, result.stderr):
            raise ValueError('actual guest transport/command failed: ' + label)
        return result.stdout.replace('\r', '')

    def shell(self, script, label):
        # GuestUi adds a fresh exit marker and checks actual guest status.
        return self.ui.shell(script, label)

    def text(self, text, label):
        path = self.output / (str(len(self.value['commands'])).zfill(4) + '-' + label + '.txt')
        with path.open('x') as stream:
            stream.write(text)
        return record(path)

    def identity(self, label):
        if self.shell('cat /proc/sys/kernel/random/boot_id', label + '-boot').strip() != self.boot_id:
            raise ValueError('wallpaper observation left its enclosing boot')
        account = self.shell('echo "bootevent.account.ready=$(param get bootevent.account.ready)"; '
                             'hidumper -s AccountMgr -a "-os_account_infos"', label + '-account')
        from account_state import parse_snapshot
        if not all(parse_snapshot(account).values()):
            raise ValueError('actual foreground account100 required; never silently default to100')
        return self.text(account, label + '-account')

    def action(self, action, **details):
        self.identity('before-action-' + str(len(self.value['actions'])))
        request = {'schema_version': 1, 'run_id': self.run, 'boot_id': self.boot_id,
                   'sequence': len(self.value['actions']) + 1, 'nonce': secrets.token_hex(16),
                   'action': action, 'details': details}
        row = {'action': action, 'started_ns': time.monotonic_ns(),
               **wait_ack(self.args.actions, request, timeout=self.args.action_timeout)}
        row['finished_ns'] = time.monotonic_ns()
        self.value['actions'].append(row)
        self.save()
        return row

    def receive(self, remote, label, *, maximum=32 * 1024 * 1024):
        quoted = shlex.quote(remote)
        stat = self.shell('test -f ' + quoted + ' && test ! -L ' + quoted +
                          " && stat -c '%u %g %a %s %Y %i' " + quoted + ' && sha256sum ' + quoted, label + '-stat')
        from batch_media_verify_wallpaper_runtime import parse_remote_stat
        metadata = parse_remote_stat(stat, remote, maximum)
        local = self.output / ('received-' + str(len(self.value['commands'])).zfill(4) + '-' + label)
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'recv', remote, local], label + '-recv')
        stat_after = self.shell('test -f ' + quoted + ' && test ! -L ' + quoted +
                                " && stat -c '%u %g %a %s %Y %i' " + quoted + ' && sha256sum ' + quoted, label + '-stat-after')
        if stat_after != stat or sha(local) != metadata['sha256'] or local.stat().st_size != metadata['size']:
            raise ValueError('guest file changed during read or transfer differs')
        return {'remote': remote, 'before': self.text(stat, label + '-stat'),
                'after': self.text(stat_after, label + '-stat-after'), 'file': record(local)}

    def renderer_bms(self):
        path = Path(self.value['renderer_identity']['path'])
        if sha(path) != self.value['renderer_identity']['sha256']:
            raise ValueError('actual renderer BMS observation changed')
        text = path.read_text()
        start = text.find('{')
        if start < 0: raise ValueError('actual renderer BMS JSON missing')
        def unique(pairs):
            value = {}
            for key, row in pairs:
                if key in value: raise ValueError('duplicate actual renderer BMS JSON key')
                value[key] = row
            return value
        value, _ = json.JSONDecoder(object_pairs_hook=unique).raw_decode(text[start:])
        return value

    def renderer_pid(self, label, *, permit_absence=False):
        try:
            text = self.shell('pidof com.ohos.wallpaper', label)
        except GuestUiCommandError as error:
            if not permit_absence or error.exit_code != 1:
                raise
            row = self.value['commands'][-1]
            if row['label'] != label: raise ValueError('wrong renderer pidof command receipt')
            return '', exact_absent_renderer_command(row, target=self.guest.target, hdc=self.args.hdc)
        if re.fullmatch(r'[1-9][0-9]*', text) is None:
            raise ValueError('one actual renderer PID required; no empty successful command')
        return text, {'state': 'actual_pid_ONLY_NOT_connected', 'guest_exit_code': 0, 'command_label': label}

    def wait_renderer(self, name):
        """Wait only on typed valid pending states, then retain strict stage proof."""
        from batch_apps_wallpaper_connection import ConnectionNotReady, parse_connection
        bms = self.renderer_bms()
        result = {'stage': name, 'started_ns': time.monotonic_ns(), 'probes': [],
                  'scope': 'real_public_desktop_set_connection_readiness_ONLY', 'status': 'pending'}
        self.value.setdefault('renderer_readiness', []).append(result)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            index = len(result['probes'])
            label = name + '-wait-renderer-' + str(index).zfill(3)
            began = time.monotonic_ns()
            pids, observation = self.renderer_pid(label + '-pid', permit_absence=True)
            ams = self.shell('aa dump -a -u 100', label + '-AMS')
            row = {'started_ns': began, 'finished_ns': time.monotonic_ns(), 'pid_observation': observation,
                   'renderer_pids': self.text(pids, label + '-pid'), 'ams': self.text(ams, label + '-AMS')}
            result['probes'].append(row)
            try:
                row['connection'] = parse_connection(ams, bms, pids, module_name=self.renderer_module, allow_pending=True)
            except ConnectionNotReady as error:
                row['state'] = error.state
                self.save(); time.sleep(0.2)
                continue
            if time.monotonic() > deadline:
                row['state'] = 'deadline_exceeded'; break
            row['state'] = 'connected'
            result.update(status='connected', finished_ns=time.monotonic_ns())
            self.save()
            return result
        result.update(status='timeout', finished_ns=time.monotonic_ns())
        self.save()
        raise ValueError('real foreground renderer connection did not become ready after public desktop set')

    def snapshot(self, name, *, screen=None):
        stage = {'name': name, 'started_ns': time.monotonic_ns(), 'account': self.identity(name), 'files': {}}
        if name in ('desktop-1', 'desktop-2'):
            stage['renderer_readiness'] = self.wait_renderer(name)
        # Capture the screen immediately after the coordinator's real UI
        # transition, before slower evidence transfers can hit normal suspend.
        # Never add a keepalive, forced wake or power override.
        if screen:
            layout, path = self.ui.layout(label=name + '-system-window')
            picture = self.ui.screenshot(label=name + '-system-pixels')
            stage.update(screen_kind=screen, layout=record(path), screenshot=record(picture))
        dump = self.shell('aa dump -a -u 100', name + '-AMS')
        stage['ams'] = self.text(dump, name + '-AMS')
        pids, observation = self.renderer_pid(name + '-renderer-pid', permit_absence=name == 'baseline')
        if not pids:
            from batch_apps_wallpaper_connection import ConnectionNotReady, parse_connection
            try:
                parse_connection(dump, self.renderer_bms(), pids, module_name=self.renderer_module, allow_pending=True)
            except ConnectionNotReady as error:
                if error.state != 'absent_service_and_process': raise ValueError('baseline is not fully unstarted') from error
            else: raise ValueError('baseline absence contradicts actual AMS')
            observation['state'] = 'absent_before_first_public_desktop_set'
        stage['renderer_observation'] = observation
        stage['renderer_pids'] = self.text(pids, name + '-renderer-pid')
        if name in ('desktop-1', 'desktop-2'):
            from batch_apps_wallpaper_connection import parse_connection
            stage['renderer_connection'] = parse_connection(dump, self.renderer_bms(), pids, module_name=self.renderer_module)

        base = '/data/service/el1/public/wallpaper/100'
        # Inventory both directories, including absence, so cancelling/denial
        # cannot hide a write to the other wallpaper or an unexpected file.
        for kind, directory in (('desktop', 'system'), ('lock', 'lockscreen')):
            remote = base + '/' + directory
            listing = self.shell('test -d ' + remote + ' && test ! -L ' + remote +
                                 ' && find ' + remote + ' -mindepth 1 -maxdepth 1 -print', name + '-' + kind + '-inventory')
            stage[kind + '_inventory'] = self.text(listing, name + '-' + kind + '-inventory')
            paths = listing.splitlines()
            if len(paths) > 32 or len(paths) != len(set(paths)):
                raise ValueError('unbounded/duplicate wallpaper inventory')
            for path in paths:
                if not path.startswith(remote + '/') or re.fullmatch('[a-z0-9_]{1,64}', path[len(remote) + 1:]) is None:
                    raise ValueError('unexpected nested or unsafe wallpaper resource')
                stage['files'][path] = self.receive(path, name + '-' + kind + '-' + path.rsplit('/', 1)[1])
        cfg = base + '/wallpapercfg'
        exists = self.shell('if test -e ' + cfg + '; then echo present; else echo absent; fi', name + '-cfg-presence')
        stage['cfg_presence'] = self.text(exists, name + '-cfg-presence')
        if exists.strip() == 'present':
            stage['files'][cfg] = self.receive(cfg, name + '-cfg', maximum=4096)
        elif exists.strip() != 'absent':
            raise ValueError('unknown cfg presence')
        stage['finished_ns'] = time.monotonic_ns()
        self.value['stages'].append(stage)
        self.save()
        return stage

    def click(self, identifier, *, bundle=SETTINGS, text=None, label=None):
        label = label or identifier
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                value = self.ui.click(bundle, identifier=None if text else identifier, text=text, label=label)
                value.update(kind='click', bundle=bundle, selector={'text': text} if text else {'identifier': identifier},
                             layout_sha256=sha(value['layout']), monotonic_ns=time.monotonic_ns())
                self.value.setdefault('ui_actions', []).append(value)
                self.save()
                return value
            except (LayoutNotReady, NodeNotReady):
                time.sleep(0.25)
        raise ValueError('actual visible enabled wallpaper control unavailable: ' + label)

    def settings(self):
        self.action('show-settings-main', bundle=SETTINGS)
        for selector in self.plan['settings_navigation']:
            if selector.get('bundle') != SETTINGS or set(selector) not in ({'bundle', 'identifier'}, {'bundle', 'text'}):
                raise ValueError('observed Settings-only navigation required')
            self.click(selector.get('identifier', ''), text=selector.get('text'))
        self.click('settings_wallpaper_entry')
        self.wait_preview(False)

    def wait_preview(self, required=True):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                layout, path = self.ui.layout(label='wallpaper-ready')
                select_node(layout, SETTINGS, identifier='wallpaper_choose_image', clickable=True)
                if required:
                    select_node(layout, SETTINGS, identifier='wallpaper_preview')
                return path
            except (LayoutNotReady, NodeNotReady):
                time.sleep(0.25)
        raise ValueError('real Settings wallpaper page/preview never became ready')

    def select(self, case):
        self.click('wallpaper_choose_image')
        from batch_media_verify_wallpaper_runtime import thumbnail
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                layout, path = self.ui.layout(label=case + '-Photos')
                picture = self.ui.screenshot(label=case + '-Photos')
                owner = self.plan.get('picker_ui_bundle', SETTINGS)
                node, metrics = thumbnail(layout, picture, self.challenge['images'][case]['path'], owner=owner)
            except (LayoutNotReady, NodeNotReady):
                time.sleep(0.25)
                continue
            left, top, width, height = node['rect']
            # A single-select picker can close in the click itself. Bind its
            # real provider while it is still visible, before dispatching.
            provider_dump = self.text(self.shell('aa dump -a -u 100', case + '-picker-AMS'), case + '-picker-AMS')
            self.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2), case + '-actual-thumbnail')
            self.value.setdefault('ui_actions', []).append({'kind': 'challenge-thumbnail', 'case': case,
                'layout': str(path), 'layout_sha256': sha(path), 'screenshot': record(picture),
                'node': node, 'metrics': metrics, 'ui_bundle': owner,
                'provider_dump': provider_dump,
                'monotonic_ns': time.monotonic_ns()})
            # Single-select may return immediately, or require real Complete.
            while time.monotonic() < deadline:
                try:
                    current, current_path = self.ui.layout(label=case + '-Photos-result')
                    try:
                        select_node(current, SETTINGS, identifier='wallpaper_preview')
                        return self.wait_preview()
                    except NodeNotReady:
                        select_node(current, owner, identifier='Complete', clickable=True)
                        self.click('Complete', bundle=owner, label=case + '-complete')
                        return self.wait_preview()
                except (LayoutNotReady, NodeNotReady):
                    time.sleep(0.25)
            break
        raise ValueError('unique painted fresh Photos thumbnail/result unavailable')

    def exercise(self):
        from batch_media_verify_wallpaper_runtime import checked, check_challenge, seed_rows
        check_challenge(self.challenge)
        self.guest.start()
        self.identity('initial')
        self.value['seed_identity'] = self.text(self.shell('bm dump -n ' + SEED, 'seed-BMS'), 'seed-BMS')
        self.value['settings_identity'] = self.text(self.shell('bm dump -n ' + SETTINGS, 'settings-BMS'), 'settings-BMS')
        self.value['renderer_identity'] = self.text(self.shell('bm dump -n com.ohos.wallpaper', 'renderer-BMS'), 'renderer-BMS')
        self.value['photos_identity'] = self.text(self.shell('bm dump -n ' + PHOTOS, 'photos-BMS'), 'photos-BMS')
        self.action('verify-package-identities-and-permissions', required_permission='ohos.permission.SET_WALLPAPER')
        self.action('resolve-service-default-resources', required_output=str(self.output / 'default-resolution.json'))
        resolution = self.output / 'default-resolution.json'
        self.value['default_resolution'] = record(resolution)
        defaults = json.loads(resolution.read_text())
        self.value['defaults'] = {}
        for kind in ('desktop', 'lock'):
            self.value['defaults'][kind] = self.receive(defaults[kind]['remote'], kind + '-actual-default')
        self.action('import-five-PNGs-via-real-Photos-consent', challenge=str(self.args.challenge.resolve()),
                    bundle=SEED, output=str(self.output / 'import-observation.json'))
        observation = self.output / 'import-observation.json'
        self.value['import_observation'] = record(observation)
        seed_path = '/data/app/el2/100/base/' + SEED + '/files/'
        self.value['seed_log'] = self.receive(seed_path + 'wallpaper-' + self.run + '.jsonl', 'seed-results', maximum=65536)
        seed_rows(checked(self.value['seed_log']['file']).read_text(), self.run)
        self.value['private_PNGs'] = {name: self.receive(seed_path + name + '.png', name + '-private.png') for name in CASES}
        self.snapshot('baseline')
        # Two independent updates for each type prove that the second result
        # cannot be satisfied by the preceding image/cache.
        for case in CASES[:4]:
            kind = case.split('-')[0]
            self.settings()
            self.select(case)
            self.click('wallpaper_apply_home' if kind == 'desktop' else 'wallpaper_apply_lock')
            self.action('show-real-' + kind, case=case)
            self.snapshot(case, screen=kind)
        self.settings()
        self.click('wallpaper_choose_image')
        self.action('cancel-real-Photos-picker', bundle=PHOTOS,
                    output=str(self.output / 'picker-cancel-observation.json'))
        self.value['picker_cancel_observation'] = record(self.output / 'picker-cancel-observation.json')
        self.wait_preview(False)
        self.snapshot('picker-cancel')
        self.select('cancel')
        self.click('wallpaper_cancel')
        self.snapshot('preview-cancel')
        self.settings()
        self.select('cancel')
        self.shell('uitest uiInput keyEvent Back', 'preview-back-real-key')
        self.value['back_return_layout'] = record(self.wait_entry())
        self.snapshot('preview-back')
        self.action('ordinary-denied-set-and-restore', bundle=SEED, output=str(self.output / 'denied-observation.json'))
        self.value['denied_observation'] = record(self.output / 'denied-observation.json')
        self.value['denied_log'] = self.receive(seed_path + 'wallpaper-' + self.run + '.jsonl', 'denied-results', maximum=65536)
        self.snapshot('permission-denied')
        for kind in ('desktop', 'lock'):
            self.settings()
            self.click('wallpaper_restore_home' if kind == 'desktop' else 'wallpaper_restore_lock')
            self.action('show-real-' + kind, case=kind + '-restore')
            self.snapshot(kind + '-restore', screen=kind)
        self.action('delete-only-created-Photos-assets-via-real-UI', output=str(self.output / 'cleanup-observation.json'))
        self.value['cleanup_observation'] = record(self.output / 'cleanup-observation.json')
        self.action('remove-owned-seed-private-inputs', bundle=SEED)
        absent = self.shell('for wallpaper_name in desktop-1 desktop-2 lock-1 lock-2 cancel; do '
            'test ! -e ' + shlex.quote(seed_path) + '$wallpaper_name.png || exit 1; done', 'owned-private-inputs-absent')
        self.value['private_cleanup'] = self.text(absent, 'private-cleanup')
        self.identity('final')
        # Independent verifier recomputes all assertions; run status alone has
        # no evidentiary weight. Runtime never marks the package gate passed.
        self.value['status'] = 'collected'
        self.save()

    def wait_entry(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                layout, path = self.ui.layout(label='wallpaper-back-return')
                select_node(layout, SETTINGS, identifier='settings_wallpaper_entry', clickable=True)
                return path
            except (LayoutNotReady, NodeNotReady):
                time.sleep(0.25)
        raise ValueError('Back did not return to the real Settings wallpaper entry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--width', type=int, required=True)
    prep.add_argument('--height', type=int, required=True)
    run = sub.add_parser('run')
    for name in ('boot', 'archive', 'challenge', 'plan', 'output', 'actions'):
        run.add_argument('--' + name, type=Path, required=True)
    run.add_argument('--hdc', required=True)
    run.add_argument('--action-timeout', type=int, default=90)
    args = parser.parse_args()
    if args.mode == 'prepare':
        print(prepare(args.output, args.width, args.height))
        return 0
    runtime = None
    try:
        runtime = Runtime(args)
        runtime.exercise()
        from batch_media_verify_wallpaper_runtime import verify
        value = verify(runtime.save())
        write_json(runtime.output / 'verified.json', value)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        if runtime:
            runtime.value['status'] = 'fail'
            runtime.value['failures'].append(type(error).__name__ + ': ' + str(error))
            try:
                runtime.capture_failure()
            except Exception as capture_error:
                runtime.value['failure_capture_error'] = str(capture_error)
            runtime.save()
        print(type(error).__name__ + ': ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
