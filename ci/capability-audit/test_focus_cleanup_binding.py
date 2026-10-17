"""Synthetic complete transport controls; never a real Focus runtime pass."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audio_capture_runtime import BOOT_SCRIPT
from media_capture_contract import BUNDLES
from run_audio_focus_probe import cleanup_owned_applications
from verify_audio_focus_results import verify_application_cleanup

BOOT = '12345678-1234-1234-1234-123456789abc'


class FocusCleanupBindingTests(unittest.TestCase):
    def fixture(self, root):
        commands = []
        def command(argv, label, **kwargs):
            raw = 'uninstall bundle successfully.\n'
            if argv[3] == 'shell':
                script = argv[4].split('; focus_rc=$?', 1)[0]
                if script == BOOT_SCRIPT: raw = BOOT + '\n'
                elif script.endswith(tuple('aa force-stop ' + b for b in BUNDLES)):
                    raw = 'force stop process successfully.\n'
                elif script.startswith('focus_pids='): raw = 'ABSENT\n'
                elif script == 'aa dump -a -u 100': raw = 'User ID #100\n  AppRunningRecords:\n'
                elif script == 'bm dump -a': raw = 'com.ohos.launcher\n'
                elif script.startswith('test ! -d '): raw = ''
                else: raise AssertionError(script)
                raw += '\n__FOCUS_EXIT_' + 'a' * 32 + '__=0\n'
            row = dict(argv=argv, label=label, exit_code=0, timed_out=False)
            for name, content in (('stdout', raw), ('stderr', '')):
                p = root / (str(len(commands)) + '-' + name); p.write_text(content)
                row[name + '_path'] = str(p); row[name + '_sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
            commands.append(row); return raw
        def shell(script, label, **kwargs):
            wrapped = script + '; focus_rc=$?; printf "\\n__FOCUS_EXIT_' + 'a' * 32 + '__=%s\\n" "$focus_rc"'
            text = command(['hdc', '-t', 'owned', 'shell', wrapped], label)
            return text.rsplit('\n__FOCUS_EXIT_', 1)[0].rstrip('\n')
        with patch('run_audio_focus_probe.time.sleep'):
            cleanup = cleanup_owned_applications(shell, command, 'hdc', 'owned', BOOT, commands=commands)
        return dict(boot_id=BOOT, target='owned', owned_application_cleanup=cleanup), dict(
            hdc={'argv0': 'hdc'}, orchestration_commands=commands)

    def test_exact_complete_two_bundle_transport_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            verify_application_cleanup(*self.fixture(Path(directory)))

    def test_summary_flags_cannot_hide_changed_boot_target_or_failed_uninstall(self):
        for change in ('incomplete', 'missing-uninstall', 'reused-index', 'wrong-target', 'false-raw', 'boot', 'truncated-footer'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                value, capture = self.fixture(Path(directory)); cleanup = value['owned_application_cleanup']
                if change == 'incomplete': cleanup['complete'] = False
                if change == 'missing-uninstall': cleanup['uninstalls'].pop()
                if change == 'reused-index': cleanup['uninstalls'][1]['command_index'] = cleanup['uninstalls'][0]['command_index']
                if change == 'wrong-target': capture['orchestration_commands'][0]['argv'][2] = 'other'
                if change == 'false-raw': cleanup['uninstalls'][0]['raw'] = 'claimed success'
                if change in ('boot', 'truncated-footer'):
                    observed = cleanup['observations'][0]; command = capture['orchestration_commands'][observed['command_index']]
                    path = Path(command['stdout_path']); text = path.read_text()
                    if change == 'boot':
                        text = text.replace(BOOT, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
                        observed['raw'] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
                    else: text = text[:-1]
                    path.write_text(text); command['stdout_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError): verify_application_cleanup(value, capture)


if __name__ == '__main__': unittest.main()
