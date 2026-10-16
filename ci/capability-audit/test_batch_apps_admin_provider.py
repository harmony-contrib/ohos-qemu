"""Exact provisioning source, authority retention and real-method host checks."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'ci/capability-audit/fixtures/batch_apps/admin_provider'
ADMIN='applications/standard/admin_provisioning'
HAP='applications/standard/hap'
COMPONENTS={ADMIN:ROOT/'patches/common/applications/standard/admin_provisioning/source_provider',HAP:ROOT/'patches/common/applications/standard/hap/admin_provider'}
class AdminProviderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='batch-apps-admin-provider-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.meta=json.loads((FIXTURE/'provenance.json').read_text())
        for project,record in self.meta['projects'].items():
            for name,item in record['files'].items():
                data=gzip.decompress(base64.b64decode((FIXTURE/item['fixture']).read_bytes()))
                self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
                target=self.root/project/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    def apply(self,project):
        return subprocess.run(['bash',str(COMPONENTS[project]/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True)
    def prepare(self):
        for project in (ADMIN,HAP):
            r=self.apply(project);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_exact_source_hashes_replay_drift_and_crlf(self):
        self.prepare()
        for project,record in self.meta['projects'].items():
            for name,sha in record['patched_sha256'].items():
                self.assertEqual(hashlib.sha256((self.root/project/name).read_bytes()).hexdigest(),sha)
            self.assertEqual(self.apply(project).returncode,0)
        target=self.root/ADMIN/'entry/src/main/ets/pages/applicationInfo.ets'
        self.assertIn(b'\r\n',target.read_bytes())
        target.write_bytes(target.read_bytes()+b'// unknown source edit\r\n');before=target.read_bytes()
        self.assertNotEqual(self.apply(ADMIN).returncode,0);self.assertEqual(before,target.read_bytes())
    def test_real_hap_predecessors_and_two_complete_stack_replays(self):
        record=json.loads((FIXTURE/'hap-pristine.json').read_text())
        data=gzip.decompress(base64.b64decode(record['gzip_base64']))
        self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
        target=self.root/HAP/'BUILD.gn';target.write_bytes(data)
        components=('calendar_provider','photos_provider','settings_provider','admin_provider')
        for cycle in range(3):
            for name in components:
                component=ROOT/'patches/common/applications/standard/hap'/name
                r=subprocess.run(['bash',str(component/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),self.meta['projects'][HAP]['patched_sha256']['BUILD.gn'])

    def test_real_entry_authority_and_signing_policy_retained(self):
        before=json.loads((self.root/ADMIN/'entry/src/main/module.json5').read_text())['module']
        legacy=json.loads((self.root/ADMIN/'entry/src/main/module.json').read_text())['module']
        self.prepare();after=json.loads((self.root/ADMIN/'entry/src/main/module.json5').read_text())['module']
        self.assertEqual(after['requestPermissions'],before['requestPermissions'])
        for entry in before['abilities']+before['extensionAbilities']+legacy['abilities']:
            if 'srcEntrance' in entry:entry['srcEntry']=entry.pop('srcEntrance')
            if entry.get('type')=='ui':entry['type']='sys/commonUI'
        self.assertEqual(after['abilities'][:-1],before['abilities'])
        self.assertEqual(after['abilities'][-1],next(x for x in legacy['abilities'] if x['name']=='ByodAdminProvisionAbility'))
        self.assertEqual(after['extensionAbilities'],before['extensionAbilities'])
        build=(self.root/ADMIN/'BUILD.gn').read_text()
        self.assertIn('certificate_profile = "signature/adminprovisioning.p7b"',build)
        self.assertNotIn('ohos_resources(',build);self.assertNotIn('ohos_js_assets(',build)
        hap=(self.root/HAP/'BUILD.gn').read_text()
        self.assertIn('product_name == "arm64_virt"',hap)
        self.assertIn('//applications/standard/admin_provisioning:adminprovisioning_hap',hap)
    def test_actual_methods_backend_state_rejection_reentry_and_request_lifetime(self):
        self.prepare()
        for scenario in ('enable','disable','unsupported','super_admin','enable_failure','state_mismatch','query_failure','duplicate','cancel','new_want_before_write','new_want_during_write','destroy_before_write','failed_then_valid_query'):
            with self.subTest(scenario=scenario):
                r=subprocess.run(['node','--unhandled-rejections=strict',str(FIXTURE/'methods.cjs'),str(self.root/ADMIN),scenario],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_actual_ui_extension_and_deploy_session_protocol(self):
        self.prepare()
        scenarios=('extension_success','extension_duplicate','extension_missing','extension_invalid','extension_type','extension_destroyed','extension_isolated','deploy_success','deploy_missing','deploy_failed','deploy_mismatch','deploy_cancel','deploy_duplicate','deploy_destroyed','deploy_delivery_retry')
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                r=subprocess.run(['node','--unhandled-rejections=strict',str(FIXTURE/'sessions.cjs'),str(self.root/ADMIN),scenario],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
