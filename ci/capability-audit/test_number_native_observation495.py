"""Portable source/diagnostic tests; private scratch only, no target or guest calls."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / 'patches'
FIXTURES = HERE / 'fixtures/number_native_observation495'
COMPONENT_PATHS = (
    'patches/common/foundation/ability/ability_runtime/number_identity_native_trace495',
    'patches/common/base/telephony/number_identity/native_observation495',
)
# Original component FILES are the finite inventory; no private handoff layout.
INVENTORY = []
for relative in COMPONENT_PATHS:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location('number495_inventory_' + path.name, path / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    INVENTORY.append(dict(component=relative, project=baseline.PROJECT, files=baseline.FILES,
                          paths=[baseline.PROJECT + '/' + row[0] for row in baseline.FILES]))

_SCRATCH = tempfile.TemporaryDirectory(prefix='number-native495-tests-')
WORK = Path(_SCRATCH.name).resolve()
ENV = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
ENV.update(PYTHONDONTWRITEBYTECODE='1', GIT_CEILING_DIRECTORIES=str(WORK),
           GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, TMPDIR=str(WORK))
HELPER_PINS = {
    'apply_exact_component.py': 'be60d0be4e741af2768f1936779f94aac5d778cd2d627db898353b3b3d47cc65',
    'exact_source_states.py': 'd876f46528b81323414866a97987ac72d82a5b7e748cddda8d8fef01e239e1a2',
}


def fixture_input(row):
    """Only fixed local fixture paths; historical receipt path/argv is inert."""
    relative = row['source_relative']
    for item in INVENTORY:
        for name, before, after in item['files']:
            if before is not None and relative == item['project'] + '/' + name:
                return ROOT / item['component'] / 'fixtures/original' / relative
    extra = {
        'base/telephony/number_identity/utils/log/include/number_identity_log_wrapper.h': 'number_identity_log_wrapper.h',
        'foundation/distributeddatamgr/data_share/frameworks/native/provider/src/datashare_stub.cpp': 'datashare_stub.cpp',
        'foundation/distributeddatamgr/data_share/frameworks/native/provider/include/datashare_stub.h': 'datashare_stub.h',
    }
    return FIXTURES / extra[relative]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root):
    return {str(p.relative_to(root)): digest(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def component(row):
    path = ROOT / row['component']
    spec = importlib.util.spec_from_file_location('baseline495_' + path.name, path / 'verify_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return path, module


def pristine(row, root):
    path, baseline = component(row)
    for relative, before, after in row['files']:
        target = root / row['project'] / relative
        if before is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path / 'fixtures/original' / row['project'] / relative, target)
    return path, baseline


def apply(path, root):
    result = subprocess.run([sys.executable, '-B', str(PATCHES / 'lib/apply_exact_component.py'),
        '--component-dir', str(path), '--source-root', str(root)], env=ENV,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result


class ExactCandidateTests(unittest.TestCase):
    def test_actual_datashare_dispatch_retains_direct_ipc_context(self):
        receipt = FIXTURES / 'datashare-receipt495.json'
        self.assertEqual(digest(receipt), '1e7fdc3a4776010eb1af53c3eb9b9f145dca48113f77af4ab488acb8637a1e92')
        data = json.loads(receipt.read_text())
        for row in data['files']:
            self.assertEqual(digest(fixture_input(row)), row['sha256'])
        source = next(fixture_input(row).read_text() for row in data['files'] if row['source_relative'].endswith('.cpp'))
        dispatch = source.split('int DataShareStub::OnRemoteRequest(', 1)[1].split('\nbool DataShareStub::VerifyPermissionAndUri', 1)[0]
        query = source.split('ErrCode DataShareStub::CmdQuery(', 1)[1].split('\nErrCode DataShareStub::CmdGetType', 1)[0]
        self.assertIn('ret = (this->*(itFunc->second))(data, reply);', dispatch)
        self.assertIn('auto resultSet = Query(uri, predicates, columns, businessError);', query)
        for text in (dispatch, query):
            for invalid in ('ResetCallingIdentity', 'SetCallingIdentity', 'PostTask', 'std::async', 'std::thread'):
                self.assertNotIn(invalid, text)

    def test_actual_parent_inputs_and_unchanged_helpers(self):
        manifest = json.loads((FIXTURES / 'actual-source495.json').read_text())
        receipt = manifest['receipt']
        self.assertEqual(digest(FIXTURES / 'actual-source-receipt495.json'), receipt['sha256'])
        for row in manifest['files']:
            self.assertEqual(digest(fixture_input(row)), row['sha256'])
        for name in ('apply_exact_component.py', 'exact_source_states.py'):
            self.assertEqual(digest(PATCHES / 'lib' / name), HELPER_PINS[name])

    def test_complete_apply_repeat_verify_and_reverse(self):
        for row in INVENTORY:
            with self.subTest(component=row['component']), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                root = Path(temp)
                path, baseline = pristine(row, root)
                self.assertFalse(baseline.validate(root))
                with self.assertRaises(ValueError): baseline.validate(root, require_patched=True)
                first = apply(path, root)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertTrue(baseline.validate(root, require_patched=True))
                for relative, before, after in row['files']:
                    self.assertEqual(digest(root / row['project'] / relative), after)
                after_first = tree(root)
                again = apply(path, root)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual(tree(root), after_first)
                patch = path / '0001-record-number-native-causal-observations.patch'
                for mode in ('--check', None):
                    argv = ['git', '-C', str(root), 'apply', '-R']
                    if mode: argv.append(mode)
                    argv.append(str(patch))
                    result = subprocess.run(argv, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(baseline.validate(root))
                for relative, before, after in row['files']:
                    target = root / row['project'] / relative
                    if before is None: self.assertFalse(target.exists())
                    else: self.assertEqual(digest(target), before)

    def test_unknown_each_file_refuses_before_any_source_write(self):
        for row in INVENTORY:
            for relative, before, after in row['files']:
                with self.subTest(component=row['component'], path=relative), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                    root = Path(temp)
                    path, baseline = pristine(row, root)
                    target = root / row['project'] / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(target.read_bytes() + b'\nUNKNOWN_DIAGNOSTIC_INPUT\n' if target.exists() else b'')
                    original = tree(root)
                    result = apply(path, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(tree(root), original)
                    self.assertFalse((root / '.ohos-qemu-patches').exists())
                if before is not None:
                    with self.subTest(component=row['component'], missing=relative), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                        root = Path(temp)
                        path, baseline = pristine(row, root)
                        (root / row['project'] / relative).unlink()
                        original = tree(root)
                        result = apply(path, root)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(tree(root), original)
                        self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_partial_states_including_new_header_rejected(self):
        row = INVENTORY[1]
        for chosen in row['files']:
            with self.subTest(chosen=chosen[0]), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                root = Path(temp)
                path, baseline = pristine(row, root)
                target = root / row['project'] / chosen[0]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path / 'fixtures/final' / row['project'] / chosen[0], target)
                original = tree(root)
                result = apply(path, root)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree(root), original)
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_file_symlink_hardlink_and_parent_alias_rejected(self):
        for row in INVENTORY:
            relative, before, after = next(r for r in row['files'] if r[1] is not None)
            for alias in ('symlink', 'hardlink', 'parent'):
                with self.subTest(component=row['component'], alias=alias), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                    root = Path(temp)
                    path, baseline = pristine(row, root)
                    target = root / row['project'] / relative
                    if alias == 'parent':
                        real_parent = target.parent.with_name(target.parent.name + '-actual')
                        target.parent.rename(real_parent)
                        target.parent.symlink_to(real_parent, target_is_directory=True)
                    else:
                        actual = root / 'alias-inode'
                        target.rename(actual)
                        if alias == 'symlink': target.symlink_to(actual)
                        else: os.link(actual, target)
                    original = tree(root)
                    result = apply(path, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(tree(root), original)
                    self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_patch_business_deletions_are_only_reviewed_equivalent_returns(self):
        actual = {}
        for row in INVENTORY:
            path, baseline = component(row)
            patch = (path / baseline.EXPECTED['patch']).read_text()
            removed = [line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')]
            actual[row['project']] = removed
        self.assertEqual(actual['foundation/ability/ability_runtime'], [])
        self.assertEqual(actual['base/telephony/number_identity'], [
            'NumberLocationAbility::NumberLocationAbility() : DataShareExtAbility() {}',
            '    return NumberLocationAbility::Create();',
            '    return remoteObject->AsObject();'])

    def test_exact_loader_scope_and_preserved_failure_error(self):
        row = INVENTORY[0]
        path, baseline = component(row)
        data = (path / 'fixtures/final' / row['paths'][0]).read_text()
        prefix, body = data.split('void MainThread::LoadNativeLibrary(', 1)
        self.assertNotIn('NUMBER_NATIVE495', prefix)
        self.assertEqual(body.count('bundleInfo.name == "com.ohos.numberidentity"'), 1)
        self.assertEqual(body.count('== "libnumber_identity.z.so"'), 1)
        self.assertIn('dlerror());\n                observeNumberLoad("result", 0);\n                exit(-1);', body)
        self.assertIn('if (handleAbilityLib != nullptr) {\n            observeNumberLoad("result", 1);', body)

    def test_published_object_identity_and_query_pair_preserve_payload(self):
        row = INVENTORY[1]
        path, baseline = component(row)
        base = path / 'fixtures/final' / row['project'] / 'number_location'
        location = (base / 'src/number_location_ability.cpp').read_text()
        stub = (base / 'src/number_identity_datashare_stub_impl.cpp').read_text()
        header = (base / 'include/number_identity_native_trace.h').read_text()
        self.assertLess(location.index('SetNativeObservationIdentity('), location.index('auto result = remoteObject->AsObject();'))
        self.assertEqual(location.count('remoteObject->AsObject()'), 1)
        self.assertEqual(stub.count('auto resultSet = extension->Query(uri, predicates, columns, businessError);'), 1)
        self.assertLess(stub.index('observeQuery("query-enter", -1);'), stub.index('extension->Query(uri, predicates, columns, businessError)'))
        self.assertIn('observeQuery("query-result", 0);\n        return nullptr;', stub)
        self.assertIn('observeQuery("query-result", resultSet != nullptr ? 1 : 0);\n    return resultSet;', stub)
        self.assertIn('static std::atomic<uint64_t> next { 1 };', header)
        self.assertIn('visibility("hidden")', header)
        self.assertNotIn('GetWhereArgs', header + stub)
        self.assertNotIn('predicates.ToString', header + stub)
        self.assertNotIn('accepted', header)
        self.assertNotIn('native_callback_proven', header)
        self.assertIn('static_cast<unsigned long long>(sequence)', header)
        self.assertIn('errno = savedErrno;', header)


class CompleteSequenceTests(unittest.TestCase):
    def setup_sequence(self, root, state='old-original', b_final=False):
        a_path, a = pristine(INVENTORY[0], root)
        b_path, b = pristine(INVENTORY[1], root)
        main = root / a.PROJECT / a.FILES[0][0]
        old_path = PATCHES / a.OLD_COMPONENT
        if state == 'old-original':
            shutil.copy2(old_path / 'fixtures/original' / a.PROJECT / a.FILES[0][0], main)
        elif state == 'trace-final':
            shutil.copy2(a_path / 'fixtures/final' / a.PROJECT / a.FILES[0][0], main)
        elif state != 'old-loaded':
            raise ValueError('host test state')
        if b_final:
            for relative, before, after in b.FILES:
                target = root / b.PROJECT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(b_path / 'fixtures/final' / b.PROJECT / relative, target)
        return a_path, a, b_path, b

    def test_all_four_admitted_complete_vectors_and_default_cli(self):
        for state, b_final, expected in (
            ('old-original', False, ['OLD_COMPONENT', 'A_COMPONENT', 'B_COMPONENT']),
            ('old-loaded', False, ['A_COMPONENT', 'B_COMPONENT']),
            ('trace-final', False, ['B_COMPONENT']),
            ('trace-final', True, [])):
            with self.subTest(state=state, b_final=b_final), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                root = Path(temp)
                path, a, _, _ = self.setup_sequence(root, state, b_final)
                original = tree(root)
                result = a.preflight_sequence(root)
                self.assertEqual(result['component_sequence'], [getattr(a, name) for name in expected])
                self.assertEqual(tree(root), original)
                cli = subprocess.run([sys.executable, '-B', str(path / 'verify_source.py'), '--source-root', str(root)], env=ENV,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.assertEqual(cli.returncode, 0, cli.stderr)
                self.assertEqual(json.loads(cli.stdout), result)
                final = state == 'trace-final' and b_final
                if final: self.assertTrue(a.preflight_sequence(root, True)['whole_final'])
                else:
                    with self.assertRaises(ValueError): a.preflight_sequence(root, True)
                require = subprocess.run([sys.executable, '-B', str(path / 'verify_source.py'), '--source-root', str(root), '--require-patched'], env=ENV,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.assertEqual(require.returncode == 0, final)
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_real_original_helper_transition_repeat_and_full_reverse(self):
        with tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
            root = Path(temp)
            path, a, _, _ = self.setup_sequence(root)
            original = tree(root)
            planned = a.preflight_sequence(root)['component_sequence']
            for component_name in planned:
                result = apply(PATCHES / component_name, root)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(a.preflight_sequence(root, True)['whole_final'])
            self.assertEqual(a.preflight_sequence(root)['component_sequence'], [])
            for component_name in reversed(planned):
                patch = next((PATCHES / component_name).glob('0001-*.patch'))
                reverse = subprocess.run(['git', '-C', str(root), 'apply', '-R', str(patch)], env=ENV,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.assertEqual(reverse.returncode, 0, reverse.stderr)
            source_tree = {p: value for p, value in tree(root).items() if not p.startswith('.ohos-qemu-patches/')}
            self.assertEqual(source_tree, original)
            self.assertEqual(a.preflight_sequence(root)['component_sequence'], planned)

    def test_provider_after_with_either_old_mainthread_is_rejected(self):
        for state in ('old-original', 'old-loaded'):
            with self.subTest(state=state), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                root = Path(temp)
                path, a, _, _ = self.setup_sequence(root, state, True)
                original = tree(root)
                with self.assertRaisesRegex(ValueError, 'provider-final with old MainThread'):
                    a.preflight_sequence(root)
                self.assertEqual(tree(root), original)

    def test_partial_unknown_alias_vectors_and_fixed_guard_tampering(self):
        for failure in ('b-partial', 'a-unknown', 'a-hardlink', 'a-parent-symlink'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
                root = Path(temp)
                path, a, b_path, b = self.setup_sequence(root, 'trace-final', False)
                main = root / a.PROJECT / a.FILES[0][0]
                if failure == 'b-partial':
                    relative = b.FILES[0][0]
                    shutil.copy2(b_path / 'fixtures/final' / b.PROJECT / relative, root / b.PROJECT / relative)
                elif failure == 'a-unknown': main.write_bytes(main.read_bytes() + b'\nUNKNOWN\n')
                elif failure == 'a-hardlink': os.link(main, root / 'main-alias')
                else:
                    parent = main.parent
                    real = parent.with_name('actual-parent')
                    parent.rename(real)
                    parent.symlink_to(real, target_is_directory=True)
                original = tree(root)
                with self.assertRaises(ValueError): a.preflight_sequence(root)
                self.assertEqual(tree(root), original)
                self.assertFalse((root / '.ohos-qemu-patches').exists())
        with tempfile.TemporaryDirectory(dir=ENV['TMPDIR']) as temp:
            root = Path(temp)
            _, a, _, _ = self.setup_sequence(root, 'trace-final', True)
            original = tree(root)
            with self.assertRaisesRegex(ValueError, 'guard identity differs'):
                a._fixed_guard(a.B_COMPONENT, '0' * 64, 'never_imported_bad_guard')
            self.assertEqual(tree(root), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
