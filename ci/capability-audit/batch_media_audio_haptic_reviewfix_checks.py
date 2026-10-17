#!/usr/bin/env python3
"""Controlled host counterexamples ONLY: no SDK/signing/native/guest success."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import batch_media_audio_haptic_project as project
import batch_media_audio_haptic_runtime as runtime
import batch_media_audio_haptic_verify as verify


class ReviewFixChecks(unittest.TestCase):
    def test_signer_uses_new_shared_payload_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); unsigned = root/'controlled-unsigned.hap'; unsigned.write_bytes(b'controlled host input')
            jar = root/'controlled.jar'; jar.write_bytes(b'not executable')
            commands = []
            def command(argv, label):
                commands.append(argv)
                Path(argv[argv.index('--output')+1]).write_bytes(b'controlled signed stand-in; never guest evidence')
            with patch.object(runtime.signatures, 'ordinary_hap'), patch.object(runtime.signatures, 'signer_inputs', return_value=(root,jar,{})), \
                 patch.object(runtime.signatures, 'verify_signed_payload', create=True) as comparator, \
                 patch.object(runtime.signatures, 'verify_signed_hap_artifacts', return_value={}):
                proof = runtime.sign_ordinary_hap(unsigned, project.ROLES['normal'][0], ['ohos.permission.VIBRATE'],
                    'a'*64, root, jar, root/'signing', command)
                comparator.assert_called_once_with(unsigned, root/'signing/signed.hap')
                self.assertEqual(commands[0][-2:], ['--sign-code','1'])
                self.assertEqual(proof['unsigned_hap'], project.record(unsigned))
        tree = ast.parse((project.HERE/'batch_media_audio_haptic_runtime.py').read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                 and node.func.attr == 'Commands']
        self.assertEqual(len(calls),1)
        self.assertEqual(ast.unparse(calls[0].args[1]), "value['signature_reverification_commands']")

    def test_sdk_receipt_rejects_wrong_origin_and_commands(self):
        # These are deliberately synthetic host receipts for this validator;
        # the real generic compiled-HAP checker remains a separate prerequisite.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); cpu=root/'cpu-cap.cjs'; cpu.write_bytes((project.FIX/'cpu-cap.cjs').read_bytes())
            tools = {}
            for name in ('node','ohpm','hvigor'):
                path=root/('controlled-'+name);path.write_text('not an SDK executable\n');tools[name]=path
            tools['cpu_cap']=cpu
            sdk = {}
            for name in ('metadata','audio_haptic','device_default'):
                path=root/('controlled-'+name+'.json');path.write_text('{}\n');sdk[name]=project.record(path)
            sources={role:root/role for role in project.ROLES}
            for path in sources.values(): path.mkdir()
            report=dict(scope=project.SDK_SCOPE,exit_code=0,failures=[],source_commit='a'*40,
                runner_sha256=project.sha(project.HERE/'batch_media_audio_haptic_build_callers.py'),
                source_tools={name:project.sha(project.HERE/name) for name in project.SDK_SOURCE_TOOLS},
                fixture_hashes=project.fixture_hashes(),sdk=sdk,source_files={role:{} for role in project.ROLES},
                projects={role:str(path) for role,path in sources.items()},runtime_inputs={name:project.record(path) for name,path in tools.items()},
                commands=[],haps=[],node_version='v18.20.1')
            prefix=[str(tools['node']),'--max-old-space-size=2048','--require',str(cpu)]
            expected=[('_toolchain','node-version',[str(tools['node']),'--version'],str(root))]
            for role in project.ROLES:
                expected += [(role,'dependencies',prefix+[str(tools['ohpm']),'install','--all','--registry',
                    'http://127.0.0.1:9','--fetch_timeout','10000','--retry_times','0'],str(sources[role])),
                    (role,'compile',prefix+[str(tools['hvigor']),'assembleHap','--mode','module','-p','product=default','-p',
                     'module=entry','-p','debuggable=false','-p','hvigor-obfuscation=false','--no-daemon','--no-parallel',
                     '--no-incremental','--max-old-space-size','2048'],str(sources[role]))]
                hap=sources[role]/'controlled-host-input.hap';hap.write_bytes(b'not a compiled HAP; unit test only')
                report['haps'].append(dict(project=role,path=str(hap),sha256=project.sha(hap),bytes=hap.stat().st_size))
            for index,(role,label,argv,cwd) in enumerate(expected):
                log=root/('controlled-command-'+str(index)+'.log');log.write_text('v18.20.1\n' if index==0 else 'controlled host validation input\n')
                report['commands'].append(dict(project=role,label=label,argv=argv,cwd=cwd,exit_code=0,timed_out=False,
                    log=str(log),sha256=project.sha(log)))
            path=root/'controlled-receipt.json'
            def spec(value):
                path.write_text(json.dumps(value))
                return dict(sdk_project='normal',sdk_evidence=project.record(path),source_project=str(sources['normal']),
                    unsigned_hap=project.record(sources['normal']/'controlled-host-input.hap'))
            project.verify_sdk_receipt(spec(report),'normal',sdk)
            mutations=[lambda r:r.update(scope='generic SDK scope'), lambda r:r.update(runner_sha256='f'*64),
                lambda r:r.update(exit_code=1),lambda r:r['failures'].append('actual failure'),
                lambda r:r['source_tools'].update({project.SDK_SOURCE_TOOLS[0]:'f'*64}),
                lambda r:r['commands'][2].update(cwd=str(root)),lambda r:r['commands'][2]['argv'].append('--unexpected'),
                lambda r:r['commands'][2].update(timed_out=True),lambda r:r.update(node_version='v0.0.0'),
                lambda r:r.update(haps=r['haps'][:1])]
            for mutate in mutations:
                changed=copy.deepcopy(report);mutate(changed)
                with self.assertRaises(ValueError): project.verify_sdk_receipt(spec(changed),'normal',sdk)
            wrong=spec(report);wrong['sdk_project']='denied'
            with self.assertRaises(ValueError): project.verify_sdk_receipt(wrong,'normal',sdk)
            changed_sdk=copy.deepcopy(sdk);changed_sdk['metadata']=sdk['audio_haptic']
            with self.assertRaises(ValueError): project.verify_sdk_receipt(spec(report),'normal',changed_sdk)

    def test_same_click_pairs_are_complete_fresh_and_keep_original_duration(self):
        plan=project.execution_plan();flat=[row for block in plan for row in block]
        self.assertEqual(flat,project.phases())
        pairs=[block for block in plan if len(block)==2]
        self.assertEqual(len(pairs),11)
        wanted={row['name'] for row in project.phases() if row['active_before'] is not None}
        self.assertEqual({block[1]['name'] for block in pairs},wanted)
        self.assertTrue(all(block[0]['action']=='start' and block[1]['action'] in ('stop','release') for block in pairs))
        self.assertTrue(all(block[0]['hold_ms'] in (1100,9200) for block in pairs))
        self.assertEqual(len(flat),74)
        first={'role':'normal','phase':'normal-start-1','request':dict(run_id='a'*32,boot_id='b'*36,operation_id='c'*32,action='start')}
        second={'role':'normal','phase':'normal-stop-1','request':dict(run_id='a'*32,boot_id='b'*36,operation_id='d'*32,action='stop')}
        paired=project.paired_request(first,second,1100)
        self.assertEqual(paired['following_request'],second['request'])
        self.assertEqual(paired['following_delay_ms'],1100)
        bad=copy.deepcopy(second);bad['request']['operation_id']=first['request']['operation_id']
        with self.assertRaises(ValueError):project.paired_request(first,bad,1100)
        with self.assertRaises(ValueError):project.paired_request(first,second,10001)
        source=(project.FIX/'Index.ets').read_text()
        self.assertIn('await current.step(following)',source)
        self.assertIn('setTimeout(',source)
        self.assertEqual(source.count('new AudioHapticProbe('),1)

    def test_failed_stop_still_attempts_release_and_preserves_failure(self):
        invoked=[];captured={};errors=[]
        envelope={'role':'normal','phase':'normal-stop-1','request':{'operation_id':'a'*32,'action':'stop'}}
        def invoke(current,cleanup):
            invoked.append(current['request']['action']);self.assertTrue(cleanup)
            if current['request']['action']=='stop':raise ValueError('controlled genuine-style Stop failure')
            captured['row']={'operation_id':current['request']['operation_id'],'event':'complete'}
            return 'controlled-operation'
        runtime.cleanup_player_actions(invoke,envelope,lambda op:[captured['row']],errors,'normal')
        self.assertEqual(invoked,['stop','release']);self.assertEqual(len(errors),1)
        self.assertIn('Stop failure',errors[0]);self.assertEqual(envelope['request']['operation_id'],'a'*32)

    def test_exact_clock_token_and_owned_cleanup_scripts(self):
        remote='/data/local/tmp/audio-haptic-'+'a'*32;run='a'*32;boot='b'*36
        self.assertEqual(project.sampler_script(remote,'clock',run,boot),
            'unset LD_LIBRARY_PATH LD_PRELOAD; '+remote+'/sampler clock '+run+' '+boot)
        token=project.sampler_script(remote,'token',run,boot,project.ROLES['normal'][0],20010001)
        self.assertTrue(token.endswith(' token '+run+' '+boot+' '+project.ROLES['normal'][0]+' 20010001'))
        with self.assertRaises(ValueError):project.sampler_script(remote,'start',run,boot)
        ui='/data/local/tmp/qemu-capability-ui-'+'c'*32+'-1.json'
        paths,script=project.private_cleanup_script(remote,[ui,ui])
        self.assertEqual(paths,[remote+'/sampler',ui]);self.assertIn('rmdir '+remote,script)
        self.assertIn('test ! -L '+remote,script);self.assertNotIn('rm -rf',script)
        with self.assertRaises(ValueError):project.private_cleanup_script('/data/local/tmp/not-owned',[ui])
        with self.assertRaises(ValueError):project.private_cleanup_script(remote,['/data/local/tmp/foreign.json'])

    def test_loop_with_explicit_stop_requires_long_real_signal_and_quiet_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);challenge=project.challenge(root/'challenge');data=project.validate_challenge(challenge)
            raw=project.checked(data['reference']).read_bytes()
            path=root/'controlled-loop-stopped.wav'
            with wave.open(str(path),'wb') as stream:
                stream.setparams((2,2,48000,0,'NONE','none'));stream.writeframes(raw*9+bytes(48000*4))
            capture=dict(wav=project.record(path),host_begin_ns=1000000000,host_end_ns=11000000000)
            expectation={'audio':'loop','action':'start'}
            with self.assertRaises(ValueError):verify.audio_metrics(capture,expectation,project.pcm.pcm_values(raw))
            result=verify.audio_metrics(capture,expectation,project.pcm.pcm_values(raw),followed_by_boundary=True)
            self.assertLess(result['tail_rms'],1)
            quiet=verify.audio_metrics(capture,{'audio':'quiet','action':'stop'},project.pcm.pcm_values(raw))
            self.assertLess(quiet['tail_rms'],1)

    def test_active_boundary_rejects_eos_inactive_stale_and_ended_pcm(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);challenge=project.challenge(root/'challenge');data=project.validate_challenge(challenge)
            reference=project.checked(data['reference']).read_bytes()
            def wav(name,active_frames):
                path=root/(name+'.wav')
                with wave.open(str(path),'wb') as stream:
                    stream.setparams((2,2,48000,0,'NONE','none'))
                    stream.writeframes(bytes(9600*4)+(reference*2)[:active_frames*4]+bytes(24000*4))
                return project.record(path)
            first=root/'controlled-start.json';second=root/'controlled-stop.json'
            project.write(first,{'request':{'operation_id':'c'*32}});project.write(second,{'request':{'operation_id':'d'*32}})
            expected=next(row for row in project.phases() if row['name']=='normal-stop-1')
            segment=dict(boundary_expected=expected,operation={'request':project.record(first)},
                boundary_operation={'request':project.record(second)},sampler={},
                audio_capture={'wav':wav('controlled-active',57600),'host_begin_ns':10000000000})
            journal=[dict(operation_id='c'*32,event='return',api='AudioHapticPlayer.start',player_epoch=1,sequence=1),
                     dict(operation_id='d'*32,event='begin',player_epoch=1,sequence=3,timestamp_ms=1100)]
            samples=[dict(realtime_ns=t*1000000,before_ns=t*1000000,after_ns=t*1000000+100,running=True)
                     for t in range(1010,1100,10)]
            with patch.object(verify,'sampler_rows',return_value=({},samples)):
                result=verify.active_boundary_metrics(segment,data,'b'*36,journal,(10000000000,10000000000))
                self.assertEqual(result['preceding_VDI_samples'],9)
                eos=journal+[dict(operation_id='c'*32,event='callback',api='AudioHapticPlayer.endOfStream',sequence=2)]
                with self.assertRaises(ValueError):verify.active_boundary_metrics(segment,data,'b'*36,eos,(10000000000,10000000000))
                with self.assertRaises(ValueError):verify.active_boundary_metrics(segment,data,'b'*36,journal,(10000000000,10200000000))
                ended=copy.deepcopy(segment);ended['audio_capture']['wav']=wav('controlled-ended',24000)
                with self.assertRaises(ValueError):verify.active_boundary_metrics(ended,data,'b'*36,journal,(10000000000,10000000000))
            inactive=copy.deepcopy(samples);inactive[-1]['running']=False
            with patch.object(verify,'sampler_rows',return_value=({},inactive)):
                with self.assertRaises(ValueError):verify.active_boundary_metrics(segment,data,'b'*36,journal,(10000000000,10000000000))
            with patch.object(verify,'sampler_rows',return_value=({},samples[:3])):
                with self.assertRaises(ValueError):verify.active_boundary_metrics(segment,data,'b'*36,journal,(10000000000,10000000000))


if __name__=='__main__':
    print('CONTROLLED HOST COUNTEREXAMPLES ONLY: no SDK, signer, native compiler, guest, actual audio or VDI validation')
    unittest.main(verbosity=2)
