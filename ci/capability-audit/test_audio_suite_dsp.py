"""Exact ABI, patch ownership, installer guards and real DSP signal regression."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/multimedia/audio_framework/audio_suite_dsp'
FIXTURE = REPO / 'ci/capability-audit/fixtures/audio_suite/imedia_api.h'
spec = importlib.util.spec_from_file_location('qemu_audiosuite_dsp_installer', COMPONENT / 'apply.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class AudioSuiteDspTests(unittest.TestCase):
    def test_fixture_is_pinned_primary_ABI_except_final_newline(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()[:-1]).hexdigest(), installer.HEADER_HASH)

    def test_real_host_signal_processing_and_boundaries_with_sanitizers(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler, 'real host clang++ required, do not turn a missing compiler into a pass')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'dsp'
            subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I' + str(FIXTURE.parent),
                            str(REPO / 'ci/capability-audit/probes/audio_suite_dsp_host.cpp'),
                            '-o', str(binary)], check=True, capture_output=True)
            challenge = 'e1e6a3c2495a46d38c68f7f7bf963ad3'
            result = subprocess.run([str(binary), challenge], check=True, capture_output=True, text=True)
            rows = [json.loads(row) for row in result.stdout.splitlines()]
            self.assertEqual(len(rows), 150)
            self.assertTrue(all(row['run_id'] == challenge and row['pass'] is True for row in rows))
            self.assertEqual(rows[-1]['checks'], 149)
            self.assertEqual(rows[-1]['failures'], 0)
            self.assertEqual(rows[-1]['scope'], 'host_real_DSP_not_guest')
            boosted = [row['actual'] for row in rows if row['case'] == 'eq_left_center_plus6dB']
            cut = [row['actual'] for row in rows if row['case'] == 'eq_right_center_minus6dB']
            self.assertEqual(len(boosted), 10)
            self.assertEqual(len(cut), 10)
            self.assertTrue(all(abs(value - 6) < .08 for value in boosted))
            self.assertTrue(all(abs(value + 6) < .08 for value in cut))
            self.assertNotEqual(subprocess.run([str(binary), 'stale'], capture_output=True).returncode, 0)

    def run_installer(self, root, head=installer.REVISION, check_only=False):
        argv = ['apply.py', '--source-root', str(root)] + (['--check-only'] if check_only else [])
        def git(command, **kwargs):
            if command[-2:] == ['rev-parse', 'HEAD']: return head + '\n'
            return preimages()[command[-1].removeprefix('HEAD:')]
        with patch.object(sys, 'argv', argv), patch.object(installer.subprocess, 'check_output', side_effect=git), contextlib.redirect_stdout(io.StringIO()):
            installer.main()

    def fixture_root(self, root):
        project = root / 'foundation/multimedia/audio_framework'
        header = project / 'services/audio_suite/client/utils/include/imedia_api.h'
        header.parent.mkdir(parents=True)
        header.write_bytes(FIXTURE.read_bytes()[:-1])
        for name, original in preimages().items():
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            transform = installer.repaired_build if name == installer.BUILD else installer.repaired_configuration
            target.write_bytes(transform(original))
        return project, header

    def test_exact_revision_header_and_unknown_sources_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, header = self.fixture_root(root)
            with self.assertRaises(SystemExit): self.run_installer(root, head='master')
            header.write_bytes(header.read_bytes() + b'unknown')
            with self.assertRaises(SystemExit): self.run_installer(root)
            self.assertFalse((project / 'services/audio_suite/qemu_dsp').exists())
            header.write_bytes(FIXTURE.read_bytes()[:-1])
            destination = project / 'services/audio_suite/qemu_dsp'
            destination.mkdir()
            (destination / 'BUILD.gn').write_text('user change\n')
            with self.assertRaises(SystemExit): self.run_installer(root)
            self.assertEqual((destination / 'BUILD.gn').read_text(), 'user change\n')
            self.assertFalse((destination / 'qemu_audio_suite_dsp.cpp').exists())

    def test_installer_preflight_no_write_and_repeated_install_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, _ = self.fixture_root(root)
            self.run_installer(root, check_only=True)
            destination = project / 'services/audio_suite/qemu_dsp'
            self.assertFalse(destination.exists())
            for _ in range(2):
                self.run_installer(root)
                for name in ('BUILD.gn', 'qemu_audio_suite_dsp.cpp', 'qemu_audio_suite_dsp.map'):
                    self.assertEqual((destination / name).read_bytes(), (COMPONENT / 'files' / name).read_bytes())

    def test_exact_pre_specs_sources_upgrade_but_foreign_edit_is_preserved(self):
        import re
        old = (COMPONENT / 'files/qemu_audio_suite_dsp.cpp').read_text()
        old = re.sub(r'^constexpr uint32_t kPcmS16Le = .*\n', '', old, flags=re.MULTILINE)
        old = re.sub(r'\niMedia_Support_SPECS GetSpecs\(\)\n\{\n.*?\n\}\n', '', old, flags=re.DOTALL)
        old = re.sub(r'^iMedia_Support_SPECS iMedia_.*_GetSPECS\(\).*\n', '', old, flags=re.MULTILINE)
        old_map = ''.join(line for line in (COMPONENT / 'files/qemu_audio_suite_dsp.map').read_text()
                          .splitlines(keepends=True) if '_GetSPECS;' not in line)
        previous = {'qemu_audio_suite_dsp.cpp': old.encode(), 'qemu_audio_suite_dsp.map': old_map.encode()}
        self.assertEqual({name: hashlib.sha256(content).hexdigest() for name, content in previous.items()},
                         installer.PRE_SPECS_FILES)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, _ = self.fixture_root(root)
            self.run_installer(root)
            destination = project / 'services/audio_suite/qemu_dsp'
            for name, content in previous.items():
                (destination / name).write_bytes(content)
            self.run_installer(root, check_only=True)
            for name, content in previous.items():
                self.assertEqual((destination / name).read_bytes(), content)
            self.run_installer(root)
            for name in previous:
                self.assertEqual((destination / name).read_bytes(), (COMPONENT / 'files' / name).read_bytes())
            for name, content in previous.items():
                (destination / name).write_bytes(content)
            changed = previous['qemu_audio_suite_dsp.cpp'] + b'// foreign edit\n'
            (destination / 'qemu_audio_suite_dsp.cpp').write_bytes(changed)
            with self.assertRaises(SystemExit):
                self.run_installer(root)
            self.assertEqual((destination / 'qemu_audio_suite_dsp.cpp').read_bytes(), changed)
            self.assertEqual((destination / 'qemu_audio_suite_dsp.map').read_bytes(), previous['qemu_audio_suite_dsp.map'])

    def test_source_child_symlink_rejected_without_touching_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, _ = self.fixture_root(root)
            outside = root / 'outside'
            outside.mkdir()
            (project / 'services/audio_suite/qemu_dsp').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(SystemExit): self.run_installer(root)
            self.assertEqual(list(outside.iterdir()), [])

    def test_configuration_symlink_rejected_before_patch_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, _ = self.fixture_root(root)
            target = project / installer.CONFIG
            outside = root / 'outside-configuration.xml'
            original = target.read_bytes()
            target.unlink()
            outside.write_bytes(original)
            target.symlink_to(outside)
            with self.assertRaises(SystemExit): self.run_installer(root, check_only=True)
            self.assertEqual(outside.read_bytes(), original)

    def test_patch_routes_only_three_real_effects_and_applies_twice(self):
        patch_file = COMPONENT / '0001-package-real-cpu-effects.patch'
        added = [row for row in patch_file.read_text().splitlines() if row.startswith('+') and not row.startswith('+++')]
        self.assertEqual(sum('libqemu_audio_suite_dsp.z.so' in row for row in added), 3)
        self.assertFalse(any('NOISE_REDUCTION' in row or 'AUDIO_SEPARATION' in row for row in added))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for section in patch_file.read_text().split('diff --git ')[1:]:
                name = section.split('+++ b/')[1].splitlines()[0]
                hunk = section.split('@@', 2)[2].splitlines()[1:]
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('\n'.join(row[1:] for row in hunk if row.startswith((' ', '-'))) + '\n')
            helper = REPO / 'patches/lib/apply_component_dir.sh'
            for _ in range(2):
                subprocess.run(['bash', str(helper), str(COMPONENT), '--source-root', str(root)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(patch_file)], check=True)

    def test_real_library_package_feature_and_pretraversal_wiring(self):
        gn = (COMPONENT / 'files/BUILD.gn').read_text()
        self.assertIn('if (audio_framework_feature_audiosuite_support)', gn)
        self.assertIn('ohos_shared_library("qemu_audio_suite_dsp")', gn)
        self.assertIn('install_enable = true', gn)
        self.assertIn('part_name = "audio_framework"', gn)
        for flag in ('cfi = true', 'cfi_cross_dso = true', 'debug = false',
                     'integer_overflow = true', 'ubsan = true', 'boundary_sanitize = true'):
            self.assertIn(flag, gn)
        self.assertNotIn('allow_sanitize_debug', gn)
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertLess(builder.index('bash "${AUDIO_SUITE_DSP_COMPONENT_SCRIPT}"'),
                        builder.index('  write_source_preparation_metadata'))

    def test_stale_marker_or_altered_configuration_cannot_enable_DSP(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, _ = self.fixture_root(root)
            for name, original in preimages().items():
                target = project / name
                patched = target.read_bytes()
                target.write_bytes(original)
                self.run_installer(root, check_only=True)
                with self.assertRaises(SystemExit): self.run_installer(root)
                target.write_bytes(patched + b'unknown source edit')
                with self.assertRaises(SystemExit): self.run_installer(root, check_only=True)
                self.assertFalse((project / 'services/audio_suite/qemu_dsp').exists())
                target.write_bytes(patched)


def preimages():
    result = {}
    for section in (COMPONENT / '0001-package-real-cpu-effects.patch').read_text().split('diff --git ')[1:]:
        name = section.split('+++ b/')[1].splitlines()[0].removeprefix('foundation/multimedia/audio_framework/')
        hunk = section.split('@@', 2)[2].splitlines()[1:]
        result[name] = ('\n'.join(row[1:] for row in hunk if row.startswith((' ', '-'))) + '\n').encode()
    return result


if __name__ == '__main__':
    unittest.main()
