"""Constructed orchestration/transport controls, never SDK or guest evidence."""
import copy
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import watchdog_boot_clocks as w


class ClockBootBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.binary=self.root/'probe';self.binary.write_bytes(b'HOST-CONTROL-NOT-ELF')
        self.receipt=self.root/'build.json';self.receipt.write_text('HOST-CONTROL-NOT-A-BUILD')
        self.proof={'arch':'arm64','runtime_validated':False,'scope':'CONSTRUCTED-CONTROL-ONLY'}
        self.builder_patch=patch.object(w,'builder',return_value=SimpleNamespace(verify_build=lambda *args:dict(self.proof)))
        self.builder_patch.start();self.addCleanup(self.builder_patch.stop)
        self.guest=SimpleNamespace(arch='arm64',target='127.0.0.1:4567',args=SimpleNamespace(hdc='/actual-hdc'),
            report={'commands':[],'test_environment':{'guest_arch':'arm64','boot_id':'12345678-1234-1234-1234-123456789abc',
                'target':'127.0.0.1:4567'},'stable_seconds_without_external_keepalive':60})
        self.guest.command=self.command
        self.samples=0

    def command(self,argv,label,timeout=30):
        v=self.guest.report['watchdog_clocks'];token=v['token']
        if label=='clock-create-owned-directory':raw='CLOCK_DIRECTORY_CREATED '+token+'\n'
        elif label=='clock-send-built-helper':raw='HOST-CONTROL transfer success\n'
        elif label=='clock-actual-staged-identity':
            raw='\n'.join(['CLOCK_STAGE_V1 '+token,'0 0 700','0 0 500',v['binary']['sha256']+'  '+v['remote'],'END_CLOCK_STAGE_V1 '+token])+'\n'
        elif label.startswith('clock-before') or label.startswith('clock-after'):
            nonce=re.findall(r' ([a-f0-9]{32});',argv[-1])[0];self.samples+=1;base=self.samples*61000000000
            value={'schema_version':1,'nonce':nonce,'monotonic_before_ns':base,'boottime_ns':base+500000000,
                'monotonic_after_ns':base+1000}
            raw=v['boot_id']+'\n'+json.dumps(value)+'\n'+v['boot_id']+'\n'
        elif label=='clock-remove-only-owned-helper':raw='CLOCK_HELPER_REMOVED '+token+'\n'
        else:raise AssertionError(label)
        path=self.root/(str(len(self.guest.report['commands']))+'.log');path.write_text(raw)
        self.guest.report['commands'].append({'argv':list(argv),'label':label,'exit_code':0,'log':str(path),'sha256':w.digest(path)})
        return raw

    def complete(self):
        observer=w.Observer(self.guest,self.binary,self.receipt);observer.prepare()
        for phase in w.PHASES:observer.sample(phase)
        observer.cleanup();v=self.guest.report['watchdog_clocks'];rows=v['observations']
        # Constructed elapsed host time; this is never emitted as guest evidence.
        rows[1]['host_started_ns']=rows[0]['host_finished_ns']+60000000000
        rows[1]['host_finished_ns']=rows[1]['host_started_ns']+1000000
        return self.guest.report

    def test_complete_binding_recomputes_intervals_without_inventing_sleep_state(self):
        payload=self.complete();result=w.verify(payload,required=True)
        self.assertEqual(result['sleep_clock_difference_ns'],{'minimum':-1000,'maximum':1000})
        self.assertNotIn('suspended',result);self.assertNotIn('status',result)
        self.assertEqual(payload['watchdog_clocks']['cleanup_errors'],[])

    def test_required_missing_clock_evidence_rejected(self):
        self.assertIsNone(w.verify(self.guest.report))
        with self.assertRaises(ValueError):w.verify(self.guest.report,required=True)

    def test_raw_sample_target_nonce_boot_and_json_tampering_fail(self):
        payload=self.complete();v=payload['watchdog_clocks'];row=v['observations'][0]
        for mutate in (lambda p:p['watchdog_clocks'].update(boot_id='another'),
                       lambda p:p['commands'][row['command_index']]['argv'].__setitem__(2,'127.0.0.1:9999'),
                       lambda p:p['watchdog_clocks']['observations'][0].update(nonce='f'*32),
                       lambda p:p['watchdog_clocks']['observations'][0]['value'].update(boottime_ns=0)):
            changed=copy.deepcopy(payload);mutate(changed)
            with self.assertRaises(ValueError):w.verify(changed,required=True)
        path=Path(payload['commands'][row['command_index']]['log']);path.write_text('invented')
        with self.assertRaises(ValueError):w.verify(payload,required=True)

    def test_cleanup_scope_schema_and_missing_list_cannot_be_truthy_shortcuts(self):
        payload=self.complete()
        for changes in ({'cleanup_complete':False},{'cleanup_errors':None},{'cleanup_errors':{}},
                        {'schema_version':True},{'directory':'/data/other'}):
            altered=copy.deepcopy(payload);altered['watchdog_clocks'].update(changes)
            with self.assertRaises(ValueError):w.verify(altered,required=True)

    def test_actual_command_order_and_quiet_interval_are_required(self):
        payload=self.complete()
        for mutate in (lambda v:v['observations'][1].update(host_started_ns=v['observations'][0]['host_finished_ns']),
                       lambda v:v.update(cleanup_command=v['staging_command']),
                       lambda v:v['observations'].__setitem__(slice(None),list(reversed(v['observations'])))):
            altered=copy.deepcopy(payload);mutate(altered['watchdog_clocks'])
            with self.assertRaises(ValueError):w.verify(altered,required=True)

    def test_changed_native_build_receipt_or_binary_fails(self):
        payload=self.complete();self.proof['scope']='different source/compiler contract'
        with self.assertRaises(ValueError):w.verify(payload,required=True)
        self.proof['scope']='CONSTRUCTED-CONTROL-ONLY';self.binary.write_bytes(b'changed')
        with self.assertRaises(ValueError):w.verify(payload,required=True)


if __name__=='__main__':unittest.main()
