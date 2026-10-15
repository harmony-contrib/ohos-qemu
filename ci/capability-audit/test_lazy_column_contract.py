"""Captured diagnostic regressions; fixtures are never fresh package acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from build_arkui_lazy_types_probe import CONTRACTS, source
from verify_lazy_column_results import verify, pixels
from verify_lazy_column_evidence import verify_evidence

FIXTURE=Path(__file__).parent/'fixtures/lazy_column_diagnostic'


class LazyColumnContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((FIXTURE/'fixture.json').read_text())
        for name,sha in self.fixture['files_sha256'].items():
            self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),sha)
        self.raw=(FIXTURE/self.fixture['journal']).read_text()
        self.rows=[json.loads(line) for line in self.raw.splitlines()]

    def test_actual_two_cycles_close_exactly_two_factory_types(self):
        self.assertEqual(verify(self.raw,self.fixture['nonce'],self.fixture['uid']),CONTRACTS)
        self.assertFalse(self.fixture['first_artifact_behavior_gate_passed'])

    def test_foreign_root_or_replayed_identity_rejected(self):
        for nonce,uid in (('a'*32,self.fixture['uid']), (self.fixture['nonce'],0),
                          (self.fixture['nonce'],self.fixture['uid']+1)):
            with self.subTest(nonce=nonce,uid=uid),self.assertRaises(ValueError):verify(self.raw,nonce,uid)

    def test_missing_recreation_reset_native_boundary_and_late_callback_rejected(self):
        changes=[]
        changes.append([row for row in self.rows if row['cycle']==0])
        changes.append([row for row in self.rows if row['name']!='modifier.column.reset'])
        bad=copy.deepcopy(self.rows)
        for row in bad:
            if row['name']=='visible.column' and row['values'][1]==39:row['values']=[33,38]
        changes.append(bad)
        changes.append(self.rows+[dict(runId=self.fixture['nonce'],cycle=1,name='visible.column',values=[0,5],error='')])
        for rows in changes:
            with self.subTest(length=len(rows)),self.assertRaises(ValueError):
                verify('\n'.join(json.dumps(row) for row in rows),self.fixture['nonce'],self.fixture['uid'])

    def test_actual_all_eight_compositor_phases_and_old_frame_rejected(self):
        for key,row in self.fixture['phases'].items():
            cycle,phase=key.split(':');layout=json.loads((FIXTURE/row['layout']).read_text())
            metrics,fingerprint=pixels(FIXTURE/row['screenshot'],layout,self.fixture['nonce'],int(cycle),phase)
            self.assertTrue(metrics);self.assertTrue(fingerprint)
        bottom=self.fixture['phases']['0:bottom'];initial=self.fixture['phases']['0:initial']
        with self.assertRaises(ValueError):
            pixels(FIXTURE/initial['screenshot'],json.loads((FIXTURE/bottom['layout']).read_text()),self.fixture['nonce'],0,'bottom')
        removed=self.fixture['phases']['0:removed']
        with self.assertRaises(ValueError):
            pixels(FIXTURE/initial['screenshot'],json.loads((FIXTURE/removed['layout']).read_text()),self.fixture['nonce'],0,'removed')

    def test_diagnostic_or_partial_child_cannot_attest_packaged_proof(self):
        for status,scope in (('collected_diagnostic_only',self.fixture['scope']),('pass',self.fixture['scope']),('pass','metadata_only')):
            with self.subTest(status=status),self.assertRaises(ValueError):
                verify_evidence(dict(status=status,scope=scope),'a'*64,'foreign','arm64','phone','foreign')

    def test_ledger_rejects_old_assisted_or_foreign_boot_before_any_registration(self):
        from verify_gap_closure import behavior_results
        for change in ('diagnostic','assisted','foreign'):
            with tempfile.TemporaryDirectory() as directory:
                runtime=Path(directory);(runtime/'boot').mkdir();(runtime/'lazy-column').mkdir()
                archive='a'*64;boot_id='11111111-1111-1111-1111-111111111111'
                (runtime/'lazy-column/evidence.json').write_text(json.dumps(dict(status='pass',archive_sha256=archive,boot_id=boot_id)))
                boot=dict(status='pass',purpose='acceptance',scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                    archive_sha256=archive,test_environment=dict(boot_id=boot_id,external_keepalive=False,device_type='phone'))
                if change=='diagnostic':boot['purpose']='diagnostic'
                elif change=='assisted':boot['diagnostic_assistance']=['forced kernel']
                else:boot['archive_sha256']='b'*64
                (runtime/'boot/boot.json').write_text(json.dumps(boot))
                with self.assertRaisesRegex(ValueError,'unchanged fresh acceptance package'):
                    behavior_results(runtime,boot_id,archive,'phone')

    def test_missing_or_replayed_source_nonce_rejected(self):
        for nonce in ('','old-device','a'*31):
            with self.assertRaises(ValueError):source(nonce)


if __name__=='__main__':unittest.main()
