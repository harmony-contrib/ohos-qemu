"""Synthetic verifier unit cases, never packaged-device evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from router_observer_contract import SCOPE, inputs, sources
from run_root_probe import digest
import verify_router_observer_results as verifier
from verify_router_observer_results import verify, verify_evidence

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010001}})


def fixture():
    rows = []
    for generation in range(2):
        counts = [0, 0]
        for phase, start, end in ((0, 'registered', 'both-returned'),
                                  (1, 'first-removed', 'second-returned'),
                                  (2, 'all-removed', 'unsubscribed-returned')):
            def marker(name):
                rows.append(dict(runId=RUN, name=name, listener='', generation=generation,
                    phase=phase, index=0, pageName='', path='', state=0, pageId='',
                    contextMatches=True, counts=counts[:]))
            marker(start)
            if phase < 2:
                for state in (0, 2, 3, 1):
                    for listener, slot in ((('a', 0), ('b', 1)) if phase == 0 else (('b', 1),)):
                        counts[slot] += 1
                        rows.append(dict(runId=RUN, name='event', listener=listener, generation=generation,
                            phase=phase, index=2, pageName='ObserverDetail', path='pages/ObserverDetail',
                            state=state, pageId=str(10 + generation * 2 + phase), contextMatches=True,
                            counts=counts[:]))
            marker(end)
    rows.append(dict(runId=RUN, name='summary', listener='', generation=2, phase=2,
        index=0, pageName='', path='', state=0, pageId='', contextMatches=True, counts=counts[:]))
    return rows


def check(rows):
    return verify('\n'.join(map(json.dumps, rows)), RUN, IDENTITY)


class RouterObserverTests(unittest.TestCase):
    def test_package_binding_replays_exact_compiled_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, sdk = root / 'project', root / 'sdk'
            for name, text in sources(RUN).items():
                path = project / f'entry/src/main/ets/pages/{name}.ets'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            (project / 'entry/src/main/module.json5').write_text(json.dumps({'module': {'requestPermissions': []}}))
            pages = project / 'entry/src/main/resources/base/profile/main_pages.json'
            pages.parent.mkdir(parents=True)
            pages.write_text(json.dumps({'src': ['pages/Index', 'pages/ObserverDetail']}))
            declaration = sdk / 'ets/api/@ohos.arkui.observer.d.ts'
            declaration.parent.mkdir(parents=True)
            declaration.write_text('export class RouterPageInfo {} // synthetic fixture only\n')
            paths = {'result': root / 'verified-result.json', 'raw_results': root / 'results.log',
                     'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
                     'compiled_contract_inputs': project / 'router-observer-probe-inputs.json'}
            paths['raw_results'].write_text('\n'.join(map(json.dumps, fixture())))
            paths['ordinary_identity'].write_text(IDENTITY)
            paths['hap'].write_bytes(b'synthetic host test, not a signed package')
            paths['compiled_contract_inputs'].write_text(json.dumps(inputs(project, sdk, 'arm64', RUN)))
            checked = dict(status='pass', scope=SCOPE, failures=[], archive_sha256='archive', arch='arm64',
                run_id=RUN, first_artifact_behavior_gate_passed=False, verifier_sha256=digest(Path(verifier.__file__)),
                result=check(fixture()), results_sha256=digest(paths['raw_results']),
                application_identity_sha256=digest(paths['ordinary_identity']),
                compiled_inputs_sha256=digest(paths['compiled_contract_inputs']))
            paths['result'].write_text(json.dumps(checked))
            document = dict(status='pass', persona='router-observer', archive_sha256='archive', boot_id='boot',
                arch='arm64', failures=[], first_artifact_behavior_gate_passed=False, run_id=RUN, ordinary_uid=20010001,
                result=str(paths['result']))
            for name, path in paths.items(): document[name + '_sha256'] = digest(path)
            self.assertEqual(verify_evidence(document, 'archive', 'boot', 'arm64'), check(fixture()))
            with self.assertRaises(ValueError): verify_evidence(document, 'older', 'boot', 'arm64')
            with self.assertRaises(ValueError): verify_evidence(document, 'archive', 'older', 'arm64')
            paths['raw_results'].write_text('{}\n')
            with self.assertRaises(ValueError): verify_evidence(document, 'archive', 'boot', 'arm64')

    def test_complete_fixture_is_scoped_not_capability_closure(self):
        self.assertEqual(check(fixture())['closed'], [])
        self.assertEqual(check(fixture())['observed_child_instances'], 4)

    def test_missing_reordered_or_foreign_records_fail(self):
        for index in range(len(fixture())):
            rows = fixture()
            del rows[index]
            with self.assertRaises(ValueError):
                check(rows)
        rows = fixture()
        rows[1]['runId'] = 'b' * 32
        with self.assertRaises(ValueError):
            check(rows)

    def test_bad_context_stale_identity_and_missing_state_fail(self):
        for key, value in (('contextMatches', False), ('index', True), ('state', True),
                           ('path', 'invented'), ('pageId', ''), ('counts', [True, 0])):
            rows = fixture()
            rows[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check(rows)

    def test_callbacks_after_removal_fail(self):
        rows = fixture()
        index = next(i for i, row in enumerate(rows) if row['name'] == 'all-removed')
        extra = copy.deepcopy(rows[1])
        extra['phase'] = 2
        rows.insert(index + 1, extra)
        with self.assertRaises(ValueError):
            check(rows)
        rows = fixture()
        for row in rows:
            if row['name'] == 'event' and row['phase'] == 1:
                row['listener'] = 'a'
        with self.assertRaises(ValueError):
            check(rows)

    def test_real_templates_bind_nonce_and_public_routing(self):
        generated = sources(RUN)
        self.assertEqual(set(generated), {'Index', 'ObserverDetail'})
        self.assertIn("pushUrl({ url: 'pages/ObserverDetail' })", generated['Index'])
        self.assertIn('info: observer.RouterPageInfo', generated['Index'])
        self.assertNotIn('info.context === this.getUIContext()', generated['Index'])
        self.assertIn('context.getHostContext()', generated['Index'])
        self.assertIn('host.filesDir === ownHost.filesDir', generated['Index'])
        self.assertIn('Number(context.getRouter().getLength()) >= 1', generated['Index'])
        self.assertIn("observer.off('routerPageUpdate', context, first)", generated['Index'])
        self.assertIn('getRouter().back()', generated['ObserverDetail'])
        self.assertNotIn('__RUN__', ''.join(generated.values()))
        with self.assertRaises(ValueError):
            sources('stale')


if __name__ == '__main__':
    unittest.main()
