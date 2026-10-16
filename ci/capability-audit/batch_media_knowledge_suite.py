#!/usr/bin/env python3
"""Collect Knowledge public calls on the parent's existing VM, never build/boot it."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import subprocess
import sys
import tempfile
import time

import batch_apps_contact_picker_coordinator as signatures
import batch_media_knowledge_artifacts as inputs
import batch_media_knowledge_project as project
import batch_media_knowledge_runtime as runtime
from enclosing_acceptance_guest import EnclosingAcceptanceGuest, validate_binding
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node
from hdc_transport import failed

HERE = Path(__file__).resolve().parent
SCOPE = 'same_packaged_guest_Knowledge_account100_HOLIDAY_public_lifecycle_NOT_analysis_or_account_isolation'
CALENDAR = '/system/etc/knowledge-content/holidays.ics'
TOOLS = ('batch_media_knowledge_suite.py', 'batch_media_knowledge_artifacts.py', 'batch_media_knowledge_project.py',
         'batch_media_knowledge_runtime.py', 'batch_apps_contact_picker_coordinator.py', 'guest_ui.py',
         'enclosing_acceptance_guest.py', 'batch_system_build_runtime_helpers.py', 'sign_certificate_probe.py', 'sign_web_probe.py',
         'photos_dialog_contract.py')
checked, record, require, sha = project.checked, project.record, project.require, project.sha


def save(path, value):
    path = Path(path)
    require(not path.is_symlink() and (not path.exists() or path.is_file() and path.stat().st_nlink == 1),
            'owned single-link journal required')
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    with temporary.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
    os.replace(temporary, path)


def profile(value, role, udid, module):
    require(role in ('query', 'curator') and re.fullmatch('[a-fA-F0-9]{64}', udid or ''), 'exact system test role/UDID required')
    bundle, apl, permissions, _ = project.ROLES[role]
    require(module['app']['bundleName'] == bundle and
            [p['name'] for p in module['module'].get('requestPermissions', [])] == permissions,
            'exact Knowledge role bundle/permissions required')
    value['bundle-info'].update({'bundle-name': bundle, 'apl': apl, 'app-feature': 'hos_system_app'})
    value['debug-info']['device-ids'] = [udid]
    value['acls']['allowed-acls'] = []; value['permissions']['restricted-permissions'] = []
    return value


def bms_identity(raw, role):
    bundle, apl, _, _ = project.ROLES[role]
    value = json.loads(raw.removeprefix(bundle + ':\n'))
    app = value['applicationInfo']; uid = app['uid']; token = app['accessTokenId']
    require((app.get('name') or app.get('bundleName')) == bundle and app.get('isSystemApp') is (apl != 'normal') and
            app.get('appPrivilegeLevel') == apl and type(uid) is int and uid // 200000 == 100 and uid % 200000 >= 10000 and
            type(token) is int and 0 < token < 2**32, 'actual BMS ordinary UID/system test role/token differs')
    paths = {v['hapPath'] for v in runtime._objects(value) if isinstance(v.get('hapPath'), str) and v['hapPath'].startswith('/data/app/')}
    require(len(paths) == 1 and next(iter(paths)).endswith('.hap'), 'one actual installed BMS HAP path required')
    return dict(uid=uid, token_id=token, installed_remote=next(iter(paths)))


def photos_connection(raw):
    host = project.ROLES['importer'][0]
    records = re.split(r'(?=^    uri \[)', raw, flags=re.M)
    matches = [v for v in records if v.startswith('    uri [/com.ohos.photos/') and
               'bundle name [com.ohos.photos]' in v and 'ability type [UIEXTENSION]' in v and
               'root host bundle name [' + host + ']' in v and
               re.search(r'AbilityRecord ID #[0-9]+\s+state #(FOREGROUND|ACTIVE)\b', v)]
    require(len(matches) == 1, 'one real Photos UIExtension connected to the importer host required')


def ready_node(tree, bundle, **selector):
    try:
        return select_node(tree, bundle, **selector)
    except ValueError as error:
        if str(error) in ('selected UITest node is not actually visible', 'selected UITest node is not an enabled clickable control'):
            raise NodeNotReady(str(error)) from error
        raise


def shell_body(row):
    argv = row['argv']; require(len(argv) == 5 and argv[3] == 'shell', 'actual shell command required')
    text = checked(row['raw']).read_text().replace('\r', '')
    markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', argv[4])
    require(len(markers) == 1 and text.count(markers[0]) == 1 and text.endswith('\n' + markers[0] + '0\n'),
            'real guest command success nonce required')
    return text.rsplit('\n' + markers[0], 1)[0].rstrip('\n')


def exact_script(row, script):
    require(row['argv'][4].startswith(script + '; task_ui_rc=$?; printf '), 'actual guest operation differs')
    return shell_body(row)


def verify_commands(rows, hdc, target):
    for row in rows:
        require(type(row.get('exit_code')) is int and row['exit_code'] == 0 and not row.get('timed_out'), 'command failed/timed out')
        raw = checked(row['raw']).read_text(); argv = row['argv']
        if argv[0] != hdc:
            continue  # Signatures are independently replayed, never trusted from these logs.
        require(len(argv) >= 4 and argv[1:3] == ['-t', target] and not failed(raw), 'guest transport escaped actual owned target')
        if argv[3] == 'shell':
            if row.get('layout_transition'):
                from batch_media_verify_wallpaper_runtime import layout_transition_unavailable
                require(layout_transition_unavailable(argv, raw), 'only exact actual UITest window transition may fail')
            else:
                shell_body(row)
            require(not re.search(r'\b(?:sqlite3|pm\s+grant|bm\s+grant|power-shell|system_powerdown)\b', argv[4]),
                    'collector cannot change SQL, grants or power policy')
        elif argv[3] in ('install', 'uninstall'):
            require(re.search(r'\bsuccess', raw, re.I) and not re.search(r'\bfail', raw, re.I), 'real package operation failed')
        else:
            require(argv[3] == 'file' and argv[4] in ('send', 'recv'), 'unknown guest operation')


class Collector:
    def __init__(self, args, value):
        self.args, self.value = args, value
        self.guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, args.output / 'guest').start()
        self.env = self.guest.env
        self.ui = GuestUi(self.command, args.hdc, self.guest.target, args.output / 'ui')
        self.roles = value['capture']['roles']; self.identities = {}; self.uris = {}
        self.data = runtime.validate_challenge(checked(value['artifacts_data']['challenge']))
        self.remote = '/data/local/tmp/knowledge-' + self.data['run_id']
        self.installed = []; self.curator_pid = None; self.remote_created = False

    def persist(self):
        save(self.args.output / 'evidence.json', self.value)

    def text(self, text, name):
        path = self.args.output / (str(len(self.value['observations'])).zfill(4) + '-' + name + '.txt')
        with path.open('x') as stream: stream.write(text)
        return record(path)

    def command(self, argv, label):
        self.guest.healthy(); argv = list(map(str, argv))
        path = self.args.output / (str(len(self.value['commands'])).zfill(4) + '-' + label + '.log')
        row = dict(argv=argv, label=label, exit_code=None, timed_out=False)
        with path.open('x') as stream:
            child = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            try: child.wait(timeout=300)
            except subprocess.TimeoutExpired:
                row['timed_out'] = True; os.killpg(child.pid, signal.SIGTERM)
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
        row.update(exit_code=child.returncode, raw=record(path)); self.value['commands'].append(row); self.persist()
        text = path.read_text(errors='replace')
        require(child.returncode == 0 and not row['timed_out'] and not failed(text), 'actual command failed: ' + label)
        return text

    def shell(self, script, label):
        return self.ui.shell(script, label)

    def observe(self, script, name):
        raw = self.shell(script, name)
        result = self.text(raw, name)
        self.value['observations'].append(dict(name=name, script=script, raw=result, command=len(self.value['commands']) - 1))
        self.persist(); return result

    def identity(self, label):
        observed = self.observe('cat /proc/sys/kernel/random/boot_id', label)
        require(checked(observed).read_text() == self.env['boot_id'], 'actual kernel boot changed')
        return observed

    def receive(self, remote, name, maximum=64*1024*1024):
        path = self.args.output / (name + '-' + secrets.token_hex(4) + '.bin')
        guard = self.observe('test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                             ' && sha256sum ' + shlex.quote(remote), name + '-guest-hash')
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'recv', remote, path], name + '-receive')
        require(0 < path.stat().st_size <= maximum and checked(guard).read_text().split() == [sha(path), remote],
                'actual complete guest file differs from received bytes')
        result = record(path)
        self.value['received'].append(dict(remote=remote, raw=result, guest_hash=guard, command=len(self.value['commands']) - 1))
        self.persist(); return result

    def stage(self, local, remote, uid, *, replace=False, executable=False):
        local = checked(local); temp = remote + '.' + secrets.token_hex(8) + '.tmp' if replace else remote
        require(not replace or remote.endswith('/knowledge-request.json'), 'only owned request may be replaced')
        self.shell('test ! -e ' + shlex.quote(temp) + ' && test ! -L ' + shlex.quote(temp), 'fresh-stage-target')
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'send', local, temp], 'send-owned-file')
        sent = len(self.value['commands']) - 1
        mode = '700' if executable else '600'
        self.shell('chown ' + str(uid) + ':' + str(uid) + ' ' + shlex.quote(temp) + ' && chmod ' + mode + ' ' + shlex.quote(temp), 'owned-stage-mode')
        if replace:
            self.shell('test ! -L ' + shlex.quote(remote) + ' && mv ' + shlex.quote(temp) + ' ' + shlex.quote(remote), 'publish-owned-request')
        observed = self.observe('sha256sum ' + shlex.quote(remote), 'actual-staged-sha')
        require(checked(observed).read_text().split() == [sha(local), remote], 'staged input bytes differ')
        self.value['staged'].append(dict(local=record(local), remote=remote, sent_remote=temp, uid=uid, mode=mode, command=sent, guest_hash=observed))
        self.persist()

    def journal(self, role, name):
        remote = self.files(role) + '/knowledge-' + self.data['run_id'] + '.jsonl'
        sentinel = '__KNOWLEDGE_EOF_' + secrets.token_hex(16) + '__'
        observed = self.observe('if test -f ' + shlex.quote(remote) + '; then cat ' + shlex.quote(remote) +
                                ' || exit 1; fi && printf ' + shlex.quote('\n' + sentinel + '\n'), name)
        raw = checked(observed).read_text()
        require(raw.endswith('\n' + sentinel) and raw.count(sentinel) == 1, 'actual whole-journal EOF missing')
        text = raw[:-len(sentinel)-1]
        path = self.args.output / (name + '-' + secrets.token_hex(4) + '.jsonl')
        with path.open('x') as stream: stream.write(text)
        result = record(path)
        self.value['journals'].append(dict(role=role, raw=result, observation=observed, sentinel=sentinel, remote=remote))
        return result

    def files(self, role):
        return '/data/app/el2/100/base/' + project.ROLES[role][0] + '/files'

    def pid(self):
        value = self.observe('pidof ' + project.ROLES['curator'][0], 'curator-singleton-pid')
        raw = checked(value).read_text()
        require(re.fullmatch('[1-9][0-9]*', raw), 'one actual retained curator process required')
        if self.curator_pid is None: self.curator_pid = raw
        require(raw == self.curator_pid, 'retained public PhotoAsset curator process restarted')
        return value

    def wait_control(self, bundle, control, kind, phase, *, title=None):
        deadline = time.monotonic() + 45
        while True:
            try:
                tree, path = self.ui.layout(label=phase + '-' + kind)
                if kind == 'consent':
                    from photos_dialog_contract import select_dialog
                    label = inputs.role_label(self.value['artifacts_data']['projects']['importer'], 'importer')
                    node, _ = select_dialog(tree, bundle, 'save', label=label, count=len(self.data['cases']))
                else:
                    if title: ready_node(tree, bundle, **title)
                    node = ready_node(tree, bundle, **control, clickable=True)
                break
            except (LayoutNotReady, NodeNotReady):
                if self.value['commands']:
                    last = self.value['commands'][-1]
                    from batch_media_verify_wallpaper_runtime import layout_transition_unavailable
                    if layout_transition_unavailable(last['argv'], checked(last['raw']).read_text()): last['layout_transition'] = True
                if time.monotonic() >= deadline: raise ValueError('actual unique UI unavailable: ' + phase + '/' + kind)
                time.sleep(.25)
        return tree, path, node

    def click(self, bundle, control, kind, phase, *, title=None):
        tree, path, node = self.wait_control(bundle, control, kind, phase, title=title)
        layout_command = len(self.value['commands']) - 1
        ams = self.observe('aa dump -a -u 100', phase + '-' + kind + '-AMS')
        if kind == 'consent': photos_connection(checked(ams).read_text())
        screenshot = record(self.ui.screenshot(label=phase + '-' + kind))
        screenshot_command = len(self.value['commands']) - 1
        screenshot_remote = self.value['commands'][screenshot_command]['argv'][-2]
        screenshot_hash = self.observe('sha256sum ' + shlex.quote(screenshot_remote), phase + '-' + kind + '-screen-sha')
        require(checked(screenshot_hash).read_text().split() == [screenshot['sha256'], screenshot_remote], 'actual screenshot transfer bytes differ')
        x, y, w, h = node['rect']
        self.shell(f'uitest uiInput click {x+w//2} {y+h//2}', phase + '-' + kind + '-click')
        row = dict(phase=phase, kind=kind, bundle=bundle, selector=control, title=title, layout=record(path),
                   selected_node=node, screenshot=screenshot, ams=ams, command=len(self.value['commands']) - 1,
                   layout_command=layout_command, screenshot_command=screenshot_command, screenshot_guest_hash=screenshot_hash)
        if kind == 'consent':
            from photos_dialog_contract import select_dialog
            label = inputs.role_label(self.value['artifacts_data']['projects']['importer'], 'importer')
            _, row['dialog_contract'] = select_dialog(tree, bundle, 'save', label=label, count=len(self.data['cases']))
        self.value['ui_actions'].append(row); self.persist(); return row

    def phase(self, phase, uris=None, *, emergency=None):
        request = runtime.prepare_request(checked(self.value['artifacts_data']['challenge']), self.env['boot_id'], phase, uris)
        if emergency:
            request.update(emergency)
        role = request['role']; bundle = project.ROLES[role][0]
        name = 'request-' + request['operation_id']; path = self.args.output / (name + '.json')
        project.write(path, request)
        row = dict(phase=phase, role=role, request=record(path), begin_boot=self.identity(name + '-boot-before'), complete=False)
        self.value['phases'].append(row); self.persist()
        self.shell('aa start -b ' + bundle + ' -a EntryAbility', 'launch-' + role)
        self.wait_control(bundle, {'identifier': 'knowledge_run'}, 'ready', phase)
        self.stage(record(path), self.files(role) + '/knowledge-request.json', self.identities[role]['uid'], replace=True)
        if self.curator_pid is not None: row['curator_pid_before'] = self.pid()
        self.click(bundle, {'identifier': 'knowledge_run'}, 'run', phase)
        plan = self.value['ui_plan_data']
        for dialog in plan['permissions'][role] if request['action'] == 'permission' else []:
            self.click(dialog['bundle'], dialog['allow'], 'permission', phase, title=dialog['title'])
        if request['action'] == 'import':
            dialog = plan['photo_consent']
            self.click(dialog['bundle'], dialog['allow'], 'consent', phase, title=dialog['title'])
        deadline = time.monotonic() + 180
        while True:
            journal = self.journal(role, name + '-poll')
            text = checked(journal).read_text()
            if text.endswith('\n'):
                rows = [json.loads(line) for line in text.splitlines()]
                operation = [v for v in rows if v.get('operation_id') == request['operation_id']]
                require(not any(v.get('event') == 'error' for v in operation), 'actual public operation failed: ' + phase)
                if operation and operation[-1].get('event') == 'complete': break
            if time.monotonic() >= deadline: raise ValueError('actual public operation timed out: ' + phase)
            time.sleep(.4)
        row.update(journal=journal, end_boot=self.identity(name + '-boot-after'), complete=True)
        if request['action'] == 'prepare' or self.curator_pid is not None: row['curator_pid_after'] = self.pid()
        if phase == 'import':
            created = [json.loads(v['value_json']) for v in operation if v['event'] == 'created']
            self.uris = {v['case_id']: v['uri'] for v in created}
            require(set(self.uris) == {c['case_id'] for c in self.data['cases']}, 'real complete created URI map missing')
        self.roles[role]['journal'] = journal; self.persist(); return row

    def token(self, role, when):
        bundle = project.ROLES[role][0]
        script = 'unset LD_LIBRARY_PATH LD_PRELOAD; ' + ' '.join(map(shlex.quote,
            [self.remote + '/observer', self.data['run_id'], str(self.identities[role]['uid']), bundle]))
        raw = self.observe(script, role + '-token-' + when)
        token = json.loads(checked(raw).read_text())
        require(token.get('api') == 'AccessTokenKit::VerifyAccessToken' and token.get('run_id') == self.data['run_id'] and
                token.get('boot_id') == self.env['boot_id'] and token.get('bundle') == bundle and
                token.get('uid') == self.identities[role]['uid'] and token.get('token_id') == self.identities[role]['token_id'],
                'actual observer returned another role/boot/token')
        self.roles[role]['token_' + when] = raw; self.persist()

    def install(self, role):
        artifacts = self.value['artifacts_data']; spec = artifacts['projects'][role]
        bundle, apl, permissions, _ = project.ROLES[role]
        unsigned = checked(spec['unsigned_hap']); dist = Path(artifacts['signer']['dist']); jar = checked(artifacts['signer']['jar'])
        if apl == 'normal':
            proof = signatures.sign_normal_hap(unsigned, bundle, permissions, self.env['udid'], dist, jar,
                self.args.output / (role + '-signing'), self.command)
        else:
            signed = self.args.output / (role + '-signed.hap')
            self.command([sys.executable, HERE / 'batch_media_knowledge_suite.py', 'sign-role', '--role', role,
                '--unsigned', unsigned, '--signer-dist', dist, '--jar', jar, '--udid', self.env['udid'], '--output', signed], 'sign-' + role)
            proof = signatures.verify_signed_hap_artifacts(signed, bundle, permissions, self.env['udid'], dist, jar,
                self.args.output / (role + '-signature-verification'), self.command, apl=apl, system_app=True)
        require(signatures.hap_contents(unsigned)[1] == signatures.hap_contents(checked(proof['signed_hap']))[1],
                'signing changed actual compiled HAP members')
        self.installed.append(bundle)  # Include an install whose transport reply might be lost.
        reply = self.command([self.args.hdc, '-t', self.guest.target, 'install', checked(proof['signed_hap'])], 'install-' + role)
        require(re.search(r'\bsuccess', reply, re.I) and not re.search(r'\bfail', reply, re.I), 'actual role install failed')
        bms = self.observe('bm dump -n ' + bundle, role + '-BMS')
        identity = bms_identity(checked(bms).read_text(), role); self.identities[role] = identity
        self.roles[role] = dict(sdk=spec, signed_hap=proof['signed_hap'], signature=proof, bms=bms,
            installed_remote=identity['installed_remote'], installed_hap=self.receive(identity['installed_remote'], role + '-installed-HAP'),
            private_source_readbacks={})
        self.token(role, 'initial')

    def emergency_cleanup(self):
        """Attempt only real public cleanup; any unproved result stops VM reuse."""
        if not any(v['phase'] == 'import' and v['kind'] == 'run' for v in self.value['ui_actions']):
            return {'scope': 'no_import_action_started', 'owned_assets_absent': True}
        journal = self.journal('importer', 'failure-import-journal')
        rows = [json.loads(v) for v in checked(journal).read_text().splitlines()]
        consent = [json.loads(v['value_json'])['uris'] for v in rows if v['event'] == 'consent_result']
        if not consent:
            raise ValueError('import was started without a complete consent result; created assets cannot be disproved')
        require(len(consent) == 1 and len(consent[0]) == len(self.data['cases']), 'actual partial consent needs retained guest investigation')
        self.uris = {case['case_id']: uri for case, uri in zip(self.data['cases'], consent[0])}
        require(len(set(self.uris.values())) == len(self.uris), 'duplicate actual consent URI')
        complete = {r['phase'] for r in self.value['phases'] if r.get('complete')}
        if 'prepare' not in complete:
            self.phase('prepare', self.uris, emergency={'phase': 'emergency-prepare'})
        if 'hide' in complete and 'unhide' not in complete:
            self.phase('unhide', self.uris, emergency={'phase': 'emergency-unhide'})
        lifecycle_deleted = 'delete' in complete
        if ('trash-again' in complete or 'trash' in complete and 'recover' not in complete) and not lifecycle_deleted:
            self.phase('delete', self.uris, emergency={'phase': 'emergency-delete'})
            lifecycle_deleted = True
        request = runtime.prepare_request(checked(self.value['artifacts_data']['challenge']), self.env['boot_id'], 'cleanup-assets', self.uris)
        selected = [c for c in self.data['cases'] if not lifecycle_deleted or c['case_id'] != self.data['lifecycle_case']]
        if 'cleanup-assets' not in complete:
            items = [{k: c[k] for k in ('case_id', 'day', 'title', 'file_name')} | {'uri': self.uris[c['case_id']]} for c in selected]
            self.phase('cleanup-assets', self.uris, emergency={'phase': 'emergency-assets', 'items': items})
        cleanup = self.phase('cleanup', self.uris)
        if 'cleanup-private' not in complete: self.phase('cleanup-private', self.uris)
        return cleanup_observation(cleanup, self.data, self.uris)

    def cleanup(self):
        errors = self.value['cleanup_errors']; cleanup = self.value.setdefault('cleanup', {})
        try:
            if self.value.get('raw_semantics'):
                cleanup['assets'] = {'scope': 'full_22_phase_raw_cleanup', 'raw_semantics': self.value['raw_semantics']}
            else:
                cleanup['assets'] = self.emergency_cleanup()
        except Exception as error: errors.append('public owned-asset cleanup unproved: ' + str(error))
        cleanup['roles'] = []
        for bundle in reversed(self.installed):
            try:
                reply = self.command([self.args.hdc, '-t', self.guest.target, 'uninstall', bundle], 'uninstall-owned-role')
                require(re.search(r'\bsuccess', reply, re.I), 'real uninstall failed')
                uninstall = len(self.value['commands']) - 1
                deadline = time.monotonic() + 30
                while True:
                    process = self.observe('pidof ' + bundle + ' || true', 'owned-process-absent')
                    if checked(process).read_text() == '': break
                    require(time.monotonic() < deadline, 'actual owned process remains after uninstall')
                    time.sleep(.25)
                cleanup['roles'].append(dict(bundle=bundle, process_absent=process, uninstall_command=uninstall))
            except Exception as error: errors.append('owned package cleanup: ' + bundle + ': ' + str(error))
        try:
            listing = self.observe('bm dump -a', 'owned-BMS-absent')
            assert_bundles_absent(checked(listing).read_text(), self.installed)
            cleanup['bms_absent'] = listing
        except Exception as error: errors.append('owned BMS cleanup: ' + str(error))
        try:
            deadline = time.monotonic() + 30
            while True:
                ams = self.observe('aa dump -a -u 100', 'owned-host-provider-sessions-absent')
                raw = checked(ams).read_text()
                if '  AppRunningRecords:' in raw and 'process name [com.ohos.sceneboard]' in raw and all(bundle not in raw for bundle in self.installed): break
                require(time.monotonic() < deadline, 'owned host/provider AMS session remains after uninstall')
                time.sleep(.25)
            cleanup['ams_absent'] = ams
        except Exception as error: errors.append('owned AMS session cleanup: ' + str(error))
        try:
            ui_paths = sorted({match for row in self.value['commands'] if len(row['argv']) == 5 and row['argv'][3] == 'shell'
                for match in re.findall(r'/data/local/tmp/qemu-capability-ui-' + self.ui.challenge + r'-[1-9][0-9]*\.(?:json|png)', row['argv'][4])})
            paths = ([self.remote + '/observer'] if self.remote_created else []) + ui_paths
            if paths:
                script = 'rm -f -- ' + ' '.join(map(shlex.quote, paths))
                script += ' && ' + ' && '.join('test ! -e ' + shlex.quote(p) + ' && test ! -L ' + shlex.quote(p) for p in paths)
                if self.remote_created: script += ' && if test -d ' + shlex.quote(self.remote) + '; then rmdir ' + shlex.quote(self.remote) + '; fi'
                cleanup['private_removal'] = self.observe(script, 'only-owned-private-files-absent')
            cleanup['private_paths'] = paths
        except Exception as error: errors.append('owned private helper/UI cleanup: ' + str(error))
        try: cleanup['final_boot'] = self.identity('wrapper-final-same-boot')
        except Exception as error: errors.append('final owned guest identity: ' + str(error))
        self.value['guest_commands'] = self.guest.report['commands']
        self.value['cleanup_complete'] = not errors
        self.persist()


def assert_bundles_absent(raw, bundles):
    require('com.ohos.' in raw and not failed(raw), 'actual full BMS listing required for absence')
    for bundle in bundles:
        require(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(bundle) + r'(?![A-Za-z0-9_.])', raw) is None,
                'owned bundle remains installed: ' + bundle)


def assert_ams_absent(raw, bundles):
    require('  AppRunningRecords:' in raw and 'process name [com.ohos.sceneboard]' in raw and
            all(bundle not in raw for bundle in bundles), 'actual live system AMS must prove owned host/provider sessions absent')


def verify_click(row, commands, hdc, target, observed, *, importer_label=None, count=None):
    layout = signatures.load(checked(row['layout']))
    read = commands[row['layout_command']]
    prefix = read['argv'][4].split('; task_ui_rc=$?; printf ', 1)[0]
    match = re.fullmatch(r'cat (/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.json)', prefix)
    require(match is not None and json.loads(exact_script(read, prefix)) == layout, 'UI hierarchy differs from actual nonce-scoped guest dump')
    remote = match[1]
    exact_script(commands[row['layout_command']-1], 'test ! -e ' + remote + ' && uitest dumpLayout -p ' + remote)
    if row['kind'] == 'consent':
        from photos_dialog_contract import select_dialog
        node, contract = select_dialog(layout, row['bundle'], 'save', label=importer_label, count=count)
        require(contract == row['dialog_contract'], 'actual titled same-dialog Allow/Deny contract differs')
    else:
        if row['title']: select_node(layout, row['bundle'], **row['title'])
        node = select_node(layout, row['bundle'], **row['selector'], clickable=True)
    require(node == row['selected_node'], 'UI click did not select the actual unique visible enabled node')
    x, y, width, height = node['rect']
    exact_script(commands[row['command']], f'uitest uiInput click {x+width//2} {y+height//2}')
    screen = checked(row['screenshot']); transfer = commands[row['screenshot_command']]
    remote = transfer['argv'][-2]
    require(re.fullmatch(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.png', remote) and
            transfer['argv'] == [hdc, '-t', target, 'file', 'recv', remote, str(screen)], 'actual compositor screenshot transfer differs')
    exact_script(commands[row['screenshot_command']-1], 'test ! -e ' + remote + ' && uitest screenCap -p ' + remote)
    require(observed(row['screenshot_guest_hash'], 'sha256sum ' + shlex.quote(remote)).split() == [sha(screen), remote],
            'actual screenshot SHA differs from captured guest bytes')
    require(row['layout_command'] < row['screenshot_command'] < row['command'], 'UI dump/screenshot/click order differs')
    from PIL import Image
    with Image.open(screen) as picture:
        picture.verify(); require(picture.format == 'PNG' and min(picture.size) >= 100, 'actual compositor PNG required')


def cleanup_observation(phase, data, uris):
    request = signatures.load(checked(phase['request'])); rows = [json.loads(v) for v in checked(phase['journal']).read_text().splitlines()]
    group = [v for v in rows if v['operation_id'] == request['operation_id']]
    require(group and group[-1]['event'] == 'complete' and all(v['event'] != 'error' for v in group), 'real cleanup query incomplete')
    cases = {c['case_id'] for c in data['cases']}
    assets = {json.loads(v['value_json'])['case_id']: json.loads(v['value_json']) for v in group if v['event'] == 'asset'}
    require(set(assets) == cases and all(type(v['count']) is int and v['count'] == 0 and v['requested_uri'] == uris[k] for k, v in assets.items()),
            'actual public cleanup query still sees owned assets')
    albums = [json.loads(v['value_json'])['count'] for v in group if v['event'] == 'trash_album']
    require(len(albums) == 1 and type(albums[0]) is int and albums[0] in (0, 1), 'actual cleanup TRASH album query absent')
    if albums[0]:
        trash = {json.loads(v['value_json'])['case_id']: json.loads(v['value_json']) for v in group if v['event'] == 'trash_asset'}
        require(set(trash) == cases and all(type(v['count']) is int and v['count'] == 0 and v['uri'] == uris[k] for k, v in trash.items()),
                'actual TRASH cleanup still sees owned assets')
    return dict(scope='real_public_active_and_TRASH_absence', query=phase['journal'], operation_id=request['operation_id'], owned_assets_absent=True)


def run(args):
    args.output = args.output.resolve(); args.output.mkdir(parents=True, exist_ok=False)
    value = dict(schema_version=1, status='fail', scope=SCOPE, archive=record(args.archive), archive_sha256=sha(args.archive),
        boot=record(args.boot), artifacts=record(args.artifacts), hdc=str(Path(args.hdc).resolve()),
        tools={name: record(HERE / name) for name in TOOLS}, commands=[], observations=[], received=[], staged=[], journals=[],
        phases=[], ui_actions=[], failures=[], cleanup_errors=[], cleanup_complete=False, first_artifact_behavior_gate_passed=False)
    collector = None
    try:
        spec = inputs.artifacts(args.artifacts); data = runtime.validate_challenge(checked(spec['challenge']))
        value.update(artifacts_data=spec, ui_plan_data=inputs.validate_plan(signatures.load(checked(spec['ui_plan'])), data), run_id=data['run_id'])
        value['capture'] = dict(run_id=data['run_id'], archive=record(args.archive), archive_sha256=sha(args.archive), signer=spec['signer'], roles={})
        collector = Collector(args, value); env = collector.env
        require((env['product'], env['guest_arch'], env['device_type']) == ('arm64_virt', 'arm64', 'phone'), 'representative ARM64 phone helpers required')
        value.update(boot_id=env['boot_id'], test_environment=env); value['capture']['boot_id'] = env['boot_id']
        collector.identity('wrapper-initial-same-boot')
        listing = collector.observe('bm dump -a', 'no-preexisting-owned-roles')
        assert_bundles_absent(checked(listing).read_text(), [r[0] for r in project.ROLES.values()])
        value['capture']['guest_calendar'] = collector.receive(CALENDAR, 'real-system-holiday-calendar', 1048576)
        require(sha(checked(value['capture']['guest_calendar'])) == data['calendar']['sha256'], 'guest authoritative holiday ICS differs')
        value['helper'] = inputs.helper_binding(spec['helpers'])
        collector.shell('test ! -e ' + collector.remote + ' && test ! -L ' + collector.remote, 'fresh-owned-helper-directory')
        collector.remote_created = True
        collector.shell('mkdir -m 700 ' + collector.remote, 'create-only-owned-helper-directory')
        collector.stage(value['helper']['binary'], collector.remote + '/observer', 0, executable=True)
        value['helper_guest_DSOs'] = []
        for dso in value['helper']['product_DSOs']:
            name = dso['soname']; candidates = ['/system/lib64/' + name, '/system/lib64/module/' + name, '/system/lib64/platformsdk/' + name, '/lib/' + name]
            script = 'for task_dso in ' + ' '.join(map(shlex.quote, candidates)) + '; do if test -f "$task_dso"; then sha256sum "$task_dso" || exit 1; fi; done'
            raw = collector.observe(script, 'actual-helper-DSO-' + name)
            lines = checked(raw).read_text().splitlines()
            require(lines and all(line.split()[0] == dso['sha256'] for line in lines), 'actual guest helper dependency differs from product link: ' + name)
            value['helper_guest_DSOs'].append(dict(soname=name, raw=raw, candidates=candidates))
        for role in project.ROLES: collector.install(role)
        require(len({v['uid'] for v in collector.identities.values()}) == 4 and len({v['token_id'] for v in collector.identities.values()}) == 4,
                'actual role identities overlap')
        for role in project.ROLES:
            value['capture']['roles'][role]['journal_before'] = collector.journal(role, role + '-journal-before')
            require(checked(value['capture']['roles'][role]['journal_before']).read_bytes() == b'', 'role journal is not fresh')
        importer = project.ROLES['importer'][0]
        collector.shell('aa start -b ' + importer + ' -a EntryAbility', 'open-normal-importer-files')
        collector.wait_control(importer, {'identifier': 'knowledge_run'}, 'ready', 'private-inputs')
        for case in data['cases']:
            remote = collector.files('importer') + '/' + case['file_name']
            collector.stage(case['image'], remote, collector.identities['importer']['uid'])
            collector.roles['importer']['private_source_readbacks'][case['case_id']] = collector.receive(remote, 'private-JPEG-' + case['case_id'], 4194304)
        for phase, _, _ in runtime.STEPS: collector.phase(phase, collector.uris or None)
        for role in project.ROLES:
            collector.roles[role]['journal'] = collector.journal(role, role + '-final-journal')
            collector.token(role, 'final')
        result = runtime.verify_raw(checked(spec['challenge']), {role: checked(r['journal']) for role, r in collector.roles.items()}, boot_id=env['boot_id'])
        project.write(args.output / 'raw-semantics.json', result); value['raw_semantics'] = record(args.output / 'raw-semantics.json')
    except Exception as error:
        value['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if collector is not None:
            collector.cleanup()
        else:
            value['cleanup_complete'] = True  # No guest command or owned resource was created.
            value['cleanup'] = {'no_guest_resources_created': True}
        save(args.output / 'evidence.json', value)
    if not value['failures'] and value['cleanup_complete']:
        value['status'] = 'pass'; save(args.output / 'evidence.json', value)
        try:
            value['independent_result'] = verify_evidence(args.output / 'evidence.json', args.archive, args.boot)
        except Exception as error:
            value['status'] = 'fail'; value['failures'].append('independent verification: ' + type(error).__name__ + ': ' + str(error))
        save(args.output / 'evidence.json', value)
    return value


def verify_transport(value, spec, env, data):
    """Re-read actual command bytes, not normalized capture status fields."""
    commands = value['commands']; target = env['target']; hdc = value['hdc']
    verify_commands(commands, hdc, target)
    observations = {}
    for row in value['observations']:
        require(type(row['command']) is int and 0 <= row['command'] < len(commands), 'actual observation command missing')
        actual = exact_script(commands[row['command']], row['script'])
        require(checked(row['raw']).read_text() == actual, 'normalized observation differs from original transport bytes')
        key = (row['raw']['path'], row['raw']['sha256'])
        require(key not in observations, 'duplicate normalized observation')
        observations[key] = row
    def observed(raw, script=None):
        key = (raw['path'], raw['sha256'])
        require(key in observations, 'claimed raw evidence not backed by actual HDC command')
        row = observations[key]
        if script is not None: require(row['script'] == script, 'claimed observer script differs')
        return checked(raw).read_text()
    for row in value['journals']:
        marker = row['sentinel']
        remote_journal = '/data/app/el2/100/base/' + project.ROLES[row['role']][0] + '/files/knowledge-' + data['run_id'] + '.jsonl'
        require(row['remote'] == remote_journal, 'role journal must be the actual app filesDir output')
        script = 'if test -f ' + shlex.quote(remote_journal) + '; then cat ' + shlex.quote(remote_journal) + ' || exit 1; fi && printf ' + shlex.quote('\n' + marker + '\n')
        text = observed(row['observation'], script)
        require(re.fullmatch('__KNOWLEDGE_EOF_[a-f0-9]{32}__', marker) and text.endswith('\n' + marker) and text.count(marker) == 1 and
                checked(row['raw']).read_text() == text[:-len(marker)-1], 'whole JSONL bytes/EOF differ from guest')
    received = {}
    for row in value['received']:
        local = checked(row['raw']); remote = row['remote']
        require(commands[row['command']]['argv'] == [hdc, '-t', target, 'file', 'recv', remote, str(local)] and
                observed(row['guest_hash'], 'test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                         ' && sha256sum ' + shlex.quote(remote)).split() == [sha(local), remote], 'received file not bound to actual guest bytes')
        received[(row['raw']['path'], row['raw']['sha256'])] = row
    role_ids = {role: bms_identity(observed(item['bms'], 'bm dump -n ' + project.ROLES[role][0]), role)
                for role, item in value['capture']['roles'].items()}
    allowed = {('/data/app/el2/100/base/' + project.ROLES[role][0] + '/files/knowledge-request.json'): (role_ids[role]['uid'], '600')
               for role in project.ROLES}
    allowed.update({('/data/app/el2/100/base/' + project.ROLES['importer'][0] + '/files/' + c['file_name']):
                    (role_ids['importer']['uid'], '600') for c in data['cases']})
    remote = '/data/local/tmp/knowledge-' + data['run_id']
    allowed[remote + '/observer'] = (0, '700')
    for row in value['staged']:
        local = checked(row['local']); destination = row['remote']; sent = row['command']
        require(destination in allowed and (row['uid'], row['mode']) == allowed[destination] and
                commands[sent]['argv'] == [hdc, '-t', target, 'file', 'send', str(local), row['sent_remote']] and
                observed(row['guest_hash'], 'sha256sum ' + shlex.quote(destination)).split() == [sha(local), destination],
                'actual staged input/owner/permission/path differs')
        if destination == remote + '/observer': require(row['local'] == value['helper']['binary'], 'executed helper was not the actual product-built ELF')
        exact_script(commands[sent+1], 'chown ' + str(row['uid']) + ':' + str(row['uid']) + ' ' + shlex.quote(row['sent_remote']) +
                     ' && chmod ' + row['mode'] + ' ' + shlex.quote(row['sent_remote']))
        if destination != row['sent_remote']:
            require(destination.endswith('/knowledge-request.json') and
                    re.fullmatch(re.escape(destination) + r'\.[a-f0-9]{16}\.tmp', row['sent_remote']), 'only owned request may be atomically replaced')
            exact_script(commands[sent+2], 'test ! -L ' + shlex.quote(destination) + ' && mv ' + shlex.quote(row['sent_remote']) + ' ' + shlex.quote(destination))
    require(len(value['phases']) == len(runtime.STEPS), 'exact 22 real phases required')
    uris = json.loads(checked(value['raw_semantics']).read_text())['uris']
    previous_end = -1
    for row, (phase, role, _) in zip(value['phases'], runtime.STEPS):
        request = signatures.load(checked(row['request']))
        expected = runtime.prepare_request(checked(spec['challenge']), env['boot_id'], phase, uris, request['operation_id'])
        require(row['phase'] == phase and row['role'] == role and row.get('complete') is True and request == expected,
                'actual phase role/order/request changed')
        require(observed(row['begin_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'] and
                observed(row['end_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'], 'phase ran on another kernel boot')
        begin = observations[(row['begin_boot']['path'], row['begin_boot']['sha256'])]['command']
        end = observations[(row['end_boot']['path'], row['end_boot']['sha256'])]['command']
        staged = [v for v in value['staged'] if v['local'] == row['request']]
        require(len(staged) == 1 and staged[0]['remote'] == '/data/app/el2/100/base/' + project.ROLES[role][0] + '/files/knowledge-request.json' and
                previous_end < begin < staged[0]['command'] < end, 'actual request/action transport ordering differs')
        journal = [v for v in value['journals'] if v['raw'] == row['journal']]
        require(len(journal) == 1 and journal[0]['role'] == role, 'actual phase journal lacks role/transport binding')
        rows = runtime.parse_journal(checked(row['journal']).read_text(), data['run_id'], env['boot_id'], role)
        group = [v for v in rows if v['operation_id'] == request['operation_id']]
        require(group and group[0]['event'] == 'begin' and group[0]['value'] == expected and group[-1]['event'] == 'complete',
                'actual requested operation not complete in raw journal')
        previous_end = end
    expected_actions = []
    for phase, role, action in runtime.STEPS:
        expected_actions.append((phase, 'run', project.ROLES[role][0], {'identifier': 'knowledge_run'}, None))
        for dialog in value['ui_plan_data']['permissions'][role] if action == 'permission' else []:
            expected_actions.append((phase, 'permission', dialog['bundle'], dialog['allow'], dialog['title']))
        if action == 'import':
            dialog = value['ui_plan_data']['photo_consent']
            expected_actions.append((phase, 'consent', dialog['bundle'], dialog['allow'], dialog['title']))
    require(len(expected_actions) == len(value['ui_actions']), 'actual UI approvals/actions incomplete')
    for row, expected in zip(value['ui_actions'], expected_actions):
        require((row['phase'], row['kind'], row['bundle'], row['selector'], row['title']) == expected, 'unexpected/missing UI action')
        verify_click(row, commands, hdc, target, observed, importer_label=inputs.role_label(spec['projects']['importer'], 'importer'), count=len(data['cases']))
        ams = observed(row['ams'], 'aa dump -a -u 100')
        if row['kind'] == 'consent': photos_connection(ams)
    pids = []
    for row in value['phases'][7:]:
        keys = ('curator_pid_after',) if row['phase'] == 'prepare' else ('curator_pid_before', 'curator_pid_after')
        for key in keys:
            pid = observed(row[key], 'pidof ' + project.ROLES['curator'][0])
            require(re.fullmatch('[1-9][0-9]*', pid), 'actual singleton process query malformed')
            pids.append(pid)
    require(len(set(pids)) == 1, 'curator process changed while retaining actual public PhotoAssets')
    for role, item in value['capture']['roles'].items():
        require(checked(item['journal_before']).read_bytes() == b'' and any(j['raw'] == item['journal_before'] for j in value['journals']) and
                any(j['raw'] == item['journal'] for j in value['journals']), 'fresh/complete original role journal unavailable')
        key = (item['installed_hap']['path'], item['installed_hap']['sha256'])
        require(key in received and received[key]['remote'] == item['installed_remote'], 'actual installed HAP transfer binding missing')
        for when in ('initial', 'final'):
            script = 'unset LD_LIBRARY_PATH LD_PRELOAD; ' + ' '.join(map(shlex.quote,
                [remote + '/observer', data['run_id'], str(role_ids[role]['uid']), project.ROLES[role][0]]))
            observed(item['token_' + when], script)
            index = observations[(item['token_' + when]['path'], item['token_' + when]['sha256'])]['command']
            bound = value['phases'][0]['begin_boot'] if when == 'initial' else value['phases'][-1]['end_boot']
            boundary = observations[(bound['path'], bound['sha256'])]['command']
            require(index < boundary if when == 'initial' else index > boundary, 'initial/final native token observation was reordered')
    key = (value['capture']['guest_calendar']['path'], value['capture']['guest_calendar']['sha256'])
    require(key in received and received[key]['remote'] == CALENDAR, 'actual system calendar transfer missing')
    for case in data['cases']:
        raw = value['capture']['roles']['importer']['private_source_readbacks'][case['case_id']]
        require((raw['path'], raw['sha256']) in received and received[(raw['path'], raw['sha256'])]['remote'] ==
                '/data/app/el2/100/base/' + project.ROLES['importer'][0] + '/files/' + case['file_name'], 'actual private JPEG readback transport missing')
    for dso, row in zip(value['helper']['product_DSOs'], value['helper_guest_DSOs']):
        require(row['soname'] == dso['soname'], 'guest DSO identity differs')
        name = dso['soname']
        require(row['candidates'] == ['/system/lib64/' + name, '/system/lib64/module/' + name,
                '/system/lib64/platformsdk/' + name, '/lib/' + name], 'guest DSO lookup escaped the actual system loader locations')
        script = 'for task_dso in ' + ' '.join(map(shlex.quote, row['candidates'])) + '; do if test -f "$task_dso"; then sha256sum "$task_dso" || exit 1; fi; done'
        lines = observed(row['raw'], script).splitlines()
        require(lines and all(line.split()[0] == dso['sha256'] and line.split()[1] in row['candidates'] for line in lines),
                'actual guest runtime helper DSO differs from actual linked product input')
    require(len(value['helper']['product_DSOs']) == len(value['helper_guest_DSOs']), 'actual guest DSO set incomplete')
    cleanup = value['cleanup']
    require(cleanup['assets'] == {'scope': 'full_22_phase_raw_cleanup', 'raw_semantics': value['raw_semantics']}, 'full actual public asset/TRASH/private cleanup proof required')
    bundles = [v[0] for v in project.ROLES.values()]
    require(sorted(v['bundle'] for v in cleanup['roles']) == sorted(bundles), 'all four owned roles must be uninstalled')
    for row in cleanup['roles']:
        require(commands[row['uninstall_command']]['argv'] == [hdc, '-t', target, 'uninstall', row['bundle']], 'uninstall does not own this role')
        require(observed(row['process_absent'], 'pidof ' + row['bundle'] + ' || true') == '', 'owned process still running')
    assert_bundles_absent(observed(cleanup['bms_absent'], 'bm dump -a'), bundles)
    assert_ams_absent(observed(cleanup['ams_absent'], 'aa dump -a -u 100'), bundles)
    paths = cleanup['private_paths']
    require(remote + '/observer' in paths and all(path == remote + '/observer' or
            re.fullmatch(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.(?:json|png)', path) for path in paths), 'cleanup targets must be exact owned helper/UI files')
    script = 'rm -f -- ' + ' '.join(map(shlex.quote, paths)) + ' && ' + ' && '.join(
        'test ! -e ' + shlex.quote(p) + ' && test ! -L ' + shlex.quote(p) for p in paths)
    script += ' && if test -d ' + shlex.quote(remote) + '; then rmdir ' + shlex.quote(remote) + '; fi'
    observed(cleanup['private_removal'], script)
    require(observed(cleanup['final_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'], 'cleanup changed guest kernel boot')


def verify_evidence(evidence_path, archive_path, boot_path):
    """Independent hash/source/SDK/crypto/transport/token/22-phase/cleanup replay."""
    value = signatures.load(evidence_path); archive_path = signatures.regular(archive_path); boot_path = signatures.regular(boot_path)
    require(value.get('schema_version') == 1 and value.get('status') == 'pass' and value.get('scope') == SCOPE and
            value.get('failures') == [] and value.get('cleanup_complete') is True and value.get('cleanup_errors') == [] and
            value.get('first_artifact_behavior_gate_passed') is False and checked(value['archive']) == archive_path and
            value.get('archive_sha256') == sha(archive_path) and checked(value['boot']) == boot_path,
            'complete exact current-archive/boot Knowledge collector required')
    require(value['tools'] == {name: record(HERE / name) for name in TOOLS}, 'fixed current verification/collector implementation changed')
    env = validate_binding(signatures.load(boot_path), sha(archive_path))
    require(value['test_environment'] == env and value['boot_id'] == env['boot_id'] and
            (env['product'], env['guest_arch'], env['device_type']) == ('arm64_virt', 'arm64', 'phone'), 'same representative parent VM required')
    spec = inputs.artifacts(checked(value['artifacts']))
    data = runtime.validate_challenge(checked(spec['challenge']))
    require(value['artifacts_data'] == spec and value['run_id'] == data['run_id'] and
            value['ui_plan_data'] == inputs.validate_plan(signatures.load(checked(spec['ui_plan'])), data), 'actual artifact/UI plan differs')
    helper = inputs.helper_binding(spec['helpers'])
    require(value['helper'] == helper, 'actual product observer source/ELF/CFI/link receipt changed')
    result = runtime.verify_raw(checked(spec['challenge']), {role: checked(item['journal']) for role, item in value['capture']['roles'].items()}, boot_id=env['boot_id'])
    require(signatures.load(checked(value['raw_semantics'])) == result, 'independent public Knowledge oracle differs')
    verify_transport(value, spec, env, data)
    with tempfile.TemporaryDirectory(prefix='knowledge-evidence-crypto-') as temporary:
        def command(argv, label):
            completed = subprocess.run(list(map(str, argv)), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
            require(completed.returncode == 0, 'actual cryptographic re-verification failed: ' + label)
            return completed.stdout + completed.stderr
        bindings = runtime.verify_role_bindings(value['capture'], checked(spec['challenge']),
            dict(env, user_id=100, archive_sha256=sha(archive_path)), command=command, output=Path(temporary) / 'role-bindings')
    require(set(bindings['roles']) == set(project.ROLES), 'all actual role source/signature/BMS/token bindings required')
    return dict(status='pass', scope=SCOPE, archive_sha256=sha(archive_path), boot_id=env['boot_id'],
        all_phases_verified=True, role_identity_and_signatures_verified=True,
        observer_product_ABI_verified=True, transport_guest_binding_verified=True,
        stages_verified=result['stages_verified'], images_verified=result['images_verified'],
        cleanup_complete=True, cleanup_errors=[], account_isolation_verified=False,
        nonempty_analysis_producer_verified=False, first_artifact_behavior_gate_passed=False, closed_requirement_ids=[])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'sign-role':
        parser = argparse.ArgumentParser(description='Exact legitimate Knowledge system test profile')
        for name in ('unsigned', 'signer-dist', 'jar', 'output'): parser.add_argument('--' + name, required=True, type=Path)
        parser.add_argument('--role', choices=('query', 'curator'), required=True); parser.add_argument('--udid', required=True)
        from sign_certificate_probe import sign
        sign(parser.parse_args(sys.argv[2:]), configure=profile); return 0
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('boot', 'archive', 'artifacts', 'hdc', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(); args.hdc = signatures.regular(args.hdc)
    value = run(args)
    print(json.dumps({key: value[key] for key in ('status', 'cleanup_complete', 'cleanup_errors', 'failures')}))
    return 0 if value['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
