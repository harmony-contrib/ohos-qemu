"""375 successor's inherited pure adversarial protocol tests, using UNIT data."""
import copy
import unittest
import batch_network375_peer_protocol as P
from batch_network375_peer_fixture import Frame267,raw


class Peer267(unittest.TestCase):
    def setUp(self):self.f=Frame267()
    def full(self):return self.f.runtime()
    def failed(self):
        result=self.f.prove();self.assertFalse(result['closed']);self.assertFalse(result['ready']);self.assertTrue(result['errors']);return result
    def ctor(self,operation):
        ref=operation['constructor'];return self.f.ledgers[ref['ledger_path']]['spawns'][ref['index']]
    def first_inspect(self):
        return next(op for op in self.f.operations if op['origin']=='controller'and op['argv']==['docker','container','inspect',self.f.peer_id])
    def classify(self,argv):
        return P.admit_argv(self.f.contract,argv,phase='runtime',observed_ids={'build':self.f.build_id,'peer':self.f.peer_id,'network':self.f.network_id},context=self.f.context)

    def test_original_shape_names_and_source_exact_stop35(self):
        self.assertEqual(self.f.contract['names']['peer'],'owned-vpn-peer-'+'1'*32)
        self.assertEqual(self.classify(['docker','stop','--time=35',self.f.peer_id]),dict(action='stop',role='peer'))
        with self.assertRaises(P.NotReady):self.classify(['docker','stop','--time=10',self.f.peer_id])

    def test_synthetic_complete_chain_is_scoped_and_never_ready(self):
        self.full();result=self.f.prove();self.assertTrue(result['closed'],result)
        self.assertTrue(result['original_outcomes_verified']);self.assertFalse(result['runtime_validated']);self.assertFalse(result['signal_authority_granted']);self.assertFalse(result['ready'])

    def test_build_create_stays_in_full_prefix(self):
        self.full();result=self.f.prove();self.assertTrue(result['closed'],result)
        self.assertEqual(result['prefix_row_count'],9);self.assertEqual(result['runtime_create_count'],2)
        self.assertEqual(result['runtime_original_Docker_create_count'],1);self.assertEqual(result['runtime_network_create_count'],1)
        self.assertNotIn(self.f.build_id,result['actual_resource_ids'].values())
        self.assertEqual(self.f.state['commands'][:9],self.f.anchor['prefix_state']['commands'])

    def test_wrong_name_refused(self):
        argv=copy.deepcopy(self.f.contract['plan']['peer_create']);argv[argv.index('--name')+1]='foreign'
        with self.assertRaises(P.NotReady):self.classify(argv)

    def test_wrong_label_refused(self):
        argv=copy.deepcopy(self.f.contract['plan']['peer_create']);argv[argv.index('--label')+1]='org.harmonycontrib.openvpn-owned-run=wrong'
        with self.assertRaises(P.NotReady):self.classify(argv)

    def test_wrong_image_refused(self):
        argv=copy.deepcopy(self.f.contract['plan']['peer_create']);argv[argv.index(self.f.contract['plan']['image'])]='sha256:'+'9'*64
        with self.assertRaises(P.NotReady):self.classify(argv)

    def test_extra_or_reordered_original_argv_refused(self):
        original=self.f.contract['plan']['peer_create']
        for argv in (original+['--arbitrary'],original[:2]+['--privileged']+original[2:]):
            with self.subTest(argv=argv),self.assertRaises(P.NotReady):self.classify(argv)

    def test_contract_plan_tamper_even_rehashed_refused(self):
        c=copy.deepcopy(self.f.contract);c['plan']['peer_create'][3]='--platform=linux/arm64'
        c['contract_id']=P.digest({k:v for k,v in c.items()if k!='contract_id'})
        with self.assertRaises(P.NotReady):P.checked_contract(c)

    def test_original_source_changed_refused(self):
        sources=dict(self.f.sources);sources['openvpn-owned-peer-review/peer_plan.py']+=b'\n'
        with self.assertRaises(P.NotReady):P.derive_contract(self.f.config_raw,self.f.config_descriptor,sources)

    def test_original_return_boolean_is_not_a_witness(self):
        with self.assertRaises(P.NotReady):P.make_runtime_anchor(self.f.contract,verified_built_case_return=True,prefix_state_raw=self.f.prefix_state_raw,
            sdk_launcher_raw=self.f.launcher_raw,challenge_raw=self.f.challenge_raw,staged_code=self.f.staged_code,prefix_logs=self.f.prefix_logs)

    def test_backend_return_shape_is_independently_checked(self):
        state=copy.deepcopy(self.f.state);state['backend_proof']['verified']['macros']['TARGET_LINUX']=True
        with self.assertRaises(P.NotReady):P.make_runtime_anchor(self.f.contract,verified_built_case_return=state,prefix_state_raw=raw(state),
            sdk_launcher_raw=self.f.launcher_raw,challenge_raw=self.f.challenge_raw,staged_code=self.f.staged_code,prefix_logs=self.f.prefix_logs)

    def test_prefix_mutation_refused(self):
        self.full();self.f.state['commands'][0]['argv'].append('changed');self.failed()

    def test_prefix_log_changed_refused(self):
        self.full();self.f.logs[self.f.state['commands'][0]['log']]=b'changed';self.failed()

    def test_original_prefix_raw_snapshot_changed_refused(self):
        self.full();self.f.prefix_state_raw+=b'\n';self.failed()

    def test_original_suffix_multiplicity_missing_constructor_refused(self):
        self.full();self.f.state['commands'].append(copy.deepcopy(self.f.state['commands'][-1]));self.failed()

    def test_actual_constructor_omitted_from_operations_refused(self):
        self.full();self.f.operations.pop(5);self.failed()

    def test_actual_constructor_reference_reused_refused(self):
        self.full();self.f.operations[1]['constructor']=copy.deepcopy(self.f.operations[0]['constructor']);self.failed()

    def test_state_cid_substitution_refused(self):
        self.full();self.f.state['ids']['peer']='9'*64;self.failed()

    def test_actual_inspect_wrong_owner_label_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Config']['Labels']={'foreign':'true'}
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_actual_inspect_wrong_name_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Name']='/foreign'
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_actual_inspect_wrong_image_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Image']='sha256:'+'9'*64
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_complete_mount_shuffle_is_accepted(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Mounts'].reverse()
        self.f.replace_result(op['id'],stdout=raw([metadata]));result=self.f.prove();self.assertTrue(result['closed'],result)

    def test_mount_member_or_duplicate_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Mounts'].append(copy.deepcopy(metadata['Mounts'][0]))
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_mount_rw_boolean_numeric_substitution_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Mounts'][0]['RW']=0
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_host_nested_type_substitution_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['HostConfig']['Memory']=float(metadata['HostConfig']['Memory'])
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_foreign_network_occupant_refused(self):
        self.full();op=next(op for op in self.f.operations if op['origin']=='controller'and op['argv']==['docker','network','inspect',self.f.network_id])
        metadata=self.f.network();metadata['Containers']={'9'*64:{'Name':'foreign'}}
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_unknown_create_never_inferred_absent_from_later_empty_queries(self):
        self.full();op=next(op for op in self.f.operations if op['argv']==self.f.contract['plan']['peer_create'])
        self.ctor(op).update(state='unknown',pid=None,exit_code=None,reaped=False);self.failed()

    def test_empty_actual_create_id_refused(self):
        self.full();op=next(op for op in self.f.operations if op['argv']==self.f.contract['plan']['peer_create'])
        self.f.replace_result(op['id'],stdout=b'');self.failed()

    def test_missing_second_final_cut_refused(self):
        self.full();self.f.cuts.pop();self.failed()

    def test_final_cut_constructor_replay_refused(self):
        self.full();self.f.cuts[1]['process_operation']=self.f.cuts[0]['process_operation'];self.failed()

    def test_unknown_final_query_failure_is_not_absence(self):
        self.full();operation_id=self.f.cuts[0]['resource_operations'][0]
        self.f.replace_result(operation_id,code=2,stderr=b'unknown engine error\n');self.failed()

    def test_actual_group_still_present_refused_without_signal_authority(self):
        self.full();operation_id=self.f.cuts[0]['process_operation']
        self.f.replace_result(operation_id,stdout=b'1 0 1 0 Fri Oct 16 00:00:00 2026\n444 1 10001 501 Sat Oct 17 00:00:00 2026\n');result=self.failed()
        self.assertNotIn('signal_authority_granted',result)

    def test_missing_expected_none_endpoint_key_refused(self):
        self.full();op=self.f.operations[0];self.ctor(op)['effective_environment'].pop('DOCKER_HOST');self.failed()

    def test_boolean_pid_refused(self):
        self.full();self.ctor(self.f.operations[0])['pid']=True;self.failed()

    def test_actual_final_exec_argv_rewrite_refused(self):
        self.full();self.ctor(self.f.operations[0])['final_exec_argv'][0]=P.CLI97['path'];self.failed()

    def test_actual_trampoline_argv_tamper_refused(self):
        self.full();self.ctor(self.f.operations[0])['actual_spawn_argv'][3]='--wrong-mask';self.failed()

    def test_unknown_extra_constructor_row_refused(self):
        self.full();ledger=next(iter(self.f.ledgers.values()));ledger['spawns'].append(copy.deepcopy(ledger['spawns'][0]));self.failed()

    def test_original_error_is_retained_after_independent_resource_closure(self):
        self.full();self.f.state['failure']='SYNTHETIC original stage error preserved';result=self.f.prove()
        self.assertTrue(result['closed'],result);self.assertFalse(result['original_outcomes_verified']);self.assertTrue(result['retained_original_failures'])

    def test_non_mount_ordered_array_drift_refused(self):
        self.full();op=self.first_inspect();metadata=self.f.container('peer',False);metadata['Config']['Env'].reverse()
        self.f.replace_result(op['id'],stdout=raw([metadata]));self.failed()

    def test_nested_config_scalar_type_is_exact(self):
        metadata=self.f.container('peer',False);metadata['Config']['Nested']={'count':1}
        first=P.immutable_container(metadata);metadata['Config']['Nested']['count']=True
        self.assertFalse(P.exact(first,P.immutable_container(metadata)))

    def test_actual_constructor_source_substitution_refused(self):
        self.full();ledger=next(iter(self.f.ledgers.values()));ledger['source']=dict(ledger['source'],sha256='8'*64);self.failed()

    def test_actual_owner_nonce_substitution_refused(self):
        self.full();self.f.binding['nonce']='3'*32;self.failed()

    def test_operation_sequence_gap_refused(self):
        self.full();self.f.operations[-1]['sequence']+=1;self.failed()

    def test_unknown_owner_observation_result_is_not_absence(self):
        self.full();op=next(op for op in self.f.operations if op['origin']=='owner-observation')
        self.f.replace_result(op['id'],code=2,stdout=b'',stderr=b'unknown query failure\n');self.failed()

    def test_old_e_commit_refused_even_with_new_raw_descriptor(self):
        config=copy.deepcopy(self.f.config);config['commit']='c14e803c33f96f5fe01e04378c868fce32aa1487';body=raw(config)
        with self.assertRaises(P.NotReady):P.derive_contract(body,P.record_bytes('/fixture/intent.json',body),self.f.sources)

    def test_final_name_or_id_query_cannot_be_skipped(self):
        self.full();self.f.cuts[0]['resource_operations'].pop();self.failed()


if __name__=='__main__':unittest.main()
