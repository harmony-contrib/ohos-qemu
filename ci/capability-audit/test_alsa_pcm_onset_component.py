#!/usr/bin/env python3
"""Pure-file regression; no GN, target compiler, build.sh, SDK, Git or resources."""
import hashlib
import difflib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / 'fixtures/alsa_pcm_onset'
BEFORE = FIXTURES / 'before'
C = ROOT / 'patches/common/third_party/alsa-lib/pcm_onset'
SPEC = importlib.util.spec_from_file_location('component452', C / 'apply.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
SCRIPT = ROOT / 'scripts/build_standard_qemu_in_docker.sh'
MODIFIED = [name for name, entry in M.FILES.items() if not entry['guard_only']]


def file_state(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ['symlink', os.readlink(path)]
        elif path.is_file():
            result[str(path.relative_to(root))] = ['file', hashlib.sha256(path.read_bytes()).hexdigest()]
    return result


def after_bytes(relative):
    entry = M.FILES[relative]
    if entry['guard_only']:
        return (BEFORE / relative).read_bytes()
    return (C / 'files' / entry['payload']).read_bytes()


def make_tree(root, after=False):
    shutil.copytree(BEFORE / 'third_party', root / 'third_party')
    if after:
        for relative in MODIFIED:
            (root / relative).write_bytes(after_bytes(relative))
    return root


def product_patch():
    # Exactly the reviewed452 full diff, derived from before fixtures and the
    # canonical payloads. No redundant after-source fixture is installed.
    chunks = []
    for relative in M.FILES:
        path = BEFORE / relative
        before = path.read_bytes() if path.exists() else None
        after = after_bytes(relative)
        if before != after:
            chunks.extend(difflib.unified_diff((before or b'').decode().splitlines(True),
                after.decode().splitlines(True), fromfile='a/' + relative if before is not None else '/dev/null',
                tofile='b/' + relative))
    return ''.join(chunks)


def block(source, start, end):
    return source.split(start, 1)[1].split(end, 1)[0]


class PureFiles452(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='alsa-pcm-onset-case-')
        self.t = Path(self.tmp.name)
        self.root = make_tree(self.t / 'source')

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, component=C):
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(self.root), *args],
                              capture_output=True, text=True, timeout=15)

    def reject_preserving(self, function):
        before = file_state(self.root)
        with self.assertRaises((ValueError, OSError)):
            function()
        self.assertEqual(file_state(self.root), before)

    def test_01_pristine_readonly_and_default_off(self):
        before = file_state(self.root)
        self.assertEqual(M.validate(self.root), 'before')
        self.assertEqual(M.gn_argument(self.root, '0'), '')
        self.assertEqual(before, file_state(self.root))
        self.assertFalse((self.root / '.ohos-qemu-patches').exists())
        self.reject_preserving(lambda: M.gn_argument(self.root, '1'))

    def test_02_apply_complete_exact_after_and_guard_not_written(self):
        guard = self.root / 'third_party/alsa-lib/src/pcm/pcm_local.h'
        metadata = guard.stat()
        M.run(self.root)
        self.assertEqual(M.validate(self.root, True), 'after')
        for name, entry in M.FILES.items():
            self.assertEqual(M.digest((self.root / name).read_bytes()), entry['after'])
        self.assertEqual((metadata.st_ino, metadata.st_mtime_ns), (guard.stat().st_ino, guard.stat().st_mtime_ns))

    def test_03_after_idempotent_inode_mtime_and_modes(self):
        for name in M.FILES:
            path = self.root / name
            if path.exists():
                path.chmod(0o640)
        M.run(self.root)
        before = {name: (p.stat().st_ino, p.stat().st_mtime_ns, stat.S_IMODE(p.stat().st_mode))
                  for name in M.FILES for p in [self.root / name]}
        M.run(self.root)
        after = {name: (p.stat().st_ino, p.stat().st_mtime_ns, stat.S_IMODE(p.stat().st_mode))
                 for name in M.FILES for p in [self.root / name]}
        self.assertEqual(before, after)
        self.assertEqual(before['third_party/alsa-lib/BUILD.gn'][2], 0o640)
        self.assertEqual(before['third_party/alsa-lib/src/pcm/media398_onset.h'][2], 0o644)
        self.assertEqual(M.gn_argument(self.root, '1'), M.GN_ARG + '=true')
        self.assertEqual(M.gn_argument(self.root, '0'), M.GN_ARG + '=false')

    def test_04_all_four_file_mixed_combinations_reject(self):
        # 16 finite tuples: precisely all-before and all-after are admissible.
        for bits in itertools.product((0, 1), repeat=4):
            with self.subTest(bits=bits):
                shutil.rmtree(self.root)
                make_tree(self.root)
                for bit, name in zip(bits, MODIFIED):
                    if bit:
                        (self.root / name).write_bytes(after_bytes(name))
                before = file_state(self.root)
                if all(bits):
                    self.assertEqual(M.validate(self.root), 'after')
                elif not any(bits):
                    self.assertEqual(M.validate(self.root), 'before')
                else:
                    for check in (lambda: M.validate(self.root), lambda: M.gn_argument(self.root, '0'),
                                  lambda: M.gn_argument(self.root, '1'), lambda: M.run(self.root)):
                        with self.assertRaises(ValueError):
                            check()
                        self.assertEqual(file_state(self.root), before)

    def test_05_unknown_bytes_each_managed_target_reject(self):
        for name in M.FILES:
            with self.subTest(name=name):
                shutil.rmtree(self.root)
                make_tree(self.root)
                path = self.root / name
                path.write_bytes((path.read_bytes() if path.exists() else b'') + b'unknown452\n')
                self.reject_preserving(lambda: M.run(self.root))
                self.reject_preserving(lambda: M.gn_argument(self.root, '0'))

    def test_06_missing_guard_and_required_original_reject(self):
        for name in ('third_party/alsa-lib/BUILD.gn', 'third_party/alsa-lib/src/pcm/pcm_hw.c',
                     'third_party/alsa-lib/src/pcm/pcm_local.h'):
            with self.subTest(name=name):
                shutil.rmtree(self.root)
                make_tree(self.root)
                (self.root / name).unlink()
                self.reject_preserving(lambda: M.run(self.root))

    def test_07_each_target_symlink_and_nonregular_reject(self):
        for name in M.FILES:
            for kind in ('symlink', 'directory', 'fifo'):
                with self.subTest(name=name, kind=kind):
                    shutil.rmtree(self.root)
                    make_tree(self.root)
                    p = self.root / name
                    if p.exists():
                        p.unlink()
                    if kind == 'symlink':
                        p.symlink_to(self.t / 'outside')
                    elif kind == 'directory':
                        p.mkdir()
                    else:
                        os.mkfifo(p)
                    before = {x: (self.root / x).lstat().st_mode if (self.root / x).exists() else None
                              for x in M.FILES}
                    with self.assertRaises((ValueError, OSError)):
                        M.run(self.root)
                    after = {x: (self.root / x).lstat().st_mode if (self.root / x).exists() else None
                             for x in M.FILES}
                    self.assertEqual(before, after)

    def test_08_parent_and_root_symlinks_reject(self):
        pcm = self.root / 'third_party/alsa-lib/src/pcm'
        moved = self.t / 'pcm-external'
        pcm.rename(moved)
        pcm.symlink_to(moved)
        with self.assertRaises(ValueError):
            M.run(self.root)
        link = self.t / 'root-link'
        link.symlink_to(self.root)
        with self.assertRaises(ValueError):
            M.run(link)

    def test_09_lock_symlink_reject(self):
        directory = self.root / '.ohos-qemu-patches'
        directory.mkdir()
        (directory / 'alsa-pcm-onset.lock').symlink_to(self.t / 'outside-lock')
        self.reject_preserving(lambda: M.run(self.root))
        self.assertFalse((self.t / 'outside-lock').exists())

    def test_10_payload_manifest_extra_file_reject_before_write(self):
        for change in ('payload', 'manifest', 'extra', 'symlink'):
            with self.subTest(change=change):
                copy = self.t / ('component-' + change)
                shutil.copytree(C, copy)
                if change == 'payload':
                    (copy / 'files/media398_wire.h').write_bytes(b'not443')
                elif change == 'manifest':
                    j = json.loads((copy / 'source_states.json').read_text())
                    j['files']['third_party/alsa-lib/BUILD.gn']['before']['sha256'] = '0' * 64
                    (copy / 'source_states.json').write_text(json.dumps(j))
                elif change == 'extra':
                    (copy / 'files/unregistered.c').write_bytes(b'unregistered')
                else:
                    p = copy / 'files/pcm_hw.c'
                    p.unlink()
                    p.symlink_to(C / 'files/pcm_hw.c')
                before = file_state(self.root)
                result = self.cli(component=copy)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(file_state(self.root), before)
                self.assertFalse((self.root / '.ohos-qemu-patches').exists())

    def test_11_cli_machine_output_and_nonmutating_checks(self):
        a = self.cli('--check')
        self.assertEqual((a.returncode, a.stdout), (0, 'before\n'))
        a = self.cli('--gn-arg', '0')
        self.assertEqual((a.returncode, a.stdout), (0, ''))
        self.assertEqual(self.cli('--require-patched').returncode, 1)
        self.assertFalse((self.root / '.ohos-qemu-patches').exists())
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.cli('--gn-arg', '1').stdout, M.GN_ARG + '=true\n')
        self.assertEqual(self.cli('--gn-arg', '0').stdout, M.GN_ARG + '=false\n')
        self.assertEqual(self.cli('--gn-arg', '2').returncode, 2)
        with self.assertRaises(ValueError):
            M.gn_argument(self.root, 'true')

    def test_12_gn_only_target_local_default_false_other_blocks_exact(self):
        rel = 'third_party/alsa-lib/BUILD.gn'
        before, after = (BEFORE / rel).read_text(), after_bytes(rel).decode()
        self.assertIn('alsa_lib_pcm_onset_diagnostic_enable = false', after)
        self.assertEqual(after.count('MEDIA398_ONSET_DIAGNOSTIC=1'), 1)
        self.assertEqual(block(before, 'config("alsa_lib_config") {', 'ohos_shared_library("libasound")'),
                         block(after, 'config("alsa_lib_config") {', 'ohos_shared_library("libasound")'))
        self.assertEqual(before.split('ohos_shared_library("libalsa_midi")', 1)[1],
                         after.split('ohos_shared_library("libalsa_midi")', 1)[1])
        addition = ('  if (alsa_lib_pcm_onset_diagnostic_enable) {\n'
                    '    defines = [ "MEDIA398_ONSET_DIAGNOSTIC=1" ]\n  }\n')
        b = block(before, 'ohos_shared_library("libasound") {\n', 'ohos_shared_library("libalsa_midi")')
        a = block(after, 'ohos_shared_library("libasound") {\n', 'ohos_shared_library("libalsa_midi")')
        self.assertEqual(a, addition + b)
        self.assertNotIn('MEDIA398_ONSET_DIAGNOSTIC=0', after)

    def test_13_443_product_three_payloads_exact(self):
        expected = {'pcm_hw.c': 'd6dfc03c36ec0d78414c39047e43e55d81f3d0497361235aea40c977ea949f71',
                    'media398_onset.h': '7dd8cf8102dda20a9211e9d56e79416626fcaf5c8ddc449ace5bd37fcc9438d2',
                    'media398_wire.h': '89e44af7fcc7f2f40e1fb60bdc9fba26de690049034f9d5e943d6b65b50be1da'}
        for name, sha in expected.items():
            self.assertEqual(M.digest((C / 'files' / name).read_bytes())['sha256'], sha)
        self.assertEqual(M.FILES['third_party/alsa-lib/src/pcm/pcm_local.h']['before'],
                         M.FILES['third_party/alsa-lib/src/pcm/pcm_local.h']['after'])

    def test_14_full_product_patch_replay_and_reverse(self):
        patch = self.t / 'pcm-onset452-complete.patch'
        patch.write_text(product_patch())
        def execute(*args):
            x = subprocess.run(['patch', '-p1', *args, '-i', str(patch)], cwd=self.root,
                               capture_output=True, text=True, timeout=15)
            self.assertEqual(x.returncode, 0, x.stdout + x.stderr)
        execute('--dry-run')
        self.assertEqual(M.validate(self.root), 'before')
        execute()
        self.assertEqual(M.validate(self.root, True), 'after')
        execute('--reverse')
        self.assertEqual(M.validate(self.root), 'before')

    def test_15_script_syntax_and_exact_diff_replay(self):
        for path in (SCRIPT, C / 'apply.sh'):
            x = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True, timeout=15)
            self.assertEqual(x.returncode, 0, x.stderr)
        destination = self.t / 'script-replay'
        (destination / 'scripts').mkdir(parents=True)
        path = destination / 'scripts/build_standard_qemu_in_docker.sh'
        shutil.copyfile(BEFORE / 'scripts/build_standard_qemu_in_docker.sh', path)
        diff = FIXTURES / 'build_standard_qemu_in_docker452.diff'
        x = subprocess.run(['patch', '-p1', '-i', str(diff)], cwd=destination,
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(x.returncode, 0, x.stdout + x.stderr)
        # The historical452 patch remains immutable. Strip only the exact
        # reviewed CFI wiring successor; every other build-script byte must still
        # equal the complete452 postimage, so unknown edits remain rejected.
        current = SCRIPT.read_text()
        cfi_constants = 'QRCODE_CFI_COMPONENT_SCRIPT="${PATCH_ROOT}/common/commonlibrary/qrcode_generator/cfi_metadata/apply.sh"\nACE_SEC_CFI_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/bounds_checking_function/ace_cfi/apply.sh"\nARKUI_CFI_COVERAGE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/arkui/ace_engine/cfi_coverage/apply.sh"\n'
        cfi_source_plan = '  bash "${QRCODE_CFI_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \\\n    2>&1 | tee "${CACHE_ROOT}/logs/apply_qrcode_cfi_metadata.log"\n  python3 "${QRCODE_CFI_COMPONENT_SCRIPT%/*}/verify_source.py" --source-root "${OHOS_ROOT}" --require-patched \\\n    2>&1 | tee "${CACHE_ROOT}/logs/verify_qrcode_cfi_metadata.log"\n  bash "${ACE_SEC_CFI_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \\\n    2>&1 | tee "${CACHE_ROOT}/logs/apply_ace_sec_cfi.log"\n  python3 "${ACE_SEC_CFI_COMPONENT_SCRIPT%/*}/verify_source.py" --source-root "${OHOS_ROOT}" --require-patched \\\n    2>&1 | tee "${CACHE_ROOT}/logs/verify_ace_sec_cfi.log"\n  bash "${ARKUI_CFI_COVERAGE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \\\n    2>&1 | tee "${CACHE_ROOT}/logs/apply_arkui_cfi_coverage.log"\n  python3 "${ARKUI_CFI_COVERAGE_COMPONENT_SCRIPT%/*}/verify_source.py" --source-root "${OHOS_ROOT}" --require-patched \\\n    2>&1 | tee "${CACHE_ROOT}/logs/verify_arkui_cfi_coverage.log"\n'
        for added in (cfi_constants, cfi_source_plan):
            self.assertEqual(current.count(added), 1)
            current = current.replace(added, '', 1)
        self.assertEqual(path.read_bytes(), current.encode())

    def test_16_actual_build_array_query_block_records_exact_arg(self):
        # Execute only the literal newly added finite argv block. No build.sh,
        # full launcher, GN or stub production receipt is executed/generated.
        source = SCRIPT.read_text()
        start = source.index('  local pcm_onset_gn_arg\n')
        end = source.index('  if [ -n "${DEVICE_TYPE}" ]; then', start)
        added = source[start:end]
        self.assertIn('build_args+=(--gn-args "${pcm_onset_gn_arg}")', added)
        program = ('set -euo pipefail\nrecord() {\nlocal build_args=(./build.sh --deps-guard=false)\n' +
                   added + 'printf "%s\\0" "${build_args[@]}"\n}\nrecord\n')
        for state, enabled, success, suffix in (
                ('before', '0', True, []), ('before', '1', False, []),
                ('after', '0', True, ['--gn-args', M.GN_ARG + '=false']),
                ('after', '1', True, ['--gn-args', M.GN_ARG + '=true'])):
            with self.subTest(state=state, enabled=enabled):
                shutil.rmtree(self.root)
                make_tree(self.root, after=(state == 'after'))
                env = dict(os.environ, ALSA_PCM_ONSET_COMPONENT_SCRIPT=str(C / 'apply.sh'),
                           OHOS_ROOT=str(self.root), QEMU_PCM_ONSET_COMPONENT=enabled)
                x = subprocess.run(['bash', '-c', program], env=env, capture_output=True, timeout=15)
                self.assertEqual(x.returncode == 0, success, x.stderr)
                if success:
                    argv = x.stdout.rstrip(b'\0').decode().split('\0')
                    self.assertEqual(argv, ['./build.sh', '--deps-guard=false', *suffix])
                self.assertFalse((self.root / '.ohos-qemu-patches').exists())

    def test_17_build_wiring_before_load_and_argv_evidence(self):
        text = SCRIPT.read_text()
        start = text.index('build_product() {')
        text = text[start:text.index('\npackage_product()', start)]
        self.assertLess(text.index('local build_args=('), text.index('local pcm_onset_gn_arg'))
        self.assertLess(text.index('local pcm_onset_gn_arg'), text.index('"${build_args[@]}" --device-type default --build-only-load=true'))
        self.assertLess(text.index('local pcm_onset_gn_arg'), text.index('qemu-full-build-argv.json'))
        all_text = SCRIPT.read_text()
        self.assertIn('QEMU_PCM_ONSET_COMPONENT="${QEMU_PCM_ONSET_COMPONENT:-1}"', all_text)
        toggles = block(all_text, 'apply_qemu_runtime_components() {', 'case "${QEMU_JSVM_COMPONENT}"')
        self.assertIn('"${QEMU_PCM_ONSET_COMPONENT}"', toggles)
        self.assertIn('must be 0 or 1', toggles)
        plan = block(all_text, 'apply_qemu_capability_patch_plan() {', '\nmain() {')
        self.assertIn('if [ "${QEMU_PCM_ONSET_COMPONENT}" = "1" ]; then', plan)
        self.assertIn('--source-root "${OHOS_ROOT}" --gn-arg 0', plan)
        self.assertLess(plan.index('apply_qemu_runtime_components'), plan.index('apply_alsa_pcm_onset_component.log'))

    def test_18_readonly_full_after_queries_create_no_markers(self):
        shutil.rmtree(self.root)
        make_tree(self.root, after=True)
        before = file_state(self.root)
        self.assertEqual(self.cli('--require-patched').returncode, 0)
        for enabled in ('0', '1'):
            self.assertEqual(self.cli('--gn-arg', enabled).returncode, 0)
        self.assertEqual(file_state(self.root), before)
        self.assertFalse((self.root / '.ohos-qemu-patches').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
