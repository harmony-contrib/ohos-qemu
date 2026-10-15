"""Actual fixed source states, all-nine-file guard, CRLF preservation and old stack replay."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
COMPONENT=REPO/'patches/common/foundation/multimedia/media_library/knowledge_content'
FIXTURE=Path(__file__).parent/'fixtures/batch_media/knowledge'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value


install=load('batch_knowledge_install',COMPONENT/'apply.py')


def original():
    entries=json.loads((FIXTURE/'baseline.json').read_text())['files']
    result={}
    for name,entry in entries.items():
        data=gzip.decompress(base64.b64decode(entry['gzip_base64'],validate=True))
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('bad fixed source fixture')
        result[name]=data
    return result


def write(root,values):
    for name,data in values.items():
        path=root/install.transforms.PROJECT/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)


class KnowledgeInstallTests(unittest.TestCase):
    def test_actual_source_all_targets_apply_twice_and_preserve_crlf(self):
        before=original()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write(root,before)
            self.assertFalse(install.validate(root));install.run(root);self.assertTrue(install.validate(root,True))
            after={name:(root/install.transforms.PROJECT/name).read_bytes() for name in install.MANIFEST['files']}
            install.run(root)
            self.assertEqual(after,{name:(root/install.transforms.PROJECT/name).read_bytes() for name in after})
            for name,data in before.items():
                if b'\r\n' in data:self.assertNotIn(b'\n',after[name].replace(b'\r\n',b''))

    def test_partial_unknown_and_linked_sources_reject_without_writes(self):
        for mode in ['partial','unknown','symlink']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);write(root,original())
                name='frameworks/js/src/photoaccesshelperinf.js';target=root/install.transforms.PROJECT/name
                if mode=='partial':target.write_bytes(install.transforms.repair(name,target.read_bytes()))
                elif mode=='unknown':target.write_bytes(target.read_bytes()+b'\n// user edit\n')
                else:
                    saved=root/'saved.js';target.rename(saved);target.symlink_to(saved)
                snapshots={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):install.run(root)
                self.assertEqual(snapshots,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_known_forward_overlay_preserves_all_five_prior_guards(self):
        context=json.loads((FIXTURE/'guard-context.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write(root,original());install.run(root)
            for name,entry in context.items():
                value=gzip.decompress(base64.b64decode(entry['gzip_base64'],validate=True))
                self.assertEqual(hashlib.sha256(value).hexdigest(),entry['sha256']);write(root,{name:value})
            for name in ['api26_photo_search_enums','fusion_asset_type','photos_recent_info','public_record_classes','result_set_export']:
                old=load('batch_knowledge_prior_'+name,COMPONENT.parent/name/'verify_source.py')
                self.assertTrue(old.validate(root,True),name)
            target=root/install.transforms.PROJECT/'frameworks/js/src/photoaccesshelperinf.js'
            target.write_bytes(target.read_bytes()+b'\n// unknown forward\n')
            for name in ['api26_photo_search_enums','fusion_asset_type','photos_recent_info','public_record_classes','result_set_export']:
                old=load('batch_knowledge_prior_unknown_'+name,COMPONENT.parent/name/'verify_source.py')
                with self.assertRaises(ValueError):old.validate(root,True)

    def test_review_patch_matches_all_nine_actual_outputs(self):
        # Canonical LF is only for reviewing the diff. Production installation
        # above retains the real CRLF bytes and verifies every final checksum.
        before=original()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write(root,{n:d.replace(b'\r\n',b'\n') for n,d in before.items()})
            patch=next(COMPONENT.glob('0001-*.patch'))
            subprocess.run(['git','-C',str(root),'apply','--check',str(patch)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(root),'apply',str(patch)],check=True,capture_output=True)
            for name,entry in install.MANIFEST['files'].items():
                actual=(root/install.transforms.PROJECT/name).read_bytes()
                expected=(COMPONENT/'files'/install.transforms.FILES[name]).read_bytes() if name in install.transforms.FILES else install.transforms.repair(name,before[name])
                self.assertEqual(actual,expected.replace(b'\r\n',b'\n'))


if __name__=='__main__':unittest.main(verbosity=2)
