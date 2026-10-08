"""Verifier boundary fixtures only, not a QEMU binding behavior pass."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from verify_binding_results import verify, verify_evidence, SCOPE
import verify_binding_results as verifier
from binding_contract import TEMPLATE, inputs
from run_root_probe import digest

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
    'isSystemApp': False, 'uid': 20010000}})


def fixture():
    rows = []
    for generation in range(2):
        seed = int(RUN[:4], 16) + generation * 100
        for step in range(33):
            value = seed + (step if step % 2 == 0 else -step)
            rows.append({'runId': RUN, 'name': 'number.' + str(generation) + '.' + str(step),
                'values': [value, value, -seed, value, step + 1], 'checks': [True] * 3, 'error': ''})
        rows.append({'runId': RUN, 'name': 'object.' + str(generation),
            'values': [seed + 1, seed + 1, seed], 'checks': [True] * 4, 'error': ''})
    for name, values in (('getter.exception', []), ('setter.exception', [17, 17]),
                         ('setter.recovery', [31, 31]), ('summary', [68, 3])):
        rows.append({'runId': RUN, 'name': name, 'values': values, 'checks': [True], 'error': ''})
    return rows


class BindingTests(unittest.TestCase):
    def test_two_typed_factory_classes_not_constructor_or_persistence(self):
        result = verify('\n'.join(map(json.dumps, fixture())), RUN, IDENTITY)
        self.assertEqual(len(result['closed']), 2)
        self.assertIn('constructors', result['not_claimed'])

    def test_every_value_identity_isolation_exception_and_recovery_required(self):
        original = fixture()
        for index in range(len(original)):
            for field in ('values', 'checks', 'name', 'runId', 'error'):
                rows = deepcopy(original)
                row = rows[index]
                with self.subTest(index=index, field=field):
                    if field == 'values': row[field] = [0]
                    elif field == 'checks': row[field][0] = False
                    elif field == 'name': row[field] = 'substitute'
                    elif field == 'runId': row[field] = 'b' * 32
                    else: row[field] = 'actual error'
                    with self.assertRaises(ValueError): verify('\n'.join(map(json.dumps, rows)), RUN, IDENTITY)

    def test_missing_reordered_duplicate_bool_number_extra_and_privileged_inputs_reject(self):
        for case in ('missing', 'reordered', 'duplicate', 'bool-number', 'number-bool', 'extra', 'privileged'):
            rows, identity = fixture(), IDENTITY
            with self.subTest(case=case):
                if case == 'missing': rows.pop(0)
                elif case == 'reordered': rows[0], rows[1] = rows[1], rows[0]
                elif case == 'duplicate': rows.insert(0, rows[0])
                elif case == 'bool-number': rows[0]['checks'][0] = 1
                elif case == 'number-bool': rows[-1]['values'][1] = True
                elif case == 'extra': rows[0]['ignored'] = True
                elif case == 'privileged': identity = IDENTITY.replace('normal', 'system_basic')
                with self.assertRaises(ValueError): verify('\n'.join(map(json.dumps, rows)), RUN, identity)

    def test_original_owned_caller_provenance_replays_and_mutations_reject(self):
        sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        with tempfile.TemporaryDirectory(prefix='binding-evidence-host-fixture-') as directory:
            root = Path(directory)
            project = root / 'project'
            page = project / 'entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text(TEMPLATE.read_text().replace('__BINDING_RUN_ID__', RUN))
            module = project / 'entry/src/main/module.json5'
            module.write_text(json.dumps({'module': {'requestPermissions': []}}))
            compiled = project / 'binding-probe-inputs.json'
            compiled.write_text(json.dumps(inputs(project, sdk, 'arm64', RUN)))
            raw = root / 'results.log'; raw.write_text('\n'.join(map(json.dumps, fixture())))
            identity = root / 'application-identity.json'; identity.write_text(IDENTITY)
            checked = root / 'verified-result.json'
            value = {'status': 'pass', 'scope': SCOPE, 'run_id': RUN, 'arch': 'arm64',
                'archive_sha256': 'c' * 64, 'verifier_sha256': digest(Path(verifier.__file__)),
                'results_sha256': digest(raw), 'application_identity_sha256': digest(identity),
                'compiled_inputs_sha256': digest(compiled), 'result': verify(raw.read_text(), RUN, IDENTITY)}
            checked.write_text(json.dumps(value))
            document = {'status': 'pass', 'persona': 'binding', 'archive_sha256': 'c' * 64,
                'boot_id': 'actual-boot-host-fixture', 'run_id': RUN, 'arch': 'arm64',
                'result': str(checked), 'result_sha256': digest(checked),
                'raw_results_sha256': digest(raw), 'ordinary_identity_sha256': digest(identity),
                'compiled_contract_inputs': str(compiled), 'compiled_contract_inputs_sha256': digest(compiled)}
            def replay(doc=document):
                return verify_evidence(doc, root, 'c' * 64, 'actual-boot-host-fixture')
            self.assertEqual(replay(), value['result'])
            for key in ('status', 'persona', 'archive_sha256', 'boot_id', 'run_id', 'arch',
                        'result', 'result_sha256', 'raw_results_sha256', 'ordinary_identity_sha256',
                        'compiled_contract_inputs', 'compiled_contract_inputs_sha256'):
                changed = deepcopy(document); changed[key] = 'wrong'
                with self.subTest(key=key), self.assertRaises((ValueError, KeyError)):
                    replay(changed)
            for path in (raw, identity, checked, compiled, page, module):
                content = path.read_bytes()
                path.write_bytes(content + b' ')
                with self.subTest(path=path.name), self.assertRaises(ValueError): replay()
                path.write_bytes(content)


if __name__ == '__main__': unittest.main()
