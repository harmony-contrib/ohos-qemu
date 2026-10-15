"""Synthetic replay rejection fixtures, never real screen/permission proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image
from build_screen_blink_probe import TEMPLATE, module, page
from run_root_probe import digest
from sign_screen_blink_probe import configure_profile
import test_screen_blink_results as result_fixtures
from verify_screen_blink_evidence import CONTRACTS, SCOPE, SYSTEM_SCOPE, plan, verify_evidence
from verify_screen_blink_results import verify_frames, verify_committed_stop

BOOT = '12345678-1234-1234-1234-123456789abc'
ARCHIVE = 'a' * 64
TARGET = '127.0.0.1:12345'


def fixture(root):
    doc = dict(status='pass', scope=SCOPE, boot_id=BOOT, archive_sha256=ARCHIVE, arch='arm64',
        device='phone', target=TARGET, udid='1' * 64, failures=[], cleanup_verified=True,
        first_artifact_behavior_gate_passed=False, roles={}, commands=[], wait_seconds=180,
        caller_cleanup=dict(bundle='org.harmonycontrib.capabilityaudit', kernel_process_absent=True,
            ability_process_records_absent=True, consecutive_absent_observations=2))
    def json_file(path, value):
        path.write_text(json.dumps(value)); return str(path), digest(path)
    def command(directory, argv, output, label='command'):
        path = directory / (str(len(doc['commands'])) + '-' + label + '.log'); path.write_text(output)
        doc['commands'].append(dict(argv=argv, exit_code=0, log=str(path), sha256=digest(path)))
    for number, role in enumerate(('normal', 'system-denied', 'system')):
        directory = root / role; directory.mkdir()
        nonce = str(number + 1) * 32
        uid = 20010001 if role == 'normal' else 20000001
        ident = dict(applicationInfo=dict(appPrivilegeLevel='normal' if role == 'normal' else 'system_core',
                                         isSystemApp=role != 'normal', uid=uid))
        identity_text = json.dumps(ident)
        generated = directory / 'Index.ets'; generated.write_text(page(nonce, role))
        sdk = directory / '@ohos.accessibility.config.d.ts'; sdk.write_text('// SYNTHETIC, NOT SDK')
        settings = directory / '@ohos.settings.d.ts'; settings.write_text('// SYNTHETIC, NOT SDK')
        record = dict(run_id=nonce, uid=uid, status='pass', cleanup_verified=True)
        inputs = directory / 'inputs.json'
        value = dict(schema_version=1, run_id=nonce, role=role, arch='arm64',
            scope='real_screen_window_calls_settings_and_permissions_NOT_full_behavior_gate',
            request_permissions=['ohos.permission.WRITE_ACCESSIBILITY_CONFIG',
                'ohos.permission.MANAGE_SECURE_SETTINGS'] if role == 'system' else [],
            template_sha256=digest(TEMPLATE), generated_source=str(generated), generated_source_sha256=digest(generated),
            sdk_declaration=str(sdk), sdk_declaration_sha256=digest(sdk),
            settings_declaration=str(settings), settings_declaration_sha256=digest(settings))
        for field, value in (('inputs', value), ('application_identity', ident)):
            record[field], record[field + '_sha256'] = json_file(directory / (field + '.json'), value)
        command(directory, ['python3', '/fixture/build_screen_blink_probe.py', '--role', role,
            '--arch', 'arm64', '--run-id', nonce, '--output', str(inputs.parent)], 'SYNTHETIC build fixture')
        for field in ('unsigned_hap', 'signed_hap'):
            path = directory / (field + '.hap')
            with zipfile.ZipFile(path, 'w') as hap:
                hap.writestr('module.json', json.dumps(module(role, compiled=True)))
            record[field] = str(path); record[field + '_sha256'] = digest(path)
        profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
                                    role, doc['udid'], module(role, compiled=True))
        receipt = dict(status='pass', scope='actual_signature_profile_and_codesign_NOT_guest', role=role,
            signed_sha256=record['signed_hap_sha256'], unsigned_sha256=record['unsigned_hap_sha256'],
            verified_profile=profile)
        record['signing_receipt'], record['signing_receipt_sha256'] = json_file(directory / 'signing.json', receipt)
        runtime = dict(status='pass', role=role, run_id=nonce, failures=[], cleanup_verified=True,
            first_artifact_behavior_gate_passed=False, phases=[], scope=SYSTEM_SCOPE if role == 'system' else
                'actual_calls_and_pixels_NOT_caller_death_or_competing_token_proof')
        rect, marker = [0, 30, 200, 200], [0, 0, 160, 20]
        def node(identifier, bounds='[0,0][20,20]'):
            return dict(attributes=dict(id=identifier, bundleName='org.harmonycontrib.capabilityaudit',
                visible='true', enabled='true', clickable='true', bounds=bounds), children=[])
        if role == 'system':
            surface = node('blink-pixel-surface', '[0,30][200,230]')
            surface['children'] = [node('blink-frame-marker', '[0,0][160,20]')]
            path, sha = json_file(directory / 'surface.json', surface)
            runtime.update(surface=dict(layout=path, sha256=sha, rect=rect), optical_marker=marker)
        observations = []
        generation = 0
        for phase_index, (name, kind, argument) in enumerate(plan() if role == 'system' else [('ready', 'ready', None)]):
            phase = dict(name=name)
            if kind in ('ready', 'results'):
                if kind == 'ready':
                    if generation != 0:
                        command(directory, ['hdc', '-t', TARGET, 'shell', 'aa force-stop org.harmonycontrib.capabilityaudit'],
                            'force stop process successfully.\n', 'blink-stop-own-process-with-active-window')
                        command(directory, ['hdc', '-t', TARGET, 'shell',
                            'if test -d /proc/123; then echo PRESENT; else echo ABSENT; fi'],
                            'ABSENT\n', 'blink-owner-exit')
                        command(directory, ['hdc', '-t', TARGET, 'shell',
                            'aa start -a EntryAbility -b org.harmonycontrib.capabilityaudit'],
                            'start ability successfully.\n', 'blink-restart-owned-caller')
                    rows = result_fixtures.BlinkResultTests().observations(role, restarted=generation != 0)
                    for row in rows: row['runId'] = nonce
                    rows[0]['values'] = [uid, uid, 123 + generation]
                    observations = rows; generation += 1
                else:
                    if name == 'cleanup.master':
                        observations.append(dict(runId=nonce, role=role, name='cleanup.stop',
                                                 values=[0, 0, 1], text=''))
                    observations.append(dict(runId=nonce, role=role, name=name, values=argument[0], text=argument[1]))
                path = directory / ('observations-' + str(phase_index) + '.jsonl')
                path.write_text(''.join(json.dumps(row) + '\n' for row in observations))
                phase.update(results=str(path), sha256=digest(path))
            elif kind == 'control':
                layout = node(argument)
                path, sha = json_file(directory / ('action-' + str(phase_index) + '.json'), layout)
                phase['selection'] = dict(layout=path, layout_sha256=sha, selected_node=dict(
                    attributes=layout['attributes'], bundle='org.harmonycontrib.capabilityaudit', rect=[0, 0, 20, 20]))
                control_previous_sequence = len(observations) % 256
                phase['selection']['observed_sequence_before'] = control_previous_sequence
                command(directory, ['hdc', '-t', TARGET, 'shell',
                    'uitest uiInput click 10 10; task_ui_rc=$?; printf "\\n__UITEST_EXIT_' + 'a' * 32 + '__=%s"'],
                    '__UITEST_EXIT_' + 'a' * 32 + '__=0\n')
            else:
                modes = ['on', 'off', 'on', 'off'] if argument == 'continuous' else (
                    ['off', 'on', 'off', 'off'] if argument == 'armed-single' else ['off'] * 3)
                frames = []
                for frame_index, mode in enumerate(modes):
                    path = directory / ('frame-' + str(phase_index) + '-' + str(frame_index) + '.png')
                    image = Image.new('RGB', (240, 300), (130, 140, 36) if mode == 'on' else (32, 48, 64))
                    if argument == 'bounded-committed-off':
                        for bit in range(8):
                            image.paste('white' if len(observations) & (1 << bit) else 'black',
                                        (bit * 20, 0, (bit + 1) * 20, 20))
                    image.save(path)
                    before = phase_index * 10 + frame_index
                    frames.append(dict(path=str(path), sha256=digest(path), before=before, after=before + .1))
                phase['frames'] = frames
                if kind == 'readiness':
                    # Explicit synthetic fixture metadata, never original native timing.
                    phase.update(started=frames[0]['before'], wait_seconds=180,
                                 deadline=frames[0]['before']+180)
                    for frame in frames: frame['kind'] = 'off'
                if kind == 'frames':
                    phase.update(rect=rect, mode=argument)
                    if argument == 'bounded-committed-off':
                        phase.update(marker=marker, started=phase_index * 10, expected_sequence=len(observations),
                                     previous_sequence=control_previous_sequence)
                        phase['commit'] = verify_committed_stop(frames, rect, marker, len(observations),
                            phase['started'], previous_sequence=control_previous_sequence)
                        phase['observed'] = phase['commit']['observed']
                    else: phase['observed'] = verify_frames(frames, rect, argument)
            runtime['phases'].append(phase)
        if role == 'system':
            baseline = directory / 'background.png'; Image.new('RGB', (240, 300), 'navy').save(baseline)
            frames = []
            for index in range(3):
                path = directory / ('exit-' + str(index) + '.png')
                Image.new('RGB', (240, 300), 'navy').save(path)
                frames.append(dict(path=str(path), sha256=digest(path), before=index, after=index + .1))
            runtime['caller_exit'] = dict(pid=123, restarted_pid=124,
                baseline=dict(path=str(baseline), sha256=digest(baseline)), frames=frames)
        record['runtime'], record['runtime_sha256'] = json_file(directory / 'runtime.json', runtime)
        doc['roles'][role] = record
    return doc


class ScreenBlinkEvidenceTests(unittest.TestCase):
    def verify(self, doc):
        return verify_evidence(doc, ARCHIVE, BOOT, 'arm64', 'phone', TARGET)

    def test_complete_role_phase_replay_and_tampered_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory)); self.assertEqual(self.verify(doc), CONTRACTS)
            for key, value in (('status', 'fail'), ('scope', 'exports'), ('boot_id', 'old'),
                ('archive_sha256', 'old'), ('arch', 'x86_64'), ('device', '2in1'), ('target', 'foreign'),
                ('cleanup_verified', False), ('first_artifact_behavior_gate_passed', True)):
                changed = copy.deepcopy(doc); changed[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError): self.verify(changed)
            for role in doc['roles']:
                changed = copy.deepcopy(doc); changed['roles'].pop(role)
                with self.assertRaises(ValueError): self.verify(changed)
            for field in ('inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt', 'runtime'):
                changed = copy.deepcopy(doc); changed['roles']['system'][field + '_sha256'] = '0' * 64
                with self.subTest(field=field), self.assertRaises(ValueError): self.verify(changed)
            changed = copy.deepcopy(doc); changed['commands'][-1]['exit_code'] = False
            with self.assertRaises(ValueError): self.verify(changed)

    def test_missing_foreign_false_native_pixels_and_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory)); record = doc['roles']['system']; path = Path(record['runtime'])
            original = json.loads(path.read_text())
            for change in ('missing', 'reorder', 'failed', 'marker', 'control-hash', 'control-node',
                           'pixels', 'stop-summary', 'same-pid', 'exit', 'bool-pid'):
                runtime = copy.deepcopy(original)
                if change == 'missing': runtime['phases'].pop()
                elif change == 'reorder': runtime['phases'][5:7] = reversed(runtime['phases'][5:7])
                elif change == 'failed': runtime['failures'] = ['failure']
                elif change == 'marker': runtime['optical_marker'][0] = 1
                elif change.startswith('control'):
                    phase = next(p for p in runtime['phases'] if 'selection' in p)
                    if change == 'control-hash': phase['selection']['layout_sha256'] = '0' * 64
                    else: phase['selection']['selected_node']['rect'][0] = 1
                elif change == 'pixels': next(p for p in runtime['phases'] if p['name'] == 'continuous')['observed'] = ['off'] * 4
                elif change == 'stop-summary': next(p for p in runtime['phases'] if p['name'] == 'stopped')['commit']['committed_index'] = 1
                elif change == 'same-pid': runtime['caller_exit']['restarted_pid'] = 123
                elif change == 'bool-pid': runtime['caller_exit']['pid'] = True
                else: runtime['caller_exit']['frames'].pop()
                path.write_text(json.dumps(runtime)); record['runtime_sha256'] = digest(path)
                with self.subTest(change=change), self.assertRaises(ValueError): self.verify(doc)
            path.write_text(json.dumps(original)); record['runtime_sha256'] = digest(path)
            doc['commands'] = [row for row in doc['commands'] if row['argv'][0] != 'hdc']
            with self.assertRaises(ValueError): self.verify(doc)

    def test_new_pid_or_background_alone_cannot_replace_kernel_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory)); self.verify(doc)
            owner = next(row for row in doc['commands'] if row['log'].endswith('-blink-owner-exit.log'))
            raw = Path(owner['log']); original = raw.read_text()
            for reply in ('PRESENT\n', '', 'ABSENT\nPRESENT\n'):
                raw.write_text(reply); owner['sha256'] = digest(raw)
                with self.subTest(reply=reply), self.assertRaises(ValueError): self.verify(doc)
            raw.write_text(original); owner['sha256'] = digest(raw)
            for label in ('blink-stop-own-process-with-active-window', 'blink-owner-exit', 'blink-restart-owned-caller'):
                changed = copy.deepcopy(doc)
                changed['commands'] = [row for row in changed['commands'] if not row['log'].endswith('-' + label + '.log')]
                with self.subTest(label=label), self.assertRaises(ValueError): self.verify(changed)

    def test_delivery_and_closure_replay_blink_and_luminance_not_outer_pass(self):
        root = Path(__file__).resolve().parents[2]
        gate = (root / 'scripts/verify_first_artifact_gate.py').read_text()
        closure = (root / 'ci/capability-audit/verify_gap_closure.py').read_text()
        runner = (root / 'ci/capability-audit/run_screen_blink_probe.py').read_text()
        self.assertIn('"screen-blink", "luminance-sampler"', gate)
        self.assertIn("elif name == 'screen-blink':", gate)
        self.assertIn("elif name == 'luminance-sampler':", gate)
        self.assertIn('from verify_screen_blink_evidence import verify_evidence', gate)
        self.assertIn("blink = child('screen-blink/evidence.json')", closure)
        self.assertIn("boot.get('purpose') != 'acceptance'", closure)
        self.assertIn("report['verified_contracts'] = verify_evidence", runner)


if __name__ == '__main__':
    unittest.main()
