#!/usr/bin/env python3
"""Execute the real ArkTS model with service mocks; not a guest UI/IPC test."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/applications/standard/permission_manager/open_setting"
MODEL = COMPONENT / "files/OpenSettingRequest.ets"
MAIN = "applications/standard/permission_manager/permissionmanager/src/main"

MOCK = r'''
import assert from 'node:assert/strict';
let grantCalls = [], lookupCalls = [], granted = false, grantError = false, grantNoop = false;
let lookupGate = null;
const permission = 'ohos.permission.HOOK_KEY_EVENT';
const tokenId = 0x81000001, uid = 100 * 200000 + 10001;
const want = () => ({parameters: {'ohos.open.setting.permission': permission,
  'ohos.aafwk.param.callerBundleName': 'org.example.app',
  'ohos.aafwk.param.callerUid': uid, 'ohos.aafwk.param.callerToken': tokenId | 0 }});
let info = {name:'org.example.app', appInfo:{uid, accessTokenId:tokenId}, reqPermissionDetails:[{name:permission}]};
const deviceInfo = {deviceType:'2in1'};
const manager = {
  checkAccessTokenSync: (token, name) => granted ? 0 : -1,
  grantPermission: async (token, name, flags) => {
    grantCalls.push({token, name, flags});
    if (grantError) throw new Error('service denied');
    if (!grantNoop) granted = true;
  },
  grantUserGrantedPermission: () => {throw new Error('legacy manual-grant API must not be used');}
};
const abilityAccessCtrl = {createAtManager: () => manager, GrantStatus:{PERMISSION_GRANTED:0}};
const bundleManager = {BundleFlag:{GET_BUNDLE_INFO_WITH_APPLICATION:1, GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION:2},
  getBundleInfo: async (name, flags, user) => {
    lookupCalls.push({name, flags, user});
    if (lookupGate) await lookupGate;
    return info;
  }};
'''


def execute(program, source_file=MODEL, mocks=MOCK):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node with stripTypeScriptTypes is required for ArkTS model regressions")
    # This file is plain TypeScript, not ArkUI DSL. Strip types, not executable
    # behavior. The actual model (including async races) runs in the mock VM.
    code = r'''
import {stripTypeScriptTypes} from 'node:module';
import {readFileSync} from 'node:fs';
const text = readFileSync(process.argv[1], 'utf8')
  .replace(/^import .*?;\s*/gm, '').replace(/^export default /gm, '').replace(/^export /gm, '');
const compiled = stripTypeScriptTypes(text, {mode:'strip'});
await eval('(async () => {' + process.argv[2] + compiled + process.argv[3] + '})()');
'''
    result = subprocess.run([node, "--disable-warning=ExperimentalWarning", "--input-type=module", "-e", code,
                    str(source_file), mocks.replace("import assert from 'node:assert/strict';", "const assert = (await import('node:assert/strict')).default;"),
                    program], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr)


class OpenSettingTests(unittest.TestCase):
    def test_window_session_close_reuse_and_concurrent_session_isolation(self):
        mocks = r'''
import assert from 'node:assert/strict';
class UIExtensionAbility {}
class OpenSettingRequest {active = true; constructor(want) {}}
class LocalStorage {constructor(entries) {}}
const INTERNAL_ERROR = -2;
const display = {getDefaultDisplaySync: () => ({width:400, height:600})};
let windows = [];
function session() {
  const s = {results:[], terminateSelfWithResult: result => s.results.push(result),
    getUIExtensionHostWindowProxy: () => ({createSubWindowWithOptions: async (name, options) => {
      assert.equal(options.isModal, true);
      const win = {hidden:false, destroyed:false, resize:async () => {}, setWindowBackgroundColor:() => {},
        hideNonSystemFloatingWindows: value => win.hidden = value,
        loadContent:async () => {}, showWindow:async () => {}, destroyWindow:async () => win.destroyed = true};
      windows.push(win); return win;
    }})};
  return s;
}
'''
        execute(r'''
const ability = new OpenSettingAbility(); const first = session(), rejected = session();
await ability.onSessionCreate({}, first); assert.equal(windows.length,1); assert.equal(windows[0].hidden,true);
await ability.onSessionCreate({}, rejected);
assert.equal(rejected.results[0].want.parameters['ohos.open.setting.result_code'], INTERNAL_ERROR);
await ability.onSessionDestroy(rejected); assert.equal(windows[0].destroyed,false);
await ability.onSessionDestroy(first); assert.equal(windows[0].destroyed,true); assert.equal(windows[0].hidden,false);
const next = session(); await ability.onSessionCreate({}, next);
assert.equal(windows.length,2); assert.equal(next.results.length,0); assert.equal(windows[1].hidden,true);
await ability.onDestroy(); assert.equal(windows[1].destroyed,true); assert.equal(windows[1].hidden,false);
''', COMPONENT / "files/OpenSettingAbility.ets", mocks)

    def test_display_is_read_only_and_explicit_grant_verifies_real_state(self):
        execute(r'''
const request = new OpenSettingRequest(want());
assert.equal(await request.prepare(), USER_OPENED);
assert.equal(grantCalls.length, 0);
assert.equal(lookupCalls[0].user, 100);
assert.equal(await request.confirm(), USER_OPENED);
assert.deepEqual(grantCalls, [{token:tokenId, name:permission, flags:1}]);
assert.equal(await request.confirm(), ALREADY_GRANTED);
assert.equal(grantCalls.length, 1);
''')

    def test_caller_identity_and_permission_declaration_boundaries(self):
        execute(r'''
for (const field of ['name', 'uid', 'token']) {
  const saved = structuredClone(info);
  if (field === 'name') info.name = 'spoofed';
  if (field === 'uid') info.appInfo.uid++;
  if (field === 'token') info.appInfo.accessTokenId++;
  assert.equal(await new OpenSettingRequest(want()).prepare(), NOT_SUPPORTED);
  info = saved;
}
info.reqPermissionDetails = [];
assert.equal(await new OpenSettingRequest(want()).prepare(), NOT_DECLARED);
assert.equal(grantCalls.length, 0);
''')

    def test_invalid_input_and_unsupported_profiles_never_grant(self):
        execute(r'''
for (const bad of [null, '', 'ohos.permission.CAMERA', 1]) {
  const w = want(); w.parameters['ohos.open.setting.permission'] = bad;
  assert.equal(await new OpenSettingRequest(w).confirm(), NOT_SUPPORTED);
}
for (const bad of [0, 3020, 100 * 200000 + 1000, uid + 0.5, 2147483648, '10001']) {
  const w = want(); w.parameters['ohos.aafwk.param.callerUid'] = bad;
  assert.equal(await new OpenSettingRequest(w).prepare(), NOT_SUPPORTED);
}
for (const bad of [0, -2147483649, 4294967296, 1.5, '123']) {
  const w = want(); w.parameters['ohos.aafwk.param.callerToken'] = bad;
  assert.equal(await new OpenSettingRequest(w).prepare(), NOT_SUPPORTED);
}
assert.equal(await new OpenSettingRequest({}).prepare(), NOT_SUPPORTED);
deviceInfo.deviceType = 'phone';
assert.equal(await new OpenSettingRequest(want()).confirm(), NOT_SUPPORTED);
assert.equal(grantCalls.length, 0);
''')

    def test_cancel_already_granted_and_stale_token_do_not_mutate(self):
        execute(r'''
let request = new OpenSettingRequest(want()); request.active = false;
assert.equal(await request.confirm(), USER_REJECTED);
granted = true;
assert.equal(await new OpenSettingRequest(want()).prepare(), ALREADY_GRANTED);
granted = false;
request = new OpenSettingRequest(want());
assert.equal(await request.prepare(), USER_OPENED);
info.appInfo.accessTokenId++;
assert.equal(await request.confirm(), NOT_SUPPORTED);
assert.equal(grantCalls.length, 0);
''')

    def test_service_error_or_success_noop_never_returns_opened(self):
        execute(r'''
grantError = true;
assert.equal(await new OpenSettingRequest(want()).confirm(), INTERNAL_ERROR);
grantError = false; grantNoop = true;
assert.equal(await new OpenSettingRequest(want()).confirm(), INTERNAL_ERROR);
assert.equal(granted, false);
''')

    def test_close_during_lookup_and_duplicate_click_races(self):
        execute(r'''
let release;
lookupGate = new Promise(resolve => release = resolve);
let request = new OpenSettingRequest(want());
let pending = request.confirm(); request.active = false; release();
assert.equal(await pending, USER_REJECTED);
assert.equal(grantCalls.length, 0);
lookupGate = new Promise(resolve => release = resolve);
request = new OpenSettingRequest(want()); pending = request.confirm();
assert.equal(await request.confirm(), USER_REJECTED);
release(); assert.equal(await pending, USER_OPENED);
assert.equal(grantCalls.length, 1);
''')

    def test_component_registration_idempotence_and_legacy_protocol_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / MAIN
            main.mkdir(parents=True)
            old = {"name": "com.ohos.permissionmanager.PermissionStateSheetAbility",
                   "type": "sys/commonUI", "srcEntry": "./ets/PermissionSheet/PermissionStateSheetAbility.ets",
                   "exported": True}
            for name in ("module.json", "module.json5"):
                (main / name).write_text(json.dumps({"module": {"extensionAbilities": [old]}}))
            pages = main / "resources/base/profile/main_pages.json"
            pages.parent.mkdir(parents=True)
            pages.write_text(json.dumps({"src": ["PermissionSheet/PermissionStateSheetDialog"]}))
            command = ["bash", str(COMPONENT / "apply.sh"), "--source-root", str(root)]
            subprocess.run(command, check=True, capture_output=True)
            first = {p.relative_to(main): p.read_bytes() for p in main.rglob("*") if p.is_file()}
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(first, {p.relative_to(main): p.read_bytes() for p in main.rglob("*") if p.is_file()})
            entries = json.loads((main / "module.json").read_text())["module"]["extensionAbilities"]
            self.assertEqual(entries[1], old)
            self.assertEqual(entries[0]["name"], "com.ohos.permissionmanager.OpenSettingAbility")
            self.assertIn("OpenSetting/OpenSettingDialog", json.loads(pages.read_text())["src"])
            document = json.loads((main / "module.json").read_text())
            document["module"]["extensionAbilities"][0]["srcEntry"] = old["srcEntry"]
            (main / "module.json").write_text(json.dumps(document))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
