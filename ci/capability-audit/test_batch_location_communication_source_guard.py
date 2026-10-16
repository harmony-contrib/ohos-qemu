#!/usr/bin/env python3
"""Strict communication component preflight at all three pinned project roots."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import ROOT
from test_batch_location_communication_runtime import COMPONENT, FIXTURE, sources


class CommunicationGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states={'original':json.loads(FIXTURE.read_text())['files'],
                    **{'prefix_'+str(index):sources(prefix=index) for index in range(1,len(list(COMPONENT.glob('*.patch'))))},
                    'final':sources()}

    def fixture(self,directory,state='original'):
        root=Path(directory)/'source';component=Path(directory)/'fixture'/COMPONENT.relative_to(ROOT)
        shutil.copytree(COMPONENT,component)
        manifest=json.loads((component/'source_states.json').read_text())
        verifier=(component/'verify_source.py').read_text()
        for project,revision in manifest['projects'].items():
            path=root/project;path.mkdir(parents=True)
            subprocess.run(['git','init','-q',str(path)],check=True)
            subprocess.run(['git','-C',str(path),'-c','user.name=Location fixture','-c','user.email=location-fixture@example.invalid','commit','--allow-empty','-qm','Fixture HEAD'],check=True)
            head=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
            manifest['projects'][project]=head;verifier=verifier.replace(revision,head)
        manifest['states']={name:{n:hashlib.sha256(text.encode()).hexdigest() for n,text in files.items()} for name,files in self.states.items()}
        (component/'verify_source.py').write_text(verifier);(component/'source_states.json').write_text(json.dumps(manifest))
        for name,text in self.states[state].items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        return root,component

    def apply(self,root,component):
        return subprocess.run(['bash',str(component/'apply.sh'),'--source-root',str(root)],capture_output=True,text=True)

    def contents(self,root):
        return {name:(root/name).read_bytes() for name in self.states['original']}

    def test_original_final_and_idempotence(self):
        for state in self.states:
            with self.subTest(state=state),tempfile.TemporaryDirectory(prefix='batch-location-communication-guard-') as directory:
                root,component=self.fixture(directory,state)
                result=self.apply(root,component);self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                final={n:s.encode() for n,s in self.states['final'].items()};self.assertEqual(final,self.contents(root))
                result=self.apply(root,component);self.assertEqual(0,result.returncode,result.stdout+result.stderr);self.assertEqual(final,self.contents(root))

    def test_unknown_mixed_head_symlink_and_patch_rejected(self):
        name='base/telephony/state_registry/frameworks/js/napi/src/napi_state_registry.cpp'
        for fault in ['unknown','mixed','head','symlink','patch']:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='batch-location-communication-guard-') as directory:
                root,component=self.fixture(directory);target=root/name
                if fault=='unknown':target.write_text(target.read_text()+'\n// unknown user edit\n')
                elif fault=='mixed':target.write_text(self.states['final'][name])
                elif fault=='head':subprocess.run(['git','-C',str(root/'base/telephony/core_service'),'-c','user.name=Location fixture','-c','user.email=location-fixture@example.invalid','commit','--allow-empty','-qm','Changed HEAD'],check=True)
                elif fault=='symlink':
                    external=Path(directory)/'outside';shutil.copy2(target,external);target.unlink();target.symlink_to(external)
                else:
                    patch=next(component.glob('*.patch'));patch.write_text(patch.read_text()+'\n')
                before=self.contents(root);result=self.apply(root,component);self.assertNotEqual(0,result.returncode);self.assertEqual(before,self.contents(root));self.assertFalse((root/'.ohos-qemu-patches').exists())

if __name__=='__main__':unittest.main()
