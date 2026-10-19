"""Actual recipe fragments with isolated host callbacks; no product resources."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/build_standard_qemu_in_docker.sh'
PACKAGER = ROOT / 'scripts/package_standard_qemu.sh'
COMPONENTS = (
    ('ARKUI_IDENTITY_CFI_COMPONENT_SCRIPT',
     'common/foundation/arkui/ace_engine/ui_extension_identity_cfi'),
    ('QRCODE_CFI_COMPONENT_SCRIPT',
     'common/commonlibrary/qrcode_generator/cfi_metadata'),
    ('ACE_SEC_CFI_COMPONENT_SCRIPT',
     'common/third_party/bounds_checking_function/ace_cfi'),
    ('ARKUI_CFI_COVERAGE_COMPONENT_SCRIPT',
     'common/foundation/arkui/ace_engine/cfi_coverage'),
)


def source_fragment(text):
    begin = text.index('  bash "${ARKUI_IDENTITY_CFI_COMPONENT_SCRIPT}"')
    end = text.index('  python3 "${SCRIPT_DIR}/verify_ui_extension_identity_batch.py"', begin)
    return text[begin:end]


def native_fragment(text):
    begin = text.index('verify_ace_cfi_native_closure() {\n')
    end = text.index('\ncase "${PRODUCT}" in', begin)
    return text[begin:end]


class CFIRecipe376(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cfi-recipe-HOST-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = SCRIPT.read_text()
        self.packager = PACKAGER.read_text()
        (self.root / 'cache/logs').mkdir(parents=True)
        self.env = dict(os.environ, TRACE=str(self.root / 'trace'),
                        OHOS_ROOT=str(self.root / 'source with spaces'),
                        CACHE_ROOT=str(self.root / 'cache'),
                        SCRIPT_DIR=str(self.root / 'checkout with spaces/scripts'),
                        PACKAGER=str(self.root / 'checkout with spaces/scripts/package.sh'),
                        PACKAGE_ROOT=str(self.root / 'new package'),
                        DEVICE_TYPE='phone', DEVICE_TYPE_BUILD_PROFILE='qemu_phone_full_source',
                        DEVICE_TYPE_PROFILE='qemu_phone_full_source',
                        SOURCE_ROOT=str(self.root / 'source with spaces'),
                        FAIL_COMMAND='', FAIL_STATUS='17', PACKAGER_STATUS='0')
        for variable, relative in COMPONENTS:
            self.env[variable] = str(self.root / 'patch root' / relative / 'apply.sh')

    def execute(self, program, **environment):
        trace = Path(self.env['TRACE'])
        trace.unlink(missing_ok=True)
        mocks = r'''
set -euo pipefail
event() {
  printf '%s\0' __event__ "$@" >> "$TRACE"
  if [ "$2" = "$FAIL_COMMAND" ]; then return "$FAIL_STATUS"; fi
}
bash() { event bash "$@" || return $?; return "$PACKAGER_STATUS"; }
python3() { event python3 "$@"; }
validate_prebuilt_haps() { event validate_prebuilt_haps "$@"; }
'''
        result = subprocess.run(['bash', '-c', mocks + program],
                                env=dict(self.env, **environment),
                                capture_output=True, text=True, timeout=15)
        events = []
        if trace.exists():
            values = trace.read_bytes().split(b'\0')
            self.assertEqual(values.pop(), b'')
            for value in values:
                value = value.decode()
                if value == '__event__': events.append([])
                else: events[-1].append(value)
        return result, events

    def expected_source(self):
        result = []
        for variable, _ in COMPONENTS:
            apply = self.env[variable]
            result.append(['bash', apply, '--source-root', self.env['OHOS_ROOT']])
            result.append(['python3', str(Path(apply).with_name('verify_source.py')),
                           '--source-root', self.env['OHOS_ROOT'], '--require-patched'])
        return result

    def test_exact_fixed_paths_and_order_before_traversal(self):
        for variable, relative in COMPONENTS:
            self.assertEqual(self.source.count(
                variable + '="${PATCH_ROOT}/' + relative + '/apply.sh"'), 1)
        plan = self.source.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        fragment = source_fragment(self.source)
        self.assertIn(fragment, plan)
        self.assertEqual(fragment.count('--require-patched'), 4)
        main = self.source.split('\nmain() {', 1)[1]
        # Both entry modes use the one plan. PREPARE_ONLY returns before build.
        patch_only, ordinary = main.split('  prepare_source_and_sdk', 1)
        self.assertIn('apply_qemu_capability_patch_plan', patch_only)
        self.assertNotIn('build_product ', patch_only)
        self.assertLess(ordinary.index('apply_qemu_capability_patch_plan'),
                        ordinary.index('if [ "${PREPARE_ONLY}" = "1" ]'))
        self.assertLess(ordinary.index('if [ "${PREPARE_ONLY}" = "1" ]'),
                        ordinary.index('build_product "${product}"'))

    def test_actual_source_fragment_dispatch_and_replay(self):
        result, events = self.execute(source_fragment(self.source) * 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, self.expected_source() * 2)

    def test_each_apply_and_verifier_failure_stops_later_components(self):
        expected = self.expected_source()
        for index, event in enumerate(expected):
            with self.subTest(index=index):
                result, events = self.execute(source_fragment(self.source), FAIL_COMMAND=event[1])
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertEqual(events, expected[:index + 1])

    def test_native_guard_exact_argv_both_profiles_all_three_products(self):
        for profile in ('qemu_phone_full_source', 'qemu_2in1_full_source'):
            for product, arch in (('armv7a_virt', 'arm'), ('arm64_virt', 'arm64'),
                                  ('x86_64_virt', 'x86_64')):
                with self.subTest(profile=profile, product=product):
                    result, events = self.execute(native_fragment(self.packager) +
                                                  '\nverify_ace_cfi_native_closure\n',
                                                  PRODUCT=product, DEVICE_TYPE_PROFILE=profile)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(events, [
                        ['python3', self.env['SCRIPT_DIR'] + '/../ci/capability-audit/ace_cfi_closure_guard.py',
                         '--out', self.env['SOURCE_ROOT'] + '/out/' + product, '--arch', arch,
                         '--output', self.env['SOURCE_ROOT'] + '/out/' + product + '/ace-cfi-closure.json']])

    def test_native_guard_failure_cannot_reach_package_or_change_existing_payload(self):
        payload = self.root / 'old package'
        payload.write_bytes(b'original package remains untouched')
        command = self.env['SCRIPT_DIR'] + '/../ci/capability-audit/ace_cfi_closure_guard.py'
        result, events = self.execute(native_fragment(self.packager) +
            '\nverify_ace_cfi_native_closure\nrm -- "$PAYLOAD"\n',
            PRODUCT='arm64_virt', FAIL_COMMAND=command, PAYLOAD=str(payload))
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0:2], ['python3', command])
        self.assertEqual(payload.read_bytes(), b'original package remains untouched')

    def test_unknown_full_product_rejected_without_guard(self):
        for product in ('unknown', 'qemu-arm64-linux-min'):
            result, events = self.execute(native_fragment(self.packager) +
                '\nverify_ace_cfi_native_closure\n', PRODUCT=product)
            self.assertEqual(result.returncode, 2)
            self.assertIn('unsupported full-profile ACE CFI product', result.stderr)
            self.assertEqual(events, [])

    def test_default_parameter_only_and_min_keep_existing_scope(self):
        for profile in ('default', 'param_only'):
            for product in ('armv7a_virt', 'arm64_virt', 'x86_64_virt', 'qemu-arm64-linux-min'):
                with self.subTest(profile=profile, product=product):
                    result, events = self.execute(native_fragment(self.packager) +
                        '\nverify_ace_cfi_native_closure\n', PRODUCT=product, DEVICE_TYPE_PROFILE=profile)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(events, [])

    def test_actual_rewrite_package_branch_exits_without_native_guard(self):
        begin = self.packager.index('if [ -n "${REWRITE_PACKAGE}" ]; then')
        end = self.packager.index('\n\nif [ -n "${REWRITE_ARM64_LAUNCHER}" ]; then', begin)
        fragment = self.packager[begin:end]
        program = ('rewrite_package_launchers() { event rewrite "$@"; }\n' +
                   native_fragment(self.packager) + fragment + '\nverify_ace_cfi_native_closure\n')
        result, events = self.execute(program, SOURCE_ROOT='', PRODUCT='', OUTPUT_DIR='',
                                     REWRITE_PACKAGE='actual package with spaces', REWRITE_ARM64_LAUNCHER='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, [['rewrite', 'actual package with spaces']])

    def test_actual_arm64_launcher_rewrite_exits_without_native_guard(self):
        begin = self.packager.index('if [ -n "${REWRITE_ARM64_LAUNCHER}" ]; then',
                                    self.packager.index('if [ -n "${REWRITE_PACKAGE}" ]; then'))
        end = self.packager.index('\nfi', begin) + len('\nfi')
        launcher = self.root / 'launcher with spaces.sh'
        launcher.write_text('ACCEL_MODE="${QEMU_ACCEL:-auto}"\n')
        mocks = ('sed_in_place_extended() { event rewrite-sed "$@"; }\n'
                 'normalize_common_qemu_launcher() { event rewrite-normalize "$@"; }\n')
        program = mocks + native_fragment(self.packager) + self.packager[begin:end] + '\nverify_ace_cfi_native_closure\n'
        result, events = self.execute(program, SOURCE_ROOT='', PRODUCT='', OUTPUT_DIR='',
                                     REWRITE_ARM64_LAUNCHER=str(launcher), REWRITE_PACKAGE='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([event[0] for event in events], ['rewrite-sed', 'rewrite-normalize'])
        self.assertEqual(launcher.read_text(), 'ACCEL_MODE="${QEMU_ACCEL:-auto}"\n')

    def test_single_guard_precedes_package_mutation_and_native_claims_unchanged(self):
        self.assertNotIn('ace_cfi_closure_guard.py', self.source)
        self.assertEqual(self.packager.count('ace_cfi_closure_guard.py'), 1)
        self.assertEqual(self.packager.count('\nverify_ace_cfi_native_closure\n'), 1)
        call = self.packager.index('\nverify_ace_cfi_native_closure\n')
        self.assertLess(call, self.packager.index('rm -rf "${PACKAGE_DIR}"'))
        self.assertLess(self.packager.index('rewrite_package_launchers "${REWRITE_PACKAGE}"'), call)
        self.assertLess(self.packager.index('normalize_common_qemu_launcher \\'), call)
        self.assertIn('"new_package_boot_tested": false', self.packager)
        self.assertIn('"runtime_behavior_tested": false', self.packager)
        self.assertIn('"first_artifact_behavior_gate_passed": false', self.packager)

    def test_guard_receipt_copied_exactly_for_full_profiles_only(self):
        begin = self.packager.index('case "${DEVICE_TYPE_PROFILE}" in',
                                     self.packager.index('mkdir -p "${IMAGES_OUT}"'))
        end = self.packager.index('\nesac', begin) + len('\nesac')
        fragment = self.packager[begin:end]
        source = Path(self.env['SOURCE_ROOT']) / 'out/arm64_virt/ace-cfi-closure.json'
        source.parent.mkdir(parents=True)
        raw = b'{"scope":"HOST literal receipt-copy fixture ONLY","runtime_passed":false}\n'
        source.write_bytes(raw)
        package = self.root / 'package'
        package.mkdir()
        for profile in ('qemu_phone_full_source', 'qemu_2in1_full_source', 'default', 'param_only'):
            destination = package / 'ace-cfi-closure.json'
            destination.unlink(missing_ok=True)
            result, events = self.execute(fragment, PRODUCT='arm64_virt',
                                          DEVICE_TYPE_PROFILE=profile, PACKAGE_DIR=str(package))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(events, [])
            if profile.endswith('_full_source'):
                self.assertEqual(destination.read_bytes(), raw)
            else:
                self.assertFalse(destination.exists())
        self.assertEqual(source.read_bytes(), raw)

    def test_load_and_prepare_cannot_run_native_guard(self):
        main = self.source.split('\nmain() {', 1)[1]
        self.assertIn('    build_product "${product}"\n'
                      '    if [ "${BUILD_ONLY_LOAD}" != "1" ]; then\n'
                      '      package_product "${product}"', main)
        build = self.source.split('build_product() {', 1)[1].split('\npackage_product()', 1)[0]
        self.assertIn('"${build_args[@]}" 2>&1 | tee', build)
        self.assertIn('--keep-ninja-going', build)
        self.assertIn('--log-mode=normal', build)
        self.assertIn('--build-only-load=false', build)
        self.assertIn('local pcm_onset_gn_arg', build)


if __name__ == '__main__':
    unittest.main(verbosity=2)
