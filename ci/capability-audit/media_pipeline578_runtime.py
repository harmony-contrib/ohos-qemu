"""Additional hooks for the EXISTING owned ordinary-HAP runner, never a new Owner.

No main/resource entry point: the parent passes its original command/shell,
archive/boot identity and original cleanup. Real system-picker node selectors
must come from the packaged SystemUI's actual resources. Missing selectors fail
before prepare; this module never grants permission or guesses screen coords.
"""
import json
from pathlib import Path
import re
import secrets
import subprocess
import time

from audio_capture_runtime import CaptureRuntime, BUNDLE
from audio_capture_permission import decide
from batch_media_recorder_challenge import generate
from guest_process_identity import producer_shell, identity_shell
from guest_ui import GuestUi, NodeNotReady, LayoutNotReady, select_node
from media_pipeline578 import nonce, SCENARIOS, sha, parse_journal, event

APP_FILES = '/data/app/el2/100/base/' + BUNDLE + '/files/'


def ui_plan(path):
    path = Path(path)
    if path.is_symlink() or not path.is_absolute() or not path.is_file():
        raise ValueError('actual packaged screen-picker selector input required; no SDK or guest fallback')
    value = json.loads(path.read_text())
    if set(value) != {'source_files', 'allow', 'deny', 'revoke'} or not value['source_files']:
        raise ValueError('actual screen-picker resource bytes and exact node selectors required')
    for entry in value['source_files']:
        if sha(entry['path']) != entry['sha256']:
            raise ValueError('screen-picker resource input changed')
    for action in ('allow', 'deny', 'revoke'):
        nodes = value[action]
        if not isinstance(nodes, list) or not 1 <= len(nodes) <= 4:
            raise ValueError('bounded actual system UI action sequence required')
        for node in nodes:
            is_swipe = set(node) == {'bundle', 'identifier', 'swipe_to'}
            values = {k: v for k, v in node.items() if k != 'swipe_to'}
            if (set(values) not in ({'bundle', 'text'}, {'bundle', 'identifier'}) or
                    any(not isinstance(x, str) or not x or len(x) > 256 for x in values.values()) or
                    node['bundle'] == BUNDLE):
                raise ValueError('exact packaged system control required; no caller consent button')
            if is_swipe:
                if (action != 'revoke' or values != {'bundle': 'com.ohos.systemui',
                        'identifier': 'systemui-statusbar-swipe'} or
                        node['swipe_to'] != {'bundle': BUNDLE, 'identifier': 'media578-canvas'}):
                    raise ValueError('only the real SystemUI drawer gesture toward this visible Canvas is allowed')
            elif set(node) != set(values):
                raise ValueError('unknown screen action fields')
    return value


class Media578Runtime(CaptureRuntime):
    def __init__(self, args, command, shell, report, run, boot_id):
        # Resolve mandatory unknown inputs before original prepare can run tools.
        self.scenario = args.media578_scenario
        if self.scenario not in SCENARIOS or report['persona'] != 'media-pipeline578':
            raise ValueError('explicit new ordinary media persona/scenario required')
        self.screen_plan = ui_plan(args.media578_screen_ui)
        super().__init__(args, command, shell, report, nonce(run), boot_id)
        if self.denied:
            raise ValueError('new screen-consent denial is distinct from microphone denial')
        self.value.update(kind='screen-transcode578', scenario=self.scenario, media578_runner_sha256=sha(Path(__file__)),
            screen_ui_plan={'path': str(Path(args.media578_screen_ui).resolve()), 'sha256': sha(args.media578_screen_ui)},
            screen_actions=[], canvas_observations=[], stable_outputs=[], death=None)
        self.save()

    def before_launch(self, uid):
        super().before_launch(uid)
        self.actual_shell('mkdir -p ' + APP_FILES + ' && chmod 0700 ' + APP_FILES +
            ' && chown ' + str(uid) + ':' + str(uid) + ' ' + APP_FILES,
            'prepare-only-own-media578-private-directory')

    def generate_challenge(self):
        generate(self.output / 'challenge', self.run)

    def permission(self):
        # Same actual binary/route/owned PID custody as CaptureRuntime. Reuse its
        # already-supported 60-repeat/90s producer wrapper for two picker cycles.
        self.producer_exit_marker = '__PCM_CHILD_EXIT_' + secrets.token_hex(16) + '__='
        self.producer_argv = [str(self.args.hdc), '-t', self.args.target, 'shell',
                             producer_shell(self.remote, self.producer_exit_marker, repeat=60, timeout_ms=90000)]
        self.producer_log = (self.output / 'producer.log').open('xb')
        self.process = subprocess.Popen(self.producer_argv, stdout=self.producer_log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic()+10
        while '"event":"feeding"' not in (self.output / 'producer.log').read_text(errors='replace'):
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise ValueError('original independent ALSA challenge did not start')
            time.sleep(.1)
        self.ui = GuestUi(self.command, self.args.hdc, self.args.target, self.output / 'screen-ui')
        self.value['permission_action'] = decide(self.ui, self.labels, False, min(self.args.wait_seconds, 120))
        deadline = time.monotonic()+10
        while self.token(self.uid, 'after-dialog') != 0 or self.last_token['before'] != 0:
            if time.monotonic() >= deadline:
                raise ValueError('real microphone UI/token grant did not commit')
            time.sleep(.1)
        actual_process = self.actual_shell(identity_shell(BUNDLE, all_uids=False), 'actual-media578-caller-generation')
        self.value['caller_process'] = {'raw': actual_process, 'shell_observation': len(self.value['guest_shell_observations'])-1}
        self.save()
        self.exercise()

    def journal(self):
        path = APP_FILES + 'media578-' + self.run + '-results.log'
        raw = self.actual_shell('test -f ' + path + ' && test ! -L ' + path + ' && cat ' + path,
                                'actual-media578-journal')
        # actual_shell strips only final newlines. A live fs.write can expose a
        # partial final row; retry that row, never discard earlier corruption.
        lines = raw.splitlines()
        if lines:
            try: json.loads(lines[-1])
            except json.JSONDecodeError: lines.pop()
        return [json.loads(line) for line in lines]

    def wait(self, predicate, label, seconds=35):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            rows = self.journal()
            if any(r.get('event') == 'failure' for r in rows):
                raise ValueError('actual ordinary media caller failed: ' + label)
            result = predicate(rows)
            if result: return rows
            time.sleep(.05)
        raise ValueError('actual media boundary timed out: ' + label)

    def system_action(self, name, cycle):
        for index, selector in enumerate(self.screen_plan[name]):
            deadline = time.monotonic()+15
            while True:
                try:
                    if 'swipe_to' in selector:
                        row = self.ui.swipe_down(**selector, label=f'screen-{name}-{cycle}-{index}')
                    else:
                        row = self.ui.click(**selector, label=f'screen-{name}-{cycle}-{index}')
                    break
                except (NodeNotReady, LayoutNotReady):
                    if time.monotonic() >= deadline: raise
                    time.sleep(.1)
            row.update(action=name, cycle=cycle, selector=selector, layout_sha256=sha(row['layout']),
                       ui_commands=list(range(len(self.parent['commands'])-3, len(self.parent['commands']))))
            self.value['screen_actions'].append(row); self.save()

    def canvas_observation(self, cycle):
        start = len(self.parent['commands'])
        layout, path = self.ui.layout(bundle=BUNDLE, label=f'actual-canvas-{cycle}')
        node = select_node(layout, BUNDLE, identifier='media578-canvas')
        screenshot = self.ui.screenshot(label=f'actual-compositor-{cycle}')
        from PIL import Image
        with Image.open(screenshot) as image: size = list(image.size)
        rect = node['rect']
        roi = [rect[0]/size[0], rect[1]/size[1], rect[2]/size[0], rect[3]/size[1]]
        self.value['canvas_observations'].append({'cycle': cycle, 'layout': str(path), 'layout_sha256': sha(path),
            'ui_commands': list(range(start, len(self.parent['commands']))), 'node': node, 'screenshot': str(screenshot), 'screenshot_sha256': sha(screenshot), 'display': size, 'roi': roi})
        self.save()

    def stable_output(self, name):
        if re.fullmatch('media578-' + self.run + r'-[12]-(?:capture|transcoded)\.mp4', name) is None:
            raise ValueError('only this run output may be observed')
        path = APP_FILES + name
        script = 'test -f ' + path + ' && test ! -L ' + path + ' && stat -c "%u %a %s" ' + path + ' && sha256sum ' + path + ' && cat /proc/uptime'
        observations = []
        for index in range(2):
            raw = self.actual_shell(script, 'actual-media-output-stable-' + str(index))
            observations.append({'script': script, 'raw': raw, 'shell_observation': len(self.value['guest_shell_observations'])-1})
            if index == 0: time.sleep(1.2)
        first, second = [o['raw'].splitlines() for o in observations]
        if (len(first) != 3 or len(second) != 3 or first[:2] != second[:2] or
                float(second[2].split()[0])-float(first[2].split()[0]) < 1):
            raise ValueError('actual media output continued changing or guest clock did not advance after terminal boundary')
        self.value['stable_outputs'].append({'name': name, 'observations': observations}); self.save()

    def exercise(self):
        cycles = 2 if self.scenario == 'screen-transcode' else 1
        for cycle in range(1, cycles+1):
            self.wait(lambda rows: any(r['cycle'] == cycle and r['event'] == 'screen.start.request' for r in rows), 'picker requested')
            self.system_action('deny' if self.scenario == 'screen-deny' else 'allow', cycle)
            if self.scenario == 'screen-deny': continue
            self.wait(lambda rows: any(r['cycle'] == cycle and r['event'] == 'screen.running' for r in rows), 'real screen started')
            self.canvas_observation(cycle)
            if self.scenario == 'screen-revoke':
                time.sleep(1.3)
                self.wait(lambda rows: any(r['event'] == 'owner.await-revoke' for r in rows), 'user revoke armed')
                self.system_action('revoke', cycle)
            elif self.scenario != 'screen-death':
                self.wait(lambda rows: any(r['cycle'] == cycle and r['event'] == 'owner.await-continue' for r in rows), 'canvas sampled')
                row = self.ui.click(BUNDLE, identifier='media578-continue', label=f'continue-actual-media-{cycle}')
                row.update(action='continue', cycle=cycle, selector={'bundle': BUNDLE, 'identifier': 'media578-continue'},
                           layout_sha256=sha(row['layout']),
                           ui_commands=list(range(len(self.parent['commands'])-3, len(self.parent['commands']))))
                self.value['screen_actions'].append(row); self.save()
        if self.scenario in ('screen-death', 'transcode-death'):
            rows = self.wait(lambda values: any(r['event'] == 'owner.await-death' for r in values), 'owned death armed')
            # Canonical helper already bounds the exact app UID/PID/starttime.
            before = self.actual_shell(identity_shell(BUNDLE, all_uids=False), 'actual-media-process-before-death')
            before_index = len(self.value['guest_shell_observations'])-1
            fields = before.split()
            if len(fields) != 3 or any(re.fullmatch('[1-9][0-9]*', f) is None for f in fields) or int(fields[2]) != self.uid:
                raise ValueError('actual ordinary media process identity differs')
            if int(fields[0]) != rows[0]['pid']:
                raise ValueError('death target is not the journal process')
            # Invoke the original ordinary-app stop/AA + /proc drain algorithm.
            # It never kills a media server or an unrelated PID.
            from run_normal_hap_probe import stop_previous_probe
            start = len(self.value['guest_shell_observations'])
            def owned_shell(script, label, **kwargs): return self.actual_shell(script, label)
            stopped = stop_previous_probe(owned_shell)
            self.value['death'] = {'before': before, 'before_observation': before_index,
                'stop': stopped, 'stop_shells': list(range(start, len(self.value['guest_shell_observations'])))}
            self.save()
            if self.scenario == 'transcode-death':
                self.stable_output(f'media578-{self.run}-1-capture.mp4')
            self.stable_output(f'media578-{self.run}-1-' + ('capture' if self.scenario == 'screen-death' else 'transcoded') + '.mp4')
        else:
            self.wait(lambda rows: bool(rows) and rows[-1]['event'] == 'summary', 'caller completed', seconds=60)
            for cycle in range(1, cycles+1):
                self.stable_output(f'media578-{self.run}-{cycle}-capture.mp4')
                if self.scenario in ('screen-transcode', 'transcode-cancel'):
                    self.stable_output(f'media578-{self.run}-{cycle}-transcoded.mp4')

    def result_text(self):
        path = APP_FILES + 'media578-' + self.run + '-results.log'
        raw = self.actual_shell('test -f ' + path + ' && test ! -L ' + path + ' && cat ' + path,
                                'final-actual-media578-journal') + '\n'
        parse_journal(raw, self.run, self.scenario, incomplete=self.scenario.endswith('-death'))
        return raw

    def collect(self, app_files):
        if app_files != APP_FILES: raise ValueError('original ordinary app private directory required')
        private = self.output / 'private'; private.mkdir(exist_ok=False)
        names = [f'media578-{self.run}-results.log']
        for cycle in range(1, 3 if self.scenario == 'screen-transcode' else 2):
            names.append(f'media578-{self.run}-{cycle}-capture.mp4')
            if self.scenario in ('screen-transcode', 'transcode-cancel', 'transcode-death'):
                names.append(f'media578-{self.run}-{cycle}-transcoded.mp4')
        for name in names:
            remote = APP_FILES+name
            script = 'test -f ' + remote + ' && test ! -L ' + remote + ' && stat -c "%u %a %s" ' + remote
            raw = self.actual_shell(script, 'actual-media578-file-custody')
            uid_text, mode_text, size_text = raw.split()
            uid, mode, size = int(uid_text), int(mode_text, 8), int(size_text)
            if uid != self.uid or mode & 0o007 or not 0 <= size <= 16*1024*1024:
                raise ValueError('actual ordinary media private file custody differs')
            local = private / name
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local], 'receive-actual-'+name)
            if local.stat().st_size != size: raise ValueError('actual media transfer truncated')
            self.value['files'][name] = {'path': str(local), 'sha256': sha(local), 'bytes': size,
                'remote': remote, 'uid': uid, 'mode': mode, 'stat_observation': len(self.value['guest_shell_observations'])-1}
        if self.token(self.uid, 'after-capture') != 0:
            raise ValueError('MIC permission unexpectedly changed')
        status = self.process.wait(timeout=95)
        self.producer_log.close(); self.producer_log = None
        self.value['producer'] = self.producer_receipt(status)
        if status != 0 or self.value['producer']['guest_exit_code'] != 0:
            raise ValueError('actual PCM source failed')
        self.value['status'] = 'captured_NOT_independently_verified'; self.save()
        return self.output / 'runtime.json'
