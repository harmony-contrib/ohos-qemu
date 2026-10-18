"""Whole-source/replay counterexamples using authentic E source fixtures.

These host tests exercise only source selection and additive diagnostics. They
do not simulate native sessions, fabricate callback state, or certify a package.
Root runs them after the complete source batch; the location agent did not.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent/'fixtures/batch_system/location_native_identity'
CONTRACT = json.loads((FIXTURE/'source-contract.json').read_text())


def module(row):
    path=ROOT/row['component']/'verify_source.py'
    spec=importlib.util.spec_from_file_location('native_identity_'+row['role'],path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


class NativeIdentityExactStateTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='location-native-identity-HOST-')
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.rows=CONTRACT['components'];self.modules={row['role']:module(row) for row in self.rows}
        self.write_state('original')
        # All negatives begin with both complete authentic original files.
        self.assertFalse(self.modules['arkui'].validate_batch(self.root))

    def write_state(self,state,role=None):
        for row in self.rows:
            if role and row['role']!=role:continue
            target=self.root/row['source_path'];target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((FIXTURE/state/row['source_path']).read_bytes())

    def bytes(self):
        return {row['source_path']:(self.root/row['source_path']).read_bytes() for row in self.rows}

    def apply(self,row):
        # Only root executes this test. Git apply targets an owned host scratch
        # source tree, never a real upstream source/out or repository index.
        result=subprocess.run([sys.executable,'-B',str(ROOT/'patches/lib/apply_exact_component.py'),
            '--component-dir',str(ROOT/row['component']),'--source-root',str(self.root)],
            capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),check=False)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_original_and_final_whole_file_hashes_are_exact(self):
        for row in self.rows:
            for state,key in [('original','original_sha256'),('final','final_sha256')]:
                with self.subTest(role=row['role'],state=state):
                    self.assertEqual(hashlib.sha256((FIXTURE/state/row['source_path']).read_bytes()).hexdigest(),row[key])
            self.assertEqual(self.modules[row['role']].metadata()['patch_sha256'],row['patch_sha256'])
        self.write_state('final');self.assertTrue(self.modules['arkui'].validate_batch(self.root,require_patched=True))

    def test_exact_apply_and_second_replay_leave_identical_final_bytes(self):
        for row in self.rows:self.apply(row)
        first=self.bytes();self.assertTrue(self.modules['arkui'].validate_batch(self.root,require_patched=True))
        for row in self.rows:self.apply(row)
        self.assertEqual(first,self.bytes())
        for row in self.rows:self.assertEqual(first[row['source_path']],(FIXTURE/'final'/row['source_path']).read_bytes())

    def test_cross_project_mixed_state_rejected_both_directions(self):
        for role in ('arkui','ams'):
            self.write_state('original');self.write_state('final',role);before=self.bytes()
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'mixed ArkUI/AMS'):
                self.modules['arkui'].validate_batch(self.root)
            self.assertEqual(before,self.bytes())

    def test_original_cannot_be_promoted_to_build_ready(self):
        before=self.bytes()
        with self.assertRaisesRegex(ValueError,'both native identity carriers must be final'):
            self.modules['arkui'].validate_batch(self.root,require_patched=True)
        self.assertEqual(before,self.bytes())

    def test_unknown_or_partial_bytes_are_preserved_and_rejected(self):
        for row in self.rows:
            self.write_state('original');path=self.root/row['source_path']
            path.write_bytes(path.read_bytes()+b'\n// HOST unknown concurrent edit\n');before=self.bytes()
            with self.subTest(role=row['role']),self.assertRaisesRegex(ValueError,'unknown/incomplete'):
                self.modules['arkui'].validate_batch(self.root)
            self.assertEqual(before,self.bytes())

    def test_one_overload_repair_is_not_a_complete_arkui_component(self):
        row=self.rows[0];self.assertEqual(row['role'],'arkui')
        original=(FIXTURE/'original'/row['source_path']).read_text()
        final=(FIXTURE/'final'/row['source_path']).read_text()
        boundary='void UIExtensionPattern::DumpInfo(std::unique_ptr<JsonValue>& json)'
        for source in (final.split(boundary)[0]+boundary+original.split(boundary)[1],
                       original.split(boundary)[0]+boundary+final.split(boundary)[1]):
            self.write_state('original');(self.root/row['source_path']).write_text(source);before=self.bytes()
            with self.assertRaisesRegex(ValueError,'unknown/incomplete'):self.modules['arkui'].validate_batch(self.root)
            self.assertEqual(before,self.bytes())

    def test_symlink_source_never_counts_as_exact_source(self):
        row=self.rows[0];path=self.root/row['source_path'];saved=self.root/'HOST-original';path.replace(saved);path.symlink_to(saved)
        with self.assertRaisesRegex(ValueError,'symlink'):self.modules['arkui'].validate_batch(self.root)


class NativeIdentitySourceScopeTests(unittest.TestCase):
    def test_arkui_only_adds_diagnostics_to_the_two_existing_dump_overloads(self):
        row=CONTRACT['components'][0];original=(FIXTURE/'original'/row['source_path']).read_text()
        final=(FIXTURE/'final'/row['source_path']).read_text()
        stripped,count=re.subn(r'    // Native diagnostic identity only\..*?\n    }\n', '', final,flags=re.S)
        self.assertEqual(count,2);self.assertEqual(stripped.replace("#include <unistd.h>\n\n", "", 1),original)
        blocks=re.findall(r'    // Native diagnostic identity only\..*?\n    }\n',final,flags=re.S)
        for block in blocks:
            self.assertLess(block.index('WillRunOnCurrentThread(TaskExecutor::TaskType::UI)'),block.index('sessionWrapper_->GetSessionId()'))
            for actual in ('getpid()', 'getuid()', 'identityHost->GetId()','identityHost->GetAccessibilityId()',
                           'sessionWrapper_->GetSessionId()','std::to_string(realHostWindowId_)','std::to_string(focusWindowId_)'):
                self.assertIn(actual,block)
            for mutation in ('CreateSession(', 'DestroySession(', 'RequestExtensionSession(', 'StartUIExtensionAbility(', 'SetSessionInfo('):
                self.assertNotIn(mutation,block)

    def test_ams_only_adds_actual_published_session_fields_inside_ui_extension_branch(self):
        row=CONTRACT['components'][1];original=(FIXTURE/'original'/row['source_path']).read_text()
        final=(FIXTURE/'final'/row['source_path']).read_text()
        stripped,count=re.subn(r'        // The same real SessionInfo identity.*?\n        }\n','',final,flags=re.S)
        self.assertEqual(count,1);self.assertEqual(stripped.replace("#include <unistd.h>\n\n", "", 1),original)
        block=re.search(r'        // The same real SessionInfo identity.*?\n        }\n',final,flags=re.S).group()
        self.assertIn('const auto identitySession = GetSessionInfo();',block)
        self.assertIn('if (identitySession)',block)
        for field in ('persistentId','hostWindowId','realHostWindowId','uiExtensionUsage'):self.assertIn('identitySession->'+field,block)
        self.assertNotIn('identitySession->sessionToken',block)
        self.assertNotRegex(block,r'identitySession->\w+\s*=(?!=)')

    def test_no_handwritten_id_time_nonce_or_global_enable_is_a_session_carrier(self):
        for row in CONTRACT['components']:
            post=(FIXTURE/'final'/row['source_path']).read_text()
            prefix='// Native diagnostic identity only.' if row['role']=='arkui' else '// The same real SessionInfo identity'
            for block in re.findall(re.escape(prefix)+r'.*?\n\s{4,8}}\n',post,flags=re.S):
                for forbidden in ('rand(', 'random(', 'chrono::', 'clock_gettime(', 'EnableGnss(', 'StartGnss(', 'uid == 0'):
                    self.assertNotIn(forbidden,block)


if __name__=='__main__':unittest.main()
