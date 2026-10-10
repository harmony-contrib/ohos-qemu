"""Minimal existing-class registration checks, not a guest constructor test."""
from pathlib import Path
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/image_framework/avis_class_export'


class AvisClassExportTests(unittest.TestCase):
    def test_only_existing_initializer_and_debug_label_are_added(self):
        sections = patch_sections(COMPONENT / '0001-register-existing-avis-metadata-class.patch')
        self.assertEqual(len(sections), 1)
        before, after = next(iter(sections.values()))[0][1:]
        added = [line for line in after if line not in before]
        self.assertEqual(added, ['    IMAGE_LOGD("AvisMetadataNapi CALL");',
                                '    MetadataNapi::InitAvisMetadata(env, exports);'])
        self.assertEqual([line for line in after if line not in added], before)
        body = '\n'.join(after)
        source = r'''
#include <cassert>
#include <vector>
using napi_env=void*;
using napi_value=void*;
std::vector<int> calls;
void Check(napi_env env,napi_value value,int id) {
    assert(env==reinterpret_cast<void*>(1));
    assert(value==reinterpret_cast<void*>(2)); calls.push_back(id);
}
struct MetadataNapi {
    static void InitJfifMetadata(napi_env e,napi_value v) {Check(e,v,1);}
    static void InitPngMetadata(napi_env e,napi_value v) {Check(e,v,2);}
    static void InitAvisMetadata(napi_env e,napi_value v) {Check(e,v,3);}
};
struct ImageReceiverNapi {static void Init(napi_env e,napi_value v) {Check(e,v,4);}};
#define IMAGE_LOGD(...) do {} while(0)
int main() {
    napi_env env=reinterpret_cast<void*>(1);
    napi_value exports=reinterpret_cast<void*>(2);
''' + body + '\nassert((calls==std::vector<int>{1,2,3,4}));\n}\n'
        compile_run(source, language='c++')

    def test_shared_recipe_and_real_typed_regressions(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${IMAGE_AVIS_CLASS_SCRIPT}" --source-root'), 1)
        self.assertIn('image_framework/avis_class_export/apply.sh', recipe)
        probe = (ROOT / 'ci/capability-audit/image_metadata_probe.ets').read_text()
        self.assertEqual(probe.count('new image.AvisMetadata()'), 3)
        self.assertIn('value instanceof image.AvisMetadata', probe)
        self.assertNotIn('new image.DngMetadata', probe)
        self.assertNotIn('new image.TiffMetadata', probe)


if __name__ == '__main__':
    unittest.main()
