"""Exercise the patched watchdog body with explicit host-only service doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/hotspot_state_reconciliation'
RELATIVE = 'applications/standard/settings/product/phone/src/main/ets/Setting/MobileNetwork/HotSpot/controller/HotspotSwitchController.ets'
ORIGINAL = '''  setStateChangeTimeoutTimer(): void {
    this.stateChangeTimeoutId = setTimeout(() => {
      try {
        if (this.isHotspotOn === wifiManager?.isHotspotActive()) {
          return;
        }
      } catch (error) {
        LogUtil.error(`${TAG} get isHotspotActive fail`);
      }
      HiSysEventUtil.reportDefaultFaultEvent(HiSysHotspotStateException.EVENT_NAME,
        HiSysHotspotStateException.HOTSPOT_STATE_CHANGE_TIMEOUT);
    }, 5000);
  }
'''


class SettingsHotspotStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='settings-hotspot-state-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_text(ORIGINAL)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_idempotence_and_drift_rejection(self):
        self.assertEqual(self.apply().returncode, 0)
        patched = self.target.read_bytes()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), patched)
        self.target.write_text(self.target.read_text().replace('this.isHotspotOn = active;',
                                                              'this.isHotspotOn = true;'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_actual_watchdog_body_failure_success_query_failure_and_recovery(self):
        self.assertEqual(self.apply().returncode, 0)
        method = self.target.read_text().replace('(): void', '()').replace('const active: boolean', 'const active')
        script = self.root / 'watchdog.js'
        script.write_text('''const assert = require('node:assert/strict');
let callback, actual, queryError = false, reports = 0, queries = 0;
const TAG = 'test';
const LogUtil = { error: () => {} };
const HiSysHotspotStateException = {EVENT_NAME: 'hotspot', HOTSPOT_STATE_CHANGE_TIMEOUT: 'timeout'};
const HiSysEventUtil = {reportDefaultFaultEvent: () => { reports++; }};
const wifiManager = {isHotspotActive: () => {
  queries++;
  if (queryError) throw new Error('actual read failed');
  return actual;
}};
function setTimeout(fn, ms) { assert.equal(ms, 5000); callback = fn; return 42; }
class Controller {
  constructor(on, checked) { this.isHotspotOn=on; this.checked=checked; this.isWaitingLastActionDone=true; this.updates=0; }
  getChecked() { return this.checked; }
  updateStatus() { this.updates++; this.checked=this.isHotspotOn; }
  startHotspot() { throw new Error('watchdog must not retry'); }
  stopHotspot() { throw new Error('watchdog must not issue a new operation'); }
''' + method + '''}
function tick(controller) {
  controller.setStateChangeTimeoutTimer();
  assert.equal(controller.stateChangeTimeoutId, 42);
  callback();
  assert.equal(controller.stateChangeTimeoutId, null);
}
for (const [on, checked, backend, changed] of [
  [true, true, false, true], [true, true, true, false],
  [false, true, false, true], [false, false, true, true],
  [false, false, false, false]
]) {
  reports=0; queries=0; actual=backend;
  const state = new Controller(on, checked);
  tick(state);
  assert.equal(state.isHotspotOn, backend);
  assert.equal(state.checked, backend);
  assert.equal(state.isWaitingLastActionDone, false);
  assert.equal(state.updates, changed ? 1 : 0);
  assert.equal(reports, changed ? 1 : 0);
  assert.equal(queries, 1);
}
queryError=true; reports=0;
const retained = new Controller(true, true);
tick(retained);
assert.equal(retained.isHotspotOn, true);
assert.equal(retained.checked, true);
assert.equal(retained.updates, 0);
assert.equal(reports, 1);
queryError=false; actual=false;
tick(retained);
assert.equal(retained.checked, false);
assert.equal(retained.isWaitingLastActionDone, false);
''')
        subprocess.run(['node', str(script)], check=True, capture_output=True, text=True)

    def test_shared_recipe_and_no_permission_or_backend_substitution(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${SETTINGS_HOTSPOT_STATE_COMPONENT_SCRIPT}" --source-root'), 1)
        patch = next(COMPONENT.glob('*.patch')).read_text()
        self.assertNotIn('startSharing(', patch)
        self.assertNotIn('stopSharing(', patch)
        self.assertNotIn('permission', patch)


if __name__ == '__main__':
    unittest.main()
