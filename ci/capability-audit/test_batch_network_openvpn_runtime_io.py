"""Host protocol/error propagation tests; synthetic bytes are never guest proof."""
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_network_openvpn_runtime_collect as collect
import batch_network_openvpn_runtime_project as project

BOOT = '11111111-2222-3333-4444-555555555555'
RUN = 'a' * 32
UID = 20010040
REMOTE = '/data/app/el2/100/base/' + project.BUNDLE + '/files/openvpn-' + RUN + '.jsonl'
DIRECTORY = str(Path(REMOTE).parent)


class JournalIOTests(unittest.TestCase):
    def shell_fixture(self, *, fault='', data='actual unit journal\n'):
        # Execute actual POSIX control flow with deliberately synthetic command
        # outputs. No /proc, device, SDK or real app state is created/read.
        calls = []
        definitions = '''
stat() {
  case "$2" in
    '%u:%F:%d:%i') printf '20010040:directory:1:2\\n';;
    '%u:%F:%h:%d:%i') printf '20010040:regular file:1:1:3\\n';;
    *) return 99;;
  esac
}
ls() { printf '.\\n..\\n'; case "$2" in */files) printf '%s\\n' NAME;; *) printf 'files\\n';; esac; }
cat() { printf '%s' DATA; }
'''.replace('NAME', shlex.quote(Path(REMOTE).name)).replace('DATA', shlex.quote(data))
        if fault == 'stat': definitions += 'stat() { printf "partial stat\\n"; return 7; }\n'
        if fault == 'list': definitions += 'ls() { printf ".\\n..\\n"; return 8; }\n'
        if fault == 'read': definitions += 'cat() { printf "partial app row"; return 9; }\n'
        if fault == 'alias': definitions += 'test() { return 1; }\n'
        if fault == 'file-alias': definitions += 'test() { if [ "$3" = ' + shlex.quote(REMOTE) + ' ]; then return 1; fi; command test "$@"; }\n'
        if fault == 'missing-files': definitions += 'ls() { printf ".\\n..\\n"; }\n'
        if fault == 'missing-journal': definitions += '''ls() { printf '.\\n..\\n'; case "$2" in */files) :;; *) printf 'files\\n';; esac; }\n'''
        if fault == 'wrong-owner': definitions += 'stat() { printf "0:directory:1:2\\n"; }\n'
        if fault in ('file-owner', 'file-hardlink', 'file-type'):
            file_meta = {'file-owner': '0:regular file:1:1:3', 'file-hardlink': '20010040:regular file:2:1:3',
                         'file-type': '20010040:symbolic link:1:1:3'}[fault]
            definitions += '''stat() { case "$2" in '%u:%F:%d:%i') printf '20010040:directory:1:2\\n';; *) printf '%s\\n' ''' + shlex.quote(file_meta) + ''';; esac; }\n'''
        if fault == 'changed':
            definitions += '''stat() { case "$2" in '%u:%F:%d:%i') printf '20010040:directory:1:2\\n';; *) printf '20010040:regular file:1:1:3\\n';; esac; }\n'''
        def shell(script, label):
            calls.append((script, label))
            raw = subprocess.run(['/bin/sh', '-c', definitions + script], capture_output=True, text=True)
            if raw.returncode: raise ValueError('actual unit shell command failed: ' + label + ':' + str(raw.returncode))
            text = raw.stdout
            if fault == 'changed' and label.endswith('-metadata-after'): text = text.replace(':1:3\n', ':1:4\n')
            if fault == 'truncated' and label.endswith('-directory'): text = text[:text.rfind('END|')]
            if fault == 'extra' and label.endswith('-directory'): text += 'foreign\n'
            if fault == 'wrong-nonce' and label.endswith('-directory'): text = text[:text.rfind('END|')] + 'END|' + 'f' * 32 + '\n'
            if fault == 'duplicate' and label.endswith('-directory'): text = text.replace('.\n..\n', '.\n..\n..\n')
            return text
        return shell, calls

    def test_actual_read_and_proved_absence_have_distinct_results(self):
        for fault, expected in (('', 'actual unit journal\n'), ('missing-files', None), ('missing-journal', None)):
            with self.subTest(fault=fault):
                shell, calls = self.shell_fixture(fault=fault)
                self.assertEqual(collect.read_app_journal(shell, REMOTE, UID, label='unit'), expected)
                self.assertTrue(calls)
                if expected is None: self.assertFalse(any(label.endswith('-read') for _, label in calls))

    def test_failed_queries_alias_or_partial_listing_never_mean_absent(self):
        for fault in ('stat', 'list', 'read', 'alias', 'file-alias', 'wrong-owner', 'file-owner',
                      'file-hardlink', 'file-type', 'changed', 'truncated', 'extra', 'wrong-nonce', 'duplicate'):
            with self.subTest(fault=fault):
                shell, _ = self.shell_fixture(fault=fault)
                with self.assertRaises(ValueError): collect.read_app_journal(shell, REMOTE, UID, label='unit')

    def test_scope_rejects_other_user_module_path_and_unsafe_filename(self):
        for remote, uid in ((REMOTE.replace('/100/', '/0/'), UID), (REMOTE, 0),
                            (REMOTE.replace('/files/', '/haps/entry/files/'), UID),
                            (REMOTE + '/../foreign', UID), (REMOTE.replace(project.BUNDLE, '..'), UID)):
            with self.subTest(remote=remote, uid=uid), self.assertRaises(ValueError):
                collect.read_app_journal(lambda *_: self.fail('out-of-scope IO'), remote, uid, label='unit')

    def caller(self, output=None):
        caller = object.__new__(collect.Collector)
        caller.data = {'run_id': RUN}; caller.identity = {'uid': UID, 'token': 123}
        caller.guest = SimpleNamespace(env={'boot_id': BOOT}, target='unit', report={'commands': []})
        caller.remote = REMOTE; caller.report = {'phases': [], 'cleanup_verified': False, 'failures': []}
        caller.save = lambda: None
        caller.shell = lambda value, label: 'start ability successfully.\n'
        caller.capture_api_failure = lambda request, error: caller.report.setdefault('captured_error', str(error))
        return caller

    def test_query_error_empty_file_and_timeout_preserve_request_and_fail_closed(self):
        for fault in ('query', 'empty-file', 'timeout'):
            with self.subTest(fault=fault):
                caller = self.caller()
                reader = patch.object(collect, 'read_app_journal', side_effect=ValueError('actual query failed')) if fault == 'query' else patch.object(
                    collect, 'read_app_journal', return_value='' if fault == 'empty-file' else None)
                with reader, patch.object(collect.time, 'monotonic', side_effect=[0, 21]):
                    with self.assertRaises(ValueError): caller.phase('inspect')
                self.assertEqual(caller.report['phases'], [])
                attempt = caller.report['phase_attempts'][0]
                self.assertEqual(attempt['request']['action'], 'inspect')
                self.assertEqual(attempt['status'], 'fail'); self.assertEqual(attempt['journal_polls'], 1)
                self.assertIn('captured_error', caller.report); self.assertFalse(caller.report['cleanup_verified'])

    def test_full_real_journal_protocol_remains_required(self):
        caller = self.caller()
        def read(shell, remote, uid, *, label):
            request = caller.report['phase_attempts'][0]['request']
            return ''.join(json.dumps(dict(schema_version=1, **request, sequence=index, uid=UID, pid=88,
                token_id=123, event=event, code=0, value=json.dumps({'config_undefined': True, 'apps': []})
                if event == 'getters' else '')) + '\n'
                for index, event in enumerate(('begin', 'permission', 'resolved', 'getters', 'complete'), 1))
        with patch.object(collect, 'read_app_journal', side_effect=read): caller.phase('inspect')
        self.assertEqual(len(caller.report['phases']), 1)
        self.assertEqual(caller.report['phase_attempts'][0]['status'], 'complete')
        self.assertNotIn('captured_error', caller.report)

    def test_unproved_diagnostic_cleanup_cannot_publish_cleanup_success(self):
        caller = self.caller(); caller.report['diagnostic_cleanup_verified'] = False
        caller.execute = lambda: (_ for _ in ()).throw(ValueError('original API failure'))
        caller.cleanup = lambda: caller.report.update(cleanup_verified=True)
        result = caller.run()
        self.assertFalse(result['cleanup_verified']); self.assertIn('original API failure', result['failures'])
        self.assertIn('guest must be disposed', result['failures'][-1])

    def test_cleanup_retry_requires_full_snapshot_and_retains_group_unknown_guards(self):
        first = {'directory': project.ROOT + '/session-Ab12Cd', 'worker': {'pid': 88}}
        for fault in ('', 'query', 'old-group', 'foreign-session', 'foreign-process'):
            with self.subTest(fault=fault):
                caller = self.caller()
                remaining = {'stats': {}, 'processes': {}, 'entries': ['backend.lock|metadata']}
                if fault == 'query': caller.snapshot = lambda label: (_ for _ in ()).throw(ValueError('actual snapshot query failed'))
                else:
                    if fault == 'old-group': remaining['stats'][89] = {'pgrp': 88}
                    if fault == 'foreign-session': remaining['entries'].append('session-Other1|metadata')
                    if fault == 'foreign-process': remaining['processes'][90] = {'exe': '/system/bin/qemu_openvpn', 'ppid': 2}
                    caller.snapshot = lambda label: remaining
                if not fault: self.assertIs(caller.wait_cleanup_retry(first), remaining)
                else:
                    with self.assertRaises(ValueError): caller.wait_cleanup_retry(first)

    def test_fault_absence_requires_readable_owned_parent_and_errors_preserve_reservation(self):
        for fault in ('absent', 'present', 'query'):
            with self.subTest(fault=fault):
                caller = self.caller(); calls = []
                original = caller.fault = project.ROOT + '/session-Ab12Cd/qa-' + RUN
                caller.shell = lambda script, label: calls.append((script, label)) or ''
                query = (patch.object(collect, '_journal_directory', side_effect=ValueError('actual parent query failed'))
                         if fault == 'query' else patch.object(collect, '_journal_directory',
                         return_value=['.', '..'] + ([Path(original).name] if fault == 'present' else [])))
                with query:
                    if fault == 'query':
                        with self.assertRaises(ValueError): caller.remove_fault()
                        self.assertEqual(caller.fault, original); self.assertEqual(calls, [])
                    else:
                        caller.remove_fault(); self.assertIsNone(caller.fault)
                        self.assertEqual(bool(calls), fault == 'present')
                        if calls:
                            self.assertNotIn('if test', calls[0][0]); self.assertIn('0:600:1', calls[0][0])

    def test_own_fault_is_never_removed_after_failed_stat_or_cat_with_valid_prefix(self):
        caller = self.caller(); caller.fault = project.ROOT + '/session-Ab12Cd/qa-' + RUN
        commands = []; caller.shell = lambda script, label: commands.append(script) or ''
        with patch.object(collect, '_journal_directory', return_value=['.', '..', Path(caller.fault).name]):
            caller.remove_fault()
        self.assertEqual(len(commands), 1)
        marker = 'openvpn-owned-' + RUN
        for fault in ('', 'stat-exit', 'cat-exit', 'extra-newline', 'wrong-marker', 'hardlink'):
            with self.subTest(fault=fault):
                size = len(marker) + (2 if fault == 'extra-newline' else 1)
                meta = f'0:600:{2 if fault == "hardlink" else 1}:{size}'
                text = ('X' + marker[1:] if fault == 'wrong-marker' else marker) + ('\n\n' if fault == 'extra-newline' else '\n')
                definitions = '''test() { case "$1" in -f|'!') return 0;; *) command test "$@";; esac; }
rm() { printf 'OWNED_REMOVED'; }
stat() { printf '%s\\n' META; return STAT_RC; }
cat() { printf '%s' CONTENT; return CAT_RC; }
'''.replace('META', shlex.quote(meta)).replace('STAT_RC', '1' if fault == 'stat-exit' else '0').replace(
                    'CONTENT', shlex.quote(text)).replace('CAT_RC', '1' if fault == 'cat-exit' else '0')
                result = subprocess.run(['/bin/sh', '-c', definitions + commands[0]], capture_output=True, text=True)
                if not fault:
                    self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout, 'OWNED_REMOVED')
                else:
                    self.assertNotEqual(result.returncode, 0); self.assertNotIn('OWNED_REMOVED', result.stdout)

    def test_cleanup_fixture_uses_app_IO_but_original_business_context(self):
        source = (project.FIX / 'EntryAbility.ets').read_text()
        page = (project.FIX / 'Index.ets').read_text()
        self.assertIn('this.context.getApplicationContext().filesDir', source)
        self.assertNotIn('this.context.filesDir', source)
        self.assertIn('vpn.createVpnConnection(this.context)', source)
        self.assertIn('this.chain = this.chain.then(() => this.call(request));', source)
        self.assertIn('this.chain.catch((error: BusinessError)', source)
        self.assertNotIn('this.chain = this.chain.catch', source)
        self.assertIn('the original chain stays rejected', source)
        self.assertIn("this.diagnostic.setOrCreate('diagnostic', 'Failed '", source)
        self.assertIn("stage.loadContent('pages/Index', this.diagnostic)", source)
        self.assertIn("@LocalStorageLink('diagnostic')", page)


class FailureDiagnosticsTests(unittest.TestCase):
    def test_same_boot_UI_raw_is_diagnostic_only_and_unknown_files_are_preserved(self):
        class UnitUi:
            def __init__(self, command, hdc, target, output):
                self.command = command; self.output = output; self.output.mkdir(); self.sequence = 0
            def layout(self, *, bundle, label):
                self.remote('.json'); self.command(['unit-never-executed'], label)
                path = self.output / 'actual-unit-layout.json'; path.write_text('{"unit":"not a guest"}')
                return {}, path
            def screenshot(self, *, label):
                self.remote('.png'); self.command(['unit-never-executed'], label)
                path = self.output / 'unit-not-a-real-screenshot.png'; path.write_bytes(b'unit fixture')
                return path
        for fault in ('', 'boot-changed', 'boot-changed-after-UI', 'unknown-file', 'UI-error'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                caller = object.__new__(collect.Collector)
                caller.args = SimpleNamespace(hdc='unit-never-executed'); caller.output = Path(temporary)
                caller.guest = SimpleNamespace(env={'boot_id': BOOT}, target='unit')
                caller.report = {'phases': [], 'cleanup_verified': False}; caller.save = lambda: None
                calls = []; changed = False
                def shell(script, label):
                    nonlocal changed
                    calls.append((script, label))
                    if fault == 'boot-changed-after-UI' and label.endswith('-tree-after'): changed = True
                    if changed: raise ValueError('owned guest kernel boot changed')
                    if 'boot' in label or label.endswith('-before') or label.endswith('-after'):
                        if fault == 'boot-changed': raise ValueError('owned guest kernel boot changed')
                        return BOOT + '\n'
                    if label.endswith('-directory-metadata'): return '0:700:directory:1:2\n'
                    if label.endswith('-cleanup-list'): return '.\n..\n1.json\n2.png\n' + ('foreign\n' if fault == 'unknown-file' else '')
                    if label.endswith('-cleanup-file-metadata'): return '0:regular file:1\n'
                    return ''
                caller.shell = shell
                def command(argv, label):
                    calls.append((argv, label))
                    if fault == 'UI-error': raise ValueError('actual UITest failure')
                    return ''
                caller.command = command
                with patch('guest_ui.GuestUi', UnitUi):
                    result = caller.capture_api_failure({'action': 'inspect'}, ValueError('original failure'))
                self.assertEqual(result['error'], 'original failure'); self.assertFalse(caller.report['cleanup_verified'])
                if fault in ('boot-changed', 'boot-changed-after-UI'):
                    self.assertNotIn('same_boot_verified', result)
                    if fault == 'boot-changed':
                        self.assertFalse(any(label.endswith('-create-owned-directory') for _, label in calls))
                else: self.assertTrue(result['same_boot_verified'])
                if fault in ('unknown-file', 'boot-changed-after-UI'):
                    self.assertFalse(result['remote_cleanup_verified'])
                    self.assertFalse(any(isinstance(script, str) and script.startswith(('rm ', 'rmdir ')) for script, _ in calls))
                else: self.assertTrue(result['remote_cleanup_verified'])
                if fault == 'UI-error': self.assertTrue(result['errors'])


if __name__ == '__main__': unittest.main()
