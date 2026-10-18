"""Pure opaque-hilog transport regressions using only synthetic temporary files.

No guest, signature, retained-runtime replay, SDK or process is invoked.
"""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from batch_media_audio_hilog_transport import AudioHilogTransport
import batch_media_knowledge_suite as ORIGINAL
from guest_ui import command_exit
from hdc_transport import failed


def descriptor(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


class OpaqueTransport(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.hdc='controlled-hdc';self.target='127.0.0.1:5555';self.marker='__UITEST_EXIT_'+'a'*32+'__='
        self.make(b'original valid informational log\n')
    def make(self,body,*,script='hilog -x',ending=None):
        self.raw=self.root/'raw.log';self.norm=self.root/'normalized.txt'
        suffix=('\n'+self.marker+'0\n').encode()if ending is None else ending
        self.raw.write_bytes(body+suffix)
        text=(body+suffix).decode('utf-8',errors='replace').replace('\r\n','\n').replace('\r','\n')
        try:normalized=command_exit(text,self.marker)[0].rstrip('\n')
        except ValueError:normalized='not an admitted footer'
        self.norm.write_text(normalized,encoding='utf-8')
        cmd=dict(argv=[self.hdc,'-t',self.target,'shell',script+'; task_ui_rc=$?; printf "\\n'+self.marker+'%s\\n" "$task_ui_rc"'],
            label='phase-native-log',exit_code=0,timed_out=False,raw=descriptor(self.raw))
        obs=dict(name='phase-native-log',script='hilog -x',command=0,raw=descriptor(self.norm))
        self.value=dict(commands=[cmd],observations=[obs],segments=[dict(phase='phase',expected=dict(action='start'),native_log=dict(obs['raw']))])
    def transport(self):
        return AudioHilogTransport(self.value,self.hdc,self.target,checked=ORIGINAL.checked,original=ORIGINAL,command_exit=command_exit,failed=failed)
    def verify(self):
        t=self.transport();t.verify_commands(self.value['commands'],self.hdc,self.target);return t
    def test_original_valid_ASCII_hilog_has_exact_original_body(self):
        expected=ORIGINAL.exact_script(self.value['commands'][0],'hilog -x');t=self.verify()
        self.assertEqual(t.exact_script(0,'hilog -x'),expected);self.assertFalse(t.audit[0]['proof_body_semantics_used'])
    def test_unrelated_binary_payload_is_opaque_and_raw_hash_retained(self):
        self.make(b'C01630/DistributedDB: [KVDB] [StartSyncerWithNoLock] [\xd2H\x04] event=3\n');before=self.raw.read_bytes();r=descriptor(self.raw)
        with self.assertRaises(UnicodeDecodeError):ORIGINAL.verify_commands(self.value['commands'],self.hdc,self.target)
        t=self.verify();self.assertEqual(self.raw.read_bytes(),before);self.assertEqual(t.audit[0]['raw'],r)
        self.assertEqual(t.audit[0]['surrogateescaped_payload_bytes'],1);self.assertIn('\ufffd',t.exact_script(0,'hilog -x'))
    def test_unbound_malformed_hilog_keeps_original_strict_failure(self):
        self.make(b'unrelated log \xd2\n');self.value['segments']=[]
        with self.assertRaises(UnicodeDecodeError):self.verify()
    def test_nonhilog_invalid_UTF8_keeps_original_strict_failure(self):
        self.make(b'not text \xd2\n',script='id -u');self.value['segments']=[]
        with self.assertRaises(UnicodeDecodeError):self.verify()
    def test_nonhilog_valid_command_uses_original_verification(self):
        self.make(b'0\n',script='id -u');self.value['segments']=[]
        expected=ORIGINAL.exact_script(self.value['commands'][0],'id -u');t=self.verify();self.assertEqual(t.exact_script(0,'id -u'),expected);self.assertEqual(t.audit,{})
    def test_malformed_footer_missing_terminal_newline_rejected(self):
        self.make(b'payload \xd2\n',ending=('\n'+self.marker+'0').encode())
        with self.assertRaises(ValueError):self.verify()
    def test_nonzero_guest_footer_rejected(self):
        self.make(b'payload \xd2\n',ending=('\n'+self.marker+'1\n').encode())
        with self.assertRaises(ValueError):self.verify()
    def test_duplicate_complete_footer_rejected(self):
        self.make(('\n'+self.marker+'0\n').encode())
        with self.assertRaises(ValueError):self.verify()
    def test_inline_echo_is_allowed_by_original_complete_record_grammar(self):
        self.make(('log echo printf "'+self.marker+'%s"\n').encode()+b'payload \xd2\n')
        t=self.verify();self.assertEqual(self.raw.read_bytes().count(self.marker.encode()),2);self.assertEqual(t.audit[0]['guest_exit_code'],0)
    def test_CRLF_and_lone_CR_match_original_file_newline_semantics(self):
        self.make(b'one\r\ntwo\rthree\n');expected=ORIGINAL.exact_script(self.value['commands'][0],'hilog -x');self.assertEqual(self.verify().exact_script(0,'hilog -x'),expected)
    def test_original_transport_error_markers_rejected(self):
        for body in (b'[Fail] binary \xd2\n',b'Device not found or connected \xd2\n',b'Connect server failed\n'):
            with self.subTest(body=body):
                self.make(body)
                with self.assertRaises(ValueError):self.verify()
    def test_normalized_projection_mismatch_rejected_even_with_new_hash(self):
        self.make(b'payload \xd2\n');self.norm.write_text('different text');row=descriptor(self.norm)
        self.value['observations'][0]['raw']=row;self.value['segments'][0]['native_log']=dict(row)
        with self.assertRaises(ValueError):self.verify()
    def test_raw_hash_change_is_not_tolerated(self):
        self.raw.write_bytes(self.raw.read_bytes()+b'change')
        with self.assertRaises(ValueError):self.verify()
    def test_host_exit_or_timeout_rejected(self):
        for field,value in (('exit_code',1),('exit_code',False),('timed_out',True)):
            with self.subTest(field=field,value=value):
                self.make(b'payload\n');self.value['commands'][0][field]=value
                with self.assertRaises(ValueError):self.verify()
    def test_hilog_cannot_claim_the_original_UITest_transition_exception(self):
        self.value['commands'][0]['layout_transition']=True
        with self.assertRaises(ValueError):self.verify()
    def test_similar_hilog_command_with_extra_shell_operation_rejected(self):
        self.value['commands'][0]['argv'][4]=self.value['commands'][0]['argv'][4].replace('hilog -x;','hilog -x; id;')
        with self.assertRaises(ValueError):self.transport()
    def test_wrong_target_or_wrong_segment_action_rejected(self):
        self.value['commands'][0]['argv'][2]='127.0.0.1:1'
        with self.assertRaises(ValueError):self.transport()
        self.make(b'payload\n');self.value['segments'][0]['expected']['action']='stop'
        with self.assertRaises(ValueError):self.transport()
    def test_unbound_normalized_observation_or_duplicate_binding_rejected(self):
        self.value['observations']=[]
        with self.assertRaises(ValueError):self.transport()
        self.make(b'payload\n');self.value['observations'].append(copy.deepcopy(self.value['observations'][0]))
        with self.assertRaises(ValueError):self.transport()
    def test_opaque_display_cannot_be_consumed_as_structured_proof(self):
        t=self.verify()
        with self.assertRaises(ValueError):t.reject_typed_proof(self.value['observations'][0]['raw'])
    def test_shared_module_not_monkeypatched(self):
        old=(ORIGINAL.verify_commands,ORIGINAL.exact_script,ORIGINAL.shell_body);self.verify()
        self.assertEqual(old,(ORIGINAL.verify_commands,ORIGINAL.exact_script,ORIGINAL.shell_body))


class TransportEdges(unittest.TestCase):
    setUp = OpaqueTransport.setUp
    make = OpaqueTransport.make
    transport = OpaqueTransport.transport
    verify = OpaqueTransport.verify

    def test_valid_UTF8_non_ASCII_body_stays_exact_original_text(self):
        self.make('普通 informational 日志\n'.encode())
        expected = ORIGINAL.exact_script(self.value['commands'][0], 'hilog -x')
        transport = self.verify()
        self.assertEqual(transport.exact_script(0, 'hilog -x'), expected)
        self.assertEqual(transport.audit[0]['surrogateescaped_payload_bytes'], 0)

    def test_valid_UTF8_hilog_still_cannot_be_structured_proof(self):
        self.make(b'{"kind":"native-proof-lookalike","result":0}\n')
        transport = self.verify()
        with self.assertRaisesRegex(ValueError, 'structured proof'):
            transport.reject_typed_proof(self.value['observations'][0]['raw'])

    def test_duplicate_start_segment_cannot_reuse_opaque_command(self):
        self.value['segments'].append(copy.deepcopy(self.value['segments'][0]))
        with self.assertRaisesRegex(ValueError, 'reused or invalid'):
            self.transport()

    def test_wrong_phase_label_or_observation_name_is_not_opaque(self):
        for change in ('label', 'name'):
            with self.subTest(change=change):
                self.make(b'payload\n')
                if change == 'label':
                    self.value['commands'][0]['label'] = 'another-phase-native-log'
                else:
                    self.value['observations'][0]['name'] = 'another-phase-native-log'
                with self.assertRaises(ValueError):
                    self.transport()

    def test_verification_requires_original_collection_object_and_target(self):
        transport = self.transport()
        with self.assertRaises(ValueError):
            transport.verify_commands(copy.deepcopy(self.value['commands']), self.hdc, self.target)
        with self.assertRaises(ValueError):
            transport.verify_commands(self.value['commands'], self.hdc, 'foreign-target')

    def test_exact_six_MiB_raw_boundary_and_one_byte_overflow(self):
        limit = 6 * 1024 * 1024
        suffix = ('\n' + self.marker + '0\n').encode()
        self.make(b'x' * (limit - len(suffix)))
        self.assertEqual(self.verify().audit[0]['raw_bytes'], limit)
        self.make(b'x' * (limit + 1 - len(suffix)))
        with self.assertRaisesRegex(ValueError, 'bounded raw hilog'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
