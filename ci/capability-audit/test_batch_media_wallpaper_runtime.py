"""Light host oracle/protocol regressions; never actual guest acceptance."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from PIL import Image
import batch_media_wallpaper_runtime as runtime
import batch_media_verify_wallpaper_runtime as verifier

SPEC = importlib.util.spec_from_file_location('wallpaper_oracle_fixture', runtime.FIXTURE/'oracle_fixture.py')
fixture = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(fixture)


class RuntimeTests(unittest.TestCase):
    def test_only_exact_uitest_window_enumeration_retry_is_allowed(self):
        marker = '__UITEST_EXIT_' + 'a' * 32 + '__='
        remote = '/data/local/tmp/qemu-capability-ui-' + 'b' * 32 + '-7.json'
        script = 'test ! -e ' + remote + ' && uitest dumpLayout -p ' + remote + ' -b com.ohos.settings'
        tail = '; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"'
        argv = ['hdc', '-t', '127.0.0.1:1234', 'shell', script + tail]
        raw = 'DumpLayout failed:Get window nodes failed\n\n' + marker + '1\n'
        self.assertTrue(verifier.layout_transition_unavailable(argv, raw))
        for output in (raw.replace('failed:Get', 'failed:Other'), raw.replace(marker, marker + marker),
                       raw.replace(marker, '__UITEST_EXIT_' + 'c' * 32 + '__='),
                       raw.replace(marker + '1', marker + '2'), '[Fail] transport disconnected\n' + raw):
            self.assertFalse(verifier.layout_transition_unavailable(argv, output))
        for command in (script.replace(remote, '/data/local/tmp/foreign.json') + tail,
                        'uitest uiInput click 1 1' + tail, script + ' && rm -f ' + remote + tail):
            self.assertFalse(verifier.layout_transition_unavailable(argv[:4] + [command], raw))

    def test_template_from_another_snapshot_requires_exact_trusted_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            challenge = json.loads(runtime.prepare(root / 'challenge', 360, 640).read_text())
            copied = root / 'other-frozen-snapshot/Index.ets';copied.parent.mkdir()
            copied.write_bytes(runtime.FIXTURE.joinpath('Index.ets').read_bytes())
            challenge['template'] = {'path': str(copied.resolve()), 'sha256': verifier.sha(copied)}
            verifier.check_challenge(challenge)
            copied.write_bytes(copied.read_bytes() + b'\n// changed template\n')
            challenge['template']['sha256'] = verifier.sha(copied)
            with self.assertRaisesRegex(ValueError, 'original seed/denial source'):
                verifier.check_challenge(challenge)

    def test_actual_API26_caller_declarations(self):
        sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        typescript = sdk/'ets/build-tools/ets-loader/node_modules/typescript'
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(['node', str(runtime.FIXTURE/'sdk-types.cjs'),
                str(runtime.FIXTURE/'Index.ets'), str(typescript), temp, str(sdk/'ets/api')],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout+result.stderr)

    def test_complete_host_oracle_and_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            case = fixture.Fixture(temp)
            self.assertEqual('pass', verifier.verify(case.path)['status'])
            copied_runner = Path(temp) / 'other-frozen-runner.py'
            copied_runner.write_bytes(runtime.HERE.joinpath('batch_media_wallpaper_runtime.py').read_bytes())
            case.value['runner'] = {'path': str(copied_runner.resolve()), 'sha256': verifier.sha(copied_runner)}
            case.save()
            self.assertEqual('pass', verifier.verify(case.path)['status'])
            copied_runner.write_bytes(copied_runner.read_bytes() + b'\n# changed runner\n')
            case.value['runner']['sha256'] = verifier.sha(copied_runner);case.save()
            with self.assertRaisesRegex(ValueError, 'original runner evidence'):verifier.verify(case.path)
            case.value['runner'] = {'path': str(runtime.HERE / 'batch_media_wallpaper_runtime.py'),
                                    'sha256': verifier.sha(runtime.HERE / 'batch_media_wallpaper_runtime.py')}
            case.save()
            mutations = [
                ('old boot', lambda v: v.update(boot_id='22222222-2222-2222-2222-222222222222')),
                ('no remote commands', lambda v: v.update(commands=[])),
                ('runner self pass', lambda v: v.update(status='pass')),
                ('missing snapshot', lambda v: v['stages'].pop(1)),
                ('reordered snapshots', lambda v: v['stages'].reverse()),
                ('no root action', lambda v: v.update(actions=[])),
                ('omitted challenge', lambda v: v['private_PNGs'].pop('lock-2')),
                ('cached screenshot', lambda v: v['stages'][2].update(screenshot=case.challenge['images']['desktop-1'])),
                ('wrong lock pixels', lambda v: v['stages'][4].update(screenshot=case.challenge['images']['desktop-2'])),
                ('missing explicit Apply', lambda v: v['ui_actions'].pop(2)),
                ('no real lock layer', lambda v: v['stages'][4].update(layout=v['stages'][2]['layout'])),
                ('missing cancellation observation', lambda v: v.pop('picker_cancel_observation')),
                ('missing token query', lambda v: v.pop('denied_observation')),
                ('missing defaults', lambda v: v.pop('default_resolution')),
                ('missing actual cleanup', lambda v: v.pop('cleanup_observation')),
                ('no Back return', lambda v: v.pop('back_return_layout')),
            ]
            original = case.clone()
            for label, mutate in mutations:
                with self.subTest(label=label):
                    case.value = copy.deepcopy(original); mutate(case.value); case.save()
                    with self.assertRaises((ValueError, KeyError, TypeError)):
                        verifier.verify(case.path)
            case.value = original
            # Recompute receipts after a corrupt/cancel write: hash consistency
            # alone is insufficient, actual no-write invariant must reject it.
            stage = case.value['stages'][6]
            stage['files'][verifier.PATHS['desktop']] = case.transfer(verifier.PATHS['desktop'],
                Path(case.challenge['images']['cancel']['path']).read_bytes())
            case.save()
            with self.assertRaisesRegex(ValueError, 'cancel/back/ordinary denial'):
                verifier.verify(case.path)

    def test_pixels_reject_flat_stale_and_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            challenge = json.loads(runtime.prepare(Path(temp)/'challenge', 360, 640).read_text())
            source = challenge['images']['desktop-1']['path']
            image = Image.open(source)
            jpeg = Path(temp)/'jpeg.jpg'; image.save(jpeg, quality=90)
            self.assertGreater(verifier.pixels(jpeg, source)['fraction'], 0.95)
            flat = Path(temp)/'flat.png'; Image.new('RGB', image.size, 'gray').save(flat)
            with self.assertRaises(ValueError): verifier.pixels(flat, source)
            with self.assertRaises(ValueError): verifier.pixels(challenge['images']['desktop-2']['path'], source)
            preview = Image.new('RGB', image.size, 'gray'); preview.paste(image.resize((120, 210)), (120, 200))
            path = Path(temp)/'preview.png'; preview.save(path)
            with self.assertRaises(ValueError): verifier.pixels(path, source)
            wrong = fixture.node('com.attacker', kind='Image')
            with self.assertRaises(verifier.NodeNotReady): verifier.thumbnail(wrong, source, source)

    def test_stat_transfer_boundaries(self):
        digest = 'a'*64; remote = verifier.PATHS['desktop']
        good = '1000 1000 600 123 10 1\n'+digest+'  '+remote+'\n'
        self.assertEqual(123, verifier.parse_remote_stat(good, remote)['size'])
        for raw in [good.replace(' 600 ', ' 666 '), good.replace(' 123 ', ' 0 '),
                    good.replace(' 123 ', ' 33554433 '), good.replace(remote, remote+'-old'), good+good]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError): verifier.parse_remote_stat(raw, remote)

    def test_seed_errors_never_become_success(self):
        with tempfile.TemporaryDirectory() as temp:
            case = fixture.Fixture(temp); rows = case.rows
            verifier.seed_rows(case.lines(), case.run, denial=True)
            original = copy.deepcopy(rows)
            for change in ('zero-error', 'unexpected-success', 'old-nonce', 'duplicate-uri', 'missing-call'):
                case.rows = copy.deepcopy(original)
                if change == 'zero-error':
                    detail = json.loads(case.rows[11]['detail']); detail['code'] = 0; case.rows[11]['detail'] = json.dumps(detail)
                elif change == 'unexpected-success': case.rows[11]['name'] = 'denied.unexpected-success'
                elif change == 'old-nonce': case.rows[0]['runId'] = '0'*32
                elif change == 'duplicate-uri': case.rows[3]['detail'] = case.rows[1]['detail']
                else: case.rows.pop()
                with self.subTest(change=change):
                    with self.assertRaises(ValueError): verifier.seed_rows(case.lines(), case.run, denial=True)

    def test_ack_security_timeout_and_real_fresh_reply(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            request = {'schema_version': 1, 'run_id': 'a'*32, 'boot_id': '1'*36,
                       'sequence': 1, 'nonce': 'b'*32, 'action': 'show-real-lock', 'details': {}}
            stem = request['run_id']+'-001-'+request['nonce']
            clock = iter([0.0, 0.1, 0.2, 2.0])
            with self.assertRaisesRegex(ValueError, 'timed out'):
                runtime.wait_ack(path, request, timeout=1, clock=lambda: next(clock), sleep=lambda _: None)
            with self.assertRaises(FileExistsError): runtime.wait_ack(path, request)
        for mode, stale, linked in [(0o644, False, False), (0o600, True, False), (0o600, False, True), (0o600, False, False)]:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp); reply = path/(stem+'.ack.json')
                def respond(_):
                    value = {k: request[k] for k in ('schema_version', 'run_id', 'boot_id', 'sequence', 'nonce', 'action')}
                    if stale: value['nonce'] = 'c'*32
                    target = path/'target' if linked else reply
                    target.write_text(json.dumps(value)); target.chmod(mode)
                    if linked: reply.symlink_to(target)
                if mode == 0o600 and not stale and not linked:
                    self.assertEqual(2, len(runtime.wait_ack(path, request, sleep=respond)))
                else:
                    with self.assertRaises((ValueError, OSError)): runtime.wait_ack(path, request, sleep=respond)


if __name__ == '__main__': unittest.main()
