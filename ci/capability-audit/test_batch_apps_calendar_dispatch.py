"""Run the exact product callback delta on distinct UI/JS threads; no guest claim."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_apps/calendar_dispatch'
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/editor_callback_dispatch'
PROJECT = 'applications/standard/calendardata'

class CalendarDispatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='batch-apps-calendar-dispatch-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / PROJECT
        self.meta = json.loads((FIXTURE / 'provenance.json').read_text())
        for relative, record in self.meta['files'].items():
            data = gzip.decompress(base64.b64decode((FIXTURE / record['fixture']).read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)], capture_output=True, text=True)

    def test_exact_predecessor_idempotence_and_drift(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, digest in self.meta['patched_sha256'].items():
            self.assertEqual(hashlib.sha256((self.project/path).read_bytes()).hexdigest(), digest)
        self.assertEqual(self.apply().returncode, 0)
        path = self.project/'calendarmanager/napi/src/calendar_manager_napi.cpp'
        path.write_text(path.read_text()+'\n// unknown drift\n')
        before=path.read_bytes()
        self.assertNotEqual(self.apply().returncode,0)
        self.assertEqual(path.read_bytes(),before)

    def test_composes_after_exact_provider_editor_predecessor(self):
        fixture=ROOT/'ci/capability-audit/fixtures/batch_apps/calendar_editor'
        meta=json.loads((fixture/'provenance.json').read_text())
        for relative,record in meta['files'].items():
            target=self.project/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(gzip.decompress(base64.b64decode((fixture/record['fixture']).read_bytes())))
        editor=ROOT/'patches/common/applications/standard/calendardata/event_editor'
        result=subprocess.run(['bash',str(editor/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=self.apply()
        self.assertEqual(result.returncode,0,result.stderr)
        for path,digest in self.meta['patched_sha256'].items():
            self.assertEqual(hashlib.sha256((self.project/path).read_bytes()).hexdigest(),digest)

    def test_real_functions_thread_scope_cleanup_destroy_and_weak_ownership(self):
        result = self.apply()
        self.assertEqual(result.returncode,0,result.stderr)
        cpp=(self.project/'calendarmanager/napi/src/calendar_manager_napi.cpp').read_text()
        header=(self.project/'calendarmanager/napi/include/calendar_manager_napi.h').read_text()
        context=header[header.index('    struct EditorEnvironment {'):header.index('    static napi_value New(')]
        functions=cpp[cpp.index('void CalendarManagerNapi::CleanupEditorEnvironment('):cpp.index('napi_value CalendarManagerNapi::New(')]
        code=(FIXTURE/'napi_harness.cpp').read_text().replace('// INSERT_CONTEXT',context).replace('// INSERT_FUNCTIONS',functions)
        self.assertNotIn('napi_value',context)
        harness=self.root/'dispatch.cpp';harness.write_text(code)
        binary=self.root/'dispatch'
        result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-pthread',str(harness),'-o',str(binary)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':
    unittest.main()
