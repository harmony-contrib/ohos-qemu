"""Actual patched JavaScript data classes; no persistence/device claim."""
from pathlib import Path
import subprocess
import unittest

from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/arkui/ace_engine/connect_options_records/0001-export-public-connect-option-records.patch'


class StateOptionRecordsTests(unittest.TestCase):
    def test_actual_data_classes_inheritance_and_independent_callbacks(self):
        sections = patch_sections(PATCH)
        self.assertEqual(len(sections), 1)
        before, after = next(iter(sections.values()))[0][1:]
        self.assertTrue(all(line in after for line in before))
        source = '\n'.join(after)
        classes = source[source.index('class ConnectOptions {}'):source.index('export default')]
        self.assertIn('  ConnectOptions,', after)
        self.assertIn('  ConnectOptionsCollections,', after)
        subprocess.run(['node', '-e', classes + r'''
const assert = require('node:assert/strict');
for (let repeat=0;repeat<256;repeat++) {
  const a = new ConnectOptions(), b = new ConnectOptions();
  const c = new ConnectOptionsCollections(), d = new ConnectOptionsCollections();
  assert(a instanceof ConnectOptions && b instanceof ConnectOptions && a !== b);
  assert(c instanceof ConnectOptions && c instanceof ConnectOptionsCollections && c !== d);
  for (const value of [a,b,c,d]) assert.deepEqual(Object.keys(value), []);
  a.key='a'; b.key='b'; a.defaultCreator=()=>({value:a.key}); b.defaultCreator=()=>({value:b.key});
  a.key='changed'; assert.equal(a.defaultCreator().value,'changed'); assert.equal(b.defaultCreator().value,'b');
  c.defaultSubCreator=()=>({value:'child'}); c.defaultCreator=()=>[c.defaultSubCreator()];
  const first=c.defaultCreator(),second=c.defaultCreator(); first[0].value='changed';
  assert.equal(second[0].value,'child'); assert.equal(d.defaultSubCreator,undefined);
  assert.throws(()=>ConnectOptions(), TypeError);
  assert.throws(()=>ConnectOptionsCollections(), TypeError);
}
'''], check=True, capture_output=True, text=True)

    def test_no_storage_implementation_or_static_codegen_change(self):
        self.assertEqual(set(patch_sections(PATCH)), {
            'foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsStateManagement.js'})
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${STATE_OPTIONS_RECORDS_COMPONENT_SCRIPT}" --source-root'), 1)


if __name__ == '__main__':
    unittest.main()
