"""Trusted owner callback boundary regressions with isolated mocks; no resources."""
import ast
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(source, name, *, parent=None):
    tree = ast.parse(source)
    body = tree.body
    if parent:
        body = next(n for n in body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == parent).body
    return next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)


class SuiteOwnerCallbacks(unittest.TestCase):
    def test_failed_start_does_not_close_the_same_guest_twice(self):
        source = (ROOT / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        tree = ast.Module(body=[function(source, 'run')], type_ignores=[])
        for factory in (False, True):
            with self.subTest(factory=factory), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary).resolve()
                class FailedGuest:
                    closes = 0
                    def __init__(self, args):
                        pass
                    def close(self):
                        type(self).closes += 1
                    def start(self):
                        self.close()  # Real QemuGuest.start settles failed startup.
                        raise ValueError('MOCK failed startup already settled')
                namespace = dict(argparse=argparse, Path=Path, tempfile=tempfile,
                    datetime=datetime, timezone=timezone, json=json, os=os,
                    subprocess=subprocess, shutil=Mock(which=Mock(return_value='/mock/hdc')),
                    test_sdk=lambda: directory, unused_port=lambda: 45678,
                    QemuGuest=FailedGuest, checksum=digest)
                exec(compile(ast.fix_missing_locations(tree), 'failed-start-MOCK', 'exec'), namespace)
                args = SimpleNamespace(package_archive=directory / 'mock.tar.gz',
                    package_directory=None, evidence_output=directory / 'report.json')
                callback = (lambda boot: FailedGuest(boot)) if factory else None
                with patch.dict(os.environ, QEMU_TEST_CLOCK_PROBE='/mock/clock',
                                QEMU_TEST_CLOCK_PROBE_BUILD='/mock/clock-build'):
                    result = namespace['run'](args, owned_guest_factory=callback)
                self.assertEqual(FailedGuest.closes, 1)
                self.assertEqual(result['status'], 'fail')
                self.assertFalse(result['first_artifact_behavior_gate_passed'])
                self.assertEqual(result['failures'], ['MOCK failed startup already settled'])

    def suite_command(self, directory, callback):
        source=(ROOT/'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        tree=ast.Module(body=[function(source,'command',parent='run')],type_ignores=[])
        namespace=dict(owned_command=callback, report={'commands':[]}, work=directory, checksum=digest,
                       subprocess=Mock(Popen=Mock(side_effect=AssertionError('unowned fallback'))))
        exec(compile(ast.fix_missing_locations(tree),'suite-command-MOCK','exec'),namespace)
        return namespace


    def test_suite_callback_exact_argv_exit_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp).resolve()
            def callback(argv,*,label,timeout,env,log):
                log.write_text('MOCK actual raw\n')
                return dict(argv=argv,exit_code=0,log=str(log),sha256=digest(log))
            ns=self.suite_command(directory,callback)
            row=ns['command'](['python','fixed.py'],'mock')
            self.assertEqual(row['argv'],['python','fixed.py'])
            self.assertEqual(ns['report']['commands'],[row])
            ns['subprocess'].Popen.assert_not_called()


    def test_legacy_suite_command_uses_original_popen_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            ns=self.suite_command(Path(tmp).resolve(),None)
            process=Mock(returncode=0)
            ns['subprocess'].Popen=Mock(return_value=process)
            ns['subprocess'].DEVNULL=subprocess.DEVNULL
            ns['subprocess'].STDOUT=subprocess.STDOUT
            row=ns['command'](['legacy-fixed'],'mock')
            process.wait.assert_called_once_with(timeout=600)
            self.assertEqual(row['exit_code'],0)
            call=ns['subprocess'].Popen.call_args
            self.assertEqual(call.args,(['legacy-fixed'],))
            self.assertEqual(set(call.kwargs),{'stdout','stderr','stdin','start_new_session','env'})
            self.assertIs(call.kwargs['start_new_session'],True)


    def test_legacy_guest_command_uses_original_run_contract(self):
        source=(ROOT/'ci/capability-audit/boot_package.py').read_text()
        tree=ast.Module(body=[function(source,'command',parent='QemuGuest')],type_ignores=[])
        process=Mock(stdout='MOCK old stdout\n',stderr='',returncode=0)
        sub=Mock(run=Mock(return_value=process),PIPE=subprocess.PIPE,DEVNULL=subprocess.DEVNULL)
        ns=dict(checksum=digest,hdc_failed=lambda a,b:False,subprocess=sub)
        exec(compile(ast.fix_missing_locations(tree),'legacy-guest-MOCK','exec'),ns)
        with tempfile.TemporaryDirectory() as tmp:
            guest=SimpleNamespace(_owned_command=None,args=SimpleNamespace(output=Path(tmp).resolve(),hdc='/fixed/hdc'),report={'commands':[]})
            self.assertEqual(ns['command'](guest,['/fixed/hdc','start'],'mock'),'MOCK old stdout\n')
            self.assertEqual(sub.run.call_args.kwargs,dict(stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,stdin=subprocess.DEVNULL,timeout=30,check=False))


    def test_suite_callback_cannot_swap_log_or_return_bool_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp).resolve()
            def callback(argv,*,label,timeout,env,log):
                log.write_text('MOCK')
                return dict(argv=argv,exit_code=True,log=str(log),sha256=digest(log))
            ns=self.suite_command(directory,callback)
            with self.assertRaises(ValueError): ns['command'](['fixed'],'mock')


    def test_guest_callback_nonzero_and_hdc_errors_are_retained(self):
        source=(ROOT/'ci/capability-audit/boot_package.py').read_text()
        tree=ast.Module(body=[function(source,'command',parent='QemuGuest')],type_ignores=[])
        ns=dict(checksum=digest,hdc_failed=lambda a,b:'[Fail]' in a+b)
        exec(compile(ast.fix_missing_locations(tree),'guest-command-MOCK','exec'),ns)
        with tempfile.TemporaryDirectory() as tmp:
            guest=SimpleNamespace(args=SimpleNamespace(output=Path(tmp).resolve(),hdc='/fixed/hdc'),report={'commands':[]})
            def callback(g,argv,*,label,timeout,log):
                log.write_text('[Fail] MOCK transport\n')
                return dict(argv=argv,exit_code=0,log=str(log),sha256=digest(log)), '[Fail] MOCK transport\n',''
            guest._owned_command=callback
            with self.assertRaises(ValueError): ns['command'](guest,['/fixed/hdc','start'],'mock')
            self.assertEqual(guest.report['commands'][0]['exit_code'],0)
            self.assertIn('[Fail]',Path(guest.report['commands'][0]['log']).read_text())


    def test_guest_callback_preserves_exact_crlf_for_allowed_connection_failure(self):
        source=(ROOT/'ci/capability-audit/boot_package.py').read_text()
        tree=ast.Module(body=[function(source,'command',parent='QemuGuest')],type_ignores=[])
        ns=dict(checksum=digest,hdc_failed=lambda a,b:'[Fail]' in a+b)
        exec(compile(ast.fix_missing_locations(tree),'guest-command-CRLF','exec'),ns)
        with tempfile.TemporaryDirectory() as tmp:
            guest=SimpleNamespace(args=SimpleNamespace(output=Path(tmp).resolve(),hdc='/fixed/hdc'),report={'commands':[]})
            stdout='[Fail]Connect failed\r\n'; stderr='transport pending\r\n'
            def callback(g,argv,*,label,timeout,log):
                log.write_bytes((stdout+stderr).encode('utf-8'))
                return dict(argv=argv,exit_code=0,log=str(log),sha256=digest(log)),stdout,stderr
            guest._owned_command=callback
            self.assertEqual(ns['command'](guest,['/fixed/hdc','tconn','127.0.0.1:45678'],'connect',allow_failure=True),stdout.replace('\r',''))
            row=guest.report['commands'][0]
            self.assertEqual(row['exit_code'],0)
            self.assertEqual(Path(row['log']).read_bytes(),(stdout+stderr).encode('utf-8'))
            with self.assertRaisesRegex(ValueError,'HDC transport/operation failed'):
                ns['command'](guest,['/fixed/hdc','tconn','127.0.0.1:45678'],'connect-strict')

    def test_guest_callback_rejects_line_ending_tampering(self):
        source=(ROOT/'ci/capability-audit/boot_package.py').read_text()
        tree=ast.Module(body=[function(source,'command',parent='QemuGuest')],type_ignores=[])
        ns=dict(checksum=digest,hdc_failed=lambda a,b:False)
        exec(compile(ast.fix_missing_locations(tree),'guest-command-raw-mismatch','exec'),ns)
        for output,returned in ((b'raw\r\n','raw\n'),(b'raw\n','raw\r\n')):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as tmp:
                guest=SimpleNamespace(args=SimpleNamespace(output=Path(tmp).resolve(),hdc='/fixed/hdc'),report={'commands':[]})
                def callback(g,argv,*,label,timeout,log):
                    log.write_bytes(output)
                    return dict(argv=argv,exit_code=0,log=str(log),sha256=digest(log)),returned,''
                guest._owned_command=callback
                with self.assertRaisesRegex(ValueError,'exact actual argv/raw/exit'):
                    ns['command'](guest,['/fixed/hdc','start'],'raw-mismatch')


if __name__ == '__main__':
    unittest.main()
