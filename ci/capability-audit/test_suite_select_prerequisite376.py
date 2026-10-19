"""Real suite/probe source slices, synthetic files only; no guest/signing/SDK."""
import ast
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]


def need(value, text):
    if not value:
        raise ValueError(text)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(path, name):
    return next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)


def literal(path, name):
    return ast.literal_eval(next(n.value for n in ast.parse(path.read_text()).body if isinstance(n, ast.Assign) and
        any(isinstance(t, ast.Name) and t.id == name for t in n.targets)))


class PrerequisiteBoundary(unittest.TestCase):
    def world(self, *, failed=(), cleanup=True, missing_cleanup=False, timed_out=False,
              no_plan=False, dead_at=None, hook_error=None, erase_failures=False, existing_defer=False):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        work = Path(tmp.name).resolve(); (work / 'boot').mkdir()
        boot = work / 'boot/boot.json'; boot.write_text('{"scope":"SYNTHETIC"}')
        families = literal(ROOT / 'ci/capability-audit/parallel_runtime_suite.py', 'FAMILIES')
        source = ROOT / 'ci/capability-audit/run_packaged_qemu_suite.py'
        run = function(source, 'run')
        outer = next(n for n in run.body if isinstance(n, ast.Try))
        start = next(i for i,n in enumerate(outer.body) if isinstance(n, ast.ImportFrom) and n.module == 'parallel_runtime_suite')
        end = next(i for i,n in enumerate(outer.body) if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'native_definitions' for t in n.targets))
        body = copy.deepcopy(outer.body[start+1:end])
        check = copy.deepcopy(next(n for n in run.body if isinstance(n, ast.FunctionDef) and n.name == 'check'))
        fragment = ast.parse('def fragment():\n pass\n').body[0]
        fragment.body = body + [ast.parse('later()').body[0], ast.parse('return report').body[0]]
        policy = function(ROOT/'ci/capability-audit/batch_probe_policy.py', 'independent_probe')
        report = dict(status='fail', first_artifact_behavior_gate_passed=False, checks={}, commands=[], failures=[],
                      package={'sha256':'a'*64})
        health_calls=[]
        def same_guest(label):
            health_calls.append(label)
            if label == dead_at:raise ValueError('SYNTHETIC dead actual guest')
            if erase_failures and label == 'before-owned-select375':report['failures'].clear()
        def command(argv, label, **kwargs):
            name = argv[0]
            output = work / name; output.mkdir()
            if not missing_cleanup:
                (output/'evidence.json').write_text(json.dumps(dict(status='fail' if name in failed else 'pass',
                    cleanup_complete=cleanup, cleanup_errors=[] if cleanup else ['SYNTHETIC unsafe'],
                    boot_id='SYNTHETIC-boot', archive_sha256='a'*64)))
            row=dict(argv=argv,exit_code=1 if name in failed else 0,timed_out=timed_out)
            report['commands'].append(row)
            if name in failed:raise ValueError('SYNTHETIC producer failed')
            return row
        def boot_copy(src, dst):
            dst.write_bytes(src.read_bytes()); return dst
        family_replay=Mock()
        def invoke(**context):
            # Interface double for the unchanged private Stage precondition.
            # The test itself depends only on portable canonical suite sources.
            for name in families:
                need(report['checks'].get(name,{}).get('status') == 'pass', 'SYNTHETIC Stage requires four passed families')
                family_replay(name)
            if hook_error:raise ValueError(hook_error)
        hook=Mock(side_effect=invoke); later=Mock()
        ns=dict(report=report,work=work,environment={'boot_id':'SYNTHETIC-boot'},
            args=SimpleNamespace(package_archive=work/'SYNTHETIC-archive',evidence_output=work/'suite.json'),
            hdc='/SYNTHETIC/hdc',guest=SimpleNamespace(save=Mock()),owned_select_hook=hook,
            save=Mock(),same_guest=same_guest,checksum=sha,json=json,contextmanager=contextmanager,subprocess=subprocess,
            Path=Path,os=SimpleNamespace(environ={'QEMU_TEST_CAPABILITY_INPUTS':'/SYNTHETIC/plan'}),
            representative=lambda _:True,FAMILIES=families,TIMEOUTS={x:1 for x in families},load_plan=Mock(),
            boot_copy=boot_copy,capability_argv=lambda name,*a:[name],command=command,verify_family=Mock(),later=later)
        if no_plan:ns['load_plan'].side_effect=ValueError('SYNTHETIC missing plan')
        if existing_defer:(work/'select375-not-run.json').write_text('SYNTHETIC preexisting')
        exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(policy),check,fragment],type_ignores=[])),str(source),'exec'),ns)
        return SimpleNamespace(run=ns['fragment'],report=report,work=work,hook=hook,later=later,
                               health=health_calls,family_replay=family_replay,namespace=ns)

    def test_all_pass_calls_original_stage_once(self):
        w=self.world();w.run();w.hook.assert_called_once();w.later.assert_called_once()
        self.assertEqual(w.family_replay.call_count,4)
        self.assertFalse((w.work/'select375-not-run.json').exists())

    def test_each_safely_failed_family_defers_without_stage_dispatch(self):
        families=literal(ROOT/'ci/capability-audit/parallel_runtime_suite.py','FAMILIES')
        for name in families:
            with self.subTest(family=name):
                w=self.world(failed=(name,));w.run();w.hook.assert_not_called();w.later.assert_called_once()
                p=w.work/'select375-not-run.json';v=json.loads(p.read_text())
                self.assertEqual(v['failed_families'],[name]);self.assertFalse(v['dispatched'])
                self.assertEqual(v['original_failures'],w.report['failures']);self.assertTrue(w.report['failures'])
                self.assertFalse(w.report['first_artifact_behavior_gate_passed']);self.assertEqual(w.report['status'],'fail')
                self.assertEqual(v['completed_original_family_probes'],list(families))
                self.assertEqual(w.report['supplemental_checks']['select375']['sha256'],sha(p))
                self.assertEqual([x for x in w.health if x.startswith('after-')],['after-'+n for n in families]+['after-owned-select375'])

    def test_failed_plan_no_child_still_requires_all_actual_health_returns(self):
        w=self.world(no_plan=True);w.run();w.hook.assert_not_called();w.later.assert_called_once()
        self.assertEqual(w.report['commands'],[]);self.assertEqual(len(w.report['failures']),4)
        self.assertTrue(all(row['status']=='fail' for row in w.report['independent_probes'].values()))

    def test_unknown_cleanup_aborts_without_deferral_or_later_case(self):
        w=self.world(failed=('contacts-picker',),cleanup=False)
        with self.assertRaisesRegex(ValueError,'cleanup failed'):w.run()
        w.hook.assert_not_called();w.later.assert_not_called()
        self.assertFalse((w.work/'select375-not-run.json').exists())

    def test_missing_child_cleanup_evidence_aborts(self):
        w=self.world(failed=('contacts-picker',),missing_cleanup=True)
        with self.assertRaisesRegex(ValueError,'cleanup evidence missing'):w.run()
        w.hook.assert_not_called();w.later.assert_not_called()

    def test_timed_out_child_aborts_even_with_cleanup_boolean(self):
        w=self.world(failed=('contacts-picker',),timed_out=True)
        with self.assertRaisesRegex(ValueError,'timed-out'):w.run()
        w.hook.assert_not_called();w.later.assert_not_called()

    def test_dead_guest_at_predispatch_aborts(self):
        w=self.world(failed=('contacts-picker',),dead_at='before-owned-select375')
        with self.assertRaisesRegex(ValueError,'dead actual guest'):w.run()
        w.hook.assert_not_called();w.later.assert_not_called()
        self.assertFalse((w.work/'select375-not-run.json').exists())

    def test_actual_stage_failure_after_dispatch_is_fatal(self):
        for error in ('SYNTHETIC actual UI failed with cleaned apps','SYNTHETIC unknown actual cleanup'):
            with self.subTest(error=error):
                w=self.world(hook_error=error)
                with self.assertRaisesRegex(ValueError,error):w.run()
                w.hook.assert_called_once();w.later.assert_not_called()
                self.assertFalse((w.work/'select375-not-run.json').exists())

    def test_original_failure_must_not_be_erased(self):
        w=self.world(failed=('contacts-picker',),erase_failures=True)
        with self.assertRaisesRegex(ValueError,'lacks original completed'):w.run()
        w.hook.assert_not_called();w.later.assert_not_called()

    def test_existing_deferral_file_is_never_overwritten(self):
        w=self.world(failed=('contacts-picker',),existing_defer=True)
        with self.assertRaises(FileExistsError):w.run()
        w.hook.assert_not_called();w.later.assert_not_called()
        self.assertEqual((w.work/'select375-not-run.json').read_text(),'SYNTHETIC preexisting')

    def test_legacy_no_hook_continues_original_independent_failures(self):
        w=self.world(failed=('contacts-picker',));w.namespace['owned_select_hook']=None
        w.run();w.hook.assert_not_called();w.later.assert_called_once()
        self.assertTrue(w.report['failures']);self.assertFalse(w.report['first_artifact_behavior_gate_passed'])
        self.assertFalse((w.work/'select375-not-run.json').exists())

    def test_missing_or_reordered_local_completion_is_not_a_certificate(self):
        for completed in ([], ['wallpaper','contacts-picker','external-inputs','knowledge-holiday']):
            with self.subTest(completed=completed):self.reject_dispatch_only(completed)

    def test_bad_or_fatal_probe_state_is_not_a_certificate(self):
        names=list(literal(ROOT/'ci/capability-audit/parallel_runtime_suite.py','FAMILIES'))
        for state in ({'status':'running'}, {'status':False}, {'status':'fail','fatal_health_error':'SYNTHETIC fatal'}, {'status':'pass'}):
            with self.subTest(state=state):self.reject_dispatch_only(names, state)

    def reject_dispatch_only(self, completed, state=None):
        w=self.world();ns=w.namespace
        ns['report']['failures']=['SYNTHETIC prerequisite failure']
        ns['report']['independent_probes']={n:{'status':'fail'} for n in ns['FAMILIES']}
        if state is not None:ns['report']['independent_probes']['contacts-picker']=state
        ns['completed_capability_probes']=completed
        run=function(ROOT/'ci/capability-audit/run_packaged_qemu_suite.py','run')
        outer=next(n for n in run.body if isinstance(n,ast.Try))
        hook=next(n for n in outer.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and
            isinstance(n.test.left,ast.Name) and n.test.left.id=='owned_select_hook')
        fragment=ast.parse('def dispatch_only():\n pass\n').body[0];fragment.body=[copy.deepcopy(hook)]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fragment],type_ignores=[])),'SYNTHETIC-dispatch-only','exec'),ns)
        with self.assertRaisesRegex(ValueError,'lacks original completed'):ns['dispatch_only']()
        w.hook.assert_not_called();self.assertFalse((w.work/'select375-not-run.json').exists())


if __name__=='__main__':unittest.main()
