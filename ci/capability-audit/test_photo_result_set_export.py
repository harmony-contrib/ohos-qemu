"""Execute the whole public facade and preserve native constructor identity."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/result_set_export'
FIXTURE = Path(__file__).with_name('fixtures') / 'photo_result_set_public.js'
RELATIVE = 'foundation/multimedia/media_library/frameworks/js/src/photoaccesshelperinf.js'


class ResultSetExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(FIXTURE.read_bytes())
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         '7843fe2799ab30bb78aae887196b06bcb96471cdc9c6bb0fb5017aab772bcce2')

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_full_facade_forwards_original_constructor_and_factory_prototype(self):
        self.assertEqual(self.apply().returncode, 0)
        script = r'''
const assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs');
class NativeResultSet { constructor() { this.position = -1; } }
const returned = Object.create(NativeResultSet.prototype);
const helper = { query: async () => returned };
const native = new Proxy({ResultSet: NativeResultSet, getPhotoAccessHelper: () => helper}, {
  get(target, key) {return key in target ? target[key] : class {};}
});
function load(path) {
  const context = {requireNapi: () => native, requireInternal: () => ({}), console};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path, 'utf8').replace('export default {', 'globalThis.facade = {'), context);
  return context.facade;
}
(async () => {
  assert.equal(load(process.argv[1]).ResultSet, undefined);
  const facade = load(process.argv[2]);
  assert.strictEqual(facade.ResultSet, NativeResultSet);
  assert.strictEqual(facade.ResultSet.prototype, NativeResultSet.prototype);
  assert.strictEqual(await facade.getPhotoAccessHelper({}).query(), returned);
  assert(returned instanceof facade.ResultSet);
  assert.strictEqual(Object.getPrototypeOf(returned), facade.ResultSet.prototype);
})().catch(error => {console.error(error);process.exitCode = 1;});
'''
        result = subprocess.run(['node', '-e', script, str(FIXTURE), str(self.target)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        repaired = self.target.read_bytes()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), repaired)

    def test_unknown_facade_and_symlink_fail_without_changes(self):
        self.target.write_bytes(self.target.read_bytes() + b'\n// unrelated\n')
        unknown = self.target.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), unknown)
        preserved = self.target.with_suffix('.preserved')
        self.target.rename(preserved); self.target.symlink_to(preserved)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(preserved.read_bytes(), unknown)


if __name__ == '__main__':
    unittest.main()
