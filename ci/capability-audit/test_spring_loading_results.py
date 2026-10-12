"""Synthetic verifier rejection tests; never actual package behavior evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from spring_loading_contract import source
from verify_spring_loading_results import verify

NONCE = 'ad9e3b2cbce840118f9149e6af10cdae'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
    'isSystemApp': False, 'uid': 20010001}})


def fixture():
    rows = []
    now = 10000
    def row(name, generation=0, count=0, state=-1, sequence=-1, config=None, summary=-1, omitted=False):
        nonlocal now
        now += 1
        value = dict(runId=NONCE, name=name, generation=generation, state=state, sequence=sequence,
            instance=True, config=config or [], summarySize=summary, count=count, time=now,
            error='', infosOmitted=omitted)
        rows.append(value)
        return value
    row('constructor')
    for generation, mode in ((1, 1), (2, 2), (3, 1), (4, 3)):
        row('ready.' + str(mode), generation)
        row('drag.started', generation)
        states = [0, 1, 1, 2] if mode == 1 else ([0] if mode == 2 else [0, 3])
        for sequence, state in enumerate(states):
            config = [] if state == 3 else ([150, 200, 2, 200] if mode == 1 and sequence else
                                           [150, 10000 if mode == 3 else 100, 2, 100])
            row('callback', generation, sequence + 1, state, sequence, config,
                -1 if state == 3 else 32, state == 3)
            action = 'begin.updated' if mode == 1 and not sequence else (
                'abort.called' if mode == 2 else 'outside-begin.ignored')
            if mode == 3 and not sequence:
                continue
            if mode == 1 and not sequence:
                config = [150, 200, 2, 200]
            row(action, generation, sequence + 1, state, sequence, config,
                -1 if state == 3 else 32, state == 3)
        row('drop', generation, len(states))
        row('drag.ended', generation, len(states))
        quiet = row('quiet.begin', generation, len(states))
        now += 1500
        row('quiet.end', generation, len(states))
        assert rows[-1]['time'] - quiet['time'] >= 1500
    return rows


class SpringLoadingResultTests(unittest.TestCase):
    def call(self, rows, nonce=NONCE, identity=IDENTITY):
        return verify('\n'.join(json.dumps(row) for row in rows), nonce, identity)

    def test_exact_lifecycle_fixture_not_device_evidence(self):
        result = self.call(fixture())
        self.assertEqual(result['native_callbacks'], 11)
        self.assertEqual(result['generations'], 4)
        self.assertEqual(len(result['closed']), 1)

    def test_real_class_config_cancel_data_and_native_summary_fail_closed(self):
        for field, value, generation, sequence in (
            ('instance', False, 1, 0), ('config', [0, 0, 0, 0], 1, 1),
            ('infosOmitted', False, 4, 1), ('summarySize', 0, 1, 0),
            ('summarySize', float('nan'), 1, 0), ('state', True, 1, 0)):
            with self.subTest(field=field, value=value):
                rows = fixture()
                target = next(row for row in rows if row['name'] == 'callback' and
                              row['generation'] == generation and row['sequence'] == sequence)
                target[field] = value
                with self.assertRaises(ValueError): self.call(rows)
        rows = fixture()
        next(row for row in rows if row['name'] == 'callback')['summarySize'] = float('inf')
        with self.assertRaises(ValueError): self.call(rows)

    def test_old_abort_cancel_reentry_and_short_quiet_rejected(self):
        rows = fixture()
        index = next(i for i, row in enumerate(rows) if row['name'] == 'abort.called')
        extra = copy.deepcopy(rows[index])
        extra.update(name='callback', state=3, sequence=1, count=2, config=[], summarySize=-1, infosOmitted=True)
        rows.insert(index + 1, extra)
        with self.assertRaises(ValueError): self.call(rows)
        rows = [row for row in fixture() if row['generation'] != 3]
        with self.assertRaises(ValueError): self.call(rows)
        rows = fixture()
        end = next(row for row in rows if row['name'] == 'quiet.end')
        start = next(row for row in rows if row['name'] == 'quiet.begin')
        end['time'] = start['time'] + 1499
        with self.assertRaises(ValueError): self.call(rows)

    def test_ordinary_identity_fresh_nonce_and_callback_source(self):
        with self.assertRaises(ValueError): self.call(fixture(), nonce='old')
        value = json.loads(IDENTITY)
        value['applicationInfo']['isSystemApp'] = True
        with self.assertRaises(ValueError): self.call(fixture(), identity=json.dumps(value))
        page = source(NONCE)
        self.assertIn('context instanceof drag.SpringLoadingContext', page)
        self.assertIn("infos === undefined", page)
        self.assertNotIn('this.callback(new', page)
        self.assertIn("Column() { Text('Drag the nonce data') }", page)
        self.assertNotIn("Text('Drag the nonce text').id('spring-source')", page)
        root = Path(__file__).resolve().parents[2]
        builder = (root / 'ci/capability-audit/build_hap_probe.py').read_text()
        self.assertIn('args.spring_loading_only', builder)
        self.assertIn("'--spring-loading-only'", builder)

    def test_observation_clock_is_real_monotonic_and_backwards_or_short_intervals_still_fail(self):
        page = source(NONCE)
        self.assertEqual(page.count('systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, false)'), 3)
        self.assertNotIn('Date.now()', page)
        rows = fixture()
        rows[3]['time'] = rows[2]['time'] - 1
        with self.assertRaises(ValueError): self.call(rows)
        rows = fixture()
        begin = next(row for row in rows if row['name'] == 'quiet.begin')
        end = next(row for row in rows if row['name'] == 'quiet.end')
        end['time'] = begin['time'] + 1499
        with self.assertRaises(ValueError): self.call(rows)

    def test_full_evidence_requires_compiled_caller_physical_actions_and_same_package_boot(self):
        from run_root_probe import digest
        from spring_loading_contract import inputs, SCOPE
        import verify_spring_loading_results as verifier
        from test_spring_loading_input import evidence, check
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions, raw = evidence(root / 'pointer')
            actions_path = root / 'pointer/actions.json'
            actions_path.write_text(json.dumps(actions))
            project, sdk = root / 'project', root / 'sdk'
            page = project / 'entry/src/main/ets/pages/Index.ets'
            module = project / 'entry/src/main/module.json5'
            pages = project / 'entry/src/main/resources/base/profile/main_pages.json'
            declaration = sdk / 'ets/api/@ohos.arkui.dragController.d.ts'
            for path in (page, module, pages, declaration): path.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(source(NONCE))
            module.write_text(json.dumps({'module': {'requestPermissions': []}}))
            pages.write_text(json.dumps({'src': ['pages/Index']}))
            declaration.write_text('class SpringLoadingContext {\nabort(): void;\n'
                                   'updateConfiguration(config: DragSpringLoadingConfiguration): void;\n}')
            for relative in ('ets/api/@ohos.data.unifiedDataChannel.d.ts', 'ets/component/common.d.ts'):
                path = sdk / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('// fixture')
            (sdk / 'ets/api/@ohos.systemDateTime.d.ts').write_text(
                '// Synthetic declaration, NOT real compiler evidence.\n'
                'STARTUP = 0\nfunction getUptime(timeType: TimeType, isNanoseconds?: boolean): number;\n')
            paths = dict(result=root / 'verified-result.json', raw_results=root / 'results.log',
                ordinary_identity=root / 'application-identity.json', hap=root / 'ordinary-probe-signed.hap',
                compiled_contract_inputs=project / 'spring-loading-probe-inputs.json', spring_loading_actions=actions_path)
            paths['raw_results'].write_text(raw); paths['ordinary_identity'].write_text(IDENTITY)
            paths['hap'].write_text('synthetic fixture NOT a real signed HAP')
            paths['compiled_contract_inputs'].write_text(json.dumps(inputs(project, sdk, 'arm64', NONCE)))
            result = self.call(fixture()); result['physical_input'] = check(actions, raw)
            value = dict(status='pass', scope=SCOPE, failures=[], archive_sha256='archive', boot_id='boot',
                arch='arm64', device='phone', target='127.0.0.1:12345', run_id=NONCE,
                first_artifact_behavior_gate_passed=False, verifier_sha256=digest(Path(verifier.__file__)),
                result=result, results_sha256=digest(paths['raw_results']),
                application_identity_sha256=digest(paths['ordinary_identity']),
                compiled_inputs_sha256=digest(paths['compiled_contract_inputs']), actions_sha256=digest(actions_path))
            paths['result'].write_text(json.dumps(value))
            doc = dict(status='pass', persona='spring-loading', archive_sha256='archive', boot_id='boot',
                arch='arm64', device='phone', target='127.0.0.1:12345', failures=[], run_id=NONCE,
                first_artifact_behavior_gate_passed=False, ordinary_uid=20010001, result=str(paths['result']))
            for key, path in paths.items(): doc[key + '_sha256'] = digest(path)
            self.assertEqual(verifier.verify_evidence(doc, 'archive', 'boot', 'arm64', 'phone', doc['target']), result)
            for key, new in (('archive_sha256', 'old'), ('boot_id', 'old'), ('arch', 'x86_64'),
                             ('device', '2in1'), ('target', 'foreign'), ('ordinary_uid', 0)):
                changed = copy.deepcopy(doc); changed[key] = new
                with self.subTest(key=key), self.assertRaises(ValueError):
                    verifier.verify_evidence(changed, 'archive', 'boot', 'arm64', 'phone', doc['target'])
            for path in (*paths.values(), page, declaration):
                original = path.read_bytes(); path.write_bytes(original + b' changed')
                with self.subTest(path=path), self.assertRaises(ValueError):
                    verifier.verify_evidence(doc, 'archive', 'boot', 'arm64')
                path.write_bytes(original)
            # The strict closure code must independently replay this evidence.
            from verify_gap_closure import behavior_results
            runtime = root / 'runtime'
            (runtime / 'spring-loading').mkdir(parents=True); (runtime / 'boot').mkdir()
            (runtime / 'spring-loading/evidence.json').write_text(json.dumps(doc))
            boot = json.loads(Path(actions['boot']).read_text())
            boot_path = runtime / 'boot/boot.json'; boot_path.write_text(json.dumps(boot))
            self.assertEqual(set(behavior_results(runtime, 'boot', 'archive', 'phone')), set(result['closed']))
            boot['purpose'] = 'diagnostic'; boot_path.write_text(json.dumps(boot))
            with self.assertRaises(ValueError): behavior_results(runtime, 'boot', 'archive', 'phone')

    def test_suite_and_gate_require_real_input_not_an_export_only_pass(self):
        from run_normal_hap_probe import PERSONAS, verifier_arguments
        root = Path(__file__).resolve().parents[2]
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        gate = (root / 'scripts/verify_first_artifact_gate.py').read_text()
        runner = (root / 'ci/capability-audit/run_normal_hap_probe.py').read_text()
        self.assertEqual(PERSONAS['spring-loading'][0], '--spring-loading-only')
        self.assertIn("personas += ('spring-loading',)", suite)
        self.assertIn("check('spring-loading', path, [record])", suite)
        self.assertIn('"spring-loading"', gate.split('DEVICE_CHECKS', 1)[0])
        self.assertIn('from verify_spring_loading_results import verify_evidence', gate)
        self.assertIn('actions_path, spring_result = exercise', runner)
        arguments = verifier_arguments('spring-loading', 'archive', 'raw', 'identity', NONCE, 'arm64', 'output')
        self.assertIn('--application-identity', arguments); self.assertIn('--arch', arguments)


if __name__ == '__main__': unittest.main()
