"""Regression mutations of actual old-image journals/pixels; never gate evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from build_arkui_selection_probe import CONTRACTS
from verify_gap_closure import behavior_results
from verify_selection_results import pixels, verify

FIXTURES = Path(__file__).with_name('fixtures')/'selection_complete_diagnostic'


class SelectionCompleteResults(unittest.TestCase):
    def setUp(self):
        self.metadata = json.loads((FIXTURES/'metadata.json').read_text())
    def journal(self, role):
        return [json.loads(line) for line in (FIXTURES/(role+'-journal.log')).read_text().splitlines()]
    def getter_contract_rows(self):
        # Model the documented additional getter shapes using actual captured
        # clipboard contents. These synthetic rows have no command provenance
        # and cannot satisfy verify_selection_evidence or package acceptance.
        result = []
        for row in self.journal('reader'):
            result.append(row)
            if row['name']=='pasteboard.deferred.read':
                for form in ('sync','callback'):
                    extra = copy.deepcopy(row); extra['name']='pasteboard.'+form+'.read';result.append(extra)
        return result
    def check(self, role, rows):
        caller = self.metadata['callers'][role]
        return verify('\n'.join(json.dumps(row) for row in rows),caller['run_id'],caller['uid'],role)
    def test_three_getter_contract_structure_from_captured_contents(self):
        self.assertEqual(self.check('reader',self.getter_contract_rows()),CONTRACTS)
        with self.assertRaisesRegex(ValueError,'sync clipboard getter'):
            self.check('reader',self.journal('reader'))
    def test_old_empty_read_is_rejected_instead_of_claiming_sdk_permission_success(self):
        for role in ('normal','reader-denied'):
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'SDK error 201'):
                self.check(role,self.journal(role))
    def test_callback_success_cannot_replace_actual_clipboard_contents(self):
        for key,value in (('text','wrong'),('records',0),('mimeTypes',['text/plain']),('html','<p>wrong</p>')):
            rows = self.getter_contract_rows()
            row = next(r for r in rows if r['cycle']==0 and r['phase']==1 and r['name']=='pasteboard.deferred.read')
            data = json.loads(row['data']);data[key]=value;row['data']=json.dumps(data)
            with self.subTest(key=key),self.assertRaises(ValueError):self.check('reader',rows)
    def test_veto_must_preserve_the_challenged_seed(self):
        rows = self.getter_contract_rows()
        row = next(r for r in rows if r['cycle']==0 and r['phase']==0 and r['name']=='pasteboard.deferred.read')
        data = json.loads(row['data']);data['text']='veto wrote new contents';row['data']=json.dumps(data)
        with self.assertRaises(ValueError):self.check('reader',rows)
    def test_negative_role_cannot_borrow_authorization_or_return_protected_contents(self):
        for mutation in ('grant','contents'):
            rows = self.journal('normal')
            if mutation=='grant':next(r for r in rows if r['name']=='permission.state')['values']=[0]
            else:
                row = next(r for r in rows if r['name']=='pasteboard.deferred.read')
                data = json.loads(row['data']);data.update(text='protected',records=1,mimeTypes=['text/plain']);row['data']=json.dumps(data)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.check('normal',rows)
    def test_missing_recreation_or_late_callback_cannot_close(self):
        rows = self.getter_contract_rows()
        with self.assertRaises(ValueError):self.check('reader',[r for r in rows if r['cycle']==0])
        late = copy.deepcopy(next(r for r in rows if r['name']=='modifier.selection'))
        late.update(cycle=1,phase=2)
        with self.assertRaises(ValueError):self.check('reader',rows+[late])
    def test_actual_selected_cleared_and_removed_pixels_verify(self):
        nonce = self.metadata['callers']['reader']['run_id']
        for phase in ('allowed-selected','allowed-cleared','removed'):
            layout = json.loads((FIXTURES/(phase+'.json')).read_text())
            with self.subTest(phase=phase):pixels(FIXTURES/(phase+'.png'),layout,nonce,'reader',0,phase)
    def test_a_valid_hierarchy_with_unpainted_pixels_is_rejected(self):
        nonce = self.metadata['callers']['reader']['run_id']
        layout = json.loads((FIXTURES/'allowed-selected.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'white.png';Image.new('RGB',(1280,800),'white').save(path)
            with self.assertRaises(ValueError):pixels(path,layout,nonce,'reader',0,'allowed-selected')
    def test_old_diagnostic_child_cannot_close_a_new_package_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root/'selection').mkdir();(root/'boot').mkdir()
            (root/'selection/evidence.json').write_text(json.dumps(dict(status='pass',boot_id='fixture',archive_sha256='0'*64)))
            (root/'boot/boot.json').write_text(json.dumps(dict(status='pass',purpose='diagnostic',archive_sha256='0'*64,
                scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                test_environment=dict(boot_id='fixture',external_keepalive=False,device_type='phone'))))
            with self.assertRaisesRegex(ValueError,'unchanged fresh acceptance'):
                behavior_results(root,'fixture','0'*64,'phone')


if __name__=='__main__':unittest.main()
