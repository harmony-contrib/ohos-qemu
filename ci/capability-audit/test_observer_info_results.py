"""Synthetic replay/tamper tests, never guest behavior proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from observer_info_contract import ABILITY, SCOPE, TEMPLATE, inputs, source
from run_root_probe import digest
import verify_observer_info_results as verifier
from verify_observer_info_results import CONTRACTS, verify, verify_evidence

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010001}})


def fixture():
    rows = []
    counts = [0, 0, 0, 0]
    target = 0
    def row(name, generation=0, phase=0, step=0, listener='', density=0, width=-1, height=-1):
        rows.append(dict(runId=RUN, name=name, listener=listener, generation=generation, phase=phase,
            step=step, target=target, density=density, width=width, height=height, instance=True,
            contextMatches=True, counts=counts[:], error=''))
    row('density.constructor'); row('breakpoint.constructor')
    target = 1.5
    for generation in range(2):
        counts = [0, 0, 0, 0]
        row('registered', generation)
        for step, phase in ((0, 0), (1, 0), (2, 1), (3, 2)):
            if phase == 1: row('first-removed', generation, phase, step)
            if phase == 2: row('all-removed', generation, phase, step)
            target = 4 if target == 0.5 else 0.5
            row('change', generation, phase, step)
            if phase < 2:
                for kind in ('density', 'breakpoint'):
                    for listener in (('a', 'b') if phase == 0 else ('b',)):
                        slot = (0 if listener == 'a' else 1) + (2 if kind == 'breakpoint' else 0)
                        counts[slot] += 1
                        row(kind, generation, phase, step, listener,
                            density=target if kind == 'density' else 0,
                            width=(5 if target == 0.5 else 0) if kind == 'breakpoint' else -1,
                            height=2 if kind == 'breakpoint' else -1)
            row('settled', generation, phase, step, density=target, width=5 if target == 0.5 else 0, height=2)
    row('restored', 2, 2, 3, density=1.5, width=2, height=2)
    row('summary', 2, 2, 3)
    return rows


def check(rows, identity=IDENTITY):
    return verify('\n'.join(map(json.dumps, rows)), RUN, identity)


def evidence(root):
    project, sdk = root / 'project', root / 'sdk'
    page = project / 'entry/src/main/ets/pages/Index.ets'
    ability = project / 'entry/src/main/ets/entryability/EntryAbility.ets'
    module = project / 'entry/src/main/module.json5'
    pages = project / 'entry/src/main/resources/base/profile/main_pages.json'
    declaration = sdk / 'ets/api/@ohos.arkui.observer.d.ts'
    for path in (page, ability, module, pages, declaration): path.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(source(RUN)); ability.write_text(ABILITY)
    module.write_text(json.dumps({'module': {'requestPermissions': []}}))
    pages.write_text(json.dumps({'src': ['pages/Index']}))
    declaration.write_text('export class DensityInfo {}\nexport class WindowSizeLayoutBreakpointInfo {}\n')
    paths = {'result': root / 'verified-result.json', 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': project / 'observer-info-probe-inputs.json'}
    paths['raw_results'].write_text('\n'.join(map(json.dumps, fixture())))
    paths['ordinary_identity'].write_text(IDENTITY)
    paths['hap'].write_bytes(b'synthetic host fixture, not a signed HAP')
    paths['compiled_contract_inputs'].write_text(json.dumps(inputs(project, sdk, 'arm64', RUN)))
    verified = dict(status='pass', scope=SCOPE, failures=[], archive_sha256='archive', arch='arm64',
        run_id=RUN, first_artifact_behavior_gate_passed=False, verifier_sha256=digest(Path(verifier.__file__)),
        result=check(fixture()), results_sha256=digest(paths['raw_results']),
        application_identity_sha256=digest(paths['ordinary_identity']),
        compiled_inputs_sha256=digest(paths['compiled_contract_inputs']))
    paths['result'].write_text(json.dumps(verified))
    document = dict(status='pass', persona='observer-info', archive_sha256='archive', boot_id='boot',
        arch='arm64', failures=[], first_artifact_behavior_gate_passed=False, run_id=RUN, ordinary_uid=20010001,
        result=str(paths['result']))
    for name, path in paths.items(): document[name + '_sha256'] = digest(path)
    return document, paths


class ObserverInfoResultsTests(unittest.TestCase):
    def test_narrow_real_subscription_fixture(self):
        self.assertEqual(check(fixture())['closed'], CONTRACTS)
        self.assertEqual(check(fixture())['real_density_changes'], 8)

    def test_every_missing_duplicate_stale_or_reordered_row_rejected(self):
        for index in range(len(fixture())):
            for mutation in ('missing', 'duplicate', 'stale'):
                rows = fixture()
                if mutation == 'missing': del rows[index]
                elif mutation == 'duplicate': rows.insert(index, copy.deepcopy(rows[index]))
                else: rows[index]['runId'] = 'b' * 32
                with self.subTest(index=index, mutation=mutation), self.assertRaises(ValueError): check(rows)

    def test_failed_constructor_context_wrong_density_prototype_and_bool_number_rejected(self):
        for key, value in (('instance', False), ('contextMatches', False), ('density', '0.5'),
                           ('width', True), ('counts', [True, 0, 0, 0]), ('error', 'failed')):
            rows = fixture(); rows[3][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): check(rows)
        rows = fixture(); next(row for row in rows if row['name'] == 'density')['density'] = 0.75
        with self.assertRaises(ValueError): check(rows)
        rows = fixture(); rows[0]['instance'] = False
        with self.assertRaises(ValueError): check(rows)

    def test_callback_after_removal_missing_boundary_and_restore_rejected(self):
        rows = fixture()
        for row in rows:
            if row['phase'] == 1 and row['name'] in ('density', 'breakpoint'): row['listener'] = 'a'
        with self.assertRaises(ValueError): check(rows)
        rows = fixture(); next(row for row in rows if row['name'] == 'restored')['density'] = 4
        with self.assertRaises(ValueError): check(rows)
        rows = fixture()
        for row in rows:
            if row['name'] in ('breakpoint', 'settled'): row['width'] = 0
        with self.assertRaises(ValueError): check(rows)

    def test_ordinary_uid_and_package_boot_arch_binding(self):
        bad = json.loads(IDENTITY); bad['applicationInfo']['isSystemApp'] = True
        with self.assertRaises(ValueError): check(fixture(), json.dumps(bad))
        with tempfile.TemporaryDirectory() as directory:
            doc, paths = evidence(Path(directory))
            self.assertEqual(verify_evidence(doc, 'archive', 'boot', 'arm64'), check(fixture()))
            for field, value in (('archive_sha256', 'old'), ('boot_id', 'old'), ('arch', 'x86_64')):
                changed = copy.deepcopy(doc); changed[field] = value
                with self.assertRaises(ValueError): verify_evidence(changed, 'archive', 'boot', 'arm64')
            for path in paths.values():
                original = path.read_bytes(); path.write_bytes(original + b' changed')
                with self.assertRaises(ValueError): verify_evidence(doc, 'archive', 'boot', 'arm64')
                path.write_bytes(original)

    def test_compiled_caller_and_stage_no_permission_change(self):
        self.assertIn('new observer.DensityInfo()', source(RUN))
        self.assertIn('new observer.WindowSizeLayoutBreakpointInfo()', source(RUN))
        self.assertIn('info.context as UIContext', source(RUN))
        self.assertIn('stage.setCustomDensity(this.target)', source(RUN))
        self.assertIn('onWindowStageDestroy', ABILITY)
        with tempfile.TemporaryDirectory() as directory:
            doc, paths = evidence(Path(directory))
            page = paths['compiled_contract_inputs'].parent / 'entry/src/main/ets/pages/Index.ets'
            page.write_text(source(RUN) + '// unrecorded\n')
            with self.assertRaises(ValueError): verify_evidence(doc, 'archive', 'boot', 'arm64')

    def test_full_suite_and_gate_require_actual_observer_evidence(self):
        root = Path(__file__).resolve().parents[2]
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        gate = (root / 'scripts/verify_first_artifact_gate.py').read_text()
        self.assertIn("personas += ('observer-info',)", suite)
        self.assertIn("check('observer-info', path, [record])", suite)
        self.assertIn('"observer-info"', gate.split('DEVICE_CHECKS', 1)[0])
        self.assertIn('from verify_observer_info_results import verify_evidence', gate)

    def test_ledger_replays_actual_bound_evidence_and_rejects_diagnostic_boot(self):
        from verify_gap_closure import behavior_results
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc, paths = evidence(root)
            runtime = root / 'ledger'
            (runtime / 'observer-info').mkdir(parents=True)
            (runtime / 'boot').mkdir()
            (runtime / 'observer-info/evidence.json').write_text(json.dumps(doc))
            boot = dict(status='pass', purpose='acceptance',
                scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate', archive_sha256='archive',
                test_environment=dict(boot_id='boot', guest_arch='arm64', device_type='phone',
                                      external_keepalive=False))
            boot_path = runtime / 'boot/boot.json'
            boot_path.write_text(json.dumps(boot))
            checked = lambda: behavior_results(runtime, 'boot', 'archive', 'phone')
            self.assertEqual(set(checked()), set(CONTRACTS))
            for key, value in (('purpose', 'diagnostic'), ('candidate_kernel', 'replacement')):
                boot_path.write_text(json.dumps(dict(boot, **{key: value})))
                with self.assertRaises(ValueError): checked()
            boot_path.write_text(json.dumps(boot))
            paths['raw_results'].write_text('{}')
            with self.assertRaises(ValueError): checked()


if __name__ == '__main__': unittest.main()
