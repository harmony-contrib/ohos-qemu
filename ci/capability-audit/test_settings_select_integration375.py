"""Cross-component host checks over retained actual source bytes; no IPC claim."""
import importlib.util
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
from batch_apps_select375_fixture import COMPONENT, installer, materialize

class SelectIntegration(unittest.TestCase):
    def test_successor_guards_and_actual_CLI_reject_incomplete_vector(self):
        with tempfile.TemporaryDirectory(prefix='select375-core-') as temporary:
            root = Path(temporary).resolve(); materialize(root)
            # Retained chooser vector does not include the two unchanged input
            # extension files. Materialize them using their actual predecessor
            # fixtures and actual component installer, never invented stubs.
            import test_settings_external_input as external
            fixture = external.SettingsExternalInputTests('test_exact_and_idempotent')
            fixture.setUp(); self.addCleanup(fixture.doCleanups)
            applied = fixture.apply(); self.assertEqual(applied.returncode, 0, applied.stderr)
            for relative, before, after in external.baseline.FILES:
                if before is None:
                    target = root / external.baseline.PROJECT / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((fixture.project / relative).read_bytes())
            app = installer(); value = app.manifest()
            with mock.patch.object(app, 'revisions'): app.apply(root)
            real = subprocess.check_output
            for project in value['projects']: (root / project / '.git').mkdir()
            def git(argv, *args, **kwargs):
                if argv[:2] == ['git', '-C'] and len(argv) >= 5 and argv[3] == 'rev-parse':
                    project = Path(argv[2]).relative_to(root).as_posix()
                    if argv[4:] in (['--verify', 'HEAD^{commit}'], ['HEAD']): return value['projects'][project] + '\n'
                    if argv[4:] == ['--show-toplevel']: return argv[2] + '\n'
                return real(argv, *args, **kwargs)
            with mock.patch.object(subprocess, 'check_output', side_effect=git):
                for name in ('share_picker', 'wallpaper_settings', 'external_input'):
                    spec = importlib.util.spec_from_file_location('select375_core_' + name, COMPONENT.parent / name / 'verify_source.py')
                    guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
                    self.assertTrue(guard.validate(root, require_patched=True))
                argv = ['verify_source.py', '--source-root', str(root), '--require-patched']
                before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with mock.patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()) as output:
                    runpy.run_path(str(COMPONENT / 'verify_source.py'), run_name='__main__')
                self.assertEqual(output.getvalue().strip(), 'patched')
                self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()})
                native = root / 'foundation/ability/ability_runtime/services/abilitymgr/src/ability_manager_service.cpp'
                native.write_bytes(native.read_bytes() + b'// unknown native state\n')
                with mock.patch.object(sys, 'argv', argv), self.assertRaises(ValueError):
                    runpy.run_path(str(COMPONENT / 'verify_source.py'), run_name='__main__')

if __name__ == '__main__': unittest.main()
