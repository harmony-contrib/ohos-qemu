"""Lightweight source/real-function tests; does not establish SDK or guest acceptance."""
import base64,gzip,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FIX=ROOT/'ci/capability-audit/fixtures/batch_apps/share_provider'
COMPONENTS=('patches/common/applications/standard/settings/share_picker','patches/common/applications/standard/mms/send_data_text')
JSON5=os.environ.get('BATCH_APPS_JSON5_MODULE','/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin/node_modules/json5')
class ShareProviderTests(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory(prefix='batch-apps-share-');self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve();self.meta=json.loads((FIX/'provenance.json').read_text())
  for name,item in self.meta['files'].items():
   data=gzip.decompress(base64.b64decode(item['gzip_base64']));self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256']);p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 def apply(self):
  for component in COMPONENTS:
   r=subprocess.run(['bash',str(ROOT/component/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True)
   if r.returncode:return r
  return r
 def prepare(self):
  r=self.apply();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def json5(self,name):
  r=subprocess.run(['node','-e','process.stdout.write(JSON.stringify(require(process.argv[1]).parse(require("fs").readFileSync(process.argv[2],"utf8"))))',JSON5,str(self.root/name)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);return json.loads(r.stdout)
 def test_exact_application_replay_and_no_drift_mutation(self):
  self.prepare()
  for name,sha in self.meta['patched_sha256'].items():self.assertEqual(hashlib.sha256((self.root/name).read_bytes()).hexdigest(),sha)
  for _ in range(2):self.assertEqual(self.apply().returncode,0)
  p=self.root/'applications/standard/settings/product/phone/src/main/module.json5';p.write_bytes(p.read_bytes()+b'// unknown edit\n');before=p.read_bytes();self.assertNotEqual(self.apply().returncode,0);self.assertEqual(p.read_bytes(),before)
 def test_new_platform_imports_exist_in_the_official_api26_sdk(self):
  import re
  sdk=Path(os.environ.get('BATCH_APPS_SDK_API','/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0/ets/api'))
  for source in (FIX/'candidate').glob('*.ets'):
   for module in re.findall(r"from '(@ohos[^']+)'",source.read_text()):self.assertTrue((sdk/(module+'.d.ts')).is_file(),module)
 def test_payload_mirrors_match_the_applied_product_files(self):
  self.prepare()
  mapping={'SharePickerController.ets':'applications/standard/settings/product/phone/src/main/ets/Setting/SharePicker/SharePickerController.ets','SharePickerExtension.ets':'applications/standard/settings/product/phone/src/main/ets/Setting/SharePicker/SharePickerExtension.ets','SharePicker.ets':'applications/standard/settings/product/phone/src/main/ets/pages/SharePicker.ets','SendDataPayload.ets':'applications/standard/mms/entry/src/main/ets/utils/SendDataPayload.ets'}
  for filename,target in mapping.items():self.assertEqual((FIX/'candidate'/filename).read_bytes(),(self.root/target).read_bytes())
 def test_bounded_manifest_and_existing_permissions_profiles_retained(self):
  setting='applications/standard/settings/product/phone/src/main/module.json5';mms='applications/standard/mms/entry/src/main/module.json5';before=self.json5(setting)['module'];before_mms=self.json5(mms)['module'];self.prepare();after=self.json5(setting)['module'];after_mms=self.json5(mms)['module']
  self.assertEqual(after['extensionAbilities'][0],self.meta['added_extension']);after['extensionAbilities']=after['extensionAbilities'][1:];self.assertEqual(after,before)
  old=next(a for a in before_mms['abilities'] if a['name']=='com.ohos.mms.MainAbility');new=next(a for a in after_mms['abilities'] if a['name']=='com.ohos.mms.MainAbility');self.assertEqual(new['skills'][0],{'actions':['ohos.want.action.sendData'],'uris':[{'type':'text/plain'}]});new['skills']=new['skills'][1:];self.assertEqual(after_mms,before_mms)
  extension=(self.root/'applications/standard/settings/product/phone/src/main/ets/Setting/SharePicker/SharePickerExtension.ets').read_text();self.assertNotIn('setReceiveDataCallback',extension)
 def test_actual_picker_controller(self):
  self.prepare();source=self.root/'applications/standard/settings/product/phone/src/main/ets/Setting/SharePicker/SharePickerController.ets'
  for case in ('enumerate_and_choose','invalid_payloads','text_array','file_flags_and_snapshot','cancel_query','destroy_query','destroy_launch','duplicate','stale_target','destroy_revalidation','result_retry','cancel_after_launch_failure','query_failure','label_failure','permission_failure','empty_targets','unknown_target','empty_payload','cancel_label','destroy_label','cancel_query_no_label','destroy_query_no_label'):
   with self.subTest(case=case):
    r=subprocess.run(['node','--unhandled-rejections=strict',str(FIX/'controller.cjs'),str(source),case],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_actual_plain_text_receiver_and_draft_router(self):
  self.prepare()
  for case in ('draft','payload_validation','stale_request','loader_failure','invalid_text'):
   with self.subTest(case=case):
    r=subprocess.run(['node','--unhandled-rejections=strict',str(FIX/'mms.cjs'),str(self.root/'applications/standard/mms'),case],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_actual_extension_session_isolation_destroy_and_error_codes(self):
  self.prepare();source=self.root/'applications/standard/settings/product/phone/src/main/ets/Setting/SharePicker/SharePickerExtension.ets'
  for case in ('isolated','invalid_duplicate','load_failure','destroy_while_loading','recreate_while_loading'):
   with self.subTest(case=case):
    r=subprocess.run(['node','--unhandled-rejections=strict',str(FIX/'extension.cjs'),str(source),case],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
