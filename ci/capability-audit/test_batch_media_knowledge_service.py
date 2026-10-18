"""Execute the actual fixed-wire/service gate bodies with host doubles only."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / 'patches/common/foundation/multimedia/media_library/knowledge_holiday_index'
FIX = ROOT / 'ci/capability-audit/fixtures/batch_media/knowledge/holiday'


class KnowledgeServiceTests(unittest.TestCase):
    def test_actual_typed_wire_and_server_auth_query_failure_counterexamples(self):
        spec = importlib.util.spec_from_file_location('knowledge_service_transforms', COMP / 'transforms.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='knowledge-service-host-') as temporary:
            root = Path(temporary)
            source = (FIX / 'service_harness.cpp').read_text().replace('// ACTUAL_SERVICE_QUERY', module.SERVICE_QUERY)
            (root / 'service.cpp').write_text(source)
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fno-exceptions',
                '-fsanitize=address,undefined', '-I', str(COMP / 'files'), str(root / 'service.cpp'),
                str(COMP / 'files/knowledge_content_query.cpp'), '-o', str(root / 'service')], check=True)
            subprocess.run([str(root / 'service')], check=True, timeout=15)

    def test_NAPI_has_no_database_path_or_visitor_fallback_and_retains_revocation_checks(self):
        source = (COMP / 'files/knowledge_content_napi.cpp').read_text()
        self.assertNotIn('MediaAssetRdbStore', source)
        self.assertNotIn('CONST_MEDIA_DB_DIR', source)
        self.assertNotIn('->QueryByStep', source)
        self.assertIn('helper->Query(uri, predicates, work.wire, &business)', source)
        self.assertIn('business.GetCode()', source)
        self.assertIn('DataShare::DataShareHelper::Create(', source)
        self.assertIn('phase=client-helper-create rc=', source)
        self.assertIn('work.rowCount < 0', source)
        self.assertIn('Knowledge::SERVICE_ROW_LIMIT', source)
        self.assertIn('phase=cursor-next rc=', source)
        for name in ('void Execute(', 'void Complete(', 'bool NextRow('):
            start = source.index(name); end = source.index('\n}', start)
            self.assertIn('AccessError()', source[start:end])

    def test_Query_fixture_records_precise_API_and_preserves_primary_native_failure(self):
        source = (ROOT / 'ci/capability-audit/fixtures/batch_media/knowledge_runtime/Query.ets').read_text()
        self.assertIn("this.operationApi = 'KnowledgeContent.getRelatedEntity'", source)
        self.assertIn('store.failure(this.operationApi, actual)', source)
        self.assertIn("store.failure('PhotoAccessHelper.release', error as BusinessError)", source)
        self.assertIn('bodyFailed = true;\n      throw error as Error;', source)


if __name__ == '__main__':
    unittest.main()
