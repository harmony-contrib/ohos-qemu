#!/usr/bin/env python3
"""Three small rejection/preservation checks; never executes SDK or guest tools."""
import ast
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import verify_media_pipeline578_results as media

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_COMMON = frozenset(('application-home', 'arkui-components', 'arkweb', 'audio-capture', 'audio-focus',
    'audio-revoke', 'avc-media', 'boot', 'certificate-manager', 'child-default-profile', 'completion-handler',
    'cxx-arkts11-gaps', 'env-reader', 'ethernet-control', 'fa-particle', 'graphics-memory', 'hitrace',
    'image-metadata', 'insight-contract', 'issue20-library-exit', 'lazy-column', 'lazy-layouts', 'luminance-sampler',
    'media-recorder', 'native-bindings-e2e', 'network-accounting', 'observer-info', 'photo-result-set', 'photos-asset',
    'power-suspend', 'project-quota', 'rpc-runtime', 'rs-objects', 'screen-blink', 'screen-modes', 'selection',
    'settings-all-navigation', 'settings-navigation', 'spring-loading', 'storage-stats', 'sys-vpn-store', 'thermal', 'vulkan'))
ORIGINAL_REPRESENTATIVE = frozenset(('contacts-picker', 'wallpaper', 'external-inputs', 'knowledge-holiday'))


class MediaCore578(unittest.TestCase):
    def test_missing_actual_UI_is_failure_before_any_resource(self):
        for configured in (None, ''):
            environment = {} if configured is None else {'QEMU_TEST_MEDIA_SCREEN_UI': configured}
            with self.assertRaisesRegex(ValueError, 'QEMU_TEST_MEDIA_SCREEN_UI'):
                media.media_suite_inputs(environment)

    def test_pass_summary_cannot_replace_actual_case_raw_replay(self):
        # These are intentionally INVALID parser fixtures, not runtime evidence.
        # Even a complete-looking 11-descriptor batch must reach the real raw
        # verifier and fail for missing original ordinary-HAP provenance.
        parent = os.environ.get('MEDIA578_CORE_HOST_ROOT')
        with tempfile.TemporaryDirectory(prefix='media578-rejection-', dir=parent) as directory:
            root = Path(directory)
            archive = root/'invalid-parser-fixture.tar.gz'; archive.write_bytes(b'not an actual package')
            source = root/'parser-only-ui.txt'; source.write_text('not a packaged SystemUI resource\n')
            plan = root/'parser-only-ui.json'; plan.write_text(json.dumps({'source_files':[
                {'path':str(source),'sha256':media.sha(source)}], 'allow':[{'bundle':'parser.fixture','text':'allow'}],
                'deny':[{'bundle':'parser.fixture','text':'deny'}], 'revoke':[{'bundle':'parser.fixture','text':'stop'}]}))
            plan_descriptor = {'path':str(plan),'sha256':media.sha(plan)}
            cases=[]
            for index,scenario in enumerate(media.BATCH):
                case = root/str(index); (case/'capture').mkdir(parents=True)
                runtime = case/'capture/runtime.json'; runtime.write_text(json.dumps({'scenario':scenario,'screen_ui_plan':plan_descriptor}))
                evidence = case/'evidence.json'; evidence.write_text(json.dumps({'status':'pass',
                    'capture_runtime_sha256':media.sha(runtime)}))
                cases.append({'scenario':scenario,'evidence':str(evidence),'sha256':media.sha(evidence)})
            batch={'schema_version':1,'status':'pass','scope':media.PACKAGE_BATCH_SCOPE,
                'archive_sha256':media.sha(archive),'boot_id':'parser-only-no-guest','arch':'arm64',
                'screen_ui_plan':plan_descriptor,'cases':cases,'closed_requirements':[],
                'first_artifact_behavior_gate_passed':False}
            with self.assertRaisesRegex(ValueError, 'original ordinary media runner evidence'):
                media.verify_package_batch(batch,archive,'parser-only-no-guest','arm64',replay_parent=root)
            for kind in ('missing-case','reused-descriptor','pretend-broad-closure'):
                bad=copy.deepcopy(batch)
                if kind=='missing-case':bad['cases'].pop()
                if kind=='reused-descriptor':bad['cases'][2]['evidence']=bad['cases'][0]['evidence']
                if kind=='pretend-broad-closure':bad['closed_requirements']=['behavior:video-encoder-dependent-media-pipelines']
                with self.assertRaises(ValueError,msg=kind):
                    media.verify_package_batch(bad,archive,'parser-only-no-guest','arm64',replay_parent=root)

    def test_original47_and_full_ledger_preserved_plus_required_media(self):
        gate = ROOT/'scripts/verify_first_artifact_gate.py'
        tree=ast.parse(gate.read_text()); names={'REQUIRED_CHECKS','REPRESENTATIVE_CHECKS','DEVICE_CHECKS'}
        statements=[]
        for node in tree.body:
            targets=node.targets if isinstance(node,ast.Assign) else [node.target] if isinstance(node,ast.AugAssign) else []
            if any(isinstance(n,ast.Name) and n.id in names for n in targets):statements.append(node)
        namespace={};exec(compile(ast.Module(body=statements,type_ignores=[]),str(gate),'exec'),namespace)
        self.assertEqual(len(ORIGINAL_COMMON),43)
        old47=ORIGINAL_COMMON|ORIGINAL_REPRESENTATIVE;self.assertEqual(len(old47),47)
        required=namespace['REQUIRED_CHECKS']|namespace['REPRESENTATIVE_CHECKS']
        self.assertTrue(old47 <= required)
        self.assertIn('media-pipeline578',required)
        self.assertGreaterEqual(len(required),48)
        suite=(ROOT/'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('cxx-arkts11-gaps', work / 'cxx-arkts11-gaps.json', [closure_record])",suite)
        self.assertIn("check('media-pipeline578', media_batch_path, media_records)",suite)
        self.assertIn('for index, scenario in enumerate(MEDIA578_BATCH):',suite)
        self.assertLess(suite.index('media578_inputs = media_suite_inputs(os.environ)'),suite.index('QemuGuest(boot_args).start()'))
        self.assertIn('verify_package_batch(payload, Path(identity[',gate.read_text())


if __name__=='__main__':unittest.main()
